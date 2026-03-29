import { useEffect, useState, useCallback } from 'react'
import { X, RefreshCw, AlertTriangle, CheckCircle, ExternalLink } from 'lucide-react'
import toast from 'react-hot-toast'
import { getServiceDetail, runServiceAction } from '../../api/infra'
import type { ServiceDetail, ServiceAction, ServiceHealth } from '../../api/infra'
import LoadingSpinner from '../common/LoadingSpinner'

// ─── helpers ────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '0 B'
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1)
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 border-b border-cyber-border last:border-0">
      <span className="text-xs text-slate-500 flex-shrink-0 capitalize">{label}</span>
      <span className="text-xs text-slate-200 font-mono text-right break-all">{value ?? '—'}</span>
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mt-5 mb-2">
      {children}
    </h3>
  )
}

// ─── action button ───────────────────────────────────────────────────────────

function ActionButton({
  action,
  serviceId,
  onDone,
}: {
  action: ServiceAction
  serviceId: string
  onDone: () => void
}) {
  const [loading, setLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)

  const handleClick = async () => {
    if (action.confirm && !confirming) { setConfirming(true); return }
    setConfirming(false)
    setLoading(true)
    try {
      const res = await runServiceAction(serviceId, action.id)
      if (res.data.ok) { toast.success(res.data.message); onDone() }
      else toast.error(res.data.message)
    } catch {
      toast.error(`Action '${action.label}' failed`)
    } finally {
      setLoading(false)
    }
  }

  const variantCls =
    action.variant === 'danger'
      ? confirming
        ? 'border-rose-500 bg-rose-500/20 text-rose-300 animate-pulse'
        : 'border-rose-500/30 text-rose-400 hover:bg-rose-500/10 focus-visible:ring-rose-500/40'
      : action.variant === 'info'
      ? 'border-blue-500/30 text-blue-400 hover:bg-blue-500/10 focus-visible:ring-blue-500/40'
      : action.variant === 'warning'
      ? 'border-amber-500/30 text-amber-400 hover:bg-amber-500/10 focus-visible:ring-amber-500/40'
      : 'border-cyber-border text-slate-300 hover:border-cyber-primary hover:text-cyber-primary focus-visible:ring-cyber-primary/40'

  return (
    <div className="space-y-1">
      <button
        onClick={handleClick}
        disabled={loading}
        className={`flex items-center justify-center gap-2 w-full px-3 py-2.5 rounded-lg border text-xs font-medium transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 ${variantCls}`}
      >
        {loading && <RefreshCw className="w-3 h-3 animate-spin" />}
        {confirming ? `⚠ Confirm: ${action.label}` : action.label}
      </button>
      {confirming && (
        <div className="flex items-start gap-2 bg-rose-500/5 rounded-lg px-3 py-2">
          <p className="text-xs text-rose-400 flex-1">{action.confirm_message}</p>
          <button onClick={() => setConfirming(false)} className="text-xs text-slate-500 hover:text-white flex-shrink-0">
            Cancel
          </button>
        </div>
      )}
    </div>
  )
}

// ─── per-service detail bodies ───────────────────────────────────────────────

function PostgresDetail({ d }: { d: ServiceDetail }) {
  return (
    <>
      <SectionTitle>Database Info</SectionTitle>
      <MetaRow label="Version"           value={d.version as string} />
      <MetaRow label="Database size"     value={d.database_size as string} />
      <MetaRow label="Active connections" value={String(d.active_connections ?? '—')} />
      <MetaRow label="Max connections"   value={String(d.max_connections ?? '—')} />
      <MetaRow label="Public tables"     value={String(d.tables ?? '—')} />
    </>
  )
}

function RedisDetail({ d }: { d: ServiceDetail }) {
  const keyspace = (d.keyspace as Record<string, string>) ?? {}
  return (
    <>
      <SectionTitle>Server Info</SectionTitle>
      <MetaRow label="Version"           value={d.version as string} />
      <MetaRow label="Uptime"            value={d.uptime_days ? `${d.uptime_days} days` : '—'} />
      <MetaRow label="Connected clients" value={String(d.connected_clients ?? '—')} />
      <MetaRow label="Used memory"       value={d.used_memory as string} />
      <MetaRow label="Max memory"        value={d.maxmemory as string} />
      <MetaRow label="Cache hit ratio"   value={d.hit_ratio ? `${d.hit_ratio}%` : '—'} />
      <MetaRow label="Total commands"    value={String(d.total_commands ?? '—')} />
      {Object.keys(keyspace).length > 0 && (
        <>
          <SectionTitle>Keyspace</SectionTitle>
          {Object.entries(keyspace).map(([db, info]) => (
            <MetaRow key={db} label={db} value={String(info)} />
          ))}
        </>
      )}
    </>
  )
}

