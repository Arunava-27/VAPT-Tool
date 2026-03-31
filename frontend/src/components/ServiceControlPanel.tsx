import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  listAllServices,
  startService,
  stopService,
  getServiceLogs,
  ServiceInfo,
} from '../api/services'

// ─── Helpers ──────────────────────────────────────────────────────────────────

const CATEGORY_LABELS: Record<string, string> = {
  data: 'Data Layer',
  backend: 'Backend & AI',
  worker: 'Workers',
}

const TYPE_BADGE: Record<string, string> = {
  docker: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  native: 'bg-violet-500/15 text-violet-400 border-violet-500/30',
  worker: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
}

function statusDot(status: string) {
  if (status === 'running') return 'bg-emerald-400 shadow-emerald-400/60'
  if (status === 'stopped') return 'bg-rose-500'
  return 'bg-slate-500'
}

function fmtUptime(secs?: number) {
  if (!secs) return null
  if (secs < 60) return `${secs}s`
  if (secs < 3600) return `${Math.floor(secs / 60)}m`
  return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`
}

// ─── Log Modal ────────────────────────────────────────────────────────────────

function LogModal({ name, label, onClose }: { name: string; label: string; onClose: () => void }) {
  const [lines, setLines] = useState<Array<{ text: string; stream: string }>>([])
  const [loading, setLoading] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setLoading(true)
    getServiceLogs(name, 150)
      .then((res) => setLines(res.lines))
      .catch(() => setLines([]))
      .finally(() => setLoading(false))
  }, [name])

  useEffect(() => {
    bottomRef.current?.scrollIntoView()
  }, [lines])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-3xl bg-gray-900 border border-gray-700 rounded-xl flex flex-col max-h-[80vh]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
          <p className="text-sm font-semibold text-white">
            Logs — <span className="text-gray-400">{label}</span>
          </p>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto font-mono text-xs p-4 space-y-0.5">
          {loading && <p className="text-gray-500">Loading…</p>}
          {!loading && lines.length === 0 && (
            <p className="text-gray-500">No log output available.</p>
          )}
          {lines.map((l, i) => (
            <p key={i} className="text-gray-300 whitespace-pre-wrap break-all leading-5">
              {l.text}
            </p>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  )
}

// ─── Service Card ─────────────────────────────────────────────────────────────

type ActionState = 'idle' | 'starting' | 'stopping'

interface ServiceCardProps {
  svc: ServiceInfo
  onRefresh: () => void
}

function ServiceCard({ svc, onRefresh }: ServiceCardProps) {
  const [actionState, setActionState] = useState<ActionState>('idle')
  const [toast, setToast] = useState<{ ok: boolean; msg: string } | null>(null)
  const [logsOpen, setLogsOpen] = useState(false)

  const showToast = (ok: boolean, msg: string) => {
    setToast({ ok, msg })
    setTimeout(() => setToast(null), 4000)
  }

  const handleStart = async () => {
    setActionState('starting')
    try {
      const res = await startService(svc.id)
      showToast(res.ok, res.message)
      onRefresh()
    } catch {
      showToast(false, 'Request failed')
    } finally {
      setActionState('idle')
    }
  }

  const handleStop = async () => {
    setActionState('stopping')
    try {
      const res = await stopService(svc.id)
      showToast(res.ok, res.message)
      onRefresh()
    } catch {
      showToast(false, 'Request failed')
    } finally {
      setActionState('idle')
    }
  }

  const handleRestart = async () => {
    setActionState('stopping')
    try {
      await stopService(svc.id)
      // brief pause so the process fully dies
      await new Promise((r) => setTimeout(r, 1200))
      setActionState('starting')
      const res = await startService(svc.id)
      showToast(res.ok, res.message)
      onRefresh()
    } catch {
      showToast(false, 'Restart failed')
    } finally {
      setActionState('idle')
    }
  }

  const isSelf = svc.self === true
  const isRunning = svc.status === 'running'
  const isBusy = actionState !== 'idle'
  const hasLogs = svc.type === 'native' || svc.type === 'worker' || svc.type === 'docker'

  return (
    <>
      <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 flex flex-col gap-3 relative">
        {/* Toast */}
        {toast && (
          <div
            className={`absolute top-2 right-2 left-2 z-10 rounded-lg px-3 py-2 text-xs font-medium border ${
              toast.ok
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
            }`}
          >
            {toast.msg}
          </div>
        )}

        {/* Header row */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span
              className={`inline-block w-2.5 h-2.5 rounded-full flex-shrink-0 shadow-sm ${statusDot(svc.status)}`}
            />
            <p className="text-sm font-semibold text-white truncate">{svc.label}</p>
          </div>
          <span
            className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-medium flex-shrink-0 ${TYPE_BADGE[svc.type] ?? TYPE_BADGE.native}`}
          >
            {svc.type.charAt(0).toUpperCase() + svc.type.slice(1)}
          </span>
        </div>

        {/* Metrics */}
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-400">
          {svc.type === 'docker' && svc.container && (
            <span className="font-mono truncate max-w-full">{svc.container}</span>
          )}
          {svc.pid != null && <span>PID {svc.pid}</span>}
          {svc.port != null && <span>:{svc.port}</span>}
          {svc.cpu_percent != null && <span>{svc.cpu_percent.toFixed(1)}% CPU</span>}
          {svc.memory_mb != null && svc.memory_mb > 0 && <span>{svc.memory_mb} MB</span>}
          {svc.uptime_seconds != null && isRunning && (
            <span>up {fmtUptime(svc.uptime_seconds)}</span>
          )}
          {svc.status !== 'running' && (
            <span
              className={`font-medium ${svc.status === 'stopped' ? 'text-rose-400' : 'text-gray-500'}`}
            >
              {svc.status}
            </span>
          )}
        </div>

        {/* Controls */}
        <div className="flex gap-2 mt-auto">
          {!isSelf && (
            <>
              {isRunning ? (
                <>
                  <button
                    onClick={handleRestart}
                    disabled={isBusy}
                    className="flex-1 py-1.5 rounded-lg border border-amber-500/30 text-amber-400 hover:bg-amber-500/10 text-xs font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                  >
                    {actionState === 'stopping' || actionState === 'starting' ? (
                      <span className="inline-block w-3 h-3 border-2 border-amber-400/40 border-t-amber-400 rounded-full animate-spin" />
                    ) : null}
                    Restart
                  </button>
                  <button
                    onClick={handleStop}
                    disabled={isBusy}
                    className="flex-1 py-1.5 rounded-lg border border-rose-500/30 text-rose-400 hover:bg-rose-500/10 text-xs font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                  >
                    {actionState === 'stopping' ? (
                      <span className="inline-block w-3 h-3 border-2 border-rose-400/40 border-t-rose-400 rounded-full animate-spin" />
                    ) : null}
                    Stop
                  </button>
                </>
              ) : (
                <button
                  onClick={handleStart}
                  disabled={isBusy}
                  className="flex-1 py-1.5 rounded-lg border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 text-xs font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                >
                  {actionState === 'starting' ? (
                    <span className="inline-block w-3 h-3 border-2 border-emerald-400/40 border-t-emerald-400 rounded-full animate-spin" />
                  ) : null}
                  Start
                </button>
              )}
            </>
          )}
          {isSelf && (
            <p className="text-xs text-gray-500 italic">Always on</p>
          )}
          {hasLogs && (
            <button
              onClick={() => setLogsOpen(true)}
              className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-400 hover:text-white hover:border-gray-500 text-xs font-medium transition-colors"
            >
              Logs
            </button>
          )}
        </div>
      </div>

      {logsOpen && (
        <LogModal name={svc.id} label={svc.label} onClose={() => setLogsOpen(false)} />
      )}
    </>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function ServiceControlPanel() {
  const [services, setServices] = useState<ServiceInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchServices = useCallback(async () => {
    try {
      const data = await listAllServices()
      setServices(data)
      setError(null)
    } catch (e) {
      setError('Cannot reach host-agent on localhost:9999')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchServices()
    intervalRef.current = setInterval(fetchServices, 5000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchServices])

  const grouped = (['data', 'backend', 'worker'] as const).reduce<
    Record<string, ServiceInfo[]>
  >((acc, cat) => {
    const svcs = services.filter((s) => s.category === cat)
    if (svcs.length) acc[cat] = svcs
    return acc
  }, {})

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <span className="inline-block w-5 h-5 border-2 border-gray-600 border-t-cyber-primary rounded-full animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 text-sm text-rose-400">
        {error} — make sure host-agent is running.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {Object.entries(grouped).map(([cat, svcs]) => (
        <div key={cat}>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            {CATEGORY_LABELS[cat] ?? cat}
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {svcs.map((svc) => (
              <ServiceCard key={svc.id} svc={svc} onRefresh={fetchServices} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
