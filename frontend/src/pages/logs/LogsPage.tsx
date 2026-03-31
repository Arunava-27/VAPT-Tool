import { useCallback, useEffect, useRef, useState } from 'react'
import { RefreshCw, Search, X, ChevronDown, FileText, Shield, Monitor, Circle } from 'lucide-react'
import clsx from 'clsx'
import { useSearchParams } from 'react-router-dom'
import {
  listContainers,
  getContainerLogs,
  getAuditLogs,
  getWorkerLogs,
  type ContainerInfo,
  type LogLine,
  type AuditLogEntry,
  type WorkerLogLine,
} from '../../api/logs'
import { getNativeWorkers, type NativeWorkerStatus } from '../../api/infra'

// ── helpers ──────────────────────────────────────────────────────────────────

type Level = 'error' | 'warn' | 'info' | 'debug' | 'success' | 'none'

function detectLevel(text: string): Level {
  const upper = text.toUpperCase()
  if (/\b(ERROR|CRITICAL|FATAL|EXCEPTION|TRACEBACK|PANIC)\b/.test(upper)) return 'error'
  if (/\b(WARN|WARNING)\b/.test(upper)) return 'warn'
  if (/\b(DEBUG)\b/.test(upper)) return 'debug'
  if (/\b(SUCCESS|SUCCESSFULLY|HEALTHY|READY|STARTED|CONNECTED|OK)\b/.test(upper)) return 'success'
  if (/\b(INFO)\b/.test(upper)) return 'info'
  return 'none'
}

function parseTimestamp(line: string): { ts: string; message: string } {
  const m = line.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z?)\s(.*)$/)
  if (m) {
    const d = new Date(m[1])
    const ts = `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}.${d.getMilliseconds().toString().padStart(3, '0')}`
    return { ts, message: m[2] }
  }
  return { ts: '', message: line }
}

const LEVEL_BADGE: Record<Level, string | null> = {
  error:   'bg-rose-500/20 text-rose-400 border border-rose-500/30',
  warn:    'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  debug:   'bg-slate-700/40 text-slate-500 border border-slate-600/30',
  success: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  info:    'bg-sky-500/20 text-sky-400 border border-sky-500/30',
  none:    null,
}

const LEVEL_TEXT: Record<Level, string> = {
  error:   'text-rose-300',
  warn:    'text-amber-300',
  debug:   'text-slate-500',
  success: 'text-emerald-300',
  info:    'text-slate-300',
  none:    'text-slate-300',
}

const CATEGORY_LABELS: Record<ContainerInfo['category'], string> = {
  backend:  'Backend',
  workers:  'Workers',
  data:     'Data Layer',
  frontend: 'Frontend',
  init:     'Init',
  other:    'Other',
}

const CATEGORY_ORDER: ContainerInfo['category'][] = ['backend', 'workers', 'data', 'frontend', 'init', 'other']

const TAIL_OPTIONS = [100, 300, 500, 1000, 2000]

type StreamFilter = 'all' | 'stdout' | 'stderr'
type LevelFilter = 'all' | Level

// ── component ────────────────────────────────────────────────────────────────

