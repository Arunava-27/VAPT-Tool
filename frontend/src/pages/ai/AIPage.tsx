import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Bot, Send, RefreshCw, ChevronRight, Cpu, CheckCircle2, XCircle, Loader2, Trash2,
  AlertTriangle, Settings, Zap, Clock, ChevronDown, ExternalLink, X
} from 'lucide-react'
import clsx from 'clsx'
import {
  sendChat, listAnalyses, getAiInfo, listModels, updateAiConfig,
  type ChatMessage, type AnalyzeJob, type AiInfo, type ModelList
} from '../../api/ai'

interface DisplayMessage extends ChatMessage {
  id: string
  ts: Date
  latency_ms?: number
  provider?: string
  model?: string
  error?: boolean
  queue_depth?: number
}

function formatResult(result: Record<string, unknown>): string {
  const parts: string[] = []
  if (result.recon) parts.push('**Recon:**\n```json\n' + JSON.stringify(result.recon, null, 2) + '\n```')
  if (result.strategy) parts.push('**Strategy:**\n```json\n' + JSON.stringify(result.strategy, null, 2) + '\n```')
  if (result.triage) parts.push('**Triage:**\n```json\n' + JSON.stringify(result.triage, null, 2) + '\n```')
  if (result.report) parts.push('**Report:**\n```json\n' + JSON.stringify(result.report, null, 2) + '\n```')
  return parts.join('\n\n') || JSON.stringify(result, null, 2)
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'completed') return (
    <span className="flex items-center gap-1 text-xs text-emerald-400">
      <CheckCircle2 className="w-3 h-3" /> Done
    </span>
  )
  if (status === 'failed') return (
    <span className="flex items-center gap-1 text-xs text-rose-400">
      <XCircle className="w-3 h-3" /> Failed
    </span>
  )
  return (
    <span className="flex items-center gap-1 text-xs text-amber-400">
      <Loader2 className="w-3 h-3 animate-spin" /> Running
    </span>
  )
}

function MessageContent({ content }: { content: string }) {
  const lines = content.split('\n')
  const rendered: React.ReactNode[] = []
  let codeBlock: string[] = []
  let inCode = false

  lines.forEach((line, i) => {
    if (line.startsWith('```')) {
      if (!inCode) { inCode = true; codeBlock = [] }
      else {
        rendered.push(
          <pre key={i} className="bg-cyber-bg rounded p-2 text-xs overflow-x-auto my-1 border border-cyber-border text-emerald-300 font-mono">
            <code>{codeBlock.join('\n')}</code>
          </pre>
        )
        inCode = false; codeBlock = []
      }
      return
    }
    if (inCode) { codeBlock.push(line); return }

    const boldParts = line.split(/\*\*(.*?)\*\*/g)
    const formatted = boldParts.map((p, j) => j % 2 === 1 ? <strong key={j} className="text-white">{p}</strong> : p)

    if (line.startsWith('## ')) rendered.push(<p key={i} className="text-base font-semibold text-white mt-2 mb-1">{line.slice(3)}</p>)
    else if (line.startsWith('# ')) rendered.push(<p key={i} className="text-lg font-bold text-white mt-2 mb-1">{line.slice(2)}</p>)
    else if (line.startsWith('- ') || line.startsWith('* ')) rendered.push(<p key={i} className="flex gap-2 ml-2"><span className="text-cyber-primary">•</span><span>{formatted}</span></p>)
    else if (line.trim() === '') rendered.push(<div key={i} className="h-1" />)
    else rendered.push(<p key={i} className="leading-relaxed">{formatted}</p>)
  })

  return <div className="text-sm space-y-0.5">{rendered}</div>
}

/** Formats seconds into a human-readable estimate like "~45 s" or "~3 min" */
function fmtWait(seconds: number): string {
  if (seconds < 90) return `~${seconds} s`
  return `~${Math.round(seconds / 60)} min`
}

