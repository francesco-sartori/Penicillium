import { last } from '../useDcs'
import { DECIMALS, batchTime, clock, fmt } from '../format'

const BW = 124 // value block width

function alarmFor(ctx, tag) {
  const list = ctx.store.alarms.filter((a) => a.tag === tag)
  if (!list.length) return null
  return list.reduce((a, b) => (b.priority < a.priority || (!b.acked && a.acked) ? b : a))
}

function AlarmMark({ alarm, x, y }) {
  if (!alarm) return null
  const cls = `alarm-mark p${alarm.priority} ${alarm.acked ? '' : 'blink'} ${alarm.active ? '' : 'rtn'}`
  return (
    <g className={cls} transform={`translate(${x},${y})`}>
      <rect x={0} y={0} width={14} height={14} />
      <text x={7} y={11} textAnchor="middle">
        {alarm.priority}
      </text>
    </g>
  )
}

/** Value block: tag, PV with unit, optional SP and mode. Clicking opens the faceplate. */
function Block({ ctx, name, x, y, sp = false, w = BW, label }) {
  const { store } = ctx
  const sig = store.meta.signals[name]
  const loopKey = ctx.loopOf[name]
  const pv = last(store.hist, name)
  const spv = sp && loopKey ? last(store.hist, `${loopKey}.sp`) ?? store.status.sp[loopKey] : null
  const mode = sp && loopKey ? store.status.modes[loopKey] : null
  const showSp = sp && loopKey && store.status.sp[loopKey] != null
  const h = showSp ? 50 : 36
  const alarm = alarmFor(ctx, sig.tag)
  const dec = DECIMALS[name] ?? 2
  return (
    <g className={`obj ${alarm ? `in-alarm p${alarm.priority}` : ''}`} transform={`translate(${x},${y})`} onClick={() => ctx.open('faceplate', name)}>
      <title>{`${sig.tag} ${sig.description} - click for faceplate and trend`}</title>
      <rect className="blk" width={w} height={h} rx={1} />
      <text className="blk-tag" x={5} y={12}>
        {label ?? sig.tag}
      </text>
      {mode && (
        <text className={`blk-mode mode-${mode.replace(/[^A-Z]/g, '')}`} x={w - 5} y={12} textAnchor="end">
          {mode}
        </text>
      )}
      <text className="blk-pv" x={w - 34} y={29} textAnchor="end">
        {fmt(pv, dec)}
      </text>
      <text className="blk-unit" x={w - 31} y={29}>
        {sig.unit}
      </text>
      {showSp && (
        <>
          <text className="blk-splabel" x={5} y={44}>
            SP
          </text>
          <text className="blk-sp" x={w - 34} y={44} textAnchor="end">
            {fmt(spv, dec)}
          </text>
          <text className="blk-unit" x={w - 31} y={44}>
            {sig.unit}
          </text>
        </>
      )}
      <AlarmMark alarm={alarm} x={-18} y={2} />
    </g>
  )
}

function Bubble({ ctx, name, x, y, letters }) {
  const sig = ctx.store.meta.signals[name]
  const [, num] = sig.tag.split('-')
  return (
    <g className="obj bubble" transform={`translate(${x},${y})`} onClick={() => ctx.open('faceplate', name)}>
      <title>{`${sig.tag} ${sig.description}`}</title>
      <circle r={17} />
      <line x1={-17} x2={17} y1={0} y2={0} />
      <text y={-4} textAnchor="middle">
        {letters ?? sig.tag.split('-')[0]}
      </text>
      <text y={11} textAnchor="middle">
        {num}
      </text>
    </g>
  )
}

/** Control valve (bow tie with actuator), filled when open. */
function Valve({ x, y, open, vertical = false }) {
  return (
    <g className={`valve ${open ? 'open' : 'closed'}`} transform={`translate(${x},${y}) rotate(${vertical ? 90 : 0})`}>
      <path d="M-11,-7 L11,7 L11,-7 L-11,7 Z" />
      <line x1={0} y1={0} x2={0} y2={-13} />
      <path d="M-7,-13 A7,6 0 0 1 7,-13 Z" />
    </g>
  )
}

