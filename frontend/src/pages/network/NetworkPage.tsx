import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import {
  Laptop, Smartphone, Router, Server, Wifi, HelpCircle, Printer, Camera,
  RefreshCw, Search, Trash2, Zap, X, Network, Upload,
  AlertTriangle, CheckCircle, XCircle, Cpu, Shield, Monitor, GitBranch,
} from 'lucide-react'
import toast from 'react-hot-toast'
import {
  getNodes, discoverNetwork, scanNode, deleteNode, getScan,
  getHostInterfaces, cancelScan, getHostAgentStatus,
  getNodeVulnerabilities, getAllVulnerabilities, updateVulnStatus,
  getTopology, discoveryWsUrl,
} from '../../api/network'
import apiClient from '../../api/client'
import { store } from '../../store'
import type {
  NetworkNode, NetworkScan, HostInterfacesResponse, HostAgentStatus,
  HostVulnerability, TopologyData,
} from '../../api/network'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import TopologyMap from '../../components/network/TopologyMap'
import TrafficMonitor from '../../components/network/TrafficMonitor'

// suppress unused import lint warnings
void Cpu; void Monitor

// ─── Types ────────────────────────────────────────────────────────────────────
type FilterType = typeof DEVICE_FILTER_TYPES[number]
type SeverityFilter = 'all' | 'critical' | 'high' | 'medium' | 'low' | 'info'
type SortBy = 'ip' | 'risk_score' | 'last_seen'

// ─── Constants ────────────────────────────────────────────────────────────────
const DEVICE_ICONS: Record<string, React.ElementType> = {
  pc: Laptop, mobile: Smartphone, router: Router, switch: Wifi,
  server: Server, printer: Printer, iot: Camera, unknown: HelpCircle,
}
const DEVICE_LABELS: Record<string, string> = {
  pc: 'PC', mobile: 'Mobile', router: 'Router', switch: 'Switch',
  server: 'Server', printer: 'Printer', iot: 'IoT', unknown: 'Unknown',
}
const DEVICE_FILTER_TYPES = ['all', 'pc', 'mobile', 'router', 'switch', 'server', 'printer', 'iot', 'unknown'] as const

const SEV = {
  critical: { label: 'CRITICAL', dot: 'bg-rose-500',    text: 'text-rose-400',   border: 'border-rose-500/30',   bg: 'bg-rose-500/10'   },
  high:     { label: 'HIGH',     dot: 'bg-orange-500',  text: 'text-orange-400', border: 'border-orange-500/30', bg: 'bg-orange-500/10' },
  medium:   { label: 'MED',      dot: 'bg-amber-500',   text: 'text-amber-400',  border: 'border-amber-500/30',  bg: 'bg-amber-500/10'  },
  low:      { label: 'LOW',      dot: 'bg-yellow-500',  text: 'text-yellow-400', border: 'border-yellow-500/30', bg: 'bg-yellow-500/10' },
  info:     { label: 'INFO',     dot: 'bg-slate-500',   text: 'text-slate-400',  border: 'border-slate-500/30',  bg: 'bg-slate-500/10'  },
} as const

const SORT_OPTIONS: { value: SortBy; label: string }[] = [
  { value: 'ip', label: 'IP Address' },
  { value: 'risk_score', label: 'Risk Score' },
  { value: 'last_seen', label: 'Last Seen' },
]

// ─── HostIPInput ──────────────────────────────────────────────────────────────
function deriveRange(ip: string): string | null {
  const parts = ip.trim().split('.')
  if (parts.length !== 4 || parts.some(p => isNaN(Number(p)) || Number(p) < 0 || Number(p) > 255)) return null
  return `${parts[0]}.${parts[1]}.${parts[2]}.0/24`
}

function HostIPInput({ onRangeDetected }: { onRangeDetected: (range: string) => void }) {
  const [ip, setIp] = useState('')
  const [error, setError] = useState('')
  const apply = () => {
    const range = deriveRange(ip)
    if (!range) { setError('Enter a valid IPv4 (e.g. 192.168.1.1)'); return }
    setError(''); onRangeDetected(range); toast.success(`Range set to ${range}`)
  }
  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-1.5">
        <input
          value={ip} onChange={e => { setIp(e.target.value); setError('') }}
          onKeyDown={e => e.key === 'Enter' && apply()}
          placeholder="e.g. 192.168.1.100"
          className="flex-1 bg-[#070c1a] border border-cyber-border rounded px-2 py-1.5 text-xs text-white placeholder-slate-600 font-mono focus:outline-none focus:border-cyber-primary"
        />
        <button onClick={apply} className="px-2 py-1.5 rounded bg-cyber-primary/10 border border-cyber-primary/30 text-cyber-primary text-xs hover:bg-cyber-primary/20 whitespace-nowrap">Set</button>
      </div>
      {error && <p className="text-xs text-rose-400">{error}</p>}
      {ip && deriveRange(ip) && <p className="text-xs text-slate-500 font-mono">→ {deriveRange(ip)}</p>}
    </div>
  )
}

// ─── Small helpers ────────────────────────────────────────────────────────────
function DeviceIcon({ type, className = 'w-4 h-4' }: { type: string; className?: string }) {
  const Icon = DEVICE_ICONS[type] ?? HelpCircle
  return <Icon className={className} />
}

function StatusDot({ status }: { status: string }) {
  return <span className={`inline-block w-2 h-2 rounded-full ${status === 'active' ? 'bg-emerald-400' : 'bg-slate-500'}`} />
}

function ScanStatusBadge({ status }: { status: NetworkScan['status'] }) {
  const cls: Record<string, string> = {
    pending: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    running: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
    completed: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    failed: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
    cancelled: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
  }
  return <span className={`px-2 py-0.5 rounded border text-xs font-medium ${cls[status] ?? cls.failed}`}>{status}</span>
}

function SeverityBadge({ severity }: { severity: string }) {
  const cfg = SEV[severity as keyof typeof SEV] ?? SEV.info
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-xs font-bold ${cfg.bg} ${cfg.border} ${cfg.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  )
}

