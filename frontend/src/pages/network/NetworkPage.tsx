import { useState, useCallback, useRef, useEffect } from 'react'
import {
  Laptop, Smartphone, Router, Server, Wifi, HelpCircle, Printer, Camera,
  RefreshCw, Search, Trash2, Zap, ChevronRight, X, Globe, Network,
} from 'lucide-react'
import toast from 'react-hot-toast'
import {
  getNetworkStatus, getNodes, discoverNetwork, scanNode, deleteNode, getScan, listScans,
} from '../../api/network'
import type { NetworkNode, NetworkScan, NetworkStatus } from '../../api/network'
import LoadingSpinner from '../../components/common/LoadingSpinner'

// ─── Device type icon mapping ────────────────────────────────────────────────
const DEVICE_ICONS: Record<string, React.ElementType> = {
  pc: Laptop,
  mobile: Smartphone,
  router: Router,
  switch: Wifi,
  server: Server,
  printer: Printer,
  iot: Camera,
  unknown: HelpCircle,
}

const DEVICE_LABELS: Record<string, string> = {
  pc: 'PC',
  mobile: 'Mobile',
  router: 'Router',
  switch: 'Switch',
  server: 'Server',
  printer: 'Printer',
  iot: 'IoT',
  unknown: 'Unknown',
}

const FILTER_TYPES = ['all', 'pc', 'mobile', 'router', 'switch', 'server', 'printer', 'iot', 'unknown'] as const
type FilterType = (typeof FILTER_TYPES)[number]

// ─── Small helper components ─────────────────────────────────────────────────
function DeviceIcon({ type, className = 'w-6 h-6' }: { type: string; className?: string }) {
  const Icon = DEVICE_ICONS[type] ?? HelpCircle
  return <Icon className={className} />
}

function StatusDot({ status }: { status: string }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${
        status === 'active' ? 'bg-emerald-400' : 'bg-slate-500'
      }`}
    />
  )
}

function ScanStatusBadge({ status }: { status: NetworkScan['status'] }) {
  const map: Record<string, string> = {
    pending:   'bg-amber-500/10 text-amber-400 border-amber-500/30',
    running:   'bg-sky-500/10 text-sky-400 border-sky-500/30',
    completed: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    failed:    'bg-rose-500/10 text-rose-400 border-rose-500/30',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded border text-xs font-medium ${map[status] ?? map.failed}`}>
      {status}
    </span>
  )
}

