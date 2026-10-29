import { useEffect, useMemo, useRef, useState } from 'react'
import { useDcs } from './useDcs'
import { batchTime, clock } from './format'
import ProcessGraphic from './components/ProcessGraphic'
import Faceplate, { PEN_COLORS } from './components/Faceplate'
import Trend from './components/Trend'
import { AlarmList, BatchDialog, EventList, LabDisplay, RamanDisplay } from './components/Displays'

function Window({ win, title, onClose, onFocus, onMove, children }) {
  const drag = useRef(null)
  const down = (e) => {
    onFocus()
    drag.current = { dx: e.clientX - win.x, dy: e.clientY - win.y }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const move = (e) => {
    if (!drag.current) return
    onMove(Math.max(-200, e.clientX - drag.current.dx), Math.max(0, e.clientY - drag.current.dy))
  }
  const up = () => {
    drag.current = null
  }
  return (
    <div className="window" style={{ left: win.x, top: win.y, zIndex: win.z }} onPointerDown={onFocus}>
      <div className="window-title" onPointerDown={down} onPointerMove={move} onPointerUp={up}>
        <span>{title}</span>
        <button className="window-close" onPointerDown={(e) => e.stopPropagation()} onClick={onClose} title="Close">
          ×
        </button>
      </div>
      <div className="window-body">{children}</div>
    </div>
  )
}

const KEY_TRENDS = ['T', 'pH', 'DO2', 'CO2', 'V']
const GROUP_COLORS = ['#2fc4ff', '#7be35a', '#ffd23f', '#ff8a5c', '#c792ff', '#ff5fd2']

function GroupTrend({ ctx }) {
  const { meta, hist, status } = ctx.store
  const pens = KEY_TRENDS.map((k, i) => ({
    key: k,
    label: `${meta.signals[k].tag} ${meta.signals[k].description}`,
    color: GROUP_COLORS[i],
    lo: meta.signals[k].low,
    hi: meta.signals[k].high,
    unit: meta.signals[k].unit,
    decimals: 2,
  }))
  pens.splice(1, 0, { key: 'T.sp', label: 'TIC-101 SP', color: PEN_COLORS.sp, lo: meta.signals.T.low, hi: meta.signals.T.high, unit: '°C', decimals: 2, dash: '5 3' })
  return (
    <div className="display">
      <Trend hist={hist} pens={pens} lengthH={status.length_h} width={760} height={320} />
    </div>
  )
}

function AlarmBand({ ctx, onList }) {
  const { alarms, status } = ctx.store
  const shown = alarms.slice(0, 4)
  return (
    <div className="alarm-area">
      <div className="alarm-band">
        {[1, 2, 3].map((p) => {
          const list = alarms.filter((a) => a.priority === p)
          const unacked = list.some((a) => !a.acked)
          return (
            <button
              key={p}
              className={`band-btn p${p} ${list.length ? 'has' : ''} ${unacked ? 'blink' : ''}`}
              onClick={onList}
              title={`Priority ${p} alarms`}
            >
              <span className="band-p">P{p}</span>
              <span className="band-n">{list.length}</span>
            </button>
          )
        })}
      </div>
      <div className="alarm-line" onDoubleClick={onList}>
        {shown.map((a) => (
          <div key={a.key} className={`alarm-row ${a.active ? '' : 'rtn'} ${a.acked ? 'acked' : ''}`}>
            <span className={`alarm-icon p${a.priority} ${a.acked ? '' : 'blink'} ${a.active ? '' : 'rtn'}`}>{a.priority}</span>
            <span className="al-time">{clock(status.started_at, a.time_h)}</span>
            <button className="link al-tag" onClick={() => ctx.tagToSignal[a.tag] && ctx.open('faceplate', ctx.tagToSignal[a.tag])}>
              {a.tag}
            </button>
            <span className="al-text">{a.text}</span>
            <span className="al-state">{a.active ? (a.acked ? 'ACK' : 'UNACK') : 'RTN'}</span>
          </div>
        ))}
        {!shown.length && <div className="alarm-row empty">No active alarms</div>}
      </div>
      <div className="alarm-actions">
        <button className="btn" onClick={() => ctx.send('ack')} disabled={!alarms.some((a) => !a.acked)} title="Acknowledge all alarms">
          Ack all
        </button>
        <button className="btn" onClick={onList}>
          Alarm list
        </button>
      </div>
    </div>
  )
}

function Clock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <div className="clock">
      <div className="clock-time">{now.toLocaleTimeString([], { hour12: false })}</div>
      <div className="clock-date">{now.toLocaleDateString()}</div>
    </div>
  )
}

const TITLES = {
  alarms: 'Alarm List',
  events: 'Event List',
  trends: 'Trend Display — F-101 key variables',
  raman: 'Raman Spectrum — AT-103',
  batch: 'Batch Control — F-101',
}

