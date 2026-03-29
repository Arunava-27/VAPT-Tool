import { useState, useCallback, useRef } from 'react'
import { RefreshCw, Database, Layers, Cpu, HardDrive, Server, Bot, Radio,
  CheckCircle, XCircle, AlertTriangle, Clock, Network, Globe, Container, Cloud, Swords } from 'lucide-react'
import toast from 'react-hot-toast'
import { getServicesHealth } from '../../api/infra'
import type { ServiceHealth, ServicesHealthResponse } from '../../api/infra'
import { usePolling } from '../../hooks/usePolling'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ServiceDrawer from '../../components/infra/ServiceDrawer'

// Per-category fallback icon
const CATEGORY_ICON: Record<string, React.ElementType> = {
  database: Database,
  cache: Layers,
  queue: Radio,
  search: HardDrive,
  storage: HardDrive,
  backend: Bot,
  worker: Cpu,
}

// Per-worker-id icon override
const WORKER_ICON: Record<string, React.ElementType> = {
  'worker-nmap':       Network,
  'worker-zap':        Globe,
  'worker-trivy':      Container,
  'worker-prowler':    Cloud,
  'worker-metasploit': Swords,
}

const CATEGORY_LABEL: Record<string, string> = {
  database: 'Database',
  cache: 'Cache',
  queue: 'Message Queue',
  search: 'Search',
  storage: 'Object Storage',
  backend: 'Backend Service',
  worker: 'Worker',
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'healthy') return <CheckCircle className="w-4 h-4 text-emerald-400" />
  if (status === 'degraded') return <AlertTriangle className="w-4 h-4 text-amber-400" />
  return <XCircle className="w-4 h-4 text-rose-400" />
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    healthy:     'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    degraded:    'bg-amber-500/10  text-amber-400  border-amber-500/30',
    unhealthy:   'bg-rose-500/10   text-rose-400   border-rose-500/30',
    unreachable: 'bg-slate-500/10  text-slate-400  border-slate-500/30',
  }
  const cls = map[status] ?? map.unhealthy
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-xs font-medium ${cls}`}>
      <StatusIcon status={status} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  )
}

function LatencyBadge({ ms }: { ms?: number }) {
  if (ms === undefined) return null
  const color = ms < 50 ? 'text-emerald-400' : ms < 200 ? 'text-amber-400' : 'text-rose-400'
  return <span className={`text-xs font-mono ${color}`}>{ms} ms</span>
}

function ServiceCard({ svc, onClick }: { svc: ServiceHealth; onClick: () => void }) {
  const Icon = WORKER_ICON[svc.id] ?? CATEGORY_ICON[svc.category] ?? Server
  const isHealthy = svc.status === 'healthy'

  return (
    <div
      onClick={onClick}
      className={`bg-cyber-surface border rounded-xl p-4 transition-all cursor-pointer select-none ${
        isHealthy
          ? 'border-cyber-border hover:border-cyber-primary/50 hover:bg-cyber-primary/5'
          : 'border-rose-500/30 bg-rose-500/5 hover:border-rose-500/60'
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2.5">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
            isHealthy ? 'bg-cyber-primary/10 border border-cyber-primary/20' : 'bg-rose-500/10 border border-rose-500/20'
          }`}>
            <Icon className={`w-4 h-4 ${isHealthy ? 'text-cyber-primary' : 'text-rose-400'}`} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white truncate">{svc.name}</p>
            <p className="text-xs text-slate-500">{svc.description ?? (CATEGORY_LABEL[svc.category] ?? svc.category)}</p>
          </div>
        </div>
        <StatusBadge status={svc.status} />
      </div>

      <div className="space-y-1.5 text-xs border-t border-cyber-border pt-3">
        {svc.latency_ms !== undefined && (
          <div className="flex justify-between items-center">
            <span className="text-slate-500">Latency</span>
            <LatencyBadge ms={svc.latency_ms} />
          </div>
        )}
        {svc.used_memory && (
          <div className="flex justify-between items-center">
            <span className="text-slate-500">Memory</span>
            <span className="text-slate-300 font-mono">{svc.used_memory}</span>
          </div>
        )}
        {svc.cluster_status && (
          <div className="flex justify-between items-center">
            <span className="text-slate-500">Cluster</span>
            <span className="text-slate-300">{svc.cluster_status} · {svc.nodes} node{svc.nodes !== 1 ? 's' : ''}</span>
          </div>
        )}
        {svc.concurrency !== undefined && (
          <div className="flex justify-between items-center">
            <span className="text-slate-500">Concurrency</span>
            <span className="text-slate-300">{svc.concurrency}</span>
          </div>
        )}
        {svc.active_model && (
          <div className="flex justify-between items-center">
            <span className="text-slate-500">Model</span>
            <span className="text-cyber-primary font-mono truncate max-w-[140px]">{svc.active_model}</span>
          </div>
        )}
        {svc.active_provider && (
          <div className="flex justify-between items-center">
            <span className="text-slate-500">Provider</span>
            <span className="text-slate-300 capitalize">{svc.active_provider}</span>
          </div>
        )}
        {svc.tasks_processed && Object.keys(svc.tasks_processed).length > 0 && (
          <div className="flex justify-between items-center">
            <span className="text-slate-500">Tasks done</span>
            <span className="text-slate-300 font-mono">
              {Object.values(svc.tasks_processed).reduce((a, b) => a + b, 0)}
            </span>
          </div>
        )}
        {svc.error && (
          <p className="text-rose-400 font-mono break-all pt-2 border-t border-rose-500/20 leading-relaxed">
            {svc.error}
          </p>
        )}
      </div>
    </div>
  )
}

function OverallBanner({ data }: { data: ServicesHealthResponse }) {
  const { overall, healthy, total, duration_ms } = data
  const pct = Math.round((healthy / total) * 100)

  const theme = {
    healthy:   { bar: 'bg-emerald-400', text: 'text-emerald-400', border: 'border-emerald-500/20', bg: 'bg-emerald-500/5' },
    degraded:  { bar: 'bg-amber-400',   text: 'text-amber-400',   border: 'border-amber-500/20',   bg: 'bg-amber-500/5' },
    unhealthy: { bar: 'bg-rose-400',    text: 'text-rose-400',    border: 'border-rose-500/20',     bg: 'bg-rose-500/5' },
  }[overall] ?? { bar: 'bg-rose-400', text: 'text-rose-400', border: 'border-rose-500/20', bg: 'bg-rose-500/5' }

  return (
    <div className={`border rounded-xl p-5 ${theme.border} ${theme.bg}`}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Platform Status</p>
          <p className={`text-2xl font-bold ${theme.text}`}>
            {overall.charAt(0).toUpperCase() + overall.slice(1)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-3xl font-bold text-white">
            {healthy}<span className="text-slate-500 text-xl">/{total}</span>
          </p>
          <p className="text-xs text-slate-500">services healthy</p>
        </div>
      </div>
      <div className="h-2 bg-cyber-border rounded-full overflow-hidden mb-2">
        <div
          className={`h-full ${theme.bar} rounded-full transition-all duration-700`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-slate-600">Checked in {duration_ms} ms</p>
    </div>
  )
}

const ORDERED_CATEGORIES = ['database', 'cache', 'queue', 'search', 'storage', 'backend', 'worker'] as const

export default function InfraPage() {
  const [data, setData] = useState<ServicesHealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastChecked, setLastChecked] = useState<Date | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [selectedSvc, setSelectedSvc] = useState<ServiceHealth | null>(null)

  const hasData = useRef(false)

  const fetchHealth = useCallback(async () => {
    try {
      const res = await getServicesHealth()
      setData(res.data)
      hasData.current = true
      setLastChecked(new Date())
    } catch (err) {
      console.error('Services health check failed:', err)
      if (!hasData.current) toast.error('Failed to fetch service health')
    } finally {
      setLoading(false)
    }
  }, [])

  usePolling(fetchHealth, 15_000, autoRefresh)

  const grouped = data
    ? ORDERED_CATEGORIES.reduce<Record<string, ServiceHealth[]>>((acc, cat) => {
        const svcs = data.services.filter((s) => s.category === cat)
        if (svcs.length) acc[cat] = svcs
        return acc
      }, {})
    : {}

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Infrastructure Monitor</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {lastChecked
              ? `Last checked ${lastChecked.toLocaleTimeString()}`
              : 'Fetching service status…'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoRefresh(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border text-xs font-medium transition-colors ${
              autoRefresh
                ? 'border-cyber-primary/30 text-cyber-primary bg-cyber-primary/10'
                : 'border-cyber-border text-slate-400 hover:text-white'
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            {autoRefresh ? 'Auto (15s)' : 'Manual'}
          </button>
          <button
            onClick={fetchHealth}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cyber-border text-xs font-medium text-slate-400 hover:text-white hover:border-cyber-primary transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Loading */}
      {loading && !data && (
        <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>
      )}

      {/* Overall banner */}
      {data && <OverallBanner data={data} />}

      {/* Service groups */}
      {Object.entries(grouped).map(([cat, svcs]) => (
        <section key={cat}>
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
            {(() => { const I = CATEGORY_ICON[cat] ?? Server; return <I className="w-3.5 h-3.5" /> })()}
            {cat === 'worker' ? 'Security Workers' : (CATEGORY_LABEL[cat] ?? cat) + 's'}
            <span className="ml-auto text-slate-600 font-normal normal-case">
              {svcs.filter(s => s.status === 'healthy').length}/{svcs.length} healthy
            </span>
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {svcs.map((svc) => (
              <ServiceCard key={svc.id} svc={svc} onClick={() => setSelectedSvc(svc)} />
            ))}
          </div>
        </section>
      ))}

      <ServiceDrawer svc={selectedSvc} onClose={() => setSelectedSvc(null)} />
    </div>
  )
}