export default function LogsPage() {
  const [searchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState<'containers' | 'workers' | 'audit'>(() => {
    return searchParams.get('worker') ? 'workers' : 'containers'
  })

  // ── Container logs state ──────────────────────────────────────────────────
  const [containers, setContainers] = useState<ContainerInfo[]>([])
  const [containersLoading, setContainersLoading] = useState(true)
  const [containersError, setContainersError] = useState<string | null>(null)

  const [selected, setSelected] = useState<ContainerInfo | null>(null)
  const [lines, setLines] = useState<LogLine[]>([])
  const [logsLoading, setLogsLoading] = useState(false)
  const [logsError, setLogsError] = useState<string | null>(null)

  const [tail, setTail] = useState(300)
  const [streamFilter, setStreamFilter] = useState<StreamFilter>('all')
  const [levelFilter, setLevelFilter] = useState<LevelFilter>('all')
  const [search, setSearch] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const userScrolledUp = useRef(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Audit log state ────────────────────────────────────────────────────────
  const [auditEntries, setAuditEntries] = useState<AuditLogEntry[]>([])
  const [auditTotal, setAuditTotal] = useState(0)
  const [auditPage, setAuditPage] = useState(1)
  const [auditLoading, setAuditLoading] = useState(false)
  const [auditError, setAuditError] = useState<string | null>(null)
  const [auditSearch, setAuditSearch] = useState('')
  const [auditSearchInput, setAuditSearchInput] = useState('')

  // ── Worker log state ───────────────────────────────────────────────────────
  const [nativeWorkers, setNativeWorkers] = useState<NativeWorkerStatus[]>([])
  const [workersLoading, setWorkersLoading] = useState(false)
  const [selectedWorker, setSelectedWorker] = useState<string | null>(() => searchParams.get('worker'))
  const [workerLines, setWorkerLines] = useState<WorkerLogLine[]>([])
  const [workerLogsLoading, setWorkerLogsLoading] = useState(false)
  const [workerLogsError, setWorkerLogsError] = useState<string | null>(null)
  const [workerTail, setWorkerTail] = useState(200)
  const [workerStream, setWorkerStream] = useState<'stdout' | 'stderr' | 'all'>('all')
  const [workerSearch, setWorkerSearch] = useState('')
  const [workerAutoRefresh, setWorkerAutoRefresh] = useState(true)
  const workerScrollRef = useRef<HTMLDivElement>(null)
  const workerScrolledUp = useRef(false)
  const workerIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchAuditLogs = useCallback(async (page: number, action?: string) => {
    setAuditLoading(true)
    setAuditError(null)
    try {
      const r = await getAuditLogs(page, 50, action)
      setAuditEntries(r.data.entries)
      setAuditTotal(r.data.total)
      setAuditPage(page)
    } catch {
      setAuditError('Failed to load audit logs')
    } finally {
      setAuditLoading(false)
    }
  }, [])

  useEffect(() => {
    if (activeTab === 'audit') fetchAuditLogs(1)
  }, [activeTab, fetchAuditLogs])

  // ── Worker log fetch ───────────────────────────────────────────────────────

  const fetchNativeWorkers = useCallback(async () => {
    setWorkersLoading(true)
    try {
      const r = await getNativeWorkers()
      setNativeWorkers(r.data)
    } catch {
      // silently fail — host agent may not be running
    } finally {
      setWorkersLoading(false)
    }
  }, [])

  const fetchWorkerLogs = useCallback(async (name: string, tailN: number, stream: 'stdout' | 'stderr' | 'all') => {
    setWorkerLogsLoading(true)
    setWorkerLogsError(null)
    try {
      const r = await getWorkerLogs(name, tailN, stream)
      setWorkerLines(r.data.lines)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      setWorkerLogsError(err?.response?.data?.detail ?? 'Failed to fetch worker logs')
    } finally {
      setWorkerLogsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (activeTab === 'workers') {
      fetchNativeWorkers()
    }
  }, [activeTab, fetchNativeWorkers])

  useEffect(() => {
    if (activeTab === 'workers' && selectedWorker) {
      fetchWorkerLogs(selectedWorker, workerTail, workerStream)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedWorker, activeTab])

  useEffect(() => {
    if (!workerScrolledUp.current && workerScrollRef.current) {
      workerScrollRef.current.scrollTop = workerScrollRef.current.scrollHeight
    }
  }, [workerLines])

  useEffect(() => {
    if (workerIntervalRef.current) clearInterval(workerIntervalRef.current)
    if (workerAutoRefresh && selectedWorker && activeTab === 'workers') {
      workerIntervalRef.current = setInterval(() => {
        fetchWorkerLogs(selectedWorker, workerTail, workerStream)
        fetchNativeWorkers()
      }, 3000)
    }
    return () => { if (workerIntervalRef.current) clearInterval(workerIntervalRef.current) }
  }, [workerAutoRefresh, selectedWorker, workerTail, workerStream, activeTab, fetchWorkerLogs, fetchNativeWorkers])

  // Services that run natively — their Docker containers are always exited and not useful here
  const NATIVE_ONLY_CONTAINERS = new Set(['vapt-api-gateway', 'vapt-frontend'])

  useEffect(() => {
    setContainersLoading(true)
    listContainers()
      .then(r => setContainers(r.data.filter(c => !NATIVE_ONLY_CONTAINERS.has(c.name))))
      .catch(e => setContainersError(e?.response?.data?.detail ?? 'Failed to load containers'))
      .finally(() => setContainersLoading(false))
  }, [])

  // ── fetch logs ─────────────────────────────────────────────────────────────

  const fetchLogs = useCallback(async (container: ContainerInfo, tailN: number) => {
    setLogsLoading(true)
    setLogsError(null)
    try {
      const r = await getContainerLogs(container.id, tailN)
      setLines(r.data.lines)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      setLogsError(err?.response?.data?.detail ?? 'Failed to fetch logs')
    } finally {
      setLogsLoading(false)
    }
  }, [])

  // ── select container ───────────────────────────────────────────────────────

  const handleSelect = useCallback((c: ContainerInfo) => {
    setSelected(c)
    setLines([])
    setLogsError(null)
    userScrolledUp.current = false
    fetchLogs(c, tail)
  }, [fetchLogs, tail])

  // ── tail change ────────────────────────────────────────────────────────────

  const handleTailChange = (t: number) => {
    setTail(t)
    if (selected) fetchLogs(selected, t)
  }

  // ── auto-scroll ────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!userScrolledUp.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [lines])

  const handleScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    userScrolledUp.current = scrollHeight - scrollTop - clientHeight > 80
  }

  // ── auto-refresh ───────────────────────────────────────────────────────────

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current)
    if (autoRefresh && selected) {
      intervalRef.current = setInterval(() => fetchLogs(selected, tail), 5000)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [autoRefresh, selected, tail, fetchLogs])

  // ── filtered lines ─────────────────────────────────────────────────────────

  const filtered = lines.filter(l => {
    if (streamFilter !== 'all' && l.stream !== streamFilter) return false
    const level = detectLevel(l.text)
    if (levelFilter !== 'all' && level !== levelFilter) return false
    if (search && !l.text.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  // ── container groups ───────────────────────────────────────────────────────

  const groups = CATEGORY_ORDER.map(cat => ({
    cat,
    items: containers.filter(c => c.category === cat),
  })).filter(g => g.items.length > 0)

  // ── status dot ────────────────────────────────────────────────────────────

  function StatusDot({ state, category }: { state: string; category?: string }) {
    const color =
      state === 'running'  ? 'bg-emerald-400' :
      state === 'exited' && category === 'init' ? 'bg-slate-500' :
      state === 'exited'   ? 'bg-slate-400' :
                             'bg-amber-400'
    return <span className={clsx('w-2 h-2 rounded-full flex-shrink-0', color)} />
  }

  // ── state badge ───────────────────────────────────────────────────────────

  function StateBadge({ state, category }: { state: string; category?: string }) {
    const isInit = category === 'init'
    const label = state === 'exited' && isInit ? 'completed' : state
    const cls =
      state === 'running' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' :
      state === 'exited' && isInit ? 'bg-slate-700/40 text-slate-500 border-slate-600/30' :
      state === 'exited'  ? 'bg-slate-600/30 text-slate-400 border-slate-500/30' :
                            'bg-amber-500/20 text-amber-400 border-amber-500/30'
    return (
      <span className={clsx('px-2 py-0.5 rounded text-xs font-mono border', cls)}>
        {label}
      </span>
    )
  }

  // ── render ─────────────────────────────────────────────────────────────────

  const ACTION_COLORS: Record<string, string> = {
    user_login: 'bg-sky-500/20 text-sky-300 border-sky-500/30',
    node_scan_started: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    node_scan_completed: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    network_discovery_started: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
    network_discovery_completed: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  }

  function timeAgo(iso: string) {
    const diff = Date.now() - new Date(iso).getTime()
    if (diff < 60000) return `${Math.floor(diff / 1000)}s ago`
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
    return new Date(iso).toLocaleDateString()
  }

  return (
    <div className="flex flex-col h-full bg-cyber-bg text-white overflow-hidden">
      {/* ── Tab bar ── */}
      <div className="flex-shrink-0 border-b border-cyber-border bg-cyber-surface px-4 flex items-center gap-1 pt-2">
        <button
          onClick={() => setActiveTab('containers')}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t transition-colors border-b-2',
            activeTab === 'containers'
              ? 'text-cyber-primary border-cyber-primary'
              : 'text-slate-400 border-transparent hover:text-white'
          )}>
          <FileText className="w-3.5 h-3.5" /> Container Logs
        </button>
        <button
          onClick={() => setActiveTab('workers')}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t transition-colors border-b-2',
            activeTab === 'workers'
              ? 'text-cyber-primary border-cyber-primary'
              : 'text-slate-400 border-transparent hover:text-white'
          )}>
          <Monitor className="w-3.5 h-3.5" /> Worker Logs
          <span className="ml-1 px-1.5 py-0.5 rounded text-[10px] bg-cyber-primary/20 border border-cyber-primary/30 text-cyber-primary">
            Host
          </span>
        </button>
        <button
          onClick={() => setActiveTab('audit')}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t transition-colors border-b-2',
            activeTab === 'audit'
              ? 'text-cyber-primary border-cyber-primary'
              : 'text-slate-400 border-transparent hover:text-white'
          )}>
          <Shield className="w-3.5 h-3.5" /> Audit Logs
        </button>
      </div>

      {activeTab === 'workers' ? (
        /* ── Worker Logs panel ── */
        <div className="flex flex-1 bg-cyber-bg text-white overflow-hidden">
          {/* Left panel: worker list */}
          <aside className="w-64 flex-shrink-0 border-r border-cyber-border bg-cyber-surface flex flex-col overflow-hidden">
            <div className="px-4 py-3 border-b border-cyber-border flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-200">Native Workers</h2>
              <button onClick={fetchNativeWorkers} disabled={workersLoading}
                className="text-slate-500 hover:text-white transition-colors">
                <RefreshCw className={clsx('w-3.5 h-3.5', workersLoading && 'animate-spin')} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto py-2">
              {workersLoading && nativeWorkers.length === 0 && (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="w-5 h-5 animate-spin text-cyber-primary" />
                </div>
              )}
              {!workersLoading && nativeWorkers.length === 0 && (
                <p className="px-4 py-3 text-xs text-slate-600">Host agent not reachable. Start it with host-agent/start.bat</p>
              )}
              {nativeWorkers.map(w => (
                <button
                  key={w.name}
                  onClick={() => {
                    setSelectedWorker(w.name)
                    setWorkerLines([])
                    workerScrolledUp.current = false
                    fetchWorkerLogs(w.name, workerTail, workerStream)
                  }}
                  className={clsx(
                    'w-full flex items-center gap-2 px-4 py-2.5 text-left transition-colors',
                    selectedWorker === w.name
                      ? 'bg-cyber-primary/10 border-l-2 border-cyber-primary'
                      : 'border-l-2 border-transparent hover:bg-cyber-border'
                  )}
                >
                  <Circle className={clsx('w-2 h-2 flex-shrink-0 fill-current',
                    w.status === 'running' ? 'text-emerald-400' : 'text-rose-400'
                  )} />
                  <div className="min-w-0 flex-1">
                    <p className={clsx('text-xs font-medium truncate',
                      selectedWorker === w.name ? 'text-cyber-primary' : 'text-slate-300'
                    )}>{w.label}</p>
                    <p className="text-[10px] text-slate-600 truncate">
                      {w.status === 'running' ? `PID ${w.pid}` : w.status}
                    </p>
                  </div>
                  {w.stats?.memory_mb && (
                    <span className="text-[10px] text-slate-600 font-mono flex-shrink-0">{w.stats.memory_mb}MB</span>
                  )}
                </button>
              ))}
            </div>
            {/* Worker auto-refresh toggle */}
            <div className="border-t border-cyber-border p-3">
              <button
                onClick={() => setWorkerAutoRefresh(v => !v)}
                className={clsx(
                  'w-full flex items-center justify-center gap-1.5 py-1.5 rounded border text-xs transition-colors',
                  workerAutoRefresh
                    ? 'border-cyber-primary text-cyber-primary bg-cyber-primary/10'
                    : 'border-cyber-border text-slate-400 hover:text-white'
                )}
              >
                <RefreshCw className={clsx('w-3 h-3', workerAutoRefresh && 'animate-spin')} />
                {workerAutoRefresh ? 'Auto (3s)' : 'Manual refresh'}
              </button>
            </div>
          </aside>

          {/* Right panel: worker log viewer */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {!selectedWorker ? (
              <div className="flex-1 flex items-center justify-center text-slate-600">
                <div className="text-center space-y-2">
                  <Monitor className="w-8 h-8 mx-auto opacity-30" />
                  <p className="text-sm">Select a worker to view its logs</p>
                </div>
              </div>
            ) : (
              <>
                {/* Controls */}
                <div className="flex-shrink-0 border-b border-cyber-border bg-cyber-surface px-4 py-3 flex items-center gap-3 flex-wrap">
                  <div className="flex items-center gap-2 flex-1">
                    <h3 className="text-sm font-semibold text-white font-mono">
                      {nativeWorkers.find(w => w.name === selectedWorker)?.label ?? selectedWorker}
                    </h3>
                    {(() => {
                      const w = nativeWorkers.find(w => w.name === selectedWorker)
                      if (!w) return null
                      return (
                        <span className={clsx('text-xs px-1.5 py-0.5 rounded border font-mono',
                          w.status === 'running'
                            ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                            : 'bg-rose-500/20 text-rose-400 border-rose-500/30'
                        )}>
                          {w.status}
                        </span>
                      )
                    })()}
                  </div>
                  {/* Tail selector */}
                  <div className="relative">
                    <select
                      value={workerTail}
                      onChange={e => {
                        const t = Number(e.target.value)
                        setWorkerTail(t)
                        if (selectedWorker) fetchWorkerLogs(selectedWorker, t, workerStream)
                      }}
                      className="appearance-none bg-cyber-bg border border-cyber-border text-slate-300 text-xs rounded px-2 py-1 pr-6 focus:outline-none focus:border-cyber-primary cursor-pointer"
                    >
                      {TAIL_OPTIONS.map(t => <option key={t} value={t}>{t} lines</option>)}
                    </select>
                    <ChevronDown className="w-3 h-3 text-slate-500 absolute right-1.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                  </div>
                  {/* Stream filter */}
                  <div className="flex rounded border border-cyber-border overflow-hidden text-xs">
                    {(['all', 'stdout', 'stderr'] as const).map(s => (
                      <button key={s} onClick={() => {
                        setWorkerStream(s)
                        if (selectedWorker) fetchWorkerLogs(selectedWorker, workerTail, s)
                      }}
                        className={clsx('px-2 py-1 transition-colors',
                          workerStream === s
                            ? 'bg-cyber-primary text-cyber-bg font-semibold'
                            : 'text-slate-400 hover:text-white hover:bg-cyber-border'
                        )}
                      >{s}</button>
                    ))}
                  </div>
                  {/* Search */}
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      placeholder="Filter…"
                      value={workerSearch}
                      onChange={e => setWorkerSearch(e.target.value)}
                      className="bg-cyber-bg border border-cyber-border rounded text-xs text-slate-300 placeholder-slate-600 pl-7 pr-6 py-1 w-40 focus:outline-none focus:border-cyber-primary"
                    />
                    {workerSearch && (
                      <button onClick={() => setWorkerSearch('')} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                        <X className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                  {/* Manual refresh */}
                  <button
                    onClick={() => selectedWorker && fetchWorkerLogs(selectedWorker, workerTail, workerStream)}
                    disabled={workerLogsLoading}
                    className="flex items-center gap-1 px-2 py-1 rounded border border-cyber-border text-xs text-slate-400 hover:text-white hover:bg-cyber-border disabled:opacity-50"
                  >
                    <RefreshCw className={clsx('w-3 h-3', workerLogsLoading && 'animate-spin')} />
                  </button>
                </div>

                {/* Log area */}
                <div
                  ref={workerScrollRef}
                  onScroll={() => {
                    if (!workerScrollRef.current) return
                    const { scrollTop, scrollHeight, clientHeight } = workerScrollRef.current
                    workerScrolledUp.current = scrollHeight - scrollTop - clientHeight > 80
                  }}
                  className="flex-1 overflow-y-auto font-mono text-xs bg-[#070c1a] p-3 space-y-0.5"
                >
                  {workerLogsLoading && workerLines.length === 0 && (
                    <div className="flex items-center justify-center py-12">
                      <RefreshCw className="w-5 h-5 animate-spin text-cyber-primary" />
                    </div>
                  )}
                  {workerLogsError && (
                    <p className="text-rose-400 py-4 text-center">{workerLogsError}</p>
                  )}
                  {!workerLogsLoading && !workerLogsError && workerLines.length === 0 && (
                    <p className="text-slate-600 py-4 text-center">No log lines found. The worker may not have run any tasks yet.</p>
                  )}
                  {workerLines
                    .filter(l => !workerSearch || l.text.toLowerCase().includes(workerSearch.toLowerCase()))
                    .map((l, i) => {
                      const { ts, message } = parseTimestamp(l.text)
                      const level = detectLevel(l.text)
                      const badgeCls = LEVEL_BADGE[level]
                      const textCls = LEVEL_TEXT[level]
                      return (
                        <div key={i} className="flex items-start gap-2 py-0.5 hover:bg-white/5 rounded px-1">
                          {ts && <span className="text-slate-600 flex-shrink-0 select-none w-[92px]">{ts}</span>}
                          {badgeCls && (
                            <span className={clsx('flex-shrink-0 px-1.5 py-0.5 rounded text-[10px] leading-none', badgeCls)}>
                              {level}
                            </span>
                          )}
                          {l.stream === 'stderr' && (
                            <span className="flex-shrink-0 px-1 py-0.5 rounded text-[10px] leading-none bg-rose-900/40 text-rose-400 border border-rose-700/30">
                              err
                            </span>
                          )}
                          <span className={clsx('break-all', textCls)}>{message || l.text}</span>
                        </div>
                      )
                    })}
                </div>

                {/* Footer */}
                <div className="flex-shrink-0 border-t border-cyber-border bg-cyber-surface px-4 py-1.5 flex items-center justify-between text-[10px] text-slate-600">
                  <span>{workerLines.filter(l => !workerSearch || l.text.toLowerCase().includes(workerSearch.toLowerCase())).length} / {workerLines.length} lines</span>
                  <span>{selectedWorker} worker · host machine</span>
                </div>
              </>
            )}
          </div>
        </div>
      ) : activeTab === 'audit' ? (
        /* ── Audit Logs panel ── */
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Controls */}
          <div className="flex-shrink-0 border-b border-cyber-border bg-cyber-surface px-4 py-3 flex items-center gap-3 flex-wrap">
            <div className="relative flex-1 min-w-[200px] max-w-xs">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Filter by action…"
                value={auditSearchInput}
                onChange={e => setAuditSearchInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') { setAuditSearch(auditSearchInput); fetchAuditLogs(1, auditSearchInput || undefined) }
                }}
                className="w-full bg-cyber-bg border border-cyber-border rounded text-xs text-slate-300 placeholder-slate-600 pl-7 pr-7 py-1.5 focus:outline-none focus:border-cyber-primary"
              />
              {auditSearchInput && (
                <button onClick={() => { setAuditSearchInput(''); setAuditSearch(''); fetchAuditLogs(1) }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
            <button
              onClick={() => fetchAuditLogs(1, auditSearch || undefined)}
              disabled={auditLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-cyber-border text-xs text-slate-400 hover:text-white hover:bg-cyber-border transition-colors disabled:opacity-50">
              <RefreshCw className={clsx('w-3 h-3', auditLoading && 'animate-spin')} />
              Refresh
            </button>
            <span className="text-xs text-slate-500 ml-auto">{auditTotal} entries</span>
          </div>

          {/* Table */}
          <div className="flex-1 overflow-y-auto">
            {auditLoading && auditEntries.length === 0 && (
              <div className="flex items-center justify-center py-12">
                <RefreshCw className="w-5 h-5 animate-spin text-cyber-primary" />
              </div>
            )}
            {auditError && <p className="text-rose-400 text-sm text-center py-8">{auditError}</p>}
            {!auditLoading && !auditError && auditEntries.length === 0 && (
              <p className="text-slate-600 text-sm text-center py-12">No audit log entries yet. Actions like logins and scans will appear here.</p>
            )}
            {auditEntries.length > 0 && (
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-cyber-surface border-b border-cyber-border">
                  <tr>
                    <th className="text-left px-4 py-2.5 text-slate-500 font-medium w-32">Time</th>
                    <th className="text-left px-4 py-2.5 text-slate-500 font-medium w-48">Action</th>
                    <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Resource</th>
                    <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Details</th>
                    <th className="text-left px-4 py-2.5 text-slate-500 font-medium w-40">User</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-cyber-border/40">
                  {auditEntries.map(entry => (
                    <tr key={entry.id} className="hover:bg-cyber-border/20 transition-colors">
                      <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap" title={entry.created_at}>
                        {timeAgo(entry.created_at)}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={clsx(
                          'px-2 py-0.5 rounded border text-[11px] font-mono font-medium',
                          ACTION_COLORS[entry.action] ?? 'bg-slate-700/40 text-slate-300 border-slate-600/30'
                        )}>
                          {entry.action}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-slate-400">
                        {entry.resource_type && (
                          <span className="font-mono">{entry.resource_type}
                            {entry.resource_id && <span className="text-slate-600"> #{entry.resource_id.slice(0, 8)}</span>}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-slate-400 max-w-xs truncate">
                        {Object.entries(entry.details ?? {})
                          .filter(([k]) => k !== 'celery_task_id')
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(' · ')}
                      </td>
                      <td className="px-4 py-2.5 text-slate-400 truncate">{entry.user_email}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Pagination */}
          {auditTotal > 50 && (
            <div className="flex-shrink-0 border-t border-cyber-border bg-cyber-surface px-4 py-2 flex items-center gap-2 justify-end text-xs text-slate-400">
              <button disabled={auditPage <= 1} onClick={() => fetchAuditLogs(auditPage - 1, auditSearch || undefined)}
                className="px-2 py-1 rounded border border-cyber-border hover:bg-cyber-border disabled:opacity-40">Prev</button>
              <span>Page {auditPage} of {Math.ceil(auditTotal / 50)}</span>
              <button disabled={auditPage >= Math.ceil(auditTotal / 50)} onClick={() => fetchAuditLogs(auditPage + 1, auditSearch || undefined)}
                className="px-2 py-1 rounded border border-cyber-border hover:bg-cyber-border disabled:opacity-40">Next</button>
            </div>
          )}
        </div>
      ) : (
      <div className="flex flex-1 bg-cyber-bg text-white overflow-hidden">
      {/* ── Left panel: container list ── */}
      <aside className="w-64 flex-shrink-0 border-r border-cyber-border bg-cyber-surface flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-cyber-border">
          <h2 className="text-sm font-semibold text-slate-200">Containers</h2>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          {containersLoading && (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="w-5 h-5 animate-spin text-cyber-primary" />
            </div>
          )}
          {containersError && (
            <p className="px-4 py-3 text-xs text-rose-400">{containersError}</p>
          )}
          {!containersLoading && !containersError && groups.map(({ cat, items }) => (
            <div key={cat} className="mb-2">
              <p className="px-4 py-1 text-[10px] font-semibold uppercase tracking-widest text-slate-600">
                {CATEGORY_LABELS[cat]}
              </p>
              {items.map(c => (
                <button
                  key={c.id}
                  onClick={() => handleSelect(c)}
                  className={clsx(
                    'w-full flex items-center gap-2 px-4 py-2 text-left text-xs transition-colors',
                    selected?.id === c.id
                      ? 'bg-cyber-primary/10 border-l-2 border-cyber-primary text-cyber-primary'
                      : 'border-l-2 border-transparent text-slate-400 hover:text-slate-200 hover:bg-cyber-border'
                  )}
                >
                  <StatusDot state={c.state} category={c.category} />
                  <span className="truncate font-mono">
                    {c.name.replace(/^vapt-/, '')}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </div>
      </aside>

      {/* ── Right panel: log viewer ── */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!selected ? (
          <div className="flex-1 flex items-center justify-center text-slate-600">
            <p className="text-sm">Select a container to view its logs</p>
          </div>
        ) : (
          <>
            {/* Controls bar */}
            <div className="flex-shrink-0 border-b border-cyber-border bg-cyber-surface px-4 py-3 space-y-2">
              {/* Row 1: title + state + tail + stream + auto-refresh + refresh */}
              <div className="flex items-center gap-3 flex-wrap">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <h3 className="text-sm font-semibold text-white truncate font-mono">
                    {selected.name}
                  </h3>
                  <StateBadge state={selected.state} category={selected.category} />
                </div>

                {/* Tail selector */}
                <div className="relative">
                  <select
                    value={tail}
                    onChange={e => handleTailChange(Number(e.target.value))}
                    className="appearance-none bg-cyber-bg border border-cyber-border text-slate-300 text-xs rounded px-2 py-1 pr-6 focus:outline-none focus:border-cyber-primary cursor-pointer"
                  >
                    {TAIL_OPTIONS.map(t => (
                      <option key={t} value={t}>{t} lines</option>
                    ))}
                  </select>
                  <ChevronDown className="w-3 h-3 text-slate-500 absolute right-1.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                </div>

                {/* Stream filter */}
                <div className="flex rounded border border-cyber-border overflow-hidden text-xs">
                  {(['all', 'stdout', 'stderr'] as StreamFilter[]).map(s => (
                    <button
                      key={s}
                      onClick={() => setStreamFilter(s)}
                      className={clsx(
                        'px-2 py-1 transition-colors',
                        streamFilter === s
                          ? 'bg-cyber-primary text-cyber-bg font-semibold'
                          : 'text-slate-400 hover:text-white hover:bg-cyber-border'
                      )}
                    >
                      {s}
                    </button>
                  ))}
                </div>

                {/* Auto-refresh toggle */}
                <button
                  onClick={() => setAutoRefresh(v => !v)}
                  title={autoRefresh ? 'Stop auto-refresh' : 'Auto-refresh every 5s'}
                  className={clsx(
                    'flex items-center gap-1.5 px-2 py-1 rounded border text-xs transition-colors',
                    autoRefresh
                      ? 'border-cyber-primary text-cyber-primary bg-cyber-primary/10'
                      : 'border-cyber-border text-slate-400 hover:text-white hover:bg-cyber-border'
                  )}
                >
                  <RefreshCw className={clsx('w-3 h-3', autoRefresh && 'animate-spin')} />
                  <span>Auto</span>
                </button>

                {/* Manual refresh */}
                <button
                  onClick={() => fetchLogs(selected, tail)}
                  disabled={logsLoading}
                  className="flex items-center gap-1.5 px-2 py-1 rounded border border-cyber-border text-xs text-slate-400 hover:text-white hover:bg-cyber-border transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={clsx('w-3 h-3', logsLoading && 'animate-spin')} />
                  <span>Refresh</span>
                </button>
              </div>

              {/* Row 2: search + level filters */}
              <div className="flex items-center gap-3 flex-wrap">
                {/* Search */}
                <div className="relative flex-1 min-w-[160px] max-w-xs">
                  <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    placeholder="Filter logs…"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    className="w-full bg-cyber-bg border border-cyber-border rounded text-xs text-slate-300 placeholder-slate-600 pl-7 pr-7 py-1 focus:outline-none focus:border-cyber-primary"
                  />
                  {search && (
                    <button
                      onClick={() => setSearch('')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>

                {/* Level filter */}
                <div className="flex rounded border border-cyber-border overflow-hidden text-xs">
                  {(['all', 'error', 'warn', 'info', 'debug', 'success'] as LevelFilter[]).map(lv => (
                    <button
                      key={lv}
                      onClick={() => setLevelFilter(lv)}
                      className={clsx(
                        'px-2 py-1 capitalize transition-colors',
                        levelFilter === lv
                          ? 'bg-cyber-primary text-cyber-bg font-semibold'
                          : 'text-slate-400 hover:text-white hover:bg-cyber-border'
                      )}
                    >
                      {lv}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Log area */}
            <div
              ref={scrollRef}
              onScroll={handleScroll}
              className="flex-1 overflow-y-auto font-mono text-xs bg-[#070c1a] p-3 space-y-0.5"
            >
              {logsLoading && lines.length === 0 && (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className="w-5 h-5 animate-spin text-cyber-primary" />
                </div>
              )}
              {logsError && (
                <p className="text-rose-400 py-4 text-center">{logsError}</p>
              )}
              {!logsLoading && !logsError && filtered.length === 0 && (
                <p className="text-slate-600 py-4 text-center">No log lines match the current filters.</p>
              )}
              {filtered.map((l, i) => {
                const { ts, message } = parseTimestamp(l.text)
                const level = detectLevel(l.text)
                const badgeCls = LEVEL_BADGE[level]
                const textCls = LEVEL_TEXT[level]
                return (
                  <div key={i} className="flex items-start gap-2 py-0.5 hover:bg-white/5 rounded px-1">
                    {ts && (
                      <span className="text-slate-600 flex-shrink-0 select-none w-[92px]">{ts}</span>
                    )}
                    {badgeCls && (
                      <span className={clsx('flex-shrink-0 px-1.5 py-0.5 rounded text-[10px] leading-none', badgeCls)}>
                        {level}
                      </span>
                    )}
                    {l.stream === 'stderr' && (
                      <span className="flex-shrink-0 px-1 py-0.5 rounded text-[10px] leading-none bg-rose-900/40 text-rose-400 border border-rose-700/30">
                        err
                      </span>
                    )}
                    <span className={clsx('break-all', textCls)}>{message || l.text}</span>
                  </div>
                )
              })}
            </div>

            {/* Footer */}
            <div className="flex-shrink-0 border-t border-cyber-border bg-cyber-surface px-4 py-1.5 flex items-center justify-between text-[10px] text-slate-600">
              <span>{filtered.length} / {lines.length} lines</span>
              <span>{selected.image}</span>
            </div>
          </>
        )}
      </div>
      </div>
      )}
    </div>
  )
}