// ─── Scan modal ───────────────────────────────────────────────────────────────
function ScanModal({
  node,
  onClose,
  onStart,
}: {
  node: NetworkNode
  onClose: () => void
  onStart: (profile: string) => void
}) {
  const [profile, setProfile] = useState('comprehensive')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6 w-full max-w-sm shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-semibold">Scan Node</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>
        <p className="text-slate-400 text-sm mb-4 font-mono">{node.ip_address}</p>
        <div className="space-y-2 mb-6">
          {(['quick', 'comprehensive', 'vuln'] as const).map((p) => (
            <label key={p} className="flex items-center gap-3 cursor-pointer">
              <input
                type="radio"
                name="profile"
                value={p}
                checked={profile === p}
                onChange={() => setProfile(p)}
                className="accent-cyber-primary"
              />
              <div>
                <p className="text-sm font-medium text-slate-200 capitalize">{p}</p>
                <p className="text-xs text-slate-500">
                  {p === 'quick' && 'Fast top-100 ports scan'}
                  {p === 'comprehensive' && 'Full port + OS + service detection'}
                  {p === 'vuln' && 'Vulnerability scripts (slow)'}
                </p>
              </div>
            </label>
          ))}
        </div>
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 rounded-lg border border-cyber-border text-slate-400 hover:text-white text-sm transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => { onStart(profile); onClose() }}
            className="flex-1 px-4 py-2 rounded-lg bg-cyber-primary/20 border border-cyber-primary/40 text-cyber-primary hover:bg-cyber-primary/30 text-sm font-medium transition-colors"
          >
            Start Scan
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Node card ────────────────────────────────────────────────────────────────
function NodeCard({
  node,
  onScan,
  onDelete,
}: {
  node: NetworkNode
  onScan: (node: NetworkNode) => void
  onDelete: (id: string) => void
}) {
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <div className="bg-cyber-surface border border-cyber-border rounded-xl p-4 hover:border-cyber-primary/40 transition-all group">
      {/* Header row */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-cyber-primary/10 border border-cyber-primary/20 flex items-center justify-center text-cyber-primary">
            <DeviceIcon type={node.device_type} className="w-5 h-5" />
          </div>
          <div>
            <p className="text-xs text-slate-500">{DEVICE_LABELS[node.device_type] ?? 'Unknown'}</p>
            <div className="flex items-center gap-1.5">
              <StatusDot status={node.status} />
              <span className="text-xs text-slate-400">{node.status}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => onScan(node)}
            title="Scan node"
            className="p-1.5 rounded-lg text-slate-400 hover:text-cyber-primary hover:bg-cyber-primary/10 transition-colors"
          >
            <Zap className="w-3.5 h-3.5" />
          </button>
          {confirmDelete ? (
            <>
              <button
                onClick={() => { onDelete(node.id); setConfirmDelete(false) }}
                className="p-1.5 rounded-lg text-rose-400 hover:bg-rose-500/10 transition-colors text-xs"
              >
                ✓
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white transition-colors text-xs"
              >
                ✗
              </button>
            </>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              title="Delete node"
              className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* IP */}
      <p className="font-mono text-base font-bold text-white mb-1">{node.ip_address}</p>

      {/* Hostname */}
      {node.hostname && (
        <p className="text-xs text-slate-400 mb-2 truncate" title={node.hostname}>
          {node.hostname}
        </p>
      )}

      {/* MAC */}
      {node.mac_address && (
        <p className="font-mono text-xs text-slate-500 mb-2">{node.mac_address}</p>
      )}

      {/* Badges */}
      <div className="flex flex-wrap gap-1.5 mt-2">
        {node.os_family && (
          <span className="px-1.5 py-0.5 rounded bg-violet-500/10 border border-violet-500/20 text-violet-300 text-xs">
            {node.os_family}
          </span>
        )}
        {node.open_ports.length > 0 && (
          <span className="px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs">
            {node.open_ports.length} port{node.open_ports.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Last seen */}
      {node.last_seen_at && (
        <p className="text-xs text-slate-600 mt-2">
          {new Date(node.last_seen_at).toLocaleString()}
        </p>
      )}
    </div>
  )
}

// ─── Topology map ─────────────────────────────────────────────────────────────
function TopologyMap({
  nodes,
  onSelect,
  selected,
}: {
  nodes: NetworkNode[]
  onSelect: (node: NetworkNode | null) => void
  selected: NetworkNode | null
}) {
  const cx = 400
  const cy = 280
  const radius = 200

  const gateway = nodes.find((n) => n.device_type === 'router') ?? nodes[0] ?? null
  const others = nodes.filter((n) => n !== gateway)

  return (
    <div className="flex gap-4 h-full">
      <svg
        viewBox="0 0 800 560"
        className="flex-1 bg-cyber-bg/50 rounded-xl border border-cyber-border"
        onClick={() => onSelect(null)}
      >
        {/* Grid lines */}
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e2d4a" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="800" height="560" fill="url(#grid)" />

        {/* Edges from gateway to each other node */}
        {gateway &&
          others.map((n, i) => {
            const angle = (2 * Math.PI * i) / Math.max(others.length, 1)
            const nx = cx + radius * Math.cos(angle)
            const ny = cy + radius * Math.sin(angle)
            return (
              <line
                key={n.id}
                x1={cx} y1={cy}
                x2={nx} y2={ny}
                stroke="#1e2d4a"
                strokeWidth="1.5"
                strokeDasharray="4 3"
              />
            )
          })}

        {/* Satellite nodes */}
        {others.map((n, i) => {
          const angle = (2 * Math.PI * i) / Math.max(others.length, 1)
          const nx = cx + radius * Math.cos(angle)
          const ny = cy + radius * Math.sin(angle)
          const isSelected = selected?.id === n.id
          const color = n.status === 'active' ? '#00d4ff' : '#475569'
          return (
            <g
              key={n.id}
              onClick={(e) => { e.stopPropagation(); onSelect(n) }}
              className="cursor-pointer"
            >
              <circle
                cx={nx} cy={ny} r={isSelected ? 24 : 20}
                fill={isSelected ? 'rgba(0,212,255,0.2)' : 'rgba(30,45,74,0.8)'}
                stroke={isSelected ? '#00d4ff' : color}
                strokeWidth={isSelected ? 2 : 1.5}
              />
              <text x={nx} y={ny + 1} textAnchor="middle" dominantBaseline="middle" fill={color} fontSize="10">
                {DEVICE_LABELS[n.device_type]?.[0] ?? '?'}
              </text>
              <text x={nx} y={ny + 32} textAnchor="middle" fill="#94a3b8" fontSize="9">
                {n.ip_address}
              </text>
            </g>
          )
        })}

        {/* Gateway node (center) */}
        {gateway && (
          <g
            onClick={(e) => { e.stopPropagation(); onSelect(gateway) }}
            className="cursor-pointer"
          >
            <circle
              cx={cx} cy={cy} r={selected?.id === gateway.id ? 32 : 28}
              fill={selected?.id === gateway.id ? 'rgba(0,212,255,0.25)' : 'rgba(0,212,255,0.1)'}
              stroke="#00d4ff"
              strokeWidth={2}
            />
            <text x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="middle" fill="#00d4ff" fontSize="11" fontWeight="bold">
              GW
            </text>
            <text x={cx} y={cy + 40} textAnchor="middle" fill="#94a3b8" fontSize="9">
              {gateway.ip_address}
            </text>
          </g>
        )}

        {nodes.length === 0 && (
          <text x="400" y="280" textAnchor="middle" fill="#475569" fontSize="14">
            No nodes discovered yet
          </text>
        )}
      </svg>

      {/* Detail panel */}
      {selected && (
        <div className="w-64 bg-cyber-surface border border-cyber-border rounded-xl p-4 shrink-0 overflow-y-auto">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2 text-cyber-primary">
              <DeviceIcon type={selected.device_type} className="w-4 h-4" />
              <span className="text-sm font-semibold">{selected.ip_address}</span>
            </div>
            <button onClick={() => onSelect(null)} className="text-slate-500 hover:text-white">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="space-y-2 text-xs">
            <Row label="Type" value={DEVICE_LABELS[selected.device_type] ?? 'Unknown'} />
            {selected.hostname && <Row label="Hostname" value={selected.hostname} mono />}
            {selected.mac_address && <Row label="MAC" value={selected.mac_address} mono />}
            {selected.os_family && <Row label="OS" value={selected.os_family} />}
            {selected.os_version && <Row label="OS ver" value={selected.os_version} />}
            <Row label="Status" value={selected.status} />
            <Row label="Ports" value={String(selected.open_ports.length)} />
          </div>

          {selected.open_ports.length > 0 && (
            <div className="mt-3">
              <p className="text-xs text-slate-500 mb-1.5">Open Ports</p>
              <div className="flex flex-wrap gap-1">
                {selected.open_ports.slice(0, 20).map((p) => (
                  <span key={p} className="px-1.5 py-0.5 rounded bg-cyber-primary/10 border border-cyber-primary/20 text-cyber-primary text-xs font-mono">
                    {p}
                  </span>
                ))}
                {selected.open_ports.length > 20 && (
                  <span className="text-xs text-slate-500">+{selected.open_ports.length - 20} more</span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="text-slate-500 shrink-0">{label}</span>
      <span className={`text-slate-300 text-right truncate ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function NetworkPage() {
  const [nodes, setNodes] = useState<NetworkNode[]>([])
  const [netStatus, setNetStatus] = useState<NetworkStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'list' | 'topology'>('list')
  const [filter, setFilter] = useState<FilterType>('all')
  const [scanModal, setScanModal] = useState<NetworkNode | null>(null)
  const [selectedNode, setSelectedNode] = useState<NetworkNode | null>(null)
  const [activeScan, setActiveScan] = useState<NetworkScan | null>(null)
  const [showRangeInput, setShowRangeInput] = useState(false)
  const [customRange, setCustomRange] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const [nodesRes, statusRes] = await Promise.all([getNodes(), getNetworkStatus()])
      setNodes(nodesRes.data)
      setNetStatus(statusRes.data)
    } catch {
      // silently fail after initial load
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Poll active scan
  useEffect(() => {
    if (!activeScan) return
    if (activeScan.status === 'completed' || activeScan.status === 'failed') return

    pollRef.current = setInterval(async () => {
      try {
        const res = await getScan(activeScan.id)
        setActiveScan(res.data)
        if (res.data.status === 'completed') {
          toast.success(`Discovery complete — ${res.data.nodes_found} node(s) found`)
          fetchData()
          clearInterval(pollRef.current!)
        } else if (res.data.status === 'failed') {
          toast.error(`Discovery failed: ${res.data.error ?? 'unknown error'}`)
          clearInterval(pollRef.current!)
        }
      } catch {
        clearInterval(pollRef.current!)
      }
    }, 3000)

    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [activeScan?.id, activeScan?.status, fetchData])

  const handleDiscover = async () => {
    try {
      const range = customRange.trim() || undefined
      const res = await discoverNetwork(range)
      const scanRes = await getScan(res.data.scan_id)
      setActiveScan(scanRes.data)
      setShowRangeInput(false)
      setCustomRange('')
      toast.success('Network discovery started')
    } catch {
      toast.error('Failed to start discovery')
    }
  }

  const handleScanNode = async (node: NetworkNode, profile: string) => {
    try {
      const res = await scanNode(node.id, profile)
      const scanRes = await getScan(res.data.scan_id)
      setActiveScan(scanRes.data)
      toast.success(`Scan started on ${node.ip_address}`)
    } catch {
      toast.error('Failed to start scan')
    }
  }

  const handleDeleteNode = async (id: string) => {
    try {
      await deleteNode(id)
      setNodes((prev) => prev.filter((n) => n.id !== id))
      toast.success('Node removed')
    } catch {
      toast.error('Failed to delete node')
    }
  }

  const filteredNodes = filter === 'all' ? nodes : nodes.filter((n) => n.device_type === filter)
  const isScanning = activeScan?.status === 'pending' || activeScan?.status === 'running'

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      {/* Page header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Network className="w-5 h-5 text-cyber-primary" />
            Private Network
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">Discover and scan nodes on your LAN</p>
        </div>

        <div className="flex items-center gap-2">
          {showRangeInput && (
            <input
              value={customRange}
              onChange={(e) => setCustomRange(e.target.value)}
              placeholder="e.g. 192.168.1.0/24"
              className="px-3 py-1.5 rounded-lg bg-cyber-bg border border-cyber-border text-slate-300 text-sm focus:outline-none focus:border-cyber-primary/50 w-48 font-mono"
            />
          )}
          <button
            onClick={() => setShowRangeInput((v) => !v)}
            className="px-3 py-1.5 rounded-lg border border-cyber-border text-slate-400 hover:text-white text-sm transition-colors"
          >
            {showRangeInput ? <X className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
          <button
            onClick={handleDiscover}
            disabled={isScanning}
            className="flex items-center gap-2 px-4 py-1.5 rounded-lg bg-cyber-primary/20 border border-cyber-primary/40 text-cyber-primary hover:bg-cyber-primary/30 text-sm font-medium transition-colors disabled:opacity-50"
          >
            {isScanning ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Scanning…
              </>
            ) : (
              <>
                <Search className="w-4 h-4" />
                Discover Network
              </>
            )}
          </button>
          <button
            onClick={fetchData}
            className="p-1.5 rounded-lg border border-cyber-border text-slate-400 hover:text-white transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Network status bar */}
      {netStatus && (
        <div className="bg-cyber-surface border border-cyber-border rounded-xl p-4">
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <Globe className="w-4 h-4 text-cyber-primary" />
              <span className="text-slate-500">Host:</span>
              <span className="text-white font-mono">{netStatus.hostname}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-slate-500">IP:</span>
              <span className="text-white font-mono">{netStatus.host_ip}</span>
            </div>
            {netStatus.interfaces.map((iface) => (
              <div key={iface.interface} className="flex items-center gap-2">
                <span className="px-1.5 py-0.5 rounded bg-cyber-primary/10 border border-cyber-primary/20 text-cyber-primary text-xs font-mono">
                  {iface.interface}
                </span>
                <span className="text-slate-300 font-mono text-xs">{iface.ip}</span>
                <span className="text-slate-500 text-xs">{iface.network_range}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active scan progress banner */}
      {isScanning && activeScan && (
        <div className="bg-sky-500/10 border border-sky-500/30 rounded-xl px-4 py-3 flex items-center gap-3">
          <RefreshCw className="w-4 h-4 text-sky-400 animate-spin shrink-0" />
          <div>
            <span className="text-sky-300 text-sm font-medium">
              {activeScan.scan_type === 'discovery' ? 'Discovering network' : `Scanning ${activeScan.target}`}…
            </span>
            {activeScan.nodes_found > 0 && (
              <span className="text-sky-400/70 text-xs ml-2">{activeScan.nodes_found} node(s) found so far</span>
            )}
          </div>
          <ScanStatusBadge status={activeScan.status} />
        </div>
      )}

      {/* Tab bar */}
      <div className="flex items-center gap-1 border-b border-cyber-border">
        {(['list', 'topology'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 ${
              activeTab === tab
                ? 'border-cyber-primary text-cyber-primary'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            {tab === 'list' ? 'Node List' : 'Topology Map'}
          </button>
        ))}
        <span className="ml-auto text-xs text-slate-500 pb-2">{nodes.length} node(s)</span>
      </div>

      {/* Node List Tab */}
      {activeTab === 'list' && (
        <div>
          {/* Filter bar */}
          <div className="flex flex-wrap gap-2 mb-4">
            {FILTER_TYPES.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  filter === f
                    ? 'bg-cyber-primary/20 border border-cyber-primary/40 text-cyber-primary'
                    : 'bg-cyber-surface border border-cyber-border text-slate-400 hover:text-white'
                }`}
              >
                {f === 'all' ? `All (${nodes.length})` : DEVICE_LABELS[f]}
              </button>
            ))}
          </div>

          {filteredNodes.length === 0 ? (
            <div className="text-center py-16 text-slate-500">
              <Search className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">No nodes found. Run a discovery scan.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filteredNodes.map((node) => (
                <NodeCard
                  key={node.id}
                  node={node}
                  onScan={setScanModal}
                  onDelete={handleDeleteNode}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Topology Map Tab */}
      {activeTab === 'topology' && (
        <div className="h-[520px]">
          <TopologyMap nodes={nodes} onSelect={setSelectedNode} selected={selectedNode} />
        </div>
      )}

      {/* Scan modal */}
      {scanModal && (
        <ScanModal
          node={scanModal}
          onClose={() => setScanModal(null)}
          onStart={(profile) => handleScanNode(scanModal, profile)}
        />
      )}
    </div>
  )
}
