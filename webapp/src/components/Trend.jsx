import { useId, useMemo, useState } from 'react'
import { fmt } from '../format'

const RANGES = [
  { label: '2 h', hours: 2 },
  { label: '8 h', hours: 8 },
  { label: '24 h', hours: 24 },
  { label: '72 h', hours: 72 },
  { label: 'Batch', hours: null },
]

const PAD = { left: 52, right: 12, top: 10, bottom: 22 }

function lowerBound(arr, x) {
  let lo = 0
  let hi = arr.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (arr[mid] < x) lo = mid + 1
    else hi = mid
  }
  return lo
}

/** Path of a series over [i0, i1), min/max per pixel column when there are more points than pixels. */
function seriesPath(t, y, i0, i1, sx, sy, width) {
  let d = ''
  let pen = false
  const n = i1 - i0
  if (n <= width * 2) {
    for (let i = i0; i < i1; i++) {
      const v = y[i]
      if (v == null) {
        pen = false
        continue
      }
      d += `${pen ? 'L' : 'M'}${sx(t[i]).toFixed(1)},${sy(v).toFixed(1)}`
      pen = true
    }
    return d
  }
  let col = null
  let mn = Infinity
  let mx = -Infinity
  let first = null
  let lastV = null
  const flush = () => {
    if (col == null || first == null) return
    d += `${pen ? 'L' : 'M'}${col},${sy(first).toFixed(1)}L${col},${sy(mn).toFixed(1)}L${col},${sy(mx).toFixed(1)}L${col},${sy(lastV).toFixed(1)}`
    pen = true
  }
  for (let i = i0; i < i1; i++) {
    const c = Math.round(sx(t[i]))
    if (c !== col) {
      flush()
      col = c
      mn = Infinity
      mx = -Infinity
      first = null
    }
    const v = y[i]
    if (v == null) continue
    if (first == null) first = v
    mn = Math.min(mn, v)
    mx = Math.max(mx, v)
    lastV = v
  }
  flush()
  return d
}

