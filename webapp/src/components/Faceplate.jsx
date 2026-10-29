import { useState } from 'react'
import { last } from '../useDcs'
import { DECIMALS, fmt, fmtSignal } from '../format'
import Trend from './Trend'

export const PEN_COLORS = { pv: '#2fc4ff', sp: '#7be35a', out: ['#ffa82e', '#ff5fd2'] }

function Bar({ x, label, value, lo, hi, color, sp, height = 150, width = 26, decimals }) {
  const y0 = 14
  const frac = (v) => Math.max(0, Math.min(1, (v - lo) / (hi - lo || 1)))
  const yOf = (v) => y0 + (1 - frac(v)) * height
  return (
    <g transform={`translate(${x},0)`}>
      <text x={width / 2} y={9} textAnchor="middle" className="fp-bar-label">
        {label}
      </text>
      <rect x={0} y={y0} width={width} height={height} className="fp-bar-bg" />
      {value != null && (
        <rect x={0} y={yOf(value)} width={width} height={y0 + height - yOf(value)} fill={color} />
      )}
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <line key={f} x1={width} x2={width + 4} y1={y0 + (1 - f) * height} y2={y0 + (1 - f) * height} className="fp-tick" />
      ))}
      {sp != null && (
        <path
          d={`M${width + 1},${yOf(sp)} l9,-6 v12 z`}
          className="fp-sp-marker"
        />
      )}
      <text x={width / 2} y={y0 + height + 12} textAnchor="middle" className="fp-bar-scale">
        {fmt(lo, decimals)}
      </text>
    </g>
  )
}

