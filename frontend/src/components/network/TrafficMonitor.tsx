import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity, Play, Square, Trash2, WifiOff, Filter,
  ChevronDown, Radio,
} from 'lucide-react'
import { CaptureInterface, CapturePacket, trafficWsUrl } from '../../api/network'
import { store } from '../../store'

interface TrafficMonitorProps {
  onActiveIpsChange?: (ips: Set<string>) => void
}

// Wireshark-inspired row colors
const PROTO_ROW: Record<string, string> = {
  TCP:   'bg-[#e7f3ff]/5',
  UDP:   'bg-[#dafbe1]/5',
  DNS:   'bg-[#fff8e1]/5',
  HTTP:  'bg-[#fce4ec]/5',
  TLS:   'bg-[#ede7f6]/5',
  SSH:   'bg-[#e0f7fa]/5',
  ICMP:  'bg-[#fce4ec]/5',
  ARP:   'bg-[#f3e5f5]/5',
}

const PROTO_BADGE: Record<string, string> = {
  TCP:   'text-blue-300   bg-blue-900/40',
  UDP:   'text-emerald-300 bg-emerald-900/40',
  DNS:   'text-yellow-300  bg-yellow-900/40',
  HTTP:  'text-pink-300    bg-pink-900/40',
  TLS:   'text-violet-300  bg-violet-900/40',
  SSH:   'text-cyan-300    bg-cyan-900/40',
  ICMP:  'text-orange-300  bg-orange-900/40',
  ARP:   'text-purple-300  bg-purple-900/40',
}

const MAX_PACKETS = 1000

function fmt(ts: number) {
  const d = new Date(ts * 1000)
  return d.toTimeString().slice(0, 8) + '.' + String(d.getMilliseconds()).padStart(3, '0')
}

type WsState = 'disconnected' | 'connecting' | 'capturing' | 'stopped' | 'error'