function niceStep(span, target) {
  const raw = span / target
  const p = 10 ** Math.floor(Math.log10(raw))
  const m = raw / p
  return (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p
}

/**
 * Trend display. `pens`: [{ key, label, color, lo, hi, unit, decimals, dash, points }] where `points`
 * (optional) are [{ t, v }] drawn as markers (lab results) instead of the history series `key`.
 */
export default function Trend({ hist, pens, lengthH, width = 640, height = 280, defaultRange = null }) {
  const [range, setRange] = useState(defaultRange)
  const [selected, setSelected] = useState(0)
  const [auto, setAuto] = useState(false)
  const [cursor, setCursor] = useState(null) // time in h
  const clipId = `clip${useId().replace(/[^a-zA-Z0-9]/g, '')}`
  const t = hist.t
  const tLast = t.length ? t[t.length - 1] : 0
  const x1 = range == null ? Math.max(lengthH ?? 0, tLast) : Math.max(tLast, range)
  const x0 = range == null ? 0 : x1 - range
  const w = width - PAD.left - PAD.right
  const h = height - PAD.top - PAD.bottom
  const sx = (x) => PAD.left + ((x - x0) / (x1 - x0)) * w
  const i0 = Math.max(0, lowerBound(t, x0) - 1)
  const i1 = t.length

  const scales = useMemo(
    () =>
      pens.map((p) => {
        if (!auto) return [p.lo, p.hi]
        let mn = Infinity
        let mx = -Infinity
        const vals = p.points ? p.points.filter((q) => q.t >= x0).map((q) => q.v) : (hist[p.key] ?? []).slice(i0, i1)
        for (const v of vals) {
          if (v == null) continue
          mn = Math.min(mn, v)
          mx = Math.max(mx, v)
        }
        if (!Number.isFinite(mn)) return [p.lo, p.hi]
        const pad = (mx - mn) * 0.08 || Math.abs(mx) * 0.02 || 1
        return [mn - pad, mx + pad]
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pens, auto, x0, i0, i1, hist],
  )

  const sel = Math.min(selected, pens.length - 1)
  const [slo, shi] = scales[sel] ?? [0, 1]
  const yTicks = 10
  const xStep = niceStep(x1 - x0, 8)
  const xTicks = []
  for (let x = Math.ceil(x0 / xStep) * xStep; x <= x1 + 1e-9; x += xStep) xTicks.push(x)

  const cursorIndex = cursor == null || !t.length ? null : Math.min(t.length - 1, lowerBound(t, cursor - 1e-9))
  const valueAt = (p) => {
    if (p.points) {
      const pts = p.points.filter((q) => (cursor == null ? true : q.t <= cursor))
      return pts.length ? pts[pts.length - 1].v : null
    }
    const s = hist[p.key]
    if (!s || !s.length) return null
    return cursorIndex == null ? s[s.length - 1] : s[cursorIndex]
  }

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * width
    if (px < PAD.left || px > width - PAD.right) return setCursor(null)
    setCursor(x0 + ((px - PAD.left) / w) * (x1 - x0))
  }

  return (
    <div className="trend">
      <div className="trend-tools">
        {RANGES.map((r) => (
          <button key={r.label} className={`btn small ${range === r.hours ? 'active' : ''}`} onClick={() => setRange(r.hours)}>
            {r.label}
          </button>
        ))}
        <span className="spacer" />
        <button className={`btn small ${auto ? 'active' : ''}`} onClick={() => setAuto(!auto)} title="Autoscale">
          Auto scale
        </button>
      </div>
      <svg
        className="trend-plot"
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        onMouseMove={onMove}
        onMouseLeave={() => setCursor(null)}
      >
        <rect x={PAD.left} y={PAD.top} width={w} height={h} className="trend-bg" />
        {Array.from({ length: yTicks + 1 }, (_, i) => {
          const y = PAD.top + (i / yTicks) * h
          const v = shi - (i / yTicks) * (shi - slo)
          return (
            <g key={`y${i}`}>
              <line x1={PAD.left} x2={PAD.left + w} y1={y} y2={y} className="trend-grid" />
              {i % 2 === 0 && (
                <text x={PAD.left - 4} y={y + 3} textAnchor="end" className="trend-axis" fill={pens[sel]?.color}>
                  {fmt(v, Math.abs(shi - slo) < 2 ? 2 : Math.abs(shi - slo) < 20 ? 1 : 0)}
                </text>
              )}
            </g>
          )
        })}
        {xTicks.map((x) => (
          <g key={`x${x}`}>
            <line x1={sx(x)} x2={sx(x)} y1={PAD.top} y2={PAD.top + h} className="trend-grid" />
            <text x={sx(x)} y={height - 7} textAnchor="middle" className="trend-axis">
              {`${+x.toFixed(1)} h`}
            </text>
          </g>
        ))}
        <clipPath id={clipId}>
          <rect x={PAD.left} y={PAD.top} width={w} height={h} />
        </clipPath>
        <g clipPath={`url(#${clipId})`}>
          {pens.map((p, k) => {
            const [lo, hi] = scales[k]
            const sy = (v) => PAD.top + (1 - (v - lo) / (hi - lo || 1)) * h
            if (p.points) {
              const pts = p.points.filter((q) => q.t >= x0 - 1 && q.v != null)
              return (
                <g key={p.key + k}>
                  <path
                    d={pts.map((q, j) => `${j ? 'L' : 'M'}${sx(q.t).toFixed(1)},${sy(q.v).toFixed(1)}`).join('')}
                    stroke={p.color}
                    strokeWidth={1}
                    strokeDasharray="3 3"
                    fill="none"
                  />
                  {pts.map((q) => (
                    <rect key={q.t} x={sx(q.t) - 3.5} y={sy(q.v) - 3.5} width={7} height={7} fill={p.color} />
                  ))}
                </g>
              )
            }
            const series = hist[p.key]
            if (!series) return null
            return (
              <path
                key={p.key + k}
                d={seriesPath(t, series, i0, i1, sx, sy, w)}
                stroke={p.color}
                strokeWidth={k === sel ? 1.8 : 1.3}
                strokeDasharray={p.dash}
                fill="none"
              />
            )
          })}
        </g>
        {cursor != null && (
          <g>
            <line x1={sx(cursor)} x2={sx(cursor)} y1={PAD.top} y2={PAD.top + h} className="trend-cursor" />
            <text x={sx(cursor) + 4} y={PAD.top + 12} className="trend-axis cursor-label">
              {`${cursor.toFixed(1)} h`}
            </text>
          </g>
        )}
      </svg>
      <table className="pen-table">
        <thead>
          <tr>
            <th />
            <th>Pen</th>
            <th className="num">{cursor == null ? 'Value' : `@ ${cursor.toFixed(1)} h`}</th>
            <th>Unit</th>
            <th className="num">Scale</th>
          </tr>
        </thead>
        <tbody>
          {pens.map((p, k) => (
            <tr key={p.key + k} className={k === sel ? 'selected' : ''} onClick={() => setSelected(k)}>
              <td>
                <span className="swatch" style={{ background: p.color }} />
              </td>
              <td>{p.label}</td>
              <td className="num">{fmt(valueAt(p), p.decimals ?? 2)}</td>
              <td>{p.unit}</td>
              <td className="num">
                {fmt(scales[k][0], p.decimals ?? 2)} – {fmt(scales[k][1], p.decimals ?? 2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
