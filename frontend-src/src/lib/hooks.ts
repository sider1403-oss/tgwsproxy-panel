import { useCallback, useEffect, useRef, useState } from 'react'

export function usePolling<T>(
  fn: () => Promise<T>,
  intervalMs: number,
  deps: unknown[] = [],
  enabled = true,
) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!enabled) return
    let alive = true
    let timer: ReturnType<typeof setInterval> | null = null
    const tick = async () => {
      try {
        const d = await fnRef.current()
        if (alive) {
          setData(d)
          setError(null)
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (alive) setLoading(false)
      }
    }
    void tick()
    timer = setInterval(tick, intervalMs)
    return () => {
      alive = false
      if (timer) clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, enabled, ...deps])

  return { data, error, loading, setData }
}

export function useSse<T>(url: string, eventName: string, enabled = true, onData?: (data: T) => void) {
  const [connected, setConnected] = useState(false)
  const [last, setLast] = useState<T | null>(null)
  const cbRef = useRef(onData)
  cbRef.current = onData

  useEffect(() => {
    if (!enabled) return
    let es: EventSource | null = null
    let retry: ReturnType<typeof setTimeout> | null = null
    let closed = false

    const connect = () => {
      if (closed) return
      es = new EventSource(url)
      es.onopen = () => setConnected(true)
      es.addEventListener(eventName, (ev) => {
        try {
          const data = JSON.parse((ev as MessageEvent).data) as T
          setLast(data)
          cbRef.current?.(data)
        } catch {
          /* ignore malformed frame */
        }
      })
      es.onerror = () => {
        setConnected(false)
        es?.close()
        if (!closed) retry = setTimeout(connect, 4000)
      }
    }
    connect()
    return () => {
      closed = true
      if (retry) clearTimeout(retry)
      es?.close()
      setConnected(false)
    }
  }, [url, eventName, enabled])

  return { connected, last }
}

export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(t)
  }, [intervalMs])
  return now
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => (typeof window !== 'undefined' ? window.matchMedia(query).matches : false))
  useEffect(() => {
    const mq = window.matchMedia(query)
    const handler = () => setMatches(mq.matches)
    handler()
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [query])
  return matches
}

export function useCopy() {
  const [copied, setCopied] = useState<string | null>(null)
  const copy = useCallback(async (text: string, id = text) => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    setCopied(id)
    setTimeout(() => setCopied(null), 1600)
  }, [])
  return { copied, copy }
}
