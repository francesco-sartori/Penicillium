/** Decimals shown per signal (display units). */
export const DECIMALS = {
  T: 2, pH: 2, DO2: 2, O2: 2, CO2: 2, Wt: 2, V: 2, pressure: 2, Fs: 1, Foil: 1, Fpaa: 1, Fw: 0, Fg: 1,
  discharge: 0, Fa: 1, Fb: 1, Fc: 0, Fh: 0, RPM: 0, OUR: 3, CER: 3, PAA_pred: 0,
  X: 2, P: 2, PAA: 0, NH3: 0, Viscosity: 1,
}

export function fmt(value, decimals = 2) {
  if (value == null || Number.isNaN(value)) return '---'
  return value.toFixed(decimals)
}

export function fmtSignal(name, value) {
  return fmt(value, DECIMALS[name] ?? 2)
}

const pad = (n) => String(n).padStart(2, '0')

/** Plant clock: batch start (epoch s) plus batch time in hours. */
export function clock(startedAt, hours, withDate = false) {
  if (startedAt == null || hours == null) return '--:--:--'
  const d = new Date((startedAt + hours * 3600) * 1000)
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  return withDate ? `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${time}` : time
}

/** Batch time as h:mm. */
export function batchTime(hours) {
  if (hours == null) return '--:--'
  const h = Math.floor(hours + 1e-9)
  const m = Math.round((hours - h) * 60)
  return `${h}:${pad(m === 60 ? 0 : m)}`
}

export const PRIORITY_NAMES = { 1: 'Urgent', 2: 'High', 3: 'Medium' }