export default function TrafficMonitor({ onActiveIpsChange }: TrafficMonitorProps) {
  const [wsState, setWsState]         = useState<WsState>('disconnected')
  const [packets, setPackets]         = useState<CapturePacket[]>([])
  const [stats, setStats]             = useState({ total: 0, pps: 0 })
  const [interfaces, setInterfaces]   = useState<CaptureInterface[]>([])
  const [selectedIface, setSelectedIface] = useState<string>('')
  const [bpfFilter, setBpfFilter]     = useState('')
  const [appliedFilter, setAppliedFilter] = useState('')
  const [protoFilter, setProtoFilter] = useState('ALL')
  const [textFilter, setTextFilter]   = useState('')
  const [error, setError]             = useState<string | null>(null)
  const [selectedRow, setSelectedRow] = useState<number | null>(null)

  const wsRef      = useRef<WebSocket | null>(null)
  const tableRef   = useRef<HTMLDivElement>(null)
  const autoScroll = useRef(true)

  const getToken = () => store.getState().auth.accessToken ?? ''

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      try { wsRef.current.send(JSON.stringify({ action: 'stop' })) } catch { /* ignore */ }
      wsRef.current.close()
      wsRef.current = null
    }
    setWsState('stopped')
  }, [])

  const connect = useCallback((iface?: string, filter?: string) => {
    disconnect()
    setError(null)
    setWsState('connecting')
    const url = trafficWsUrl(getToken(), iface ?? selectedIface, filter ?? appliedFilter)
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => setWsState('capturing')

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string)
        if (msg.type === 'interfaces') {
          const list: CaptureInterface[] = msg.interfaces
          setInterfaces(list)
          if (!iface && list.length > 0) setSelectedIface(list[0].name)
        } else if (msg.type === 'packet') {
          const pkt = msg as CapturePacket
          setPackets(prev => {
            const next = prev.length >= MAX_PACKETS ? prev.slice(-MAX_PACKETS + 1) : [...prev]
            next.push(pkt)
            return next
          })
          onActiveIpsChange?.(new Set([pkt.src, pkt.dst].filter(ip =>
            !ip.startsWith('127.') && !ip.startsWith('::') && ip !== '0.0.0.0'
          )))
        } else if (msg.type === 'stats') {
          setStats({ total: msg.total_packets, pps: msg.pps })
        } else if (msg.type === 'error') {
          setError(msg.message)
          setWsState('error')
        }
      } catch { /* ignore */ }
    }

    ws.onerror = () => {
      setError('WebSocket connection failed — check api-gateway is running')
      setWsState('error')
    }

    ws.onclose = (ev) => {
      if (ev.code !== 1000) setWsState('error')
      else setWsState('stopped')
      wsRef.current = null
    }
  }, [disconnect, selectedIface, appliedFilter, onActiveIpsChange])

  // Cleanup on unmount
  useEffect(() => () => { disconnect() }, [disconnect])

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll.current && tableRef.current) {
      tableRef.current.scrollTop = tableRef.current.scrollHeight
    }
  }, [packets])

  const applyFilter = () => {
    setAppliedFilter(bpfFilter)
    if (wsState === 'capturing') connect(selectedIface, bpfFilter)
  }

  const clearAll = () => {
    setPackets([])
    setStats({ total: 0, pps: 0 })
    setSelectedRow(null)
  }

  const PROTOS = ['ALL', 'TCP', 'UDP', 'DNS', 'HTTP', 'TLS', 'SSH', 'ICMP', 'ARP']

  const filtered = packets.filter(p => {
    const matchProto = protoFilter === 'ALL' || p.proto === protoFilter
    const matchText = !textFilter || [p.src, p.dst, p.info, p.proto]
      .some(v => v?.toLowerCase().includes(textFilter.toLowerCase()))
    return matchProto && matchText
  })

  const selectedPkt = selectedRow !== null ? filtered[selectedRow] : null

  return (
    <div className="flex flex-col h-full bg-slate-950">

      {/* ── Toolbar ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-slate-700 flex-shrink-0">
        {/* Start / Stop */}
        {wsState !== 'capturing' ? (
          <button
            onClick={() => connect()}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-medium rounded transition-colors"
          >
            <Play className="w-3 h-3" /> Start
          </button>
        ) : (
          <button
            onClick={disconnect}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white text-xs font-medium rounded transition-colors"
          >
            <Square className="w-3 h-3" /> Stop
          </button>
        )}

        <button
          onClick={clearAll}
          className="flex items-center gap-1 px-2 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded transition-colors"
        >
          <Trash2 className="w-3 h-3" /> Clear
        </button>

        {/* Interface selector */}
        <div className="relative flex items-center gap-1.5">
          <Radio className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
          <div className="relative">
            <select
              value={selectedIface}
              onChange={e => setSelectedIface(e.target.value)}
              disabled={wsState === 'capturing'}
              className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 pr-6 appearance-none focus:outline-none focus:border-cyan-500 disabled:opacity-50"
            >
              {interfaces.length === 0
                ? <option value="">Connect to load interfaces…</option>
                : interfaces.map(i => (
                  <option key={i.name} value={i.name}>
                    {i.name}{i.ips.length ? ` (${i.ips[0]})` : ''}
                  </option>
                ))
              }
            </select>
            <ChevronDown className="w-3 h-3 text-slate-500 absolute right-1.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        </div>

        {/* BPF Filter */}
        <div className="flex items-center gap-1 flex-1 min-w-[180px]">
          <Filter className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
          <input
            type="text"
            placeholder="BPF filter: tcp port 80, host 1.2.3.4…"
            value={bpfFilter}
            onChange={e => setBpfFilter(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && applyFilter()}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 placeholder-slate-500 flex-1 focus:outline-none focus:border-cyan-500"
          />
          <button
            onClick={applyFilter}
            className="px-2 py-1 bg-cyan-800 hover:bg-cyan-700 text-cyan-100 text-xs rounded transition-colors"
          >
            Apply
          </button>
        </div>

        {/* Status */}
        <div className="flex items-center gap-2 ml-auto text-xs">
          {wsState === 'capturing' && (
            <span className="flex items-center gap-1 text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse inline-block" />
              Capturing
            </span>
          )}
          {wsState === 'connecting' && <span className="text-yellow-400">Connecting…</span>}
          {wsState === 'stopped'    && <span className="text-slate-500">Stopped</span>}
          {wsState === 'error'      && <span className="text-red-400">Error</span>}
          <span className="text-slate-400 font-mono">{stats.total} pkts</span>
          {wsState === 'capturing' && (
            <span className="text-cyan-400 font-mono">{stats.pps}/s</span>
          )}
        </div>
      </div>

      {/* ── Protocol filter pills ───────────────────────────────── */}
      <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-slate-700/50 flex-shrink-0 flex-wrap">
        {PROTOS.map(p => (
          <button
            key={p}
            onClick={() => setProtoFilter(p)}
            className={`text-[10px] px-2 py-0.5 rounded font-medium transition-colors ${
              protoFilter === p
                ? 'bg-cyan-700 text-cyan-100'
                : (PROTO_BADGE[p] ?? 'bg-slate-700 text-slate-400 hover:bg-slate-600')
            }`}
          >
            {p}
          </button>
        ))}
        <div className="ml-auto">
          <input
            type="text"
            placeholder="Quick search…"
            value={textFilter}
            onChange={e => setTextFilter(e.target.value)}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-[11px] text-slate-200 placeholder-slate-500 w-36 focus:outline-none focus:border-cyan-500"
          />
        </div>
      </div>

      {/* ── Error banner ────────────────────────────────────────── */}
      {error && (
        <div className="mx-3 mt-2 flex items-center gap-2 text-red-400 text-xs bg-red-900/20 border border-red-800/40 rounded-lg p-2.5 flex-shrink-0">
          <WifiOff className="w-3.5 h-3.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* ── Packet table ────────────────────────────────────────── */}
      <div
        ref={tableRef}
        className="flex-1 overflow-auto font-mono"
        onScroll={e => {
          const el = e.currentTarget
          autoScroll.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 20
        }}
      >
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-slate-500 text-sm gap-2">
            <Activity className="w-8 h-8 opacity-30" />
            {wsState === 'disconnected' || wsState === 'stopped'
              ? <span>Click <strong className="text-slate-400">Start</strong> to begin live packet capture</span>
              : wsState === 'capturing'
              ? <span>Waiting for packets…</span>
              : <span>No packets match current filter</span>
            }
          </div>
        ) : (
          <table className="w-full text-[11px] border-collapse">
            <thead className="sticky top-0 bg-slate-900 z-10">
              <tr className="text-slate-500 border-b border-slate-700">
                <th className="text-left px-2 py-1.5 font-medium w-8">#</th>
                <th className="text-left px-2 py-1.5 font-medium w-24">Time</th>
                <th className="text-left px-2 py-1.5 font-medium w-32">Source</th>
                <th className="text-left px-2 py-1.5 font-medium w-32">Destination</th>
                <th className="text-left px-2 py-1.5 font-medium w-14">Proto</th>
                <th className="text-left px-2 py-1.5 font-medium w-14">Len</th>
                <th className="text-left px-2 py-1.5 font-medium">Info</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((pkt, idx) => (
                <tr
                  key={idx}
                  onClick={() => setSelectedRow(idx === selectedRow ? null : idx)}
                  className={`cursor-pointer border-b border-slate-800/50 hover:brightness-125 transition-colors ${
                    idx === selectedRow
                      ? 'bg-cyan-900/40 border-cyan-700/50'
                      : (PROTO_ROW[pkt.proto] ?? '')
                  }`}
                >
                  <td className="px-2 py-[3px] text-slate-600">{idx + 1}</td>
                  <td className="px-2 py-[3px] text-slate-500 tabular-nums">{fmt(pkt.ts)}</td>
                  <td className="px-2 py-[3px] text-slate-300 truncate max-w-[128px]">
                    {pkt.sport ? `${pkt.src}:${pkt.sport}` : pkt.src}
                  </td>
                  <td className="px-2 py-[3px] text-slate-300 truncate max-w-[128px]">
                    {pkt.dport ? `${pkt.dst}:${pkt.dport}` : pkt.dst}
                  </td>
                  <td className="px-2 py-[3px]">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${PROTO_BADGE[pkt.proto] ?? 'text-slate-400 bg-slate-700'}`}>
                      {pkt.proto}
                    </span>
                  </td>
                  <td className="px-2 py-[3px] text-slate-500 tabular-nums">{pkt.length}</td>
                  <td className="px-2 py-[3px] text-slate-400 truncate max-w-[300px]">{pkt.info}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Packet detail pane ──────────────────────────────────── */}
      {selectedPkt && (
        <div className="flex-shrink-0 border-t border-slate-700 bg-slate-900 px-4 py-3 text-[11px] font-mono">
          <div className="text-slate-400 mb-1.5 font-sans text-xs font-semibold">Packet Detail</div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-0.5">
            <span className="text-slate-500">Timestamp</span>
            <span className="text-slate-200">{fmt(selectedPkt.ts)}</span>
            <span className="text-slate-500">Source MAC</span>
            <span className="text-slate-200">{selectedPkt.src_mac || '—'}</span>
            <span className="text-slate-500">Dest MAC</span>
            <span className="text-slate-200">{selectedPkt.dst_mac || '—'}</span>
            <span className="text-slate-500">Source IP:Port</span>
            <span className="text-slate-200">{selectedPkt.src}{selectedPkt.sport ? `:${selectedPkt.sport}` : ''}</span>
            <span className="text-slate-500">Dest IP:Port</span>
            <span className="text-slate-200">{selectedPkt.dst}{selectedPkt.dport ? `:${selectedPkt.dport}` : ''}</span>
            <span className="text-slate-500">Protocol</span>
            <span className="text-cyan-300">{selectedPkt.proto}</span>
            <span className="text-slate-500">Length</span>
            <span className="text-slate-200">{selectedPkt.length} bytes</span>
            <span className="text-slate-500">Info</span>
            <span className="text-yellow-300 col-span-1">{selectedPkt.info}</span>
          </div>
        </div>
      )}

      <div className="px-3 py-1.5 border-t border-slate-700/50 text-[10px] text-slate-600 flex-shrink-0 flex items-center justify-between">
        <span>{filtered.length} of {packets.length} packets shown</span>
        <label className="flex items-center gap-1.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={autoScroll.current}
            onChange={e => { autoScroll.current = e.target.checked }}
            className="accent-cyan-500 w-3 h-3"
          />
          Auto-scroll
        </label>
      </div>
    </div>
  )
}