/** Animated elapsed-time counter shown while waiting for a CPU inference */
function ElapsedTimer({ startedAt, estimatedSeconds }: { startedAt: Date; estimatedSeconds?: number }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt.getTime()) / 1000)), 500)
    return () => clearInterval(id)
  }, [startedAt])
  const pct = estimatedSeconds ? Math.min(98, Math.round((elapsed / estimatedSeconds) * 100)) : null
  return (
    <div className="flex flex-col gap-1.5 w-full max-w-xs">
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <Loader2 className="w-3.5 h-3.5 text-cyber-primary animate-spin flex-shrink-0" />
        <span>CPU inference running… {elapsed}s elapsed</span>
      </div>
      {pct !== null && (
        <div className="w-full bg-cyber-border rounded-full h-1 overflow-hidden">
          <div
            className="h-full bg-cyber-primary/70 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
      {estimatedSeconds && (
        <p className="text-[10px] text-slate-500">
          Estimated total: {fmtWait(estimatedSeconds)} · CPU-only mode
        </p>
      )}
    </div>
  )
}

/** Persistent amber banner shown whenever CPU-only inference is active */
function CpuWarningBanner({
  info,
  onOpenSettings,
}: {
  info: AiInfo
  onOpenSettings: () => void
}) {
  const [dismissed, setDismissed] = useState(false)
  if (!info.is_cpu_only || dismissed) return null

  const est = info.estimated_wait_seconds
  const model = info.active_model ?? 'local'

  return (
    <div className="flex items-start gap-3 mx-4 mt-3 mb-0 px-3 py-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs flex-shrink-0">
      <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-amber-300 font-medium">
          CPU-only inference active
          {est && <span className="ml-1 font-normal text-amber-400/80">— expect {fmtWait(est)} per response</span>}
        </p>
        <p className="text-amber-400/70 mt-0.5 leading-relaxed">
          Running <code className="font-mono text-amber-300">{model}</code> on CPU.
          {' '}For instant responses, add an <strong className="text-amber-300">OpenAI</strong> or{' '}
          <strong className="text-amber-300">Anthropic</strong> key in <code className="font-mono">.env</code>,
          or{' '}
          <button onClick={onOpenSettings} className="underline text-amber-300 hover:text-amber-200 transition-colors">
            switch to llama3.2:1b
          </button>
          {' '}for the fastest local option.
        </p>
      </div>
      <button onClick={() => setDismissed(true)} className="text-amber-500 hover:text-amber-300 transition-colors flex-shrink-0">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}

/** Inline panel to switch Ollama model or configure cloud provider */
function ModelSwitcherPanel({
  info,
  models,
  onClose,
  onApplied,
}: {
  info: AiInfo
  models: ModelList | null
  onClose: () => void
  onApplied: (newModel: string) => void
}) {
  const [selectedModel, setSelectedModel] = useState(info.active_model ?? '')
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const quickModels = [
    { id: 'llama3.2:1b',  label: 'llama3.2:1b',  note: '~1.3 GB RAM · ~30-60 s on CPU  ⚡ fastest' },
    { id: 'llama3.2',     label: 'llama3.2 (3B)', note: '~3.8 GB RAM · ~3-5 min on CPU' },
    { id: 'phi3:mini',    label: 'phi3:mini',     note: '~2.4 GB RAM · ~60-90 s on CPU' },
  ]

  // Merge quick models with any locally pulled models, deduplicating
  const pulledModels = (models?.models ?? []).filter(
    m => !quickModels.find(q => q.id === m)
  )

  const handleApply = async () => {
    if (!selectedModel) return
    setApplying(true)
    setError(null)
    try {
      await updateAiConfig(selectedModel, 'ollama')
      onApplied(selectedModel)
      onClose()
    } catch (e: unknown) {
      setError((e as { message?: string })?.message ?? 'Failed to update model')
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="mx-4 mt-2 mb-0 p-4 rounded-lg bg-cyber-surface border border-cyber-primary/30 flex-shrink-0 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Settings className="w-4 h-4 text-cyber-primary" />
          <span className="text-sm font-semibold text-white">LLM Configuration</span>
        </div>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Cloud provider hint */}
      <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300">
        <div className="flex items-center gap-1.5 font-medium mb-1">
          <Zap className="w-3.5 h-3.5" /> Use cloud inference for instant responses
        </div>
        <p className="text-emerald-400/70 leading-relaxed">
          Add <code className="font-mono">OPENAI_API_KEY</code> or <code className="font-mono">ANTHROPIC_API_KEY</code>{' '}
          to your <code className="font-mono">.env</code> file and restart the ai-engine container.
          Cloud providers take priority over local Ollama automatically.
        </p>
      </div>

      {/* Local model picker */}
      <div className="space-y-1.5">
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Local Ollama Model</p>

        {/* Quick-select options */}
        <div className="space-y-1">
          {quickModels.map(m => (
            <label
              key={m.id}
              className={clsx(
                'flex items-start gap-2.5 p-2 rounded-lg cursor-pointer border transition-colors',
                selectedModel === m.id
                  ? 'bg-cyber-primary/10 border-cyber-primary/40'
                  : 'bg-cyber-bg border-cyber-border hover:border-cyber-primary/20'
              )}
            >
              <input
                type="radio"
                name="model"
                value={m.id}
                checked={selectedModel === m.id}
                onChange={() => setSelectedModel(m.id)}
                className="mt-0.5 accent-cyber-primary"
              />
              <div>
                <p className="text-xs font-mono text-white">{m.label}</p>
                <p className="text-[10px] text-slate-500">{m.note}</p>
              </div>
              {m.id === 'llama3.2:1b' && (
                <span className="ml-auto text-[10px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded font-medium">
                  Recommended
                </span>
              )}
            </label>
          ))}
        </div>

        {/* Any other pulled models */}
        {pulledModels.length > 0 && (
          <div className="space-y-1">
            <p className="text-[10px] text-slate-600 uppercase tracking-wider pt-1">Other pulled models</p>
            {pulledModels.map(m => (
              <label
                key={m}
                className={clsx(
                  'flex items-center gap-2.5 p-2 rounded-lg cursor-pointer border transition-colors',
                  selectedModel === m
                    ? 'bg-cyber-primary/10 border-cyber-primary/40'
                    : 'bg-cyber-bg border-cyber-border hover:border-cyber-primary/20'
                )}
              >
                <input
                  type="radio"
                  name="model"
                  value={m}
                  checked={selectedModel === m}
                  onChange={() => setSelectedModel(m)}
                  className="accent-cyber-primary"
                />
                <span className="text-xs font-mono text-white">{m}</span>
              </label>
            ))}
          </div>
        )}

        {/* Manual input */}
        <div className="pt-1">
          <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">Or type a model name</p>
          <input
            type="text"
            value={selectedModel}
            onChange={e => setSelectedModel(e.target.value)}
            placeholder="e.g. llama3.2:1b"
            className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyber-primary/50"
          />
          <p className="text-[10px] text-slate-600 mt-1">
            The model must already be pulled in the Ollama container.
            Pull new models with: <code className="font-mono text-slate-500">docker exec vapt-ollama ollama pull &lt;model&gt;</code>
          </p>
        </div>
      </div>

      {error && (
        <p className="text-xs text-rose-400 flex items-center gap-1.5">
          <XCircle className="w-3.5 h-3.5" /> {error}
        </p>
      )}

      <div className="flex gap-2 pt-1">
        <button
          onClick={handleApply}
          disabled={!selectedModel || applying || selectedModel === info.active_model}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyber-primary/20 text-cyber-primary text-xs font-medium hover:bg-cyber-primary/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {applying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
          Apply Model
        </button>
        <a
          href="https://ollama.com/library"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyber-border text-slate-400 text-xs hover:text-slate-200 transition-colors"
        >
          <ExternalLink className="w-3 h-3" /> Browse models
        </a>
      </div>
    </div>
  )
}

export default function AIPage() {
  const [messages, setMessages] = useState<DisplayMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: "Hello! I'm your VAPT AI assistant. I can help you:\n\n- **Analyze** scan results and findings\n- **Explain** vulnerabilities and their impact\n- **Recommend** remediation steps\n- **Answer** questions about your network and infrastructure\n\nSelect an analysis from the history panel, or just ask me anything.",
      ts: new Date(),
    }
  ])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [sendingStartedAt, setSendingStartedAt] = useState<Date | null>(null)
  const [analyses, setAnalyses] = useState<AnalyzeJob[]>([])
  const [loadingAnalyses, setLoadingAnalyses] = useState(false)
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalyzeJob | null>(null)
  const [aiInfo, setAiInfo] = useState<AiInfo | null>(null)
  const [modelList, setModelList] = useState<ModelList | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [showProviderDropdown, setShowProviderDropdown] = useState(false)

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const fetchAnalyses = useCallback(async () => {
    setLoadingAnalyses(true)
    try {
      const r = await listAnalyses()
      setAnalyses(r.data)
    } catch { /* AI engine may be unavailable */ }
    finally { setLoadingAnalyses(false) }
  }, [])

  const refreshAiInfo = useCallback(async () => {
    try {
      const r = await getAiInfo()
      setAiInfo(r.data)
    } catch { /* ignore */ }
  }, [])

  const fetchModels = useCallback(async () => {
    try {
      const r = await listModels()
      setModelList(r.data)
    } catch { /* ignore — models panel shows degraded state */ }
  }, [])

  useEffect(() => {
    fetchAnalyses()
    refreshAiInfo()
    fetchModels()
  }, [fetchAnalyses, refreshAiInfo, fetchModels])

  const buildContext = (job: AnalyzeJob): string => {
    const r = job.result as Record<string, unknown> | undefined
    const parts: string[] = [`Analysis job: ${job.job_id}`, `Status: ${job.status}`]
    if (r?.target) parts.push(`Target: ${r.target}`)
    if (r?.recon) parts.push(`Recon output:\n${JSON.stringify(r.recon, null, 2)}`)
    if (r?.strategy) parts.push(`Strategy:\n${JSON.stringify(r.strategy, null, 2)}`)
    if (r?.triage) parts.push(`Triage results:\n${JSON.stringify(r.triage, null, 2)}`)
    if (r?.report) parts.push(`Report:\n${JSON.stringify(r.report, null, 2)}`)
    return parts.join('\n\n')
  }

  const handleSelectAnalysis = (job: AnalyzeJob) => {
    setSelectedAnalysis(job)
    const r = job.result as Record<string, unknown> | undefined
    const contextMsg: DisplayMessage = {
      id: `ctx-${job.job_id}`,
      role: 'assistant',
      content: `I've loaded the analysis for job \`${job.job_id.slice(0, 8)}…\` (status: **${job.status}**).\n\n${r ? formatResult(r) : 'No results available yet — the job may still be running.'}\n\nFeel free to ask me questions about these findings.`,
      ts: new Date(),
    }
    setMessages(prev => [...prev, contextMsg])
  }

  const handleSend = async () => {
    const text = input.trim()
    if (!text || sending) return

    const userMsg: DisplayMessage = { id: `u-${Date.now()}`, role: 'user', content: text, ts: new Date() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setSending(true)
    setSendingStartedAt(new Date())

    const history: ChatMessage[] = messages
      .filter(m => m.id !== 'welcome' && !m.id.startsWith('ctx-') && !m.error)
      .slice(-10)
      .map(m => ({ role: m.role, content: m.content }))

    const context = selectedAnalysis ? buildContext(selectedAnalysis) : undefined

    try {
      const r = await sendChat(text, context, history)
      setMessages(prev => [...prev, {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: r.data.response,
        ts: new Date(),
        latency_ms: r.data.latency_ms,
        provider: r.data.provider,
        model: r.data.model,
        queue_depth: r.data.queue_depth,
      }])
      // Refresh info to pick up queue_depth changes
      refreshAiInfo()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setMessages(prev => [...prev, {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: `⚠️ ${detail || 'AI Engine is unavailable. Make sure Ollama is running and a model is loaded.'}`,
        ts: new Date(),
        error: true,
      }])
    } finally {
      setSending(false)
      setSendingStartedAt(null)
      textareaRef.current?.focus()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const clearChat = () => {
    setSelectedAnalysis(null)
    setMessages([{ id: 'welcome', role: 'assistant', content: 'Chat cleared. Select an analysis or ask me anything.', ts: new Date() }])
  }

  const handleModelApplied = (newModel: string) => {
    setAiInfo(prev => prev ? { ...prev, active_model: newModel } : prev)
    refreshAiInfo()
    // Add a system notice in chat
    setMessages(prev => [...prev, {
      id: `sys-${Date.now()}`,
      role: 'assistant',
      content: `✅ Switched to model \`${newModel}\`. The next message will use this model.`,
      ts: new Date(),
    }])
  }

  const isCpuOnly = aiInfo?.is_cpu_only ?? false
  const estWait = aiInfo?.estimated_wait_seconds

  return (
    <div className="flex flex-col h-full bg-cyber-bg">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-cyber-border bg-cyber-surface flex-shrink-0">
        <div className="flex items-center gap-3">
          <Bot className="w-6 h-6 text-cyber-primary" />
          <div>
            <h1 className="text-lg font-bold text-white">AI Assistant</h1>
            <p className="text-xs text-slate-400">Chat with AI · Review analysis history</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Model / Provider button */}
          {aiInfo && (
            <div className="relative">
              <button
                onClick={() => { setShowProviderDropdown(v => !v); setShowSettings(false) }}
                className={clsx(
                  'flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors',
                  isCpuOnly
                    ? 'bg-amber-500/10 border-amber-500/30 text-amber-300 hover:bg-amber-500/20'
                    : 'bg-cyber-primary/10 border-cyber-primary/20 text-cyber-primary hover:bg-cyber-primary/20'
                )}
              >
                {isCpuOnly
                  ? <Cpu className="w-3.5 h-3.5" />
                  : <Zap className="w-3.5 h-3.5" />}
                <span className="font-mono">{aiInfo.active_model ?? 'unknown'}</span>
                {isCpuOnly && estWait && (
                  <span className="flex items-center gap-0.5 text-amber-400/70">
                    <Clock className="w-3 h-3" />{fmtWait(estWait)}
                  </span>
                )}
                <ChevronDown className="w-3 h-3 opacity-60" />
              </button>
              {showProviderDropdown && (
                <div className="absolute right-0 top-full mt-1 z-50 w-64 rounded-lg bg-cyber-surface border border-cyber-border shadow-xl p-2 text-xs space-y-1">
                  <p className="text-slate-500 px-2 py-1 uppercase tracking-wider text-[10px]">Switch Provider</p>
                  {(aiInfo.available_providers ?? []).length === 0 && (
                    <p className="px-2 py-1 text-slate-500">No providers available</p>
                  )}
                  {(aiInfo.available_providers ?? []).map(p => (
                    <button
                      key={p}
                      onClick={() => {
                        updateAiConfig(undefined, p).then(() => { refreshAiInfo(); setShowProviderDropdown(false) })
                      }}
                      className={clsx(
                        'w-full text-left px-2 py-1.5 rounded-lg transition-colors',
                        aiInfo.active_provider === p
                          ? 'bg-cyber-primary/10 text-cyber-primary'
                          : 'text-slate-300 hover:bg-cyber-border'
                      )}
                    >
                      {p}
                      {aiInfo.active_provider === p && <span className="ml-1 text-[10px] text-cyber-primary/60">active</span>}
                    </button>
                  ))}
                  <hr className="border-cyber-border my-1" />
                  <button
                    onClick={() => { setShowSettings(true); setShowProviderDropdown(false) }}
                    className="w-full text-left px-2 py-1.5 rounded-lg text-slate-400 hover:bg-cyber-border hover:text-slate-200 transition-colors flex items-center gap-1.5"
                  >
                    <Settings className="w-3 h-3" /> Change Ollama model…
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Persistent CPU warning banner ── */}
      {aiInfo && (
        <CpuWarningBanner
          info={aiInfo}
          onOpenSettings={() => { setShowSettings(true); setShowProviderDropdown(false) }}
        />
      )}

      {/* ── Model switcher panel ── */}
      {showSettings && aiInfo && (
        <ModelSwitcherPanel
          info={aiInfo}
          models={modelList}
          onClose={() => setShowSettings(false)}
          onApplied={handleModelApplied}
        />
      )}

      {/* Body */}
      <div className="flex flex-1 min-h-0">
        {/* Analysis History */}
        <div className="w-64 flex-shrink-0 border-r border-cyber-border bg-cyber-surface flex flex-col">
          <div className="flex items-center justify-between px-4 py-3 border-b border-cyber-border">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Analysis History</span>
            <button onClick={fetchAnalyses} title="Refresh" disabled={loadingAnalyses}
              className="p-1 rounded hover:bg-cyber-border text-slate-400 hover:text-white transition-colors">
              <RefreshCw className={clsx('w-3.5 h-3.5', loadingAnalyses && 'animate-spin')} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto py-1">
            {analyses.length === 0 && !loadingAnalyses && (
              <p className="text-xs text-slate-500 px-4 py-4 leading-relaxed">
                No analyses yet.<br />Run <strong className="text-slate-400">AI Analyze</strong> from a scan detail page to populate history.
              </p>
            )}
            {analyses.map(job => {
              const target = (job.result as Record<string, unknown> | undefined)?.target as string | undefined
              const isSelected = selectedAnalysis?.job_id === job.job_id
              return (
                <button
                  key={job.job_id}
                  onClick={() => handleSelectAnalysis(job)}
                  className={clsx(
                    'w-full flex items-start gap-2 px-3 py-2.5 text-left transition-colors border-b border-cyber-border/40 last:border-0 border-l-2',
                    isSelected ? 'bg-cyber-primary/10 border-l-cyber-primary' : 'hover:bg-cyber-border/40 border-l-transparent'
                  )}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-200 truncate">{target ?? job.job_id.slice(0, 16) + '…'}</p>
                    <div className="mt-0.5"><StatusBadge status={job.status} /></div>
                  </div>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-500 flex-shrink-0 mt-1" />
                </button>
              )
            })}
          </div>
          {selectedAnalysis && (
            <div className="px-3 py-2 border-t border-cyber-border">
              <button onClick={() => setSelectedAnalysis(null)}
                className="text-xs text-slate-500 hover:text-rose-400 flex items-center gap-1 transition-colors">
                <XCircle className="w-3 h-3" /> Clear context
              </button>
            </div>
          )}
        </div>

        {/* Chat */}
        <div className="flex-1 flex flex-col min-w-0">
          {selectedAnalysis && (
            <div className="px-4 py-2 bg-cyber-primary/5 border-b border-cyber-primary/20 flex items-center gap-2 flex-shrink-0">
              <Bot className="w-3.5 h-3.5 text-cyber-primary" />
              <span className="text-xs text-cyber-primary">
                Context: <code className="font-mono">{selectedAnalysis.job_id.slice(0, 12)}…</code>
                {(selectedAnalysis.result as Record<string, unknown> | undefined)?.target
                  ? ` — ${(selectedAnalysis.result as Record<string, unknown>).target}` : ''}
              </span>
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {messages.map(msg => (
              <div key={msg.id} className={clsx('flex gap-3', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
                {msg.role === 'assistant' && (
                  <div className="w-7 h-7 rounded-full bg-cyber-primary/20 border border-cyber-primary/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Bot className="w-4 h-4 text-cyber-primary" />
                  </div>
                )}
                <div className={clsx(
                  'max-w-[80%] rounded-xl px-4 py-3',
                  msg.role === 'user'
                    ? 'bg-cyber-primary/15 border border-cyber-primary/25 text-slate-200'
                    : msg.error
                      ? 'bg-rose-500/10 border border-rose-500/20 text-rose-300'
                      : 'bg-cyber-surface border border-cyber-border text-slate-300'
                )}>
                  {msg.role === 'user'
                    ? <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                    : <MessageContent content={msg.content} />
                  }
                  {msg.latency_ms !== undefined && (
                    <p className="text-[10px] text-slate-600 mt-1.5 flex items-center gap-1.5">
                      <span>{msg.provider}</span>
                      {msg.model && <span className="font-mono opacity-70">· {msg.model}</span>}
                      <span>· {(msg.latency_ms / 1000).toFixed(1)}s</span>
                      {msg.queue_depth !== undefined && msg.queue_depth > 0 && (
                        <span className="text-amber-500/60">· {msg.queue_depth} queued</span>
                      )}
                    </p>
                  )}
                </div>
              </div>
            ))}

            {/* CPU-aware loading indicator */}
            {sending && (
              <div className="flex gap-3 justify-start">
                <div className="w-7 h-7 rounded-full bg-cyber-primary/20 border border-cyber-primary/30 flex items-center justify-center flex-shrink-0">
                  <Bot className="w-4 h-4 text-cyber-primary" />
                </div>
                <div className="bg-cyber-surface border border-cyber-border rounded-xl px-4 py-3">
                  {isCpuOnly && sendingStartedAt
                    ? <ElapsedTimer startedAt={sendingStartedAt} estimatedSeconds={estWait ?? undefined} />
                    : (
                      <div className="flex items-center gap-2">
                        <Loader2 className="w-4 h-4 text-cyber-primary animate-spin" />
                        <span className="text-xs text-slate-400">Thinking…</span>
                      </div>
                    )
                  }
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="px-4 pb-4 pt-2 border-t border-cyber-border flex-shrink-0">
            {/* Queue depth warning when someone else is already running */}
            {(aiInfo?.queue_depth ?? 0) > 0 && !sending && (
              <div className="flex items-center gap-1.5 text-[11px] text-amber-400/80 mb-1.5 px-1">
                <Clock className="w-3 h-3" />
                Another inference is running — your request will queue automatically.
              </div>
            )}
            <div className="flex items-end gap-2 bg-cyber-surface border border-cyber-border rounded-xl px-3 py-2 focus-within:border-cyber-primary/50 transition-colors">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  isCpuOnly && estWait
                    ? `Ask anything… (CPU mode: expect ${fmtWait(estWait)} · Enter to send)`
                    : 'Ask about scans, vulnerabilities, remediation… (Enter to send · Shift+Enter for newline)'
                }
                rows={1}
                disabled={sending}
                className="flex-1 bg-transparent text-sm text-slate-200 placeholder-slate-600 resize-none focus:outline-none min-h-[24px] max-h-32 overflow-y-auto"
                onInput={e => {
                  const t = e.currentTarget
                  t.style.height = 'auto'
                  t.style.height = Math.min(t.scrollHeight, 128) + 'px'
                }}
              />
              <div className="flex items-center gap-1 pb-0.5">
                <button onClick={clearChat} title="Clear chat"
                  className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-cyber-border transition-colors">
                  <Trash2 className="w-4 h-4" />
                </button>
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || sending}
                  className="p-1.5 rounded-lg bg-cyber-primary/20 text-cyber-primary hover:bg-cyber-primary/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Backdrop for dropdowns */}
      {showProviderDropdown && (
        <div className="fixed inset-0 z-40" onClick={() => setShowProviderDropdown(false)} />
      )}
    </div>
  )
}

