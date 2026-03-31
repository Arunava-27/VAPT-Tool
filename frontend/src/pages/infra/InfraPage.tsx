import { useState, useCallback, useRef } from 'react'
import { RefreshCw, Database, Layers, Cpu, HardDrive, Server, Bot, Radio,
  CheckCircle, XCircle, AlertTriangle, Clock, Network, Globe, Container, Cloud, Swords,
  Key, Lock, Trash2, X, Monitor, Activity, MemoryStick, Hash, ExternalLink,
  Power, PowerOff, Terminal, Copy, Check, Play, Square, Shield } from 'lucide-react'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import { getServicesHealth, runServiceAction, getHostAgentStatus, shutdownHostAgent } from '../../api/infra'
import type { ServiceHealth, ServicesHealthResponse, HostAgentStatus } from '../../api/infra'
import { startService, stopService } from '../../api/services'
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
  secrets: Shield,
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
  secrets: 'Secrets Manager',
  worker: 'Worker',
}

const WORKER_IDS = ['worker-nmap', 'worker-zap', 'worker-trivy', 'worker-prowler', 'worker-metasploit']

function StatusIcon({ status }: { status: string }) {
  if (status === 'healthy' || status === 'running') return <CheckCircle className="w-4 h-4 text-emerald-400" />
  if (status === 'degraded') return <AlertTriangle className="w-4 h-4 text-amber-400" />
  if (status === 'not_started' || status === 'unreachable') return <Clock className="w-4 h-4 text-slate-400" />
  return <XCircle className="w-4 h-4 text-rose-400" />
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    healthy:     'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    running:     'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    degraded:    'bg-amber-500/10  text-amber-400  border-amber-500/30',
    unhealthy:   'bg-rose-500/10   text-rose-400   border-rose-500/30',
    unreachable: 'bg-slate-500/10  text-slate-400  border-slate-500/30',
    stopped:     'bg-rose-500/10   text-rose-400   border-rose-500/30',
    not_started: 'bg-slate-500/10  text-slate-400  border-slate-500/30',
  }
  const cls = map[status] ?? map.unhealthy
  const label = status === 'not_started' ? 'Not Started' : status.charAt(0).toUpperCase() + status.slice(1)
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-xs font-medium ${cls}`}>
      <StatusIcon status={status} />
      {label}
    </span>
  )
}

function LatencyBadge({ ms }: { ms?: number }) {
  if (ms === undefined) return null
  const color = ms < 50 ? 'text-emerald-400' : ms < 200 ? 'text-amber-400' : 'text-rose-400'
  return <span className={`text-xs font-mono ${color}`}>{ms} ms</span>
}

// ─── Vault Unseal Modal ───────────────────────────────────────────────────────
function VaultUnsealModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [key, setKey] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [progress, setProgress] = useState(0)

  const handleSubmitKey = async () => {
    if (!key.trim()) return
    setSubmitting(true)
    try {
      const res = await runServiceAction('vault', 'unseal', { keys: [key.trim()] })
      setKey('')
      const newProgress = progress + 1
      setProgress(newProgress)
      if (res.data.message?.includes('unsealed') || newProgress >= 3) {
        toast.success('Vault unsealed successfully!')
        onSuccess()
        onClose()
      } else {
        toast.success(`Key accepted (${newProgress}/3 minimum)`)
      }
    } catch {
      toast.error('Failed to submit unseal key')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6 w-[480px] shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Lock className="w-5 h-5 text-amber-400" />
            <h3 className="text-white font-semibold">Unseal HashiCorp Vault</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
        <p className="text-sm text-slate-400 mb-4">
          Enter unseal keys one at a time. You need at minimum 3 keys to unseal the Vault.
        </p>
        {progress > 0 && (
          <div className="mb-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
            <p className="text-xs text-amber-400 font-semibold">{progress} key{progress !== 1 ? 's' : ''} accepted — {Math.max(0, 3 - progress)} more minimum required</p>
            <div className="mt-2 h-1.5 bg-slate-700 rounded-full overflow-hidden">
              <div className="h-full bg-amber-400 rounded-full transition-all" style={{ width: `${Math.min(100, (progress / 3) * 100)}%` }} />
            </div>
          </div>
        )}
        <div className="space-y-1.5 mb-4">
          <label className="text-xs text-slate-500">Unseal Key</label>
          <input
            type="password"
            value={key}
            onChange={e => setKey(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSubmitKey()}
            placeholder="Enter unseal key…"
            className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyber-primary transition-colors font-mono"
          />
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-cyber-border text-slate-400 hover:text-white text-sm">Cancel</button>
          <button onClick={handleSubmitKey} disabled={submitting || !key.trim()}
            className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-400 hover:bg-amber-500/30 text-sm font-medium disabled:opacity-50">
            {submitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Key className="w-3.5 h-3.5" />}
            Submit Key
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Vault Init Modal ─────────────────────────────────────────────────────────
function VaultInitModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [shares, setShares] = useState('5')
  const [threshold, setThreshold] = useState('3')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<{ unseal_keys: string[]; root_token: string } | null>(null)
  const [copied, setCopied] = useState(false)

  const handleInit = async () => {
    setSubmitting(true)
    try {
      const res = await runServiceAction('vault', 'init', {
        secret_shares: parseInt(shares),
        secret_threshold: parseInt(threshold),
      })
      if (res.data.ok) {
        setResult({ unseal_keys: ['Keys returned by Vault — check server logs'], root_token: res.data.message ?? '' })
        toast.success('Vault initialized!')
        onSuccess()
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'Failed to initialize Vault')
    } finally {
      setSubmitting(false)
    }
  }

  const copyAll = () => {
    if (!result) return
    const text = `Unseal Keys:\n${result.unseal_keys.join('\n')}\n\nRoot Token:\n${result.root_token}`
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6 w-[520px] shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Key className="w-5 h-5 text-cyber-primary" />
            <h3 className="text-white font-semibold">Initialize HashiCorp Vault</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
        </div>

        {!result ? (
          <>
            <p className="text-sm text-slate-400 mb-4">Configure the initial Vault secret sharing parameters.</p>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="text-xs text-slate-500 mb-1.5 block">Secret Shares</label>
                <input type="number" min="1" max="20" value={shares} onChange={e => setShares(e.target.value)}
                  className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyber-primary transition-colors" />
                <p className="text-xs text-slate-600 mt-1">Total number of key shares</p>
              </div>
              <div>
                <label className="text-xs text-slate-500 mb-1.5 block">Secret Threshold</label>
                <input type="number" min="1" max="20" value={threshold} onChange={e => setThreshold(e.target.value)}
                  className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyber-primary transition-colors" />
                <p className="text-xs text-slate-600 mt-1">Keys required to unseal</p>
              </div>
            </div>
            <div className="flex gap-3">
              <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-cyber-border text-slate-400 hover:text-white text-sm">Cancel</button>
              <button onClick={handleInit} disabled={submitting}
                className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-cyber-primary/20 border border-cyber-primary/40 text-cyber-primary hover:bg-cyber-primary/30 text-sm font-medium disabled:opacity-50">
                {submitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Key className="w-3.5 h-3.5" />}
                Initialize Vault
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="mb-4 p-4 bg-amber-500/10 border-2 border-amber-500/50 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle className="w-5 h-5 text-amber-400" />
                <p className="text-sm font-bold text-amber-400">⚠️ SAVE THESE KEYS NOW — They will not be shown again!</p>
              </div>
              <div className="space-y-2 mt-3">
                <p className="text-xs text-slate-400 font-semibold">Unseal Keys:</p>
                {result.unseal_keys.map((k, i) => (
                  <p key={i} className="text-xs font-mono text-slate-300 bg-cyber-bg p-2 rounded border border-cyber-border break-all">{k}</p>
                ))}
                <p className="text-xs text-slate-400 font-semibold mt-2">Root Token:</p>
                <p className="text-xs font-mono text-cyber-primary bg-cyber-bg p-2 rounded border border-cyber-border break-all">{result.root_token}</p>
              </div>
            </div>
            <div className="flex gap-3">
              <button onClick={copyAll}
                className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg border border-cyber-primary/40 text-cyber-primary hover:bg-cyber-primary/10 text-sm">
                {copied ? <CheckCircle className="w-3.5 h-3.5" /> : <Key className="w-3.5 h-3.5" />}
                {copied ? 'Copied!' : 'Copy All Keys'}
              </button>
              <button onClick={onClose} className="flex-1 py-2 rounded-lg bg-cyber-primary/20 border border-cyber-primary/40 text-cyber-primary hover:bg-cyber-primary/30 text-sm font-medium">
                Done
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ─── Host Agent Control Card ──────────────────────────────────────────────────

const START_CMD = 'cd host-agent && start.bat'

function HostAgentCard({ status, onRefresh }: { status: HostAgentStatus | null; onRefresh: () => void }) {
  const [stopping, setStopping] = useState(false)
  const [showStartModal, setShowStartModal] = useState(false)
  const [copied, setCopied] = useState(false)

  const isOnline = status?.status === 'online'
  const isLoading = status === null

  const handleStop = async () => {
    if (!confirm('Stop the host discovery agent? Worker monitoring and network interface detection will stop working until it is restarted.')) return
    setStopping(true)
    try {
      await shutdownHostAgent()
      toast.success('Host agent stopped')
      setTimeout(onRefresh, 800)
    } catch {
      toast.error('Failed to stop host agent')
    } finally {
      setStopping(false)
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(START_CMD)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const formatUptime = (s?: number) => {
    if (!s) return '—'
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
    return h ? `${h}h ${m}m` : m ? `${m}m ${sec}s` : `${sec}s`
  }

  return (
    <>
      <div className={`border rounded-xl p-4 transition-all ${
        isOnline
          ? 'border-cyber-primary/40 bg-cyber-primary/5'
          : 'border-rose-500/30 bg-rose-500/5'
      }`}>
        {/* Header */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-2.5">
            <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
              isOnline ? 'bg-cyber-primary/15 border border-cyber-primary/30' : 'bg-rose-500/10 border border-rose-500/20'
            }`}>
              <Terminal className={`w-4 h-4 ${isOnline ? 'text-cyber-primary' : 'text-rose-400'}`} />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">Host Discovery Agent</p>
              <p className="text-xs text-slate-500">Bridge between Docker and host machine</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            {isLoading ? (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-xs font-medium bg-slate-500/10 text-slate-400 border-slate-500/30">
                <RefreshCw className="w-3 h-3 animate-spin" /> Checking…
              </span>
            ) : isOnline ? (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-xs font-medium bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
                <CheckCircle className="w-3.5 h-3.5" /> Online
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-xs font-medium bg-rose-500/10 text-rose-400 border-rose-500/30">
                <XCircle className="w-3.5 h-3.5" /> Offline
              </span>
            )}
          </div>
        </div>

        {/* Metrics */}
        {isOnline && status && (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs border-t border-cyber-border pt-3 mb-3">
            <div className="flex justify-between items-center">
              <span className="text-slate-500 flex items-center gap-1"><Hash className="w-3 h-3" />PID</span>
              <span className="text-slate-300 font-mono">{status.pid}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-500 flex items-center gap-1"><Clock className="w-3 h-3" />Uptime</span>
              <span className="text-emerald-400 font-mono">{formatUptime(status.uptime_s)}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-500 flex items-center gap-1"><Activity className="w-3 h-3" />CPU</span>
              <span className="text-slate-300 font-mono">{status.cpu_percent?.toFixed(1) ?? '0.0'}%</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-500 flex items-center gap-1"><MemoryStick className="w-3 h-3" />RAM</span>
              <span className="text-slate-300 font-mono">{status.memory_mb ?? '—'} MB</span>
            </div>
          </div>
        )}

        {!isOnline && !isLoading && (
          <div className="border-t border-rose-500/20 pt-3 mb-3">
            <p className="text-xs text-rose-400/80">
              Worker monitoring, network interface detection, and log streaming are unavailable while the agent is offline.
            </p>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2">
          {isOnline ? (
            <button
              onClick={handleStop}
              disabled={stopping}
              className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg border border-rose-500/40 text-rose-400 hover:bg-rose-500/10 text-xs font-medium transition-colors disabled:opacity-50"
            >
              {stopping ? <RefreshCw className="w-3 h-3 animate-spin" /> : <PowerOff className="w-3 h-3" />}
              Stop Agent
            </button>
          ) : (
            <button
              onClick={() => setShowStartModal(true)}
              className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg border border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10 text-xs font-medium transition-colors"
            >
              <Power className="w-3 h-3" />
              How to Start
            </button>
          )}
          <button
            onClick={onRefresh}
            className="p-1.5 rounded-lg border border-cyber-border text-slate-400 hover:text-white hover:bg-cyber-border transition-colors"
            title="Refresh status"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Start instructions modal */}
      {showStartModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6 w-[480px] shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Power className="w-5 h-5 text-emerald-400" />
                <h3 className="text-white font-semibold">Start Host Discovery Agent</h3>
              </div>
              <button onClick={() => setShowStartModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-sm text-slate-400 mb-4">
              The host agent must be started manually on the host machine. Open a terminal in the project root and run:
            </p>

            <div className="flex items-center gap-2 bg-[#070c1a] border border-cyber-border rounded-lg px-4 py-3 mb-4">
              <code className="text-emerald-400 font-mono text-sm flex-1">{START_CMD}</code>
              <button onClick={handleCopy} className="text-slate-500 hover:text-white transition-colors flex-shrink-0">
                {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>

            <div className="bg-cyber-primary/5 border border-cyber-primary/20 rounded-lg p-3 mb-4">
              <p className="text-xs text-slate-400 leading-relaxed">
                <span className="text-cyber-primary font-medium">Why manual?</span> The agent runs natively on your host machine to access real LAN interfaces, process files, and worker logs — things Docker containers cannot do. It cannot be started remotely from Docker.
              </p>
            </div>

            <button
              onClick={() => setShowStartModal(false)}
              className="w-full py-2 rounded-lg border border-cyber-border text-slate-400 hover:text-white text-sm transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </>
  )
}


function ServiceCard({ svc, onClick, onVaultUnseal, onVaultInit, onWorkerPurge, onViewLogs, onStart, onStop }: {
  svc: ServiceHealth
  onClick: () => void
  onVaultUnseal?: () => void
  onVaultInit?: () => void
  onWorkerPurge?: () => void
  onViewLogs?: () => void
  onStart?: () => void
  onStop?: () => void
}){
  const Icon = WORKER_ICON[svc.id] ?? CATEGORY_ICON[svc.category] ?? Server
  const isHealthy = svc.status === 'healthy' || svc.status === 'running'
  const isVault = svc.id === 'vault'
  const isWorker = WORKER_IDS.includes(svc.id)
  const isNative = svc.host === 'host_machine'
  const [purging, setPurging] = useState(false)

  const handlePurge = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setPurging(true)
    try {
      if (onWorkerPurge) onWorkerPurge()
    } finally {
      setPurging(false)
    }
  }

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
            <div className="flex items-center gap-1.5 flex-wrap">
              <p className="text-sm font-semibold text-white truncate">{svc.label ?? svc.name}</p>
              {isNative && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-cyber-primary/15 border border-cyber-primary/30 text-cyber-primary text-[10px] font-medium">
                  <Monitor className="w-2.5 h-2.5" />
                  Host
                </span>
              )}
            </div>
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
        {/* Native worker metrics */}
        {isNative && svc.pid && (
          <div className="flex justify-between items-center">
            <span className="text-slate-500 flex items-center gap-1"><Hash className="w-3 h-3" />PID</span>
            <span className="text-slate-300 font-mono">{svc.pid}</span>
          </div>
        )}
        {isNative && svc.uptime && (
          <div className="flex justify-between items-center">
            <span className="text-slate-500 flex items-center gap-1"><Clock className="w-3 h-3" />Uptime</span>
            <span className="text-emerald-400 font-mono">{svc.uptime}</span>
          </div>
        )}
        {isNative && svc.cpu_percent !== undefined && (
          <div className="flex justify-between items-center">
            <span className="text-slate-500 flex items-center gap-1"><Activity className="w-3 h-3" />CPU</span>
            <span className="text-slate-300 font-mono">{svc.cpu_percent.toFixed(1)}%</span>
          </div>
        )}
        {isNative && svc.memory_mb !== undefined && (
          <div className="flex justify-between items-center">
            <span className="text-slate-500 flex items-center gap-1"><MemoryStick className="w-3 h-3" />RAM</span>
            <span className="text-slate-300 font-mono">{svc.memory_mb} MB</span>
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

      {/* Vault special actions */}
      {isVault && svc.status === 'degraded' && onVaultUnseal && (
        <div className="mt-3 pt-3 border-t border-amber-500/20">
          <button
            onClick={e => { e.stopPropagation(); onVaultUnseal() }}
            className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-400 hover:bg-amber-500/30 text-xs font-medium transition-colors"
          >
            <Lock className="w-3.5 h-3.5" />
            Unseal Vault
          </button>
        </div>
      )}
      {isVault && (svc.status === 'unhealthy' || svc.status === 'unreachable') && onVaultInit && (
        <div className="mt-3 pt-3 border-t border-rose-500/20">
          <button
            onClick={e => { e.stopPropagation(); onVaultInit() }}
            className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-cyber-primary/20 border border-cyber-primary/40 text-cyber-primary hover:bg-cyber-primary/30 text-xs font-medium transition-colors"
          >
            <Key className="w-3.5 h-3.5" />
            Initialize Vault
          </button>
        </div>
      )}

      {/* Worker actions */}
      {isWorker && (
        <div className="mt-3 pt-3 border-t border-cyber-border space-y-2">
          {svc.status === 'not_started' && (
            <div className="p-2 bg-slate-500/5 border border-slate-500/20 rounded-lg">
              <p className="text-xs text-slate-400">Optional worker — not installed on this host.</p>
            </div>
          )}
          <div className="flex gap-2">
            {onViewLogs && (
              <button
                onClick={e => { e.stopPropagation(); onViewLogs() }}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg border border-cyber-primary/30 text-cyber-primary hover:bg-cyber-primary/10 text-xs font-medium transition-colors"
              >
                <ExternalLink className="w-3 h-3" />
                View Logs
              </button>
            )}
            {onStart && svc.status !== 'healthy' && svc.status !== 'running' && svc.status !== 'not_started' && (
              <button
                onClick={e => { e.stopPropagation(); onStart() }}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg border border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10 text-xs font-medium transition-colors"
              >
                <Play className="w-3 h-3" />
                Start
              </button>
            )}
            {onStop && (svc.status === 'healthy' || svc.status === 'running') && (
              <button
                onClick={e => { e.stopPropagation(); onStop() }}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg border border-rose-500/30 text-rose-400 hover:bg-rose-500/10 text-xs font-medium transition-colors"
              >
                <Square className="w-3 h-3" />
                Stop
              </button>
            )}
            {onWorkerPurge && (svc.status === 'healthy' || svc.status === 'running') && (
              <button
                onClick={handlePurge}
                disabled={purging}
                className="px-2 flex items-center justify-center gap-1.5 py-1.5 rounded-lg border border-rose-500/30 text-rose-400 hover:bg-rose-500/10 text-xs font-medium transition-colors disabled:opacity-50"
                title="Purge queue"
              >
                {purging ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
              </button>
            )}
          </div>
        </div>
      )}
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

const ORDERED_CATEGORIES = ['database', 'cache', 'queue', 'search', 'storage', 'backend', 'secrets', 'worker'] as const

export default function InfraPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<ServicesHealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastChecked, setLastChecked] = useState<Date | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [selectedSvc, setSelectedSvc] = useState<ServiceHealth | null>(null)
  const [vaultUnsealOpen, setVaultUnsealOpen] = useState(false)
  const [vaultInitOpen, setVaultInitOpen] = useState(false)
  const [hostAgentStatus, setHostAgentStatus] = useState<HostAgentStatus | null>(null)

  const hasData = useRef(false)

  const fetchHostAgent = useCallback(async () => {
    try {
      const res = await getHostAgentStatus()
      setHostAgentStatus(res.data)
    } catch {
      setHostAgentStatus({ status: 'offline' })
    }
  }, [])

  const fetchHealth = useCallback(async () => {
    try {
      const [svcRes] = await Promise.all([
        getServicesHealth(),
        fetchHostAgent(),
      ])
      setData(svcRes.data)
      hasData.current = true
      setLastChecked(new Date())
    } catch (err) {
      console.error('Services health check failed:', err)
      if (!hasData.current) toast.error('Failed to fetch service health')
    } finally {
      setLoading(false)
    }
  }, [fetchHostAgent])

  usePolling(fetchHealth, 15_000, autoRefresh)

  const handleWorkerPurge = async (svcId: string) => {
    try {
      await runServiceAction(svcId, 'purge')
      toast.success(`Queue purged for ${svcId}`)
    } catch {
      toast.error(`Failed to purge queue for ${svcId}`)
    }
  }

  const handleWorkerStart = async (svc: ServiceHealth) => {
    try {
      const res = await startService(svc.id)
      if (res.ok) {
        toast.success(`${svc.name} started`)
        setTimeout(fetchHealth, 1500)
      } else {
        toast.error(res.message || `Failed to start ${svc.name}`)
      }
    } catch {
      toast.error(`Failed to start ${svc.name}`)
    }
  }

  const handleWorkerStop = async (svc: ServiceHealth) => {
    if (!confirm(`Stop ${svc.name}? It will no longer process scan tasks until restarted.`)) return
    try {
      const res = await stopService(svc.id)
      if (res.ok) {
        toast.success(`${svc.name} stopped`)
        setTimeout(fetchHealth, 1500)
      } else {
        toast.error(res.message || `Failed to stop ${svc.name}`)
      }
    } catch {
      toast.error(`Failed to stop ${svc.name}`)
    }
  }

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

      {/* Host Agent control */}
      <section>
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5" />
          Host Services
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          <HostAgentCard status={hostAgentStatus} onRefresh={fetchHostAgent} />
        </div>
      </section>

      {/* Service groups */}
      {Object.entries(grouped).map(([cat, svcs]) => (
        <section key={cat}>
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
            {(() => { const I = CATEGORY_ICON[cat] ?? Server; return <I className="w-3.5 h-3.5" /> })()}
            {cat === 'worker' ? 'Security Workers' : (CATEGORY_LABEL[cat] ?? cat) + 's'}
            <span className="ml-auto text-slate-600 font-normal normal-case">
              {svcs.filter(s => s.status === 'healthy' || s.status === 'running').length}/{svcs.length} healthy
            </span>
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {svcs.map((svc) => (
              <ServiceCard
                key={svc.id}
                svc={svc}
                onClick={() => setSelectedSvc(svc)}
                onVaultUnseal={svc.id === 'vault' ? () => setVaultUnsealOpen(true) : undefined}
                onVaultInit={svc.id === 'vault' ? () => setVaultInitOpen(true) : undefined}
                onWorkerPurge={WORKER_IDS.includes(svc.id) && (svc.status === 'healthy' || svc.status === 'running') ? () => handleWorkerPurge(svc.id) : undefined}
                onViewLogs={WORKER_IDS.includes(svc.id) && svc.host === 'host_machine'
                  ? () => navigate(`/logs?worker=${svc.id.replace('worker-', '')}`)
                  : undefined}
                onStart={WORKER_IDS.includes(svc.id) && svc.host === 'host_machine' ? () => handleWorkerStart(svc) : undefined}
                onStop={WORKER_IDS.includes(svc.id) && svc.host === 'host_machine' ? () => handleWorkerStop(svc) : undefined}
              />
            ))}
          </div>
        </section>
      ))}

      <ServiceDrawer svc={selectedSvc} onClose={() => setSelectedSvc(null)} />

      {vaultUnsealOpen && (
        <VaultUnsealModal
          onClose={() => setVaultUnsealOpen(false)}
          onSuccess={fetchHealth}
        />
      )}
      {vaultInitOpen && (
        <VaultInitModal
          onClose={() => setVaultInitOpen(false)}
          onSuccess={fetchHealth}
        />
      )}
    </div>
  )
}