export default function App() {
  const { store, send } = useDcs()
  const [windows, setWindows] = useState([])
  const zTop = useRef(10)

  const open = (kind, arg = null) => {
    setWindows((ws) => {
      const id = `${kind}:${arg ?? ''}`
      const z = ++zTop.current
      const existing = ws.find((w) => w.id === id)
      if (existing) return ws.map((w) => (w.id === id ? { ...w, z } : w))
      const n = ws.length % 8
      return [...ws, { id, kind, arg, x: 120 + n * 34, y: 40 + n * 30, z }]
    })
  }
  const close = (id) => setWindows((ws) => ws.filter((w) => w.id !== id))
  const focus = (id) => setWindows((ws) => ws.map((w) => (w.id === id && w.z !== zTop.current ? { ...w, z: ++zTop.current } : w)))
  const moveWin = (id, x, y) => setWindows((ws) => ws.map((w) => (w.id === id ? { ...w, x, y } : w)))

  const { meta, status } = store
  const derived = useMemo(() => {
    if (!meta) return null
    const loopOf = {}
    for (const [k, l] of Object.entries(meta.loops)) loopOf[l.pv] = k
    const tagToSignal = {}
    for (const [k, s] of Object.entries(meta.signals)) tagToSignal[s.tag] = k
    return { loopOf, tagToSignal }
  }, [meta])

  const errorRef = useRef(null)
  const [toast, setToast] = useState(null)
  useEffect(() => {
    if (store.error && store.error !== errorRef.current) {
      errorRef.current = store.error
      setToast(store.error.message)
      const id = setTimeout(() => setToast(null), 4000)
      return () => clearTimeout(id)
    }
  })

  if (!meta || !status) {
    return <div className="loading">{store.connected ? 'Loading…' : 'Connecting to the console server…'}</div>
  }
  const ctx = { store, send, open, ...derived }
  const running = status.state === 'RUNNING'

  const windowTitle = (w) => {
    if (w.kind === 'faceplate') {
      const s = meta.signals[w.arg]
      return `${s.tag} — ${s.description}`
    }
    if (w.kind === 'lab') return w.arg ? `Lab results — ${meta.analyses[w.arg].tag} ${meta.analyses[w.arg].description}` : 'Lab results — all analyses'
    return TITLES[w.kind]
  }
  const windowBody = (w) => {
    switch (w.kind) {
      case 'faceplate':
        return <Faceplate ctx={ctx} name={w.arg} />
      case 'lab':
        return <LabDisplay ctx={ctx} name={w.arg} />
      case 'alarms':
        return <AlarmList ctx={ctx} />
      case 'events':
        return <EventList ctx={ctx} />
      case 'trends':
        return <GroupTrend ctx={ctx} />
      case 'raman':
        return <RamanDisplay ctx={ctx} />
      case 'batch':
        return <BatchDialog ctx={ctx} onClose={() => close(w.id)} />
      default:
        return null
    }
  }

  return (
    <div className="workplace">
      <header className="appbar">
        <div className="system-id">
          <div className="sys-name">Penicillium Operator Workplace</div>
          <div className="sys-sub">Area 1 · Fermentation · Unit F-101</div>
        </div>
        <AlarmBand ctx={ctx} onList={() => open('alarms')} />
        <Clock />
      </header>
      <nav className="toolbar">
        <button className="btn nav active">F-101 Overview</button>
        <button className="btn nav" onClick={() => open('trends')}>
          Trends
        </button>
        <button className="btn nav" onClick={() => open('lab', null)}>
          Lab results
        </button>
        <button className="btn nav" onClick={() => open('raman')}>
          Raman
        </button>
        <button className="btn nav" onClick={() => open('events')}>
          Event list
        </button>
        <span className="sep" />
        <button className="btn" onClick={() => open('batch')}>
          Batch control…
        </button>
        <button className="btn" disabled={!running} onClick={() => send('hold')}>
          Hold
        </button>
        <button className="btn" disabled={status.state !== 'HELD'} onClick={() => send('resume')}>
          Resume
        </button>
        <span className="sep" />
        <label className="speed">
          Speed
          <select value={status.speed} onChange={(e) => send('speed', { value: parseFloat(e.target.value) })}>
            {status.speeds.map((s) => (
              <option key={s} value={s}>
                {s === 1 ? 'Real time' : `×${s}`}
                {` (${(720 / s) >= 1 ? `${+(720 / s).toFixed(1)} s` : `${Math.round(720000 / s)} ms`}/sample)`}
              </option>
            ))}
          </select>
        </label>
        <span className="spacer" />
        <span className={`state-pill state-${status.state}`}>{status.batch ?? 'NO BATCH'} · {status.state}</span>
        <span className="batch-clock">t = {batchTime(status.time_h)} h</span>
      </nav>
      <main className="main">
        <ProcessGraphic ctx={ctx} />
        {status.state === 'IDLE' && (
          <div className="idle-hint">
            No batch running. <button className="btn primary" onClick={() => open('batch')}>Start a batch…</button>
          </div>
        )}
        {windows.map((w) => (
          <Window key={w.id} win={w} title={windowTitle(w)} onClose={() => close(w.id)} onFocus={() => focus(w.id)} onMove={(x, y) => moveWin(w.id, x, y)}>
            {windowBody(w)}
          </Window>
        ))}
        {toast && <div className="toast">{toast}</div>}
      </main>
      <footer className="statusbar">
        <span className={store.connected ? 'ok' : 'bad'}>{store.connected ? '● Connected' : '● Disconnected'}</span>
        <span>Sample {status.k} / {status.length_h ? Math.round(status.length_h * 5) : '—'}</span>
        <span>Plant time {clock(status.started_at, status.time_h ?? 0, true)}</span>
        <span>{status.message}</span>
        <span className="spacer" />
        <span>Penicillium IndPenSim model · 12 min samples</span>
      </footer>
    </div>
  )
}
