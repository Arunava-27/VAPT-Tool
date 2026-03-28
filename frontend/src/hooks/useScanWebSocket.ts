/**
 * useScanWebSocket — real-time scan status via WebSocket.
 *
 * Connects to /api/v1/ws/scans/{scanId}?token=<jwt> and dispatches
 * Redux updates whenever the server pushes a status message.
 *
 * Falls back gracefully: if the browser can't connect (network, server
 * restart), the caller can re-enable polling via the `fallbackToPolling` flag.
 */

import { useEffect, useRef, useCallback, useState } from 'react'
import { useDispatch } from 'react-redux'
import { store } from '../store'
import { patchScan } from '../store/slices/scansSlice'
import type { Scan } from '../types'

// When BASE_URL is empty, derive WebSocket URL from current browser location
// so it works transparently through nginx proxy
const _HTTP_BASE = import.meta.env.VITE_API_BASE_URL || ''
const TERMINAL = new Set(['completed', 'failed', 'cancelled'])

function wsUrl(scanId: string, token: string): string {
  let base: string
  if (_HTTP_BASE) {
    // Dev mode: convert http(s):// → ws(s)://
    base = _HTTP_BASE.replace(/^http/, 'ws')
  } else {
    // Container mode: use browser's own host with same protocol converted
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    base = `${proto}//${window.location.host}`
  }
  return `${base}/api/v1/ws/scans/${scanId}?token=${encodeURIComponent(token)}`
}

interface WsMessage {
  type: 'scan_update' | 'error'
  // scan_update fields
  id?: string
  status?: string
  progress_percentage?: number
  result_summary?: Record<string, number>
  started_at?: string | null
  completed_at?: string | null
  error?: string | null
  // error fields
  detail?: string
}

interface UseScanWsOptions {
  /** Called when a terminal status is received (completed/failed/cancelled) */
  onDone?: (scan: Partial<Scan>) => void
  /** Called on unrecoverable error — caller should switch to polling */
  onError?: () => void
}

export function useScanWebSocket(
  scanId: string | undefined,
  active: boolean,
  options: UseScanWsOptions = {}
) {
  const dispatch = useDispatch()
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const { onDone, onError } = options

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
      wsRef.current = null
    }
    setConnected(false)
  }, [])

  useEffect(() => {
    if (!active || !scanId) {
      disconnect()
      return
    }

    const token = store.getState().auth.accessToken
    if (!token) return

    const url = wsUrl(scanId, token)
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)

    ws.onmessage = (event) => {
      let msg: WsMessage
      try {
        msg = JSON.parse(event.data)
      } catch {
        return
      }

      if (msg.type === 'error') {
        console.error('[WS] scan error:', msg.detail)
        onError?.()
        disconnect()
        return
      }

      if (msg.type === 'scan_update' && msg.id) {
        const partial: Partial<Scan> & { id: string } = {
          id: msg.id,
          ...(msg.status !== undefined && { status: msg.status as Scan['status'] }),
          ...(msg.result_summary !== undefined && { result_summary: msg.result_summary }),
          ...(msg.started_at !== undefined && { started_at: msg.started_at ?? undefined }),
          ...(msg.completed_at !== undefined && { completed_at: msg.completed_at ?? undefined }),
          ...(msg.error !== undefined && { error: msg.error ?? undefined }),
        }
        dispatch(patchScan(partial))

        if (msg.status && TERMINAL.has(msg.status)) {
          setConnected(false)
          onDone?.(partial)
        }
      }
    }

    ws.onerror = () => {
      console.warn('[WS] connection error — falling back to polling')
      setConnected(false)
      onError?.()
    }

    ws.onclose = () => setConnected(false)

    return disconnect
  }, [active, scanId, dispatch, disconnect, onDone, onError])

  return { connected, disconnect }
}
