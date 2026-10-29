import { useEffect, useRef, useState } from 'react'

const MAX_EVENTS = 3000

function emptyStore() {
  return {
    connected: false,
    meta: null,
    status: null,
    hist: { t: [] },
    lab: [],
    alarms: [],
    events: [],
    spectrum: null,
    error: null,
    version: 0,
  }
}

/**
 * Connection to the console server. Returns the live store (mutated in place, re-rendered at most once per
 * animation frame) and `send(cmd, args)`.
 */
export function useDcs() {
  const store = useRef(emptyStore())
  const wsRef = useRef(null)
  const [, setTick] = useState(0)

  useEffect(() => {
    let closed = false
    let retry = null
    let frame = null
    const bump = () => {
      store.current.version += 1
      if (frame == null) {
        frame = requestAnimationFrame(() => {
          frame = null
          setTick((n) => n + 1)
        })
      }
    }

    const appendEvents = (events) => {
      if (!events || !events.length) return
      const s = store.current
      s.events.push(...events)
      if (s.events.length > MAX_EVENTS) s.events.splice(0, s.events.length - MAX_EVENTS)
    }

    const handle = (msg) => {
      const s = store.current
      switch (msg.type) {
        case 'snapshot':
          s.meta = msg.meta
          s.status = msg.status
          s.hist = msg.history
          s.lab = msg.lab
          s.alarms = msg.alarms
          s.events = msg.events
          break
        case 'update':
          for (const sample of msg.samples) {
            if (sample.t == null) continue
            s.hist.t.push(sample.t)
            for (const key of Object.keys(s.hist)) {
              if (key !== 't') s.hist[key].push(sample.values[key] ?? null)
            }
            if (sample.lab.length) s.lab.push(...sample.lab)
          }
          s.status = msg.status
          s.alarms = msg.alarms
          appendEvents(msg.events)
          break
        case 'status':
          s.status = msg.status
          s.alarms = msg.alarms
          appendEvents(msg.events)
          break
        case 'spectrum':
          s.spectrum = msg.spectrum
          break
        case 'error':
          s.error = { message: msg.message, at: Date.now() }
          break
        default:
          break
      }
      bump()
    }

    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${window.location.host}/ws`)
      wsRef.current = ws
      ws.onopen = () => {
        store.current.connected = true
        bump()
      }
      ws.onclose = () => {
        store.current.connected = false
        bump()
        if (!closed) retry = setTimeout(connect, 1500)
      }
      ws.onmessage = (ev) => handle(JSON.parse(ev.data))
    }
    connect()
    return () => {
      closed = true
      clearTimeout(retry)
      if (frame != null) cancelAnimationFrame(frame)
      wsRef.current?.close()
    }
  }, [])

  const send = (cmd, args = {}) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ cmd, ...args }))
  }

  return { store: store.current, send }
}

/** Latest value of a history series (null when empty). */
export function last(hist, key) {
  const series = hist[key]
  return series && series.length ? series[series.length - 1] : null
}