function RiskBar({ score }: { score: number }) {
  if (!score) return <span className="text-slate-600 text-xs">—</span>
  const color = score >= 80 ? 'bg-rose-500' : score >= 60 ? 'bg-orange-500' : score >= 30 ? 'bg-amber-500' : 'bg-emerald-500'
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-14 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${Math.min(100, score)}%` }} />
      </div>
      <span className="text-xs text-slate-400">{score}</span>
    </div>
  )
}

// ─── Scan Modal ───────────────────────────────────────────────────────────────
function ScanModal({ node, onClose, onStart }: { node: NetworkNode; onClose: () => void; onStart: (p: string) => void }) {
  const [profile, setProfile] = useState('comprehensive')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6 w-80 shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-semibold">Scan Node</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
        <p className="font-mono text-slate-400 text-sm mb-4">{node.ip_address}</p>
        <div className="space-y-2 mb-5">
          {(['ping', 'quick', 'comprehensive', 'vuln'] as const).map(p => (
            <label key={p} className="flex items-center gap-3 cursor-pointer">
              <input type="radio" name="profile" value={p} checked={profile === p} onChange={() => setProfile(p)} className="accent-cyber-primary" />
              <div>
                <p className="text-sm font-medium text-slate-200 capitalize">{p === 'ping' ? 'Ping' : p}</p>
                <p className="text-xs text-slate-500">
                  {p === 'ping' && 'ICMP ping — check if host is alive (~5s)'}
                  {p === 'quick' && 'Fast top-100 ports scan'}
                  {p === 'comprehensive' && 'Full port + OS + service detection'}
                  {p === 'vuln' && 'Vulnerability scripts (slow) — populates vulns tab'}
                </p>
              </div>
            </label>
          ))}
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-cyber-border text-slate-400 hover:text-white text-sm">Cancel</button>
          <button onClick={() => { onStart(profile); onClose() }} className="flex-1 py-2 rounded-lg bg-cyber-primary/20 border border-cyber-primary/40 text-cyber-primary hover:bg-cyber-primary/30 text-sm font-medium">Start Scan</button>
        </div>
      </div>
    </div>
  )
}

// ─── Node Detail Panel ────────────────────────────────────────────────────────
function NodeDetailPanel({
  node, vulns, loadingVulns, isMyNode, isScanningNode, onClose, onScan, onUpdateVulnStatus,
}: {
  node: NetworkNode
  vulns: HostVulnerability[]
  loadingVulns: boolean
  isMyNode?: boolean
  isScanningNode?: boolean
  onClose: () => void
  onScan: (node: NetworkNode, profile: string) => void
  onUpdateVulnStatus: (vulnId: string, status: string) => void
}) {
  const nonInfoVulns = vulns.filter(v => v.severity !== 'info')
  const criticalCount = nonInfoVulns.filter(v => v.severity === 'critical').length
  const highCount = nonInfoVulns.filter(v => v.severity === 'high').length

  return (
    <div className="w-[460px] shrink-0 border-l border-cyber-border flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-cyber-border shrink-0 bg-cyber-surface">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5">
              <DeviceIcon type={node.device_type} className={`w-4 h-4 shrink-0 ${isMyNode ? 'text-cyan-400' : 'text-cyber-primary'}`} />
              <span className="font-mono text-base font-bold text-white truncate">{node.ip_address}</span>
              {isMyNode && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-cyan-500/15 border border-cyan-500/40 text-cyan-300 text-xs font-bold shrink-0">
                  <Monitor className="w-2.5 h-2.5" /> THIS DEVICE
                </span>
              )}
              <StatusDot status={node.status} />
              <span className={`text-xs px-1.5 py-0.5 rounded ${node.status === 'active' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-500/10 text-slate-400'}`}>
                {node.status}
              </span>
            </div>
            {node.hostname && <p className="text-slate-300 text-sm truncate">{node.hostname}</p>}
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-xs text-slate-500">
              {node.os_family && <span>{node.os_family}{node.os_version ? ` ${node.os_version}` : ''}</span>}
              {node.mac_address && <span className="font-mono">{node.mac_address}</span>}
              <span>{DEVICE_LABELS[node.device_type] ?? 'Unknown'}</span>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white p-1 shrink-0"><X className="w-4 h-4" /></button>
        </div>
      </div>

      {/* Scan buttons */}
      <div className="px-4 py-2.5 border-b border-cyber-border shrink-0 bg-cyber-surface">
        {isScanningNode ? (
          <div className="flex items-center gap-2 py-2 text-sm text-sky-300">
            <RefreshCw className="w-4 h-4 animate-spin text-cyber-primary" />
            <span>Scanning {node.ip_address}… this may take a minute</span>
          </div>
        ) : (
        <div className="flex gap-2">
          {([['ping', 'Ping'], ['quick', 'Quick Scan'], ['comprehensive', 'Full Scan'], ['vuln', 'Vuln Scan']] as const).map(([p, label]) => (
            <button key={p} onClick={() => onScan(node, p)}
              className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded bg-cyber-primary/10 border border-cyber-primary/30 text-cyber-primary text-xs font-medium hover:bg-cyber-primary/20">
              <Zap className="w-3 h-3" />{label}
            </button>
          ))}
        </div>
        )}
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* Ports & Services */}
        <section>
          <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
            Ports &amp; Services {node.open_ports.length > 0 && <span className="text-cyber-primary">({node.open_ports.length})</span>}
          </h4>
          {node.services && node.services.length > 0 ? (
            <div className="border border-cyber-border rounded-lg overflow-hidden">
              {node.services.map((svc, i) => (
                <div key={`${svc.port}-${svc.protocol}`}
                  className={`flex items-center gap-2 px-3 py-1.5 text-xs ${i !== 0 ? 'border-t border-cyber-border/50' : ''}`}>
                  <span className="font-mono text-cyber-primary w-16 shrink-0">{svc.port}/{svc.protocol}</span>
                  <span className="text-slate-300 w-16 shrink-0 truncate">{svc.service || '—'}</span>
                  <span className="text-slate-500 truncate">{[svc.product, svc.version].filter(Boolean).join(' ') || '—'}</span>
                </div>
              ))}
            </div>
          ) : node.open_ports.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {node.open_ports.map(p => (
                <span key={p} className="px-1.5 py-0.5 rounded bg-cyber-primary/10 border border-cyber-primary/20 text-cyber-primary text-xs font-mono">{p}</span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-600">No open ports detected. Run a scan.</p>
          )}
        </section>

        {/* Vulnerabilities */}
        <section>
          <div className="flex items-center gap-2 mb-2">
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Vulnerabilities</h4>
            {criticalCount > 0 && <span className="text-xs text-rose-400 font-bold">{criticalCount} critical</span>}
            {highCount > 0 && <span className="text-xs text-orange-400 font-bold">{highCount} high</span>}
          </div>
          {loadingVulns ? (
            <div className="flex justify-center py-6"><LoadingSpinner size="sm" /></div>
          ) : vulns.length === 0 ? (
            <div className="text-center py-6 text-slate-600">
              <Shield className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-xs">No findings. Run a Vuln Scan to detect issues.</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {nonInfoVulns.map(vuln => {
                const cfg = SEV[vuln.severity as keyof typeof SEV] ?? SEV.info
                return (
                  <div key={vuln.id} className={`p-2.5 rounded-lg border ${cfg.bg} ${cfg.border}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 mb-1">
                          <SeverityBadge severity={vuln.severity} />
                          {vuln.cve_id && <span className="font-mono text-xs text-slate-300">{vuln.cve_id}</span>}
                          {vuln.cvss_score && <span className="text-xs text-slate-500">CVSS {vuln.cvss_score}</span>}
                        </div>
                        <p className="text-xs text-slate-200 leading-tight">{vuln.title}</p>
                        {vuln.port && <p className="text-xs text-slate-500 mt-0.5">Port {vuln.port}/{vuln.protocol} · {vuln.service}</p>}
                      </div>
                      {vuln.status === 'open' && (
                        <button onClick={() => onUpdateVulnStatus(vuln.id, 'accepted')}
                          className="text-xs text-slate-500 hover:text-amber-300 shrink-0 whitespace-nowrap" title="Mark accepted">
                          Accept
                        </button>
                      )}
                      {vuln.status !== 'open' && (
                        <span className={`text-xs shrink-0 ${
                          vuln.status === 'fixed' ? 'text-emerald-400' :
                          vuln.status === 'accepted' ? 'text-amber-400' : 'text-slate-500'}`}>
                          {vuln.status}
                        </span>
                      )}
                    </div>
                  </div>
                )
              })}
              {vulns.filter(v => v.severity === 'info').length > 0 && (
                <p className="text-xs text-slate-600 pt-1">
                  +{vulns.filter(v => v.severity === 'info').length} informational findings (open ports)
                </p>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function NetworkPage() {
  const [nodes, setNodes] = useState<NetworkNode[]>([])
  const [allVulns, setAllVulns] = useState<HostVulnerability[]>([])
  const [nodeVulns, setNodeVulns] = useState<HostVulnerability[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingVulns, setLoadingVulns] = useState(false)
  const [loadingNodeVulns, setLoadingNodeVulns] = useState(false)
  const [hostIfaces, setHostIfaces] = useState<HostInterfacesResponse | null>(null)
  const [hostAgent, setHostAgent] = useState<HostAgentStatus | null>(null)
  const [ifacesLoading, setIfacesLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'assets' | 'vulnerabilities' | 'topology'>('assets')
  // Topology state
  const [topology, setTopology]         = useState<TopologyData | null>(null)
  const [topoLoading, setTopoLoading]   = useState(false)
  const [topoActiveIps, setTopoActiveIps] = useState<Set<string>>(new Set())
  const [deviceFilter, setDeviceFilter] = useState<FilterType>('all')
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<SortBy>('ip')
  const [selectedNode, setSelectedNode] = useState<NetworkNode | null>(null)
  const [activeScan, setActiveScan] = useState<NetworkScan | null>(null)
  const [scanningNodeId, setScanningNodeId] = useState<string | null>(null)
  const [scanModal, setScanModal] = useState<NetworkNode | null>(null)
  const [customRange, setCustomRange] = useState('')
  const [cancelling, setCancelling] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const [isDiscovering, setIsDiscovering] = useState(false)
  const [discoveryResult, setDiscoveryResult] = useState<{ nodesFound: number; range: string; newNodes: number } | null>(null)
  const [recentlyFoundIps, setRecentlyFoundIps] = useState<Set<string>>(new Set())
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Derived ─────────────────────────────────────────────────────────────────
  // Build a set of all IPs that belong to this machine.
  // Primary: host agent /interfaces (real Windows IPs)
  // Fallback: match discovered nodes by hostname (DESKTOP-EKA6D98 etc.)
  const myIps = useMemo(() => {
    const ips = new Set<string>()
    // 1. From host-interfaces (Docker bridge IPs - usually NOT in node list, but kept for completeness)
    if (hostIfaces?.interfaces) {
      for (const iface of hostIfaces.interfaces) if (iface.ip) ips.add(iface.ip)
    }
    // 2. Hostname-based matching: any node whose hostname contains the agent's hostname
    if (hostAgent?.hostname) {
      const agentHostname = hostAgent.hostname.toLowerCase()
      for (const node of nodes) {
        if (node.hostname && node.hostname.toLowerCase().includes(agentHostname)) {
          ips.add(node.ip_address)
        }
      }
    }
    // 3. host.docker.internal node = the host machine as seen from Docker
    for (const node of nodes) {
      if (node.hostname === 'host.docker.internal') ips.add(node.ip_address)
    }
    return ips
  }, [hostIfaces, hostAgent, nodes])

  const vulnsByNode = useMemo(() => {
    const map: Record<string, { critical: number; high: number; medium: number; low: number; info: number }> = {}
    for (const v of allVulns) {
      if (!map[v.node_id]) map[v.node_id] = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
      const s = v.severity as 'critical' | 'high' | 'medium' | 'low' | 'info'
      if (s in map[v.node_id]) map[v.node_id][s] = (map[v.node_id][s] as number) + 1
    }
    return map
  }, [allVulns])

  const filteredNodes = useMemo(() => {
    let r = nodes.filter(n => n.status === 'active')
    if (deviceFilter !== 'all') r = r.filter(n => n.device_type === deviceFilter)
    if (search) {
      const q = search.toLowerCase()
      r = r.filter(n => n.ip_address.includes(q) || n.hostname?.toLowerCase().includes(q) || n.mac_address?.toLowerCase().includes(q))
    }
    if (severityFilter !== 'all') {
      r = r.filter(n => (vulnsByNode[n.id]?.[severityFilter as 'critical' | 'high' | 'medium' | 'low' | 'info'] ?? 0) > 0)
    }
    r.sort((a, b) => {
      // Always pin "this device" nodes to the top
      const aMine = myIps.has(a.ip_address) ? 0 : 1
      const bMine = myIps.has(b.ip_address) ? 0 : 1
      if (aMine !== bMine) return aMine - bMine
      if (sortBy === 'risk_score') return (b.risk_score ?? 0) - (a.risk_score ?? 0)
      if (sortBy === 'last_seen') return new Date(b.last_seen_at ?? 0).getTime() - new Date(a.last_seen_at ?? 0).getTime()
      return a.ip_address.localeCompare(b.ip_address, undefined, { numeric: true, sensitivity: 'base' })
    })
    return r
  }, [nodes, deviceFilter, severityFilter, search, sortBy, vulnsByNode, myIps])

  const filteredVulns = useMemo(() => {
    let r = [...allVulns]
    if (severityFilter !== 'all') r = r.filter(v => v.severity === severityFilter)
    if (search) {
      const q = search.toLowerCase()
      r = r.filter(v => v.title.toLowerCase().includes(q) || v.cve_id?.toLowerCase().includes(q) || v.service?.toLowerCase().includes(q))
    }
    return r
  }, [allVulns, severityFilter, search])

  // ── Fetchers ────────────────────────────────────────────────────────────────
  const fetchNodes = useCallback(async () => {
    try { const res = await getNodes(); setNodes(res.data) }
    catch { /* silently fail */ }
    finally { setLoading(false) }
  }, [])

  const fetchAllVulns = useCallback(async () => {
    setLoadingVulns(true)
    try { const res = await getAllVulnerabilities(); setAllVulns(res.data) }
    catch { /* silently fail */ }
    finally { setLoadingVulns(false) }
  }, [])

  const fetchHostInterfaces = useCallback(async () => {
    setIfacesLoading(true)
    try { const res = await getHostInterfaces(); setHostIfaces(res.data) }
    catch { setHostIfaces({ interfaces: [], lan_interfaces: [], docker_only: null, has_lan_access: false, primary_range: null, gateway_ip: null, error: 'Cannot reach nmap worker' }) }
    finally { setIfacesLoading(false) }
  }, [])

  const fetchHostAgentStatus = useCallback(async () => {
    try { const res = await getHostAgentStatus(); setHostAgent(res.data) }
    catch { setHostAgent({ available: false, platform: null, hostname: null }) }
  }, [])

  const fetchTopology = useCallback(async () => {
    setTopoLoading(true)
    try { const res = await getTopology(); setTopology(res.data) }
    catch { /* silently fail */ }
    finally { setTopoLoading(false) }
  }, [])

  const fetchNodeVulns = useCallback(async (nodeId: string) => {
    setLoadingNodeVulns(true)
    setNodeVulns([])
    try { const res = await getNodeVulnerabilities(nodeId); setNodeVulns(res.data) }
    catch { /* silently fail */ }
    finally { setLoadingNodeVulns(false) }
  }, [])

  useEffect(() => {
    fetchNodes(); fetchAllVulns(); fetchHostInterfaces(); fetchHostAgentStatus()
  }, [fetchNodes, fetchAllVulns, fetchHostInterfaces, fetchHostAgentStatus])

  // Fetch topology when topology tab is opened
  useEffect(() => {
    if (activeTab === 'topology') fetchTopology()
  }, [activeTab, fetchTopology])

  const selectedNodeId = selectedNode?.id
  useEffect(() => {
    if (selectedNodeId) fetchNodeVulns(selectedNodeId)
  }, [selectedNodeId, fetchNodeVulns])

  // ── Poll active scan ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!activeScan || ['completed', 'failed', 'cancelled'].includes(activeScan.status)) return
    pollRef.current = setInterval(async () => {
      try {
        const res = await getScan(activeScan.id)
        setActiveScan(res.data)
        if (res.data.status === 'completed') {
          toast.success(`Scan complete — ${res.data.nodes_found || 0} node(s) found`)
          fetchNodes(); fetchAllVulns()
          if (selectedNodeId) fetchNodeVulns(selectedNodeId)
          clearInterval(pollRef.current!)
        } else if (res.data.status === 'failed') {
          toast.error(`Scan failed: ${res.data.error ?? 'unknown error'}`)
          clearInterval(pollRef.current!)
        } else if (res.data.status === 'cancelled') {
          toast('Scan cancelled', { icon: '⛔' })
          clearInterval(pollRef.current!)
        }
      } catch { clearInterval(pollRef.current!) }
    }, 3000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [activeScan?.id, activeScan?.status, fetchNodes, fetchAllVulns, fetchNodeVulns, selectedNodeId])

  // ── Handlers ─────────────────────────────────────────────────────────────────
  const handleDiscover = async () => {
    const range = customRange.trim() || hostIfaces?.primary_range || undefined
    if (!range && !hostAgent?.available) {
      toast.error('Enter your host IP in the sidebar to set the scan range')
      return
    }
    setIsDiscovering(true)
    setDiscoveryResult(null)
    const prevNodes = nodes

    // ── WebSocket streaming discovery ─────────────────────────────────────────
    const token = store.getState().auth.accessToken ?? ''
    const wsUrl = discoveryWsUrl(token, range)
    const ws = new WebSocket(wsUrl)
    let nodesFound = 0
    const newIps = new Set<string>()
    const prevIps = new Set(prevNodes.map(n => n.ip_address))
    const liveNodes: NetworkNode[] = [...prevNodes]

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string)
        if (msg.type === 'node' && msg.node) {
          const n = msg.node as NetworkNode
          nodesFound++
          if (!prevIps.has(n.ip_address)) {
            newIps.add(n.ip_address)
            liveNodes.push(n)
          }
          setNodes([...liveNodes])
        } else if (msg.type === 'done') {
          setDiscoveryResult({ nodesFound, range: range ?? 'network', newNodes: newIps.size })
          setRecentlyFoundIps(new Set(newIps))
          setTimeout(() => setRecentlyFoundIps(new Set()), 30000)
          toast.success(`Discovery complete — ${nodesFound} node(s) found`)
          setIsDiscovering(false)
          fetchAllVulns()
        } else if (msg.type === 'error') {
          // Fall back to REST discovery on WS error
          toast.error(msg.message ?? 'Discovery error')
          setIsDiscovering(false)
        }
      } catch { /* ignore parse errors */ }
    }

    ws.onerror = async () => {
      // WS unavailable — fall back to REST endpoint
      ws.close()
      try {
        const res = await discoverNetwork(range)
        setCustomRange('')
        if (res.data.status === 'completed') {
          const count = res.data.nodes_found ?? 0
          try {
            const refreshed = await getNodes()
            const freshNodes = refreshed.data
            const newIpsFallback = freshNodes.filter(n => !prevIps.has(n.ip_address)).map(n => n.ip_address)
            setRecentlyFoundIps(new Set(newIpsFallback))
            setNodes(freshNodes)
            setTimeout(() => setRecentlyFoundIps(new Set()), 30000)
            setDiscoveryResult({ nodesFound: count, range: range ?? 'network', newNodes: newIpsFallback.length })
          } catch { /* ignore */ }
          toast.success(`Discovery complete — ${count} node(s) found`)
        } else {
          const scanRes = await getScan(res.data.scan_id)
          setActiveScan(scanRes.data)
          toast.success('Network discovery started')
        }
      } catch (err) { toast.error('Failed to start discovery'); console.error(err) }
      finally { setIsDiscovering(false) }
    }

    ws.onclose = (ev) => {
      if (ev.code !== 1000 && isDiscovering) setIsDiscovering(false)
    }
  }

  const handleCancelScan = async () => {
    if (!activeScan) return
    setCancelling(true)
    try {
      await cancelScan(activeScan.id)
      setActiveScan(p => p ? { ...p, status: 'cancelled' } : null)
      toast('Scan cancelled', { icon: '⛔' })
    } catch { toast.error('Failed to cancel scan') }
    finally { setCancelling(false) }
  }

  const handleScanNode = async (node: NetworkNode, profile: string) => {
    setScanningNodeId(node.id)
    try {
      const res = await scanNode(node.id, profile)
      if (res.data.status === 'completed') {
        // Host agent completed synchronously — refresh nodes immediately
        toast.success(res.data.message ?? `Scan complete on ${node.ip_address}`)
        fetchNodes()
        if (selectedNode?.id === node.id) fetchNodeVulns(node.id)
      } else {
        const scanRes = await getScan(res.data.scan_id)
        setActiveScan(scanRes.data)
        toast.success(`Scan started on ${node.ip_address}`)
      }
    } catch { toast.error('Failed to start scan') }
    finally { setScanningNodeId(null) }
  }

  const handleDeleteNode = async (id: string) => {
    try {
      await deleteNode(id)
      setNodes(p => p.filter(n => n.id !== id))
      if (selectedNode?.id === id) setSelectedNode(null)
      toast.success('Node removed')
    } catch { toast.error('Failed to delete node') }
  }

  const handleVulnStatusChange = async (nodeId: string, vulnId: string, status: string) => {
    try {
      await updateVulnStatus(nodeId, vulnId, status)
      const patch = (v: HostVulnerability) => v.id === vulnId ? { ...v, status: status as HostVulnerability['status'] } : v
      setAllVulns(p => p.map(patch))
      setNodeVulns(p => p.map(patch))
      toast.success('Status updated')
    } catch { toast.error('Failed to update status') }
  }

  const handleUpdateVulnStatus = (vulnId: string, status: string) => {
    if (!selectedNode) return
    handleVulnStatusChange(selectedNode.id, vulnId, status)
  }

  const handleImportVulns = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    try {
      const text = await file.text()
      const parsed = JSON.parse(text)
      await apiClient.post('/network/import', parsed)
      toast.success('Vulnerabilities imported successfully')
      fetchAllVulns()
      setImportOpen(false)
    } catch {
      toast.error('Failed to import vulnerabilities. Check JSON format.')
    } finally {
      setImporting(false)
      e.target.value = ''
    }
  }

  const isScanning = isDiscovering || activeScan?.status === 'pending' || activeScan?.status === 'running'
  const totalCritical = allVulns.filter(v => v.severity === 'critical').length
  const totalHigh = allVulns.filter(v => v.severity === 'high').length
  const nonInfoVulnCount = allVulns.filter(v => v.severity !== 'info').length

  if (loading) return <div className="flex-1 flex items-center justify-center"><LoadingSpinner size="lg" /></div>

  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      {/* ── Banners ──────────────────────────────────────────────────────────── */}
      {hostAgent !== null && (
        hostAgent.available ? (
          <div className="flex items-center gap-2 px-4 py-2 bg-emerald-500/10 border-b border-emerald-500/20 shrink-0">
            <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span className="text-emerald-300 text-xs">Host Agent Connected — real LAN discovery active{hostAgent.hostname ? ` (${hostAgent.hostname})` : ''}</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 px-4 py-2 bg-amber-500/10 border-b border-amber-500/20 shrink-0">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
            <span className="text-amber-300 text-xs font-medium">Docker-only mode</span>
            <span className="text-amber-600 text-xs">— run host-agent/start.bat for real LAN access</span>
            <button onClick={fetchHostAgentStatus} className="text-xs text-amber-400 hover:text-amber-300 ml-auto">Recheck</button>
          </div>
        )
      )}
      {isDiscovering && (
        <div className="px-4 py-2 bg-cyber-primary/10 border-b border-cyber-primary/30 flex items-center gap-2 text-xs text-cyber-primary shrink-0">
          <RefreshCw className="w-3 h-3 animate-spin" />
          <span>Discovering network… scanning for active hosts</span>
        </div>
      )}
      {isScanning && activeScan && (
        <div className="flex items-center gap-2 px-4 py-2 bg-sky-500/10 border-b border-sky-500/20 shrink-0">
          <RefreshCw className="w-3.5 h-3.5 text-sky-400 animate-spin shrink-0" />
          <span className="text-sky-300 text-xs flex-1">
            {activeScan.scan_type === 'discovery' ? 'Discovering network' : `Scanning ${activeScan.target}`}…
          </span>
          <ScanStatusBadge status={activeScan.status} />
          <button onClick={handleCancelScan} disabled={cancelling}
            className="flex items-center gap-1 px-2 py-1 rounded border border-rose-500/40 text-rose-400 hover:bg-rose-500/10 text-xs disabled:opacity-50">
            {cancelling ? <RefreshCw className="w-3 h-3 animate-spin" /> : <XCircle className="w-3 h-3" />}
            Cancel
          </button>
        </div>
      )}

      {/* ── Body ─────────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* ── Left Sidebar ─────────────────────────────────────────────────── */}
        <div className="w-[260px] shrink-0 border-r border-cyber-border flex flex-col overflow-y-auto">
          <div className="px-4 py-3 border-b border-cyber-border shrink-0">
            <h1 className="text-sm font-bold text-white flex items-center gap-2">
              <Network className="w-4 h-4 text-cyber-primary" />
              Private Network
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">{nodes.length} asset{nodes.length !== 1 ? 's' : ''} discovered</p>
          </div>

          <div className="flex-1 p-3 space-y-4 overflow-y-auto">
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-500 pointer-events-none" />
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Search IP, hostname…"
                className="w-full bg-cyber-bg border border-cyber-border rounded px-2 py-1.5 pl-6 text-xs text-slate-300 placeholder-slate-600 focus:outline-none focus:border-cyber-primary" />
            </div>

            {/* Device type */}
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Device Type</p>
              <div className="flex flex-wrap gap-1">
                {DEVICE_FILTER_TYPES.map(f => (
                  <button key={f} onClick={() => setDeviceFilter(f)}
                    className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                      deviceFilter === f
                        ? 'bg-cyber-primary/20 border border-cyber-primary/40 text-cyber-primary'
                        : 'bg-cyber-surface border border-cyber-border text-slate-500 hover:text-white'
                    }`}>
                    {f === 'all' ? 'All' : DEVICE_LABELS[f]}
                  </button>
                ))}
              </div>
            </div>

            {/* Severity filter */}
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Severity</p>
              <div className="flex flex-wrap gap-1">
                {(['all', 'critical', 'high', 'medium', 'low', 'info'] as const).map(s => {
                  const cfg = s !== 'all' ? SEV[s] : null
                  return (
                    <button key={s} onClick={() => setSeverityFilter(s)}
                      className={`px-2 py-0.5 rounded text-xs font-medium transition-colors border ${
                        severityFilter === s
                          ? s === 'all'
                            ? 'bg-cyber-primary/20 border-cyber-primary/40 text-cyber-primary'
                            : `${cfg?.bg} ${cfg?.border} ${cfg?.text}`
                          : 'bg-transparent border-cyber-border text-slate-500 hover:text-white'
                      }`}>
                      {s === 'all' ? 'All' : cfg?.label}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Sort */}
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Sort By</p>
              <div className="space-y-0.5">
                {SORT_OPTIONS.map(({ value, label }) => (
                  <button key={value} onClick={() => setSortBy(value)}
                    className={`w-full text-left px-2 py-1 rounded text-xs transition-colors ${
                      sortBy === value ? 'bg-cyber-primary/10 text-cyber-primary' : 'text-slate-500 hover:text-slate-200'
                    }`}>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Discovery zone */}
            <div className="border-t border-cyber-border pt-3 space-y-3">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Discovery</p>

              <div>
                <p className="text-xs text-slate-500 mb-1.5">Enter host IP → auto-derive range:</p>
                <HostIPInput onRangeDetected={range => setCustomRange(range)} />
              </div>

              {customRange && (
                <p className="text-xs font-mono text-cyber-primary">{customRange}</p>
              )}

              <button onClick={handleDiscover} disabled={isScanning || isDiscovering}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-cyber-primary/20 border border-cyber-primary/40 text-cyber-primary hover:bg-cyber-primary/30 text-xs font-medium disabled:opacity-50">
                {isDiscovering ? <><RefreshCw className="w-3 h-3 animate-spin" />Discovering…</> : isScanning ? <><RefreshCw className="w-3 h-3 animate-spin" />Scanning…</> : <><Search className="w-3 h-3" />Discover Network</>}
              </button>

              {/* Discovery result banner */}
              {discoveryResult && (
                <div className="mt-2 p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-xs">
                  <div className="flex items-start justify-between gap-1">
                    <div className="flex items-start gap-1.5">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                      <div>
                        <p className="text-emerald-300 font-medium">Discovery complete</p>
                        <p className="text-slate-400 mt-0.5">{discoveryResult.nodesFound} nodes on {discoveryResult.range}</p>
                        {discoveryResult.newNodes > 0 && (
                          <p className="text-cyan-400 mt-0.5">+{discoveryResult.newNodes} new</p>
                        )}
                      </div>
                    </div>
                    <button onClick={() => setDiscoveryResult(null)} className="text-slate-500 hover:text-white shrink-0">
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              )}

              {/* Worker status */}
              <div className="pt-1">
                {ifacesLoading ? (
                  <div className="flex items-center gap-1.5 text-xs text-slate-500">
                    <RefreshCw className="w-3 h-3 animate-spin" /> Checking worker…
                  </div>
                ) : hostIfaces?.error && !hostIfaces.interfaces.length ? (
                  <div className="flex items-center gap-1.5 text-xs text-rose-400">
                    <XCircle className="w-3 h-3" /> nmap worker offline
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 text-xs text-emerald-400">
                    <CheckCircle className="w-3 h-3" /> nmap worker online
                    {hostIfaces?.gateway_ip && (
                      <button onClick={() => setCustomRange(hostIfaces.gateway_ip!.replace(/\.\d+$/, '.0') + '/24')}
                        className="font-mono text-cyber-primary hover:underline ml-auto text-xs" title="Use gateway subnet">
                        {hostIfaces.gateway_ip}
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* ── Main Content ───────────────────────────────────────────────────── */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Summary bar */}
          <div className="px-4 py-2 border-b border-cyber-border shrink-0 flex items-center gap-3">
            <span className="text-xs text-slate-500">{nodes.length} assets</span>
            {totalCritical > 0 && <span className="text-xs text-rose-400 font-bold">{totalCritical} critical</span>}
            {totalHigh > 0 && <span className="text-xs text-orange-400 font-bold">{totalHigh} high</span>}
            {nonInfoVulnCount > 0 && <span className="text-xs text-slate-500">{nonInfoVulnCount} total findings</span>}
            <div className="ml-auto">
              <button onClick={() => { fetchNodes(); fetchAllVulns() }} className="p-1 text-slate-500 hover:text-white" title="Refresh">
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Tab bar */}
          <div className="flex items-center border-b border-cyber-border px-4 shrink-0">
            {([
              ['assets', 'Assets'],
              ['vulnerabilities', 'Vulnerabilities'],
              ['topology', 'Topology & Traffic'],
            ] as const).map(([tab, label]) => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab ? 'border-cyber-primary text-cyber-primary' : 'border-transparent text-slate-400 hover:text-white'
                }`}>
                {tab === 'topology' && <GitBranch className="w-3.5 h-3.5 inline mr-1.5 -mt-0.5" />}
                {label}
                {tab === 'assets' && <span className="ml-1.5 text-xs text-slate-500">{filteredNodes.length}</span>}
                {tab === 'vulnerabilities' && nonInfoVulnCount > 0 && (
                  <span className="ml-1.5 text-xs text-rose-400 font-bold">{nonInfoVulnCount}</span>
                )}
              </button>
            ))}
            {activeTab === 'vulnerabilities' && (
              <button onClick={() => setImportOpen(true)}
                className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border border-cyber-border text-slate-400 hover:text-white hover:border-cyber-primary transition-colors my-auto">
                <Upload className="w-3 h-3" />
                Import
              </button>
            )}
            {activeTab === 'topology' && (
              <button onClick={fetchTopology}
                className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border border-cyber-border text-slate-400 hover:text-white hover:border-cyber-primary transition-colors my-auto">
                <RefreshCw className={`w-3 h-3 ${topoLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            )}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto">
            {/* ── ASSETS TAB ─────────────────────────────────────────────── */}
            {activeTab === 'assets' && (
              filteredNodes.length === 0 ? (
                <div className="text-center py-16 text-slate-500">
                  <Search className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p className="text-sm">No assets found.</p>
                  <p className="text-xs mt-1">Run a discovery scan using the sidebar.</p>
                </div>
              ) : (
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-[#070c1a] border-b border-cyber-border z-10">
                    <tr className="text-slate-500 text-left">
                      <th className="px-3 py-2.5 font-medium w-8"></th>
                      <th className="px-3 py-2.5 font-medium">IP Address</th>
                      <th className="px-3 py-2.5 font-medium">Hostname</th>
                      <th className="px-3 py-2.5 font-medium">OS</th>
                      <th className="px-2 py-2.5 font-medium text-center">Ports</th>
                      <th className="px-2 py-2.5 font-medium text-center text-rose-500">C</th>
                      <th className="px-2 py-2.5 font-medium text-center text-orange-500">H</th>
                      <th className="px-2 py-2.5 font-medium text-center text-amber-500">M</th>
                      <th className="px-2 py-2.5 font-medium text-center text-yellow-500">L</th>
                      <th className="px-3 py-2.5 font-medium">Risk</th>
                      <th className="px-3 py-2.5 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredNodes.map(node => {
                      const counts = vulnsByNode[node.id] ?? { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
                      const isSelected = selectedNode?.id === node.id
                      const isMine = myIps.has(node.ip_address)
                      const isRecent = recentlyFoundIps.has(node.ip_address)
                      return (
                        <tr key={node.id} onClick={() => setSelectedNode(isSelected ? null : node)}
                          className={`border-b border-cyber-border/40 cursor-pointer transition-colors
                            ${isRecent ? 'bg-emerald-500/10 border-l-2 border-l-emerald-500' : isMine ? 'border-l-2 border-l-cyan-500/50' : ''}
                            ${isSelected ? 'bg-cyber-primary/10' : isRecent ? 'hover:bg-emerald-500/15' : isMine ? 'bg-cyan-500/5 hover:bg-cyan-500/10' : 'hover:bg-cyber-surface'}`}>
                          <td className="px-3 py-2">
                            <div className="flex items-center gap-1.5">
                              <StatusDot status={node.status} />
                              <DeviceIcon type={node.device_type} className={`w-3.5 h-3.5 ${isMine ? 'text-cyan-400' : 'text-slate-400'}`} />
                            </div>
                          </td>
                          <td className="px-3 py-2 font-mono font-semibold">
                            <div className="flex items-center gap-1.5">
                              <span className={isMine ? 'text-cyan-300' : 'text-white'}>{node.ip_address}</span>
                              {isMine && (
                                <span className="inline-flex items-center gap-0.5 px-1 py-0.5 rounded bg-cyan-500/15 border border-cyan-500/30 text-cyan-400 text-[10px] font-bold shrink-0">
                                  <Monitor className="w-2 h-2" /> YOU
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="px-3 py-2 text-slate-400 max-w-[130px]">
                            <span className="truncate block" title={node.hostname ?? undefined}>{node.hostname ?? '—'}</span>
                          </td>
                          <td className="px-3 py-2 text-slate-400">{node.os_family ?? '—'}</td>
                          <td className="px-2 py-2 text-center">
                            {node.open_ports.length > 0
                              ? <span className="px-1.5 py-0.5 rounded bg-cyber-primary/10 border border-cyber-primary/20 text-cyber-primary font-mono">{node.open_ports.length}</span>
                              : <span className="text-slate-600">—</span>}
                          </td>
                          <td className="px-2 py-2 text-center">{counts.critical > 0 ? <span className="text-rose-400 font-bold">{counts.critical}</span> : <span className="text-slate-700">0</span>}</td>
                          <td className="px-2 py-2 text-center">{counts.high > 0 ? <span className="text-orange-400 font-bold">{counts.high}</span> : <span className="text-slate-700">0</span>}</td>
                          <td className="px-2 py-2 text-center">{counts.medium > 0 ? <span className="text-amber-400">{counts.medium}</span> : <span className="text-slate-700">0</span>}</td>
                          <td className="px-2 py-2 text-center">{counts.low > 0 ? <span className="text-yellow-400">{counts.low}</span> : <span className="text-slate-700">0</span>}</td>
                          <td className="px-3 py-2"><RiskBar score={node.risk_score ?? 0} /></td>
                          <td className="px-3 py-2">
                            <div className="flex items-center justify-end gap-1">
                              {scanningNodeId === node.id ? (
                                <span title="Scanning…"><RefreshCw className="w-3.5 h-3.5 animate-spin text-cyber-primary" /></span>
                              ) : (
                                <button onClick={e => { e.stopPropagation(); setScanModal(node) }}
                                  className="p-1 rounded text-slate-500 hover:text-cyber-primary hover:bg-cyber-primary/10" title="Scan">
                                  <Zap className="w-3.5 h-3.5" />
                                </button>
                              )}
                              <button onClick={e => { e.stopPropagation(); handleDeleteNode(node.id) }}
                                className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-500/10" title="Delete">
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )
            )}

            {/* ── VULNERABILITIES TAB ────────────────────────────────────── */}
            {activeTab === 'vulnerabilities' && (
              loadingVulns ? (
                <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
              ) : filteredVulns.length === 0 ? (
                <div className="text-center py-16 text-slate-500">
                  <Shield className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p className="text-sm">No vulnerabilities found.</p>
                  <p className="text-xs mt-1">Run a Vuln Scan on any asset to detect issues.</p>
                </div>
              ) : (
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-[#070c1a] border-b border-cyber-border z-10">
                    <tr className="text-slate-500 text-left">
                      <th className="px-3 py-2.5 font-medium">Severity</th>
                      <th className="px-3 py-2.5 font-medium">Host</th>
                      <th className="px-3 py-2.5 font-medium">Port</th>
                      <th className="px-3 py-2.5 font-medium">Service</th>
                      <th className="px-3 py-2.5 font-medium">CVE</th>
                      <th className="px-3 py-2.5 font-medium">Title</th>
                      <th className="px-3 py-2.5 font-medium">Status</th>
                      <th className="px-3 py-2.5 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredVulns.map(vuln => {
                      const hostNode = nodes.find(n => n.id === vuln.node_id)
                      return (
                        <tr key={vuln.id} className="border-b border-cyber-border/40 hover:bg-cyber-surface">
                          <td className="px-3 py-2"><SeverityBadge severity={vuln.severity} /></td>
                          <td className="px-3 py-2 font-mono text-slate-300">{hostNode?.ip_address ?? '—'}</td>
                          <td className="px-3 py-2 font-mono text-slate-400">{vuln.port ? `${vuln.port}/${vuln.protocol}` : '—'}</td>
                          <td className="px-3 py-2 text-slate-400">{vuln.service ?? '—'}</td>
                          <td className="px-3 py-2">
                            {vuln.cve_id ? <span className="font-mono text-cyber-primary">{vuln.cve_id}</span> : <span className="text-slate-600">—</span>}
                          </td>
                          <td className="px-3 py-2 text-slate-300 max-w-[200px]">
                            <span className="truncate block" title={vuln.title}>{vuln.title}</span>
                          </td>
                          <td className="px-3 py-2">
                            <span className={`px-1.5 py-0.5 rounded text-xs ${
                              vuln.status === 'open' ? 'bg-rose-500/10 text-rose-400' :
                              vuln.status === 'fixed' ? 'bg-emerald-500/10 text-emerald-400' :
                              vuln.status === 'accepted' ? 'bg-amber-500/10 text-amber-400' :
                              'bg-slate-500/10 text-slate-400'
                            }`}>{vuln.status}</span>
                          </td>
                          <td className="px-3 py-2">
                            {vuln.status === 'open' && (
                              <div className="flex items-center justify-end gap-1">
                                <button onClick={() => handleVulnStatusChange(vuln.node_id, vuln.id, 'fixed')}
                                  className="px-1.5 py-0.5 rounded text-xs text-emerald-400 hover:bg-emerald-500/10 border border-emerald-500/20">Fixed</button>
                                <button onClick={() => handleVulnStatusChange(vuln.node_id, vuln.id, 'accepted')}
                                  className="px-1.5 py-0.5 rounded text-xs text-amber-400 hover:bg-amber-500/10 border border-amber-500/20">Accept</button>
                              </div>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )
            )}

            {/* ── TOPOLOGY & TRAFFIC TAB ────────────────────────────────────── */}
            {activeTab === 'topology' && (
              topoLoading && !topology ? (
                <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
              ) : (
                <div className="flex flex-col h-full" style={{ minHeight: '600px' }}>
                  {/* Topology Map */}
                  <div className="flex-none" style={{ height: '420px' }}>
                    <div className="h-full border-b border-slate-700/60">
                      <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-700/40 bg-slate-900/50">
                        <GitBranch className="w-4 h-4 text-cyan-400" />
                        <span className="text-sm font-semibold text-white">Network Topology</span>
                        <span className="text-xs text-slate-500">
                          {topology ? `${topology.nodes.length} nodes · ${topology.edges.length} connections` : 'Loading…'}
                        </span>
                        {topology?.gateway_ip && (
                          <span className="ml-auto text-xs text-slate-500">
                            Gateway: <span className="text-blue-400 font-mono">{topology.gateway_ip}</span>
                          </span>
                        )}
                      </div>
                      <div style={{ height: 'calc(100% - 37px)' }}>
                        <TopologyMap
                          nodes={topology?.nodes ?? []}
                          edges={topology?.edges ?? []}
                          activeIps={topoActiveIps}
                          onNodeClick={n => {
                            if (n.db_id) {
                              const dbNode = nodes.find(nd => nd.id === n.db_id)
                              if (dbNode) setSelectedNode(dbNode)
                            }
                          }}
                        />
                      </div>
                    </div>
                  </div>
                  {/* Traffic Monitor */}
                  <div className="flex-1 overflow-hidden" style={{ minHeight: '240px' }}>
                    <TrafficMonitor onActiveIpsChange={setTopoActiveIps} />
                  </div>
                </div>
              )
            )}
          </div>
        </div>

        {/* ── Detail Panel ───────────────────────────────────────────────────── */}
        {selectedNode && (
          <NodeDetailPanel
            node={selectedNode}
            vulns={nodeVulns}
            loadingVulns={loadingNodeVulns}
            isMyNode={myIps.has(selectedNode.ip_address)}
            isScanningNode={scanningNodeId === selectedNode.id}
            onClose={() => setSelectedNode(null)}
            onScan={handleScanNode}
            onUpdateVulnStatus={handleUpdateVulnStatus}
          />
        )}
      </div>

      {/* Scan modal */}
      {scanModal && (
        <ScanModal
          node={scanModal}
          onClose={() => setScanModal(null)}
          onStart={profile => { setScanModal(null); handleScanNode(scanModal, profile) }}
        />
      )}

      {importOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6 w-96 shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-white font-semibold">Import Vulnerabilities</h3>
              <button onClick={() => setImportOpen(false)} className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
            </div>
            <p className="text-xs text-slate-500 mb-4">Upload a JSON file containing vulnerability data for a network node.</p>
            <div className="mb-4 p-3 bg-cyber-bg border border-cyber-border rounded-lg">
              <p className="text-xs text-slate-400 font-semibold mb-1">Expected format:</p>
              <pre className="text-xs text-slate-500 font-mono">{`{\n  "node_ip": "192.168.1.1",\n  "vulnerabilities": [...]\n}`}</pre>
            </div>
            <div className="flex flex-col gap-3">
              <label className={`flex items-center justify-center gap-2 py-3 rounded-lg border-2 border-dashed border-cyber-border hover:border-cyber-primary/50 cursor-pointer transition-colors ${importing ? 'opacity-50 pointer-events-none' : ''}`}>
                <Upload className="w-4 h-4 text-slate-400" />
                <span className="text-sm text-slate-400">{importing ? 'Importing…' : 'Choose JSON file'}</span>
                <input type="file" accept=".json" className="hidden" onChange={handleImportVulns} />
              </label>
              <button
                onClick={() => {
                  const template = JSON.stringify({ node_ip: '192.168.1.1', vulnerabilities: [{ title: 'Example Vulnerability', severity: 'high', cve_id: 'CVE-2024-0001', port: 80, protocol: 'tcp', service: 'http', description: 'Example description', solution: 'Update the service' }] }, null, 2)
                  const blob = new Blob([template], { type: 'application/json' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url; a.download = 'vuln-import-template.json'; a.click()
                  URL.revokeObjectURL(url)
                }}
                className="text-xs text-cyber-primary hover:text-cyan-300 transition-colors text-center">
                ↓ Download template
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