function Pump({ x, y, running }) {
  return (
    <g className={`pump ${running ? 'open' : 'closed'}`} transform={`translate(${x},${y})`}>
      <circle r={12} />
      <path d="M-5,-8 L9,0 L-5,8 Z" />
    </g>
  )
}

function Source({ x, y, label, sub, w = 118 }) {
  return (
    <g className="source" transform={`translate(${x},${y - 15})`}>
      <path d={`M0,0 H${w - 12} L${w},15 L${w - 12},30 H0 Z`} />
      <text x={8} y={13} className="src-label">
        {label}
      </text>
      <text x={8} y={25} className="src-sub">
        {sub}
      </text>
    </g>
  )
}

function Pipe({ d, active }) {
  return <path className={`pipe ${active ? 'active' : ''}`} d={d} />
}

const flowing = (ctx, name, eps = 0.05) => (last(ctx.store.hist, name) ?? 0) > eps

// Vessel geometry
const VX0 = 660
const VX1 = 940
const VCX = (VX0 + VX1) / 2
const VTOP = 300
const VBOT = 735
const VESSEL = `M${VX0},350 C${VX0},300 ${VCX - 90},${VTOP} ${VCX},${VTOP} C${VCX + 90},${VTOP} ${VX1},300 ${VX1},350 L${VX1},685 C${VX1},735 ${VCX + 90},${VBOT} ${VCX},${VBOT} C${VCX - 90},${VBOT} ${VX0},735 ${VX0},685 Z`
const VESSEL_M3 = 100

function Fermenter({ ctx }) {
  const v = last(ctx.store.hist, 'V')
  const frac = v == null ? 0 : Math.max(0, Math.min(1, v / VESSEL_M3))
  const levelY = VBOT - frac * (VBOT - VTOP)
  const rpm = last(ctx.store.hist, 'RPM') ?? 0
  return (
    <g>
      {/* jacket */}
      <path className="jacket" d={`M${VX0 - 12},380 V665 H${VX0} V380 Z M${VX1},380 V665 H${VX1 + 12} V380 Z`} />
      <clipPath id="vessel-clip">
        <path d={VESSEL} />
      </clipPath>
      <path className="vessel" d={VESSEL} />
      <rect className="broth" clipPath="url(#vessel-clip)" x={VX0} y={levelY} width={VX1 - VX0} height={VBOT - levelY} />
      <line className="level-line" clipPath="url(#vessel-clip)" x1={VX0} x2={VX1} y1={levelY} y2={levelY} />
      <path className="vessel-outline" d={VESSEL} />
      <text className="vessel-label" x={VCX} y={VTOP + 38} textAnchor="middle">
        F-101
      </text>
      <text className="vessel-sub" x={VCX} y={VTOP + 54} textAnchor="middle">
        FERMENTER 100 m³
      </text>
      {/* agitator */}
      <line className="shaft" x1={VCX} x2={VCX} y1={VTOP - 30} y2={690} />
      {[520, 640].map((y) => (
        <g key={y} className="impeller">
          <rect x={VCX - 36} y={y - 5} width={72} height={10} />
        </g>
      ))}
      <g className={`motor ${rpm > 0 ? 'open' : 'closed'}`} transform={`translate(${VCX},${VTOP - 44})`}>
        <rect x={-18} y={-16} width={36} height={30} rx={3} />
        <text y={4} textAnchor="middle">
          M
        </text>
      </g>
      {/* sparger */}
      <line className="sparger" x1={VCX - 70} x2={VCX + 10} y1={705} y2={705} />
      {[-60, -45, -30, -15, 0].map((dx) => (
        <circle key={dx} className="sparger-hole" cx={VCX + dx} cy={700} r={1.8} />
      ))}
      {/* legs / load cells */}
      {[VX0 + 20, VX1 - 20].map((x) => (
        <g key={x}>
          <line className="leg" x1={x} x2={x} y1={712} y2={770} />
          <path className="loadcell" d={`M${x - 9},778 L${x + 9},778 L${x},766 Z`} />
        </g>
      ))}
      {/* probes */}
      {[440, 495, 550].map((y) => (
        <line key={y} className="probe" x1={VX1 - 34} x2={VX1 + 50} y1={y} y2={y} />
      ))}
      <line className="probe" x1={VX0 + 34} x2={VX0 - 40} y1={590} y2={590} />
      <text className="level-text" x={VX0 + 12} y={levelY - 6}>
        {v == null ? '' : `${fmt(frac * 100, 0)} %`}
      </text>
    </g>
  )
}

