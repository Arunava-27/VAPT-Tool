import { useEffect, useRef } from 'react'

export function usePolling(fn: () => Promise<void>, interval: number, active: boolean) {
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!active) return
    let cancelled = false

    const poll = async () => {
      if (cancelled) return
      try {
        await fnRef.current()
      } catch {
        // polling errors are non-fatal — the caller handles them
      }
    }

    poll()
    const id = setInterval(poll, interval)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [active, interval])
}