interface RmqQueue { name: string; messages: number; consumers: number; state: string; memory: number }
function RabbitMQDetail({ d }: { d: ServiceDetail }) {
  const queues = (d.queues as RmqQueue[]) ?? []
  return (
    <>
      <SectionTitle>Broker Info</SectionTitle>
      <MetaRow label="Version"          value={d.version as string} />
      <MetaRow label="Erlang version"   value={d.erlang_version as string} />
      <MetaRow label="Connections"      value={String(d.total_connections ?? '—')} />
      <MetaRow label="Channels"         value={String(d.total_channels ?? '—')} />
      <MetaRow label="Messages ready"   value={String(d.messages_ready ?? 0)} />
      <MetaRow label="Messages unacked" value={String(d.messages_unacked ?? 0)} />
      {queues.length > 0 && (
        <>
          <SectionTitle>Queues ({queues.length})</SectionTitle>
          <div className="space-y-1.5">
            {queues.map((q) => (
              <div key={q.name} className="flex items-center justify-between bg-cyber-bg rounded-lg px-3 py-2 text-xs">
                <span className="font-mono text-slate-300">{q.name}</span>
                <div className="flex gap-3 text-slate-500">
                  <span>{q.consumers} consumer{q.consumers !== 1 ? 's' : ''}</span>
                  <span>{q.messages} msg</span>
                  <span className={q.state === 'running' ? 'text-emerald-400' : 'text-amber-400'}>{q.state}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  )
}

interface EsIndex { name: string; docs: number; size: number; status: string }
function ElasticsearchDetail({ d }: { d: ServiceDetail }) {
  const indices = (d.indices as EsIndex[]) ?? []
  return (
    <>
      <SectionTitle>Cluster Info</SectionTitle>
      <MetaRow label="Version"       value={d.version as string} />
      <MetaRow label="Cluster name"  value={d.cluster_name as string} />
      <MetaRow label="Status"        value={d.status as string} />
      <MetaRow label="Nodes"         value={String(d.nodes ?? '—')} />
      <MetaRow label="Data nodes"    value={String(d.data_nodes ?? '—')} />
      <MetaRow label="Active shards" value={String(d.active_shards ?? '—')} />
      {indices.length > 0 && (
        <>
          <SectionTitle>Indices ({indices.length})</SectionTitle>
          <div className="space-y-1.5">
            {indices.map((idx) => (
              <div key={idx.name} className="flex items-center justify-between bg-cyber-bg rounded-lg px-3 py-2 text-xs">
                <span className="font-mono text-slate-300 truncate max-w-[180px]">{idx.name}</span>
                <div className="flex gap-3 text-slate-500 flex-shrink-0">
                  <span>{idx.docs.toLocaleString()} docs</span>
                  <span>{formatBytes(idx.size)}</span>
                  <span className={idx.status === 'green' ? 'text-emerald-400' : idx.status === 'yellow' ? 'text-amber-400' : 'text-rose-400'}>{idx.status}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  )
}

interface MinioBucket { name: string; objects: number | string; size_bytes: number }
function MinioDetail({ d }: { d: ServiceDetail }) {
  const buckets = (d.buckets as MinioBucket[]) ?? []
  return (
    <>
      <SectionTitle>Storage Info</SectionTitle>
      <MetaRow label="Endpoint" value={d.endpoint as string} />
      <MetaRow label="TLS"      value={d.secure ? 'Enabled' : 'Disabled'} />
      <MetaRow label="Buckets"  value={String(buckets.length)} />
      {buckets.length > 0 && (
        <>
          <SectionTitle>Buckets</SectionTitle>
          <div className="space-y-1.5">
            {buckets.map((b) => (
              <div key={b.name} className="flex items-center justify-between bg-cyber-bg rounded-lg px-3 py-2 text-xs">
                <span className="font-mono text-slate-300">{b.name}</span>
                <div className="flex gap-3 text-slate-500">
                  <span>{typeof b.objects === 'number' ? b.objects.toLocaleString() : b.objects} obj</span>
                  <span>{formatBytes(b.size_bytes)}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  )
}

function AiEngineDetail({ d, serviceId, onRefresh }: { d: ServiceDetail; serviceId: string; onRefresh: () => void }) {
  const [switching, setSwitching] = useState(false)
  const [selectedModel, setSelectedModel] = useState<string>('')

  const availableModels: string[] = (d.available_models as string[]) ?? []
  const availableProviders: string[] = (d.available_providers as string[]) ?? []

  // Normalize model name: strip ":latest" suffix for comparison
  const norm = (m?: string) => (m ?? '').replace(/:latest$/, '')
  const activeModel = d.active_model as string | undefined
  const isActive = (m: string) => norm(m) === norm(activeModel)

  // Default selection to the currently active model
  const effectiveSelected = selectedModel || availableModels.find(isActive) || availableModels[0] || ''

  const handleModelSwitch = async () => {
    if (!effectiveSelected || isActive(effectiveSelected)) return
    setSwitching(true)
    try {
      const res = await runServiceAction(serviceId, 'change_model', { model: effectiveSelected })
      if (res.data.ok) {
        toast.success(res.data.message)
        onRefresh()
      } else {
        toast.error(res.data.message)
      }
    } catch {
      toast.error('Failed to change model')
    } finally {
      setSwitching(false)
    }
  }

  return (
    <>
      <SectionTitle>Active Configuration</SectionTitle>
      <div className="bg-cyber-primary/5 border border-cyber-primary/20 rounded-lg px-4 py-3 mb-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-slate-400">Active Model</span>
          <span className="text-sm font-bold text-cyber-primary font-mono">{d.active_model ?? '—'}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">Provider</span>
          <span className="text-xs text-slate-300 capitalize">{d.active_provider ?? '—'}</span>
        </div>
      </div>

      <MetaRow label="Fallback chain"     value={d.fallback_chain as string} />
      <MetaRow label="Ollama URL"         value={d.ollama_url as string} />
      <MetaRow label="Guardrails"         value={d.guardrails_enabled ? '✅ Enabled' : '⚠ Disabled'} />
      <MetaRow label="Agent timeout"      value={d.agent_timeout as string} />
      <MetaRow label="Max tokens"         value={String(d.max_tokens ?? '—')} />

      {availableProviders.length > 0 && (
        <>
          <SectionTitle>Available Providers</SectionTitle>
          <div className="flex flex-wrap gap-1.5">
            {availableProviders.map((p) => (
              <span key={p} className={`px-2 py-0.5 rounded text-xs font-medium border ${
                p === d.active_provider
                  ? 'bg-cyber-primary/15 border-cyber-primary/40 text-cyber-primary'
                  : 'bg-slate-800/50 border-slate-700 text-slate-400'
              }`}>
                {p}
              </span>
            ))}
          </div>
        </>
      )}

      {availableModels.length > 0 && (
        <>
          <SectionTitle>Switch Model</SectionTitle>
          <p className="text-xs text-slate-500 mb-2">
            Changes take effect immediately. Resets to default on container restart.
          </p>
          <div className="flex gap-2">
            <select
              value={effectiveSelected}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="flex-1 bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:outline-none focus:border-cyber-primary"
            >
              {availableModels.map((m) => (
                <option key={m} value={m}>{m}{isActive(m) ? ' (active)' : ''}</option>
              ))}
            </select>
            <button
              onClick={handleModelSwitch}
              disabled={switching || isActive(effectiveSelected)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-cyber-primary/40 text-cyber-primary text-xs font-medium hover:bg-cyber-primary/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0"
            >
              {switching && <RefreshCw className="w-3 h-3 animate-spin" />}
              Apply
            </button>
          </div>
          <div className="mt-2 space-y-1">
            {availableModels.map((m) => (
              <button
                key={m}
                onClick={() => setSelectedModel(m)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg border text-xs transition-colors ${
                  isActive(m)
                    ? 'border-cyber-primary/40 bg-cyber-primary/10 text-cyber-primary'
                    : m === effectiveSelected
                    ? 'border-slate-500 bg-slate-800/60 text-slate-200'
                    : 'border-cyber-border text-slate-400 hover:border-slate-500 hover:text-slate-300'
                }`}
              >
                <span className="font-mono">{m}</span>
                {isActive(m) && (
                  <span className="text-cyber-primary text-xs">● Active</span>
                )}
              </button>
            ))}
          </div>
        </>
      )}

      {availableModels.length === 0 && (
        <div className="mt-2 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2.5 text-xs text-amber-300">
          No models found in Ollama. Run: <code className="font-mono bg-black/30 px-1 rounded">docker exec vapt-ollama ollama pull llama3.2</code>
        </div>
      )}
    </>
  )
}

interface Consumer { tag: string; channel: string }
function WorkerDetail({ d }: { d: ServiceDetail }) {
  const consumers = (d.consumers as Consumer[]) ?? []
  return (
    <>
      <SectionTitle>Queue Stats</SectionTitle>
      <MetaRow label="Queue"            value={d.queue as string} />
      <MetaRow label="State"            value={d.state as string} />
      <MetaRow label="Messages ready"   value={String(d.messages_ready ?? 0)} />
      <MetaRow label="Messages unacked" value={String(d.messages_unacked ?? 0)} />
      <MetaRow label="Publish rate"     value={`${d.message_rate_in ?? 0} msg/s`} />
      <MetaRow label="Deliver rate"     value={`${d.message_rate_out ?? 0} msg/s`} />
      <MetaRow label="Memory"           value={formatBytes((d.memory as number) ?? 0)} />
      {consumers.length > 0 && (
        <>
          <SectionTitle>Consumers ({consumers.length})</SectionTitle>
          {consumers.map((c, i) => (
            <MetaRow key={i} label={`Consumer ${i + 1}`} value={c.channel} />
          ))}
        </>
      )}
    </>
  )
}

function VaultDetail({ d, serviceId, onRefresh }: { d: ServiceDetail; serviceId: string; onRefresh: () => void }) {
  const sealed = d.sealed as boolean | undefined
  const initialized = d.initialized as boolean | undefined

  return (
    <>
      <SectionTitle>Vault Status</SectionTitle>
      <MetaRow label="Version"       value={d.version as string} />
      <MetaRow label="Storage"       value={d.storage_backend as string} />
      <MetaRow label="Cluster"       value={d.cluster_name as string} />
      <MetaRow label="Cluster ID"    value={(d.cluster_id as string)?.slice(0, 18) + '…'} />
      <MetaRow
        label="Initialized"
        value={
          <span className={initialized ? 'text-cyber-primary' : 'text-red-400'}>
            {initialized ? '✓ Yes' : '✗ No'}
          </span>
        }
      />
      <MetaRow
        label="Seal State"
        value={
          <span className={!sealed ? 'text-cyber-primary' : 'text-amber-400'}>
            {!sealed ? '🔓 Unsealed' : '🔒 Sealed'}
          </span>
        }
      />

      <SectionTitle>Access</SectionTitle>
      <div className="flex items-center gap-2 py-2">
        <a
          href="http://localhost:8200/ui"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-xs text-cyber-primary hover:underline"
        >
          <ExternalLink className="w-3 h-3" />
          Open Vault UI
        </a>
      </div>

      {sealed && (
        <div className="mt-3 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2.5 text-xs text-amber-300">
          Vault is sealed. Run: <code className="font-mono bg-black/30 px-1 rounded">docker compose up vault-init</code> to unseal.
        </div>
      )}

      {(d.actions as ServiceAction[] ?? []).length > 0 && (
        <>
          <SectionTitle>Actions</SectionTitle>
          <div className="flex flex-wrap gap-2">
            {(d.actions as ServiceAction[]).map((a) => (
              <ActionButton key={a.id} action={a} serviceId={serviceId} onDone={onRefresh} />
            ))}
          </div>
        </>
      )}
    </>
  )
}

function DetailBody({ svc, detail, onRefresh }: { svc: ServiceHealth; detail: ServiceDetail; onRefresh: () => void }) {
  if (svc.category === 'database')       return <PostgresDetail d={detail} />
  if (svc.category === 'cache')          return <RedisDetail d={detail} />
  if (svc.category === 'queue')          return <RabbitMQDetail d={detail} />
  if (svc.category === 'search')         return <ElasticsearchDetail d={detail} />
  if (svc.category === 'storage')        return <MinioDetail d={detail} />
  if (svc.id === 'ai-engine')            return <AiEngineDetail d={detail} serviceId={svc.id} onRefresh={onRefresh} />
  if (svc.id === 'vault')                return <VaultDetail d={detail} serviceId={svc.id} onRefresh={onRefresh} />
  if (svc.category === 'worker')         return <WorkerDetail d={detail} />
  return <p className="text-xs text-slate-500 mt-4">No additional detail available.</p>
}

// ─── main drawer ─────────────────────────────────────────────────────────────

interface Props {
  svc: ServiceHealth | null
  onClose: () => void
}

export default function ServiceDrawer({ svc, onClose }: Props) {
  const [detail, setDetail] = useState<ServiceDetail | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (id: string) => {
    setLoading(true)
    setDetail(null)
    try {
      const res = await getServiceDetail(id)
      setDetail(res.data)
    } catch {
      setDetail({ actions: [], error: 'Failed to load service details' })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (svc) load(svc.id)
  }, [svc, load])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const isOpen = !!svc

  return (
    <>
      {/* backdrop */}
      <div
        aria-hidden="true"
        onClick={onClose}
        className={`fixed inset-0 bg-black/50 z-40 transition-opacity duration-200 ${
          isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
      />

      {/* slide-over panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={svc ? `${svc.name} service details` : 'Service details'}
        className={`fixed top-0 right-0 h-full w-full max-w-md bg-cyber-surface border-l border-cyber-border z-50 flex flex-col shadow-2xl transition-transform duration-300 ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {svc && (
          <>
            {/* header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-cyber-border flex-shrink-0">
              <div>
                <h2 className="text-base font-bold text-white">{svc.name}</h2>
                <p className="text-xs text-slate-500 capitalize mt-0.5">
                  {svc.description ?? svc.category} · <span className={
                    svc.status === 'healthy' ? 'text-emerald-400' :
                    svc.status === 'degraded' ? 'text-amber-400' : 'text-rose-400'
                  }>{svc.status}</span>
                </p>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => load(svc.id)}
                  disabled={loading}
                  title="Refresh"
                  aria-label="Refresh service details"
                  className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-cyber-border transition-colors disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-primary/50"
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                </button>
                <button
                  onClick={onClose}
                  aria-label="Close drawer"
                  className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-cyber-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-primary/50"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* status banner */}
            <div className="px-5 pt-4 pb-3">
              {svc.status !== 'healthy' ? (
                <div className="flex items-start gap-2 bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2.5">
                  <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                  <p className="text-xs text-rose-300">{svc.error ?? `Service is ${svc.status}`}</p>
                </div>
              ) : svc.latency_ms !== undefined ? (
                <div className="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2">
                  <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                  <p className="text-xs text-emerald-300">Healthy · {svc.latency_ms} ms</p>
                </div>
              ) : null}
            </div>

            {/* scrollable body */}
            <div className="flex-1 overflow-y-auto px-5 pt-1 pb-8 border-t border-cyber-border/50">
              {loading && (
                <div className="flex justify-center py-12"><LoadingSpinner size="md" /></div>
              )}

              {!loading && detail && (
                <>
                  {detail.error ? (
                    <p className="mt-4 text-xs text-rose-400 font-mono bg-rose-500/10 rounded-lg px-3 py-2">
                      {detail.error}
                    </p>
                  ) : (
                    <DetailBody svc={svc} detail={detail} onRefresh={() => load(svc.id)} />
                  )}

                  {/* quick links */}
                  {svc.id === 'rabbitmq' && (
                    <a href="http://localhost:15672" target="_blank" rel="noreferrer"
                      className="flex items-center gap-2 mt-5 text-xs text-cyber-primary hover:underline">
                      <ExternalLink className="w-3.5 h-3.5" />
                      Open RabbitMQ Management UI
                    </a>
                  )}
                  {svc.id === 'minio' && (
                    <a href="http://localhost:9001" target="_blank" rel="noreferrer"
                      className="flex items-center gap-2 mt-5 text-xs text-cyber-primary hover:underline">
                      <ExternalLink className="w-3.5 h-3.5" />
                      Open MinIO Console
                    </a>
                  )}

                  {/* actions */}
                  {detail.actions?.length > 0 && (
                    <>
                      <SectionTitle>Actions</SectionTitle>
                      <div className="space-y-2">
                        {detail.actions.map((a) => (
                          <ActionButton key={a.id} action={a} serviceId={svc.id} onDone={() => load(svc.id)} />
                        ))}
                      </div>
                    </>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </div>
    </>
  )
}