function BatchPanel({ ctx, x, y }) {
  const st = ctx.store.status
  const s = st.settings ?? {}
  const prog = st.length_h ? Math.min(1, (st.time_h ?? 0) / st.length_h) : 0
  const W = 360
  return (
    <g className="panel" transform={`translate(${x},${y})`}>
      <rect className="panel-bg" width={W} height={190} />
      <text className="panel-title" x={10} y={18}>
        BATCH {st.batch ?? '—'}
      </text>
      <g className="obj" onClick={() => ctx.open('batch')}>
        <rect className={`state-box state-${st.state}`} x={W - 128} y={6} width={118} height={18} />
        <text className="state-text" x={W - 69} y={19} textAnchor="middle">
          {st.state}
        </text>
      </g>
      {[
        ['Phase', st.phase],
        ['Recipe', `IndPenSim default${s.apc ? ' + Raman PAA control' : ''}${s.prbs ? ' + PRBS' : ''}`],
        ['Batch time', `${batchTime(st.time_h)} h  of  ${st.length_h ?? '—'} h`],
        ['Started', st.started_at ? clock(st.started_at, 0, true) : '—'],
        ['Plant time', st.started_at ? clock(st.started_at, st.time_h ?? 0, true) : '—'],
        ['Seed / fault', st.batch ? `${s.seed} / ${s.fault}` : '—'],
        ['Harvest', st.total_yield_kg != null ? `${fmt(st.total_yield_kg, 0)} kg penicillin` : 'reported at batch end'],
      ].map(([k, v], i) => (
        <g key={k}>
          <text className="panel-key" x={10} y={42 + i * 18}>
            {k}
          </text>
          <text className="panel-val" x={100} y={42 + i * 18}>
            {v}
          </text>
        </g>
      ))}
      <rect className="progress-bg" x={10} y={172} width={W - 20} height={8} />
      <rect className="progress" x={10} y={172} width={(W - 20) * prog} height={8} />
    </g>
  )
}

function LabPanel({ ctx, x, y }) {
  const { meta, lab, status } = ctx.store
  const names = Object.keys(meta.analyses)
  const W = 96
  return (
    <g className="panel" transform={`translate(${x},${y})`}>
      <rect className="panel-bg" width={names.length * (W + 6) + 6 + 96} height={96} />
      <text className="panel-title" x={8} y={16}>
        OFFLINE LABORATORY ANALYSES
      </text>
      <text className="panel-key" x={240} y={16}>
        every 12 h, reported 0.8 h after sampling
      </text>
      {names.map((name, i) => {
        const a = meta.analyses[name]
        const results = lab.filter((r) => r.analysis === name)
        const latest = results.length ? results[results.length - 1] : null
        return (
          <g key={name} className="obj lab-btn" transform={`translate(${6 + i * (W + 6)},24)`} onClick={() => ctx.open('lab', name)}>
            <title>{`${a.tag} ${a.description}: open results and trend`}</title>
            <rect width={W} height={64} rx={2} />
            <text className="lab-tag" x={6} y={13}>
              {a.tag}
            </text>
            <text className="lab-name" x={6} y={26}>
              {a.description.split(' (')[0]}
            </text>
            <text className="lab-val" x={W - 6} y={44} textAnchor="end">
              {latest ? `${fmt(latest.value, DECIMALS[name] ?? 2)}` : '---'}
              <tspan className="blk-unit"> {a.unit}</tspan>
            </text>
            <text className="lab-time" x={6} y={58}>
              {latest ? `sampled ${batchTime(latest.sample_h)} h` : status.batch ? 'awaiting sample' : ''}
            </text>
          </g>
        )
      })}
      <g className="obj lab-btn" transform={`translate(${6 + names.length * (W + 6)},24)`} onClick={() => ctx.open('lab', null)}>
        <rect width={90} height={64} rx={2} />
        <text className="lab-tag" x={45} y={30} textAnchor="middle">
          ALL
        </text>
        <text className="lab-tag" x={45} y={44} textAnchor="middle">
          RESULTS
        </text>
      </g>
    </g>
  )
}

