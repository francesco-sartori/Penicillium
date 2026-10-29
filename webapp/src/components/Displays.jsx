import { useEffect, useState } from 'react'
import { DECIMALS, PRIORITY_NAMES, batchTime, clock, fmt } from '../format'
import Trend from './Trend'

const LAB_COLORS = { X: '#7be35a', P: '#ffd23f', PAA: '#2fc4ff', NH3: '#ff8a5c', Viscosity: '#c792ff' }

/** Offline results of one analysis (trend + table), or all analyses side by side (`name` null). */
export function LabDisplay({ ctx, name }) {
  const { meta, lab, status } = ctx.store
  const start = status.started_at
  if (name) {
    const a = meta.analyses[name]
    const rows = lab.filter((r) => r.analysis === name)
    const dec = DECIMALS[name] ?? 2
    const vals = rows.map((r) => r.value)
    const hi = vals.length ? Math.max(...vals) : 1
    const pens = [
      {
        key: name,
        label: `${a.tag} ${a.description}`,
        color: LAB_COLORS[name],
        lo: 0,
        hi: hi > 0 ? hi * 1.15 : 1,
        unit: a.unit,
        decimals: dec,
        points: rows.map((r) => ({ t: r.sample_h, v: r.value })),
      },
    ]
    return (
      <div className="display lab-display">
        <div className="fp-header">
          <div className="fp-tag">{a.tag}</div>
          <div className="fp-desc">
            {a.description} — offline laboratory result, plotted at the sampling time
          </div>
        </div>
        <Trend hist={ctx.store.hist} pens={pens} lengthH={status.length_h} width={620} height={240} />
        <div className="table-wrap" style={{ maxHeight: 210 }}>
          <table className="list">
            <thead>
              <tr>
                <th>Sample</th>
                <th>Sampled (plant time)</th>
                <th className="num">Batch h</th>
                <th>Reported</th>
                <th className="num">Result</th>
                <th>Unit</th>
              </tr>
            </thead>
            <tbody>
              {[...rows].reverse().map((r) => (
                <tr key={r.id}>
                  <td>{`LS-${String(Math.round(r.sample_h * 5)).padStart(4, '0')}`}</td>
                  <td>{clock(start, r.sample_h, true)}</td>
                  <td className="num">{batchTime(r.sample_h)}</td>
                  <td>{clock(start, r.report_h)}</td>
                  <td className="num strong">{fmt(r.value, dec)}</td>
                  <td>{r.unit}</td>
                </tr>
              ))}
              {!rows.length && (
                <tr>
                  <td colSpan={6} className="empty">
                    No results yet. Samples are taken at 1 h, then every 12 h and at the end of the batch.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  const names = Object.keys(meta.analyses)
  const bySample = new Map()
  for (const r of lab) {
    if (!bySample.has(r.sample_h)) bySample.set(r.sample_h, { sample_h: r.sample_h, report_h: r.report_h })
    bySample.get(r.sample_h)[r.analysis] = r.value
  }
  const rows = [...bySample.values()].reverse()
  const download = () => {
    const header = ['sample_h', 'report_h', ...names.map((n) => `${n} [${meta.analyses[n].unit}]`)]
    const lines = [header.join(',')]
    for (const r of [...rows].reverse()) lines.push([r.sample_h, r.report_h, ...names.map((n) => r[n] ?? '')].join(','))
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${status.batch ?? 'batch'}_lab_results.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }
  return (
    <div className="display lab-display">
      <div className="toolbar-row">
        {names.map((n) => (
          <button key={n} className="btn" onClick={() => ctx.open('lab', n)}>
            {meta.analyses[n].tag} {n}
          </button>
        ))}
        <span className="spacer" />
        <button className="btn" onClick={download} disabled={!rows.length}>
          Export CSV
        </button>
      </div>
      <div className="table-wrap" style={{ maxHeight: 420 }}>
        <table className="list">
          <thead>
            <tr>
              <th>Sampled</th>
              <th className="num">Batch h</th>
              <th>Reported</th>
              {names.map((n) => (
                <th key={n} className="num">
                  {meta.analyses[n].tag}
                  <br />
                  {n} [{meta.analyses[n].unit}]
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.sample_h}>
                <td>{clock(start, r.sample_h, true)}</td>
                <td className="num">{batchTime(r.sample_h)}</td>
                <td>{clock(start, r.report_h)}</td>
                {names.map((n) => (
                  <td key={n} className="num">
                    {fmt(r[n], DECIMALS[n] ?? 2)}
                  </td>
                ))}
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={3 + names.length} className="empty">
                  No lab results yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function AlarmList({ ctx }) {
  const { alarms, status, meta } = ctx.store
  const tagToSignal = ctx.tagToSignal
  return (
    <div className="display">
      <div className="toolbar-row">
        <span>
          {alarms.length} alarm(s), {alarms.filter((a) => !a.acked).length} unacknowledged
        </span>
        <span className="spacer" />
        <button className="btn" onClick={() => ctx.send('ack')} disabled={!alarms.some((a) => !a.acked)}>
          Acknowledge all
        </button>
      </div>
      <div className="table-wrap" style={{ maxHeight: 440 }}>
        <table className="list alarm-table">
          <thead>
            <tr>
              <th>Pri</th>
              <th>Time</th>
              <th className="num">Batch h</th>
              <th>Object</th>
              <th>Description</th>
              <th>Condition</th>
              <th>State</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {alarms.map((a) => (
              <tr key={a.key} className={`${a.active ? '' : 'rtn'}`}>
                <td>
                  <span className={`alarm-icon p${a.priority} ${a.acked ? '' : 'blink'} ${a.active ? '' : 'rtn'}`}>{a.priority}</span>
                </td>
                <td>{clock(status.started_at, a.time_h)}</td>
                <td className="num">{batchTime(a.time_h)}</td>
                <td>
                  <button className="link" onClick={() => tagToSignal[a.tag] && ctx.open('faceplate', tagToSignal[a.tag])}>
                    {a.tag}
                  </button>
                </td>
                <td>{meta.signals[tagToSignal[a.tag]]?.description}</td>
                <td>{a.text}</td>
                <td>
                  {a.active ? 'Active' : 'Returned'} {a.acked ? '/ Acked' : '/ Unacked'}
                </td>
                <td>
                  {!a.acked && (
                    <button className="btn small" onClick={() => ctx.send('ack', { key: a.key })}>
                      Ack
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!alarms.length && (
              <tr>
                <td colSpan={8} className="empty">
                  No alarms.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="legend">
        {[1, 2, 3].map((p) => (
          <span key={p}>
            <span className={`alarm-icon p${p}`}>{p}</span> {PRIORITY_NAMES[p]}
          </span>
        ))}
        <span>Blinking: unacknowledged · hollow: returned to normal</span>
      </div>
    </div>
  )
}

const KINDS = ['ALL', 'ALARM', 'RTN', 'ACK', 'OPER', 'BATCH', 'LAB', 'SYSTEM']

export function EventList({ ctx }) {
  const [kind, setKind] = useState('ALL')
  const { events } = ctx.store
  const rows = events.filter((e) => kind === 'ALL' || e.kind === kind).slice(-500).reverse()
  return (
    <div className="display">
      <div className="toolbar-row">
        {KINDS.map((k) => (
          <button key={k} className={`btn small ${kind === k ? 'active' : ''}`} onClick={() => setKind(k)}>
            {k}
          </button>
        ))}
      </div>
      <div className="table-wrap" style={{ maxHeight: 440 }}>
        <table className="list">
          <thead>
            <tr>
              <th>Plant time</th>
              <th>Batch</th>
              <th className="num">Batch h</th>
              <th>Type</th>
              <th>Object</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.seq} className={`ev-${e.kind}`}>
                <td>{clock(e.at, 0, true)}</td>
                <td>{e.batch}</td>
                <td className="num">{batchTime(e.time_h)}</td>
                <td>
                  {e.priority ? <span className={`alarm-icon p${e.priority}`}>{e.priority}</span> : null} {e.kind}
                </td>
                <td>{e.tag}</td>
                <td>{e.text}</td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={6} className="empty">
                  No events.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function BatchDialog({ ctx, onClose }) {
  const { status, meta } = ctx.store
  const s = status.settings ?? {}
  const [form, setForm] = useState({
    seed: s.seed ?? 1,
    fault: s.fault_code ?? 0,
    apc: s.apc ?? false,
    prbs: s.prbs ?? false,
    disturbances: s.disturbances ?? true,
    batch_length_h: s.batch_length_h ?? 230,
  })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const active = status.state === 'RUNNING' || status.state === 'HELD'
  const start = () => {
    if (active && !window.confirm(`Discard batch ${status.batch} and start a new one?`)) return
    ctx.send('start', {
      seed: parseInt(form.seed, 10) || 0,
      fault: parseInt(form.fault, 10),
      apc: form.apc,
      prbs: form.prbs,
      disturbances: form.disturbances,
      batch_length_h: Math.round(parseFloat(form.batch_length_h) * 5) / 5,
    })
    onClose?.()
  }
  return (
    <div className="display batch-dialog">
      <div className="form-grid">
        <label>Batch seed</label>
        <input type="number" value={form.seed} onChange={set('seed')} />
        <label>Fault scenario</label>
        <select value={form.fault} onChange={set('fault')}>
          {Object.entries(meta.faults).map(([n, v]) => (
            <option key={v} value={v}>
              {v} — {n.replace(/_/g, ' ').toLowerCase()}
            </option>
          ))}
        </select>
        <label>Batch length [h]</label>
        <input type="number" step="0.2" min="1" max="350" value={form.batch_length_h} onChange={set('batch_length_h')} />
        <label>Raman PAA control (APC)</label>
        <input type="checkbox" checked={form.apc} onChange={set('apc')} />
        <label>PRBS feed perturbations</label>
        <input type="checkbox" checked={form.prbs} onChange={set('prbs')} />
        <label>Process disturbances</label>
        <input type="checkbox" checked={form.disturbances} onChange={set('disturbances')} />
      </div>
      <p className="fp-note">
        The fault scenario is the instructor's choice: the operator sees only its effects (alarms, trends, lab results).
      </p>
      <div className="toolbar-row">
        <button className="btn primary" onClick={start}>
          Start new batch
        </button>
        <span className="spacer" />
        <button className="btn" disabled={status.state !== 'RUNNING'} onClick={() => ctx.send('hold')}>
          Hold
        </button>
        <button className="btn" disabled={status.state !== 'HELD'} onClick={() => ctx.send('resume')}>
          Resume
        </button>
        <button
          className="btn danger"
          disabled={!active}
          onClick={() => window.confirm(`Abort batch ${status.batch}?`) && ctx.send('abort')}
        >
          Abort
        </button>
      </div>
    </div>
  )
}

export function RamanDisplay({ ctx }) {
  const { spectrum, status } = ctx.store
  useEffect(() => {
    ctx.send('spectrum')
    const id = setInterval(() => ctx.send('spectrum'), 2000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const W = 640
  const H = 280
  const pad = { l: 60, r: 10, t: 10, b: 28 }
  if (!spectrum) {
    return <div className="display empty">No spectrum yet (spectra start after the first 2 h of the batch).</div>
  }
  const { wavenumber: wn, intensity: y } = spectrum
  const xmin = Math.min(...wn)
  const xmax = Math.max(...wn)
  const ymin = Math.min(...y)
  const ymax = Math.max(...y)
  const sx = (x) => pad.l + ((x - xmin) / (xmax - xmin)) * (W - pad.l - pad.r)
  const sy = (v) => pad.t + (1 - (v - ymin) / (ymax - ymin || 1)) * (H - pad.t - pad.b)
  const d = wn.map((x, i) => `${i ? 'L' : 'M'}${sx(x).toFixed(1)},${sy(y[i]).toFixed(1)}`).join('')
  const ticks = [200, 600, 1000, 1400, 1800, 2200].filter((t) => t >= xmin && t <= xmax)
  return (
    <div className="display">
      <div className="fp-header">
        <div className="fp-tag">AT-103</div>
        <div className="fp-desc">
          In-line Raman spectrum at {batchTime(spectrum.t)} h ({clock(status.started_at, spectrum.t)}), refreshed every 2 s
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="trend-plot">
        <rect x={pad.l} y={pad.t} width={W - pad.l - pad.r} height={H - pad.t - pad.b} className="trend-bg" />
        {ticks.map((t) => (
          <g key={t}>
            <line x1={sx(t)} x2={sx(t)} y1={pad.t} y2={H - pad.b} className="trend-grid" />
            <text x={sx(t)} y={H - 10} textAnchor="middle" className="trend-axis">
              {t}
            </text>
          </g>
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <text key={f} x={pad.l - 4} y={pad.t + (1 - f) * (H - pad.t - pad.b) + 3} textAnchor="end" className="trend-axis">
            {((ymin + f * (ymax - ymin)) / 1000).toFixed(0)}k
          </text>
        ))}
        <path d={d} stroke="#2fc4ff" fill="none" strokeWidth={1.2} />
        <text x={W - 12} y={H - 10} textAnchor="end" className="trend-axis">
          cm⁻¹
        </text>
      </svg>
    </div>
  )
}