/** Faceplate of an online signal: a controller when the signal is a loop's PV, otherwise an indicator. */
export default function Faceplate({ ctx, name }) {
  const { store, send } = ctx
  const { meta, hist, status } = store
  const sig = meta.signals[name]
  const loopKey = ctx.loopOf[name]
  const loop = loopKey ? meta.loops[loopKey] : null
  const pv = last(hist, name)
  const sp = loopKey ? last(hist, `${loopKey}.sp`) ?? status.sp[loopKey] : null
  const nextSp = loopKey ? status.sp[loopKey] : null
  const mode = loopKey ? status.modes[loopKey] : null
  const running = status.state === 'RUNNING' || status.state === 'HELD'
  const outputs = loop ? loop.outputs : []
  const alarms = store.alarms.filter((a) => a.tag === sig.tag)
  const controlledBy = Object.entries(meta.loops).find(([, l]) => l.outputs.includes(name) && l.pv !== name)
  const [entry, setEntry] = useState('')
  const dec = DECIMALS[name] ?? 2

  const submitSp = () => {
    const v = parseFloat(entry)
    if (!Number.isFinite(v)) return
    send('set_sp', { loop: loopKey, value: v })
    setEntry('')
  }

  const pens = [
    { key: name, label: `${sig.tag} PV`, color: PEN_COLORS.pv, lo: sig.low, hi: sig.high, unit: sig.unit, decimals: dec },
  ]
  if (loopKey && sp != null) {
    pens.push({ key: `${loopKey}.sp`, label: `${sig.tag} SP`, color: PEN_COLORS.sp, lo: sig.low, hi: sig.high, unit: sig.unit, decimals: dec, dash: '5 3' })
  }
  outputs
    .filter((o) => o !== name)
    .forEach((o, k) => {
      const os = meta.signals[o]
      pens.push({ key: o, label: `${os.tag} OUT`, color: PEN_COLORS.out[k % 2], lo: os.low, hi: os.high, unit: os.unit, decimals: DECIMALS[o] ?? 1 })
    })

  const outBars = outputs.filter((o) => o !== name)

  return (
    <div className="faceplate">
      <div className="fp-left">
        <div className="fp-header">
          <div className="fp-tag">{sig.tag}</div>
          <div className="fp-desc">{sig.description}</div>
          <div className="fp-status">
            {mode && <span className={`mode-badge mode-${mode.replace(/[^A-Z]/g, '')}`}>{mode}</span>}
            {alarms.map((a) => (
              <span key={a.key} className={`alarm-icon p${a.priority} ${a.acked ? '' : 'blink'} ${a.active ? '' : 'rtn'}`} title={a.text}>
                {a.priority}
              </span>
            ))}
          </div>
        </div>
        <svg className="fp-bars" viewBox={`0 0 ${70 + outBars.length * 64} 186`} width={70 + outBars.length * 64} height={186}>
          <Bar x={14} label="PV" value={pv} lo={sig.low} hi={sig.high} color={PEN_COLORS.pv} sp={sp} decimals={dec} />
          {outBars.map((o, k) => {
            const os = meta.signals[o]
            return (
              <Bar
                key={o}
                x={80 + k * 64}
                label={os.tag}
                value={last(hist, o)}
                lo={os.low}
                hi={os.high}
                color={PEN_COLORS.out[k % 2]}
                decimals={0}
              />
            )
          })}
        </svg>
        <table className="fp-values">
          <tbody>
            <tr>
              <th>PV</th>
              <td className="num pv">{fmtSignal(name, pv)}</td>
              <td>{sig.unit}</td>
            </tr>
            {loopKey && (
              <tr>
                <th>SP</th>
                <td className="num sp">{fmt(sp, dec)}</td>
                <td>{sig.unit}</td>
              </tr>
            )}
            {loopKey && nextSp != null && sp != null && Math.abs(nextSp - sp) > 1e-9 && (
              <tr>
                <th>SP next</th>
                <td className="num sp">{fmt(nextSp, dec)}</td>
                <td>{sig.unit}</td>
              </tr>
            )}
            {loopKey && sp != null && pv != null && (
              <tr>
                <th>Dev</th>
                <td className="num">{fmt(pv - sp, dec)}</td>
                <td>{sig.unit}</td>
              </tr>
            )}
            {outBars.map((o) => (
              <tr key={o}>
                <th>OUT {meta.signals[o].tag}</th>
                <td className="num">{fmtSignal(o, last(hist, o))}</td>
                <td>{meta.signals[o].unit}</td>
              </tr>
            ))}
            <tr>
              <th>Range</th>
              <td className="num">
                {fmt(sig.low, dec)} – {fmt(sig.high, dec)}
              </td>
              <td>{sig.unit}</td>
            </tr>
          </tbody>
        </table>

        {loop && (
          <div className="fp-ops">
            {loop.recipe && (
              <div className="fp-row">
                <span className="fp-label">Mode</span>
                {['CAS', 'AUTO'].map((m) => (
                  <button
                    key={m}
                    className={`btn ${mode === m ? 'active' : ''}`}
                    disabled={!running || mode === 'PRBS' || mode === 'CAS-AIC'}
                    title={m === 'CAS' ? 'Setpoint from the batch recipe' : 'Operator setpoint'}
                    onClick={() => send('set_mode', { loop: loopKey, mode: m })}
                  >
                    {m}
                  </button>
                ))}
              </div>
            )}
            {loop.editable ? (
              <div className="fp-row">
                <span className="fp-label">SP</span>
                <input
                  className="fp-input"
                  type="number"
                  step="any"
                  min={loop.sp_low}
                  max={loop.sp_high}
                  placeholder={fmt(nextSp, dec)}
                  value={entry}
                  disabled={!running}
                  onChange={(e) => setEntry(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && submitSp()}
                />
                <button className="btn" disabled={!running || entry === ''} onClick={submitSp}>
                  Apply
                </button>
              </div>
            ) : (
              <div className="fp-note">Setpoint fixed by the PAT strategy ({fmt(nextSp, 0)} {sig.unit}).</div>
            )}
            {mode === 'PRBS' && <div className="fp-note">PRBS perturbations drive this feed; operator SP ignored.</div>}
            {mode === 'CAS-AIC' && <div className="fp-note">Setpoint from AIC-103 (Raman PAA control).</div>}
            {loop.recipe && mode === 'CAS' && <div className="fp-note">SP follows the batch recipe.</div>}
          </div>
        )}
        {controlledBy && (
          <div className="fp-ops">
            <div className="fp-note">Output of {meta.signals[controlledBy[1].pv].tag} (split range).</div>
            <button className="btn" onClick={() => ctx.open('faceplate', controlledBy[1].pv)}>
              Open {meta.signals[controlledBy[1].pv].tag}
            </button>
          </div>
        )}
        {alarms.length > 0 && (
          <div className="fp-alarm-list">
            {alarms.map((a) => (
              <div key={a.key} className="fp-alarm">
                <span className={`alarm-icon p${a.priority} ${a.acked ? '' : 'blink'} ${a.active ? '' : 'rtn'}`}>{a.priority}</span>
                <span>{a.text}</span>
                {!a.acked && (
                  <button className="btn small" onClick={() => send('ack', { key: a.key })}>
                    Ack
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="fp-right">
        <Trend hist={hist} pens={pens} lengthH={status.length_h} width={560} height={270} defaultRange={24} />
      </div>
    </div>
  )
}