export default function ProcessGraphic({ ctx }) {
  const { store } = ctx
  const apc = store.status.settings?.apc
  const feeds = [
    // name, row y, entry x, source label, sub
    ['Fs', 70, 800 - 30, 'SUGAR', 'T-111  glucose 600 g/L'],
    ['Foil', 130, 800 - 55, 'SOYBEAN OIL', 'T-112'],
    ['Fpaa', 190, 800 - 80, 'PAA PRECURSOR', 'T-113'],
    ['Fw', 250, 800 - 105, 'WATER (WFI)', 'T-114'],
  ]
  return (
    <svg className="graphic" viewBox="0 0 1600 930" preserveAspectRatio="xMidYMid meet">
      <rect className="graphic-bg" width={1600} height={930} />

      {/* ---------------- feeds into the top head */}
      {feeds.map(([name, y, ex, label, sub]) => {
        const on = flowing(ctx, name)
        return (
          <g key={name}>
            <Pipe d={`M150,${y} H${ex} V${VTOP + 30}`} active={on} />
            <Source x={30} y={y} label={label} sub={sub} />
            <Valve x={225} y={y} open={on} />
            <Block ctx={ctx} name={name} x={268} y={y - 54} sp />
          </g>
        )
      })}

      {/* ---------------- pH control: base and acid */}
      {[
        ['Fb', 430, 'BASE (NH₃)', 'T-115'],
        ['Fa', 490, 'ACID', 'T-116'],
      ].map(([name, y, label, sub]) => {
        const on = flowing(ctx, name)
        return (
          <g key={name}>
            <Pipe d={`M150,${y} H${VX0 - 12}`} active={on} />
            <Source x={30} y={y} label={label} sub={sub} />
            <Pump x={230} y={y} running={on} />
            <Block ctx={ctx} name={name} x={268} y={y - 42} />
          </g>
        )
      })}
      <path className="signal" d={`M${VX0 - 57},590 H592 M530,566 V484 M530,448 V424`} />
      <Block ctx={ctx} name="pH" x={468} y={566} sp />
      <Bubble ctx={ctx} name="pH" x={VX0 - 40} y={590} letters="AIC" />

      {/* ---------------- volume / weight */}
      <Block ctx={ctx} name="V" x={500} y={330} />
      <path className="signal" d={`M624,348 H${VX0 - 14}`} />
      <Block ctx={ctx} name="Wt" x={VX1 - 20 + 16} y={782} />
      <path className="signal" d={`M${VX1 - 20},780 V800 H${VX1 - 4}`} />

      {/* ---------------- aeration */}
      <Pipe d={`M150,815 H${VCX - 70} V705`} active={flowing(ctx, 'Fg')} />
      <Source x={30} y={815} label="PROCESS AIR" sub="filtered, sterile" />
      <Valve x={225} y={815} open={flowing(ctx, 'Fg')} />
      <Block ctx={ctx} name="Fg" x={268} y={761} sp />

      {/* ---------------- draw-off / harvest */}
      <Pipe d={`M${VCX + 40},${VBOT - 4} V860 H1200`} active={flowing(ctx, 'discharge', 1)} />
      <Pump x={VCX + 120} y={860} running={flowing(ctx, 'discharge', 1)} />
      <Valve x={VCX + 190} y={860} open={flowing(ctx, 'discharge', 1)} />
      <Block ctx={ctx} name="discharge" x={VCX + 236} y={866} sp />
      <g className="source" transform="translate(1200,825)">
        <rect width={110} height={70} />
        <text x={8} y={18} className="src-label">
          HARVEST
        </text>
        <text x={8} y={32} className="src-sub">
          T-201 to recovery
        </text>
      </g>

      {/* ---------------- agitator */}
      <Block ctx={ctx} name="RPM" x={VCX + 30} y={VTOP - 90} w={110} />

      {/* ---------------- off-gas */}
      <Pipe d={`M${VCX + 100},${VTOP + 18} V40 H1590`} active />
      <Valve x={1440} y={40} open />
      <Block ctx={ctx} name="pressure" x={1410} y={52} sp />
      <path className="signal" d="M1440,27 V20 H1395 V75 H1410" />
      <Bubble ctx={ctx} name="O2" x={1050} y={40} letters="AI" />
      <Bubble ctx={ctx} name="CO2" x={1230} y={40} letters="AI" />
      <Block ctx={ctx} name="O2" x={1000} y={64} />
      <Block ctx={ctx} name="CO2" x={1180} y={64} />
      <Block ctx={ctx} name="OUR" x={1000} y={110} />
      <Block ctx={ctx} name="CER" x={1180} y={110} />
      <text className="note" x={1000} y={162}>
        UI-201/202 calculated from off-gas analysis
      </text>
      <text className="src-label" x={1520} y={30}>
        EXHAUST
      </text>

      {/* ---------------- jacket utilities and temperature control */}
      <Pipe d={`M1590,640 H${VX1 + 12}`} active={flowing(ctx, 'Fc')} />
      <Pipe d={`M1590,700 H1000 V655 H${VX1 + 12}`} active={flowing(ctx, 'Fh')} />
      <Pipe d={`M${VX1 + 12},395 H1000 V372 H1590`} active={flowing(ctx, 'Fc') || flowing(ctx, 'Fh')} />
      <text className="src-label" x={1480} y={364}>
        CW / HW RETURN
      </text>
      <text className="src-label" x={1480} y={632}>
        COOLING WATER
      </text>
      <text className="src-label" x={1480} y={692}>
        HOT WATER
      </text>
      <Valve x={1240} y={640} open={flowing(ctx, 'Fc', 0.5)} />
      <Valve x={1240} y={700} open={flowing(ctx, 'Fh', 0.5)} />
      <Block ctx={ctx} name="Fc" x={1280} y={590} />
      <Block ctx={ctx} name="Fh" x={1280} y={706} />
      <Block ctx={ctx} name="T" x={1060} y={420} sp />
      <Bubble ctx={ctx} name="T" x={VX1 + 68} y={440} letters="TIC" />
      <path className="signal" d={`M${VX1 + 85},440 H1060 M1184,445 H1215 V615 H1240 V627 M1215,615 V675 H1240 V687`} />
      <text className="note" x={1190} y={600} textAnchor="end">
        split range
      </text>
      <Block ctx={ctx} name="DO2" x={1060} y={480} />
      <Bubble ctx={ctx} name="DO2" x={VX1 + 68} y={495} letters="AI" />
      <path className="signal" d={`M${VX1 + 85},495 H1060`} />
      <Block ctx={ctx} name="PAA_pred" x={1060} y={535} sp={apc} label={apc ? 'AIC-103' : 'AI-103'} />
      <Bubble ctx={ctx} name="PAA_pred" x={VX1 + 68} y={550} letters={apc ? 'AIC' : 'AI'} />
      <path className="signal" d={`M${VX1 + 85},550 H1060`} />

      <Fermenter ctx={ctx} />

      <BatchPanel ctx={ctx} x={1225} y={150} />
      <LabPanel ctx={ctx} x={20} y={658} />
    </svg>
  )
}

