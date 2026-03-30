import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import {
  ArrowLeft, Bot, XCircle, RefreshCw, AlertTriangle, Wifi, WifiOff,
  FileDown, ChevronDown, CheckCircle2, Loader2, Clock, ChevronRight,
  Shield, Zap, BarChart2, FileText as FileTextIcon, Search as SearchIcon,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { getScan, cancelScan } from '../../api/scans'
import { generateReport, downloadReport } from '../../api/reports'
import { startAnalysis, getAnalysisStatus } from '../../api/ai'
import { setSelectedScan, updateScan } from '../../store/slices/scansSlice'
import type { RootState } from '../../store'
import Badge from '../../components/common/Badge'
import StatusDot from '../../components/common/StatusDot'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import { usePolling } from '../../hooks/usePolling'
import { useScanWebSocket } from '../../hooks/useScanWebSocket'
import { formatDate, formatDuration, scanTypeLabel } from '../../utils/formatters'
import type { ScanStatus } from '../../types'

// ── Pipeline stage definitions ────────────────────────────────────────────────
const PIPELINE_STAGES = [
  { key: 'recon',    label: 'Reconnaissance',   icon: SearchIcon,   activeBefore: 30  },
  { key: 'strategy', label: 'Scan Strategy',     icon: Zap,          activeBefore: 90  },
  { key: 'tools',    label: 'Tool Execution',    icon: Shield,       activeBefore: 180 },
  { key: 'triage',   label: 'Triage',            icon: BarChart2,    activeBefore: 240 },
  { key: 'report',   label: 'Report',            icon: FileTextIcon, activeBefore: 320 },
] as const

function stageIndex(elapsed: number) {
  for (let i = 0; i < PIPELINE_STAGES.length; i++) {
    if (elapsed < PIPELINE_STAGES[i].activeBefore) return i
  }
  return PIPELINE_STAGES.length - 1
}

// ── AI Panel ──────────────────────────────────────────────────────────────────
interface AiPanelProps {
  aiStatus: string | null
  aiResult: Record<string, unknown> | null
  elapsedSecs: number
  onStart: () => void
  onRetry: () => void
  starting: boolean
}

function AiPanel({ aiStatus, aiResult, elapsedSecs, onStart, onRetry, starting }: AiPanelProps) {
  const current = stageIndex(elapsedSecs)

  const fmtElapsed = (s: number) => {
    const m = Math.floor(s / 60); const sec = s % 60
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`
  }

  // Extract key fields from result
  const recon = aiResult?.recon as Record<string, unknown> | undefined
  const triage = aiResult?.triage as Record<string, unknown> | undefined
  const riskLevel = recon?.risk_level as string | undefined
  const assets = (recon?.high_value_assets as unknown[]) ?? []
  const vulns = (triage?.triaged_vulnerabilities as unknown[]) ?? []
  const critHigh = vulns.filter((v: unknown) => {
    const vuln = v as Record<string, unknown>
    return vuln.severity === 'Critical' || vuln.severity === 'High'
  }).length

  const riskColor = {
    critical: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
    high:     'text-orange-400 bg-orange-500/10 border-orange-500/30',
    medium:   'text-amber-400 bg-amber-500/10 border-amber-500/30',
    low:      'text-cyan-400 bg-cyan-500/10 border-cyan-500/30',
  }[riskLevel ?? ''] ?? 'text-slate-400 bg-slate-500/10 border-slate-500/30'

  return (
    <div className="bg-cyber-surface border border-cyber-border rounded-xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-cyber-primary" />
          <h2 className="text-sm font-semibold text-slate-300">AI Analysis</h2>
        </div>
        {aiStatus === 'running' && (
          <span className="flex items-center gap-1.5 text-xs text-amber-400">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Running · <Clock className="w-3 h-3" /> {fmtElapsed(elapsedSecs)}
          </span>
        )}
        {aiStatus === 'completed' && (
          <span className="flex items-center gap-1.5 text-xs text-emerald-400">
            <CheckCircle2 className="w-3.5 h-3.5" /> Completed · {fmtElapsed(elapsedSecs)}
          </span>
        )}
        {aiStatus === 'failed' && (
          <span className="flex items-center gap-1.5 text-xs text-rose-400">
            <XCircle className="w-3.5 h-3.5" /> Failed
          </span>
        )}
      </div>

      {/* ── Idle ────────────────────────────────────────────────── */}
      {!aiStatus && (
        <div className="space-y-3">
          <p className="text-xs text-slate-400 leading-relaxed">
            Run the full AI-driven VAPT pipeline on this scan:&nbsp;
            <span className="text-slate-300">Reconnaissance → Scan Strategy → Tool Execution → Triage → Report</span>.
          </p>
          <p className="text-xs text-slate-500">
            ⚠ CPU-only inference takes <strong className="text-slate-400">2–10 minutes</strong>. Results will appear in the AI Chat history.
          </p>
          <button
            onClick={onStart}
            disabled={starting}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-cyber-primary/10 border border-cyber-primary/30 text-cyber-primary hover:bg-cyber-primary/20 disabled:opacity-50 transition-colors"
          >
            {starting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bot className="w-4 h-4" />}
            {starting ? 'Starting…' : 'Start AI Analysis'}
          </button>
        </div>
      )}

      {/* ── Running — pipeline progress ─────────────────────────── */}
      {aiStatus === 'running' && (
        <div className="space-y-3">
          <div className="flex items-center gap-0">
            {PIPELINE_STAGES.map((stage, i) => {
              const Icon = stage.icon
              const done = i < current
              const active = i === current
              return (
                <div key={stage.key} className="flex items-center">
                  <div className={`flex flex-col items-center gap-1 px-2 py-1.5 rounded-lg transition-all ${
                    done   ? 'text-emerald-400' :
                    active ? 'text-cyber-primary bg-cyber-primary/10' :
                             'text-slate-600'
                  }`}>
                    {done
                      ? <CheckCircle2 className="w-4 h-4" />
                      : active
                        ? <Loader2 className="w-4 h-4 animate-spin" />
                        : <Icon className="w-4 h-4" />
                    }
                    <span className="text-[10px] font-medium whitespace-nowrap">{stage.label}</span>
                  </div>
                  {i < PIPELINE_STAGES.length - 1 && (
                    <ChevronRight className={`w-3 h-3 flex-shrink-0 mx-0.5 ${i < current ? 'text-emerald-400/60' : 'text-slate-700'}`} />
                  )}
                </div>
              )
            })}
          </div>
          <div className="w-full bg-cyber-border rounded-full h-1">
            <div
              className="bg-cyber-primary h-1 rounded-full transition-all duration-1000"
              style={{ width: `${Math.min(100, (elapsedSecs / 320) * 100)}%` }}
            />
          </div>
          <p className="text-xs text-slate-500">
            Currently: <span className="text-slate-300">{PIPELINE_STAGES[current].label}</span> — please wait, this can take several minutes on CPU-only inference.
          </p>
        </div>
      )}

      {/* ── Completed — result summary ───────────────────────────── */}
      {aiStatus === 'completed' && aiResult && (
        <div className="space-y-3">
          {/* Pipeline done */}
          <div className="flex items-center gap-1 flex-wrap">
            {PIPELINE_STAGES.map((stage, i) => (
              <div key={stage.key} className="flex items-center">
                <span className="flex items-center gap-1 text-[10px] text-emerald-400 px-1.5 py-0.5 rounded bg-emerald-400/10">
                  <CheckCircle2 className="w-3 h-3" /> {stage.label}
                </span>
                {i < PIPELINE_STAGES.length - 1 && <ChevronRight className="w-3 h-3 text-emerald-400/40 mx-0.5" />}
              </div>
            ))}
          </div>

          {/* Key metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {riskLevel && (
              <div className={`border rounded-lg p-3 text-center ${riskColor}`}>
                <p className="text-lg font-bold uppercase">{riskLevel}</p>
                <p className="text-[10px] opacity-70 mt-0.5">Risk Level</p>
              </div>
            )}
            {assets.length > 0 && (
              <div className="border border-amber-500/30 bg-amber-500/10 text-amber-400 rounded-lg p-3 text-center">
                <p className="text-lg font-bold">{assets.length}</p>
                <p className="text-[10px] opacity-70 mt-0.5">High-Value Assets</p>
              </div>
            )}
            {vulns.length > 0 && (
              <div className="border border-orange-500/30 bg-orange-500/10 text-orange-400 rounded-lg p-3 text-center">
                <p className="text-lg font-bold">{critHigh}</p>
                <p className="text-[10px] opacity-70 mt-0.5">Crit/High Findings</p>
              </div>
            )}
          </div>

          {/* Asset list */}
          {assets.length > 0 && (
            <div>
              <p className="text-xs text-slate-500 mb-1">High-value assets identified:</p>
              <ul className="space-y-0.5">
                {assets.slice(0, 5).map((a, i) => (
                  <li key={i} className="text-xs text-slate-300 flex items-start gap-1.5">
                    <span className="text-cyber-primary mt-0.5">•</span> {String(a)}
                  </li>
                ))}
                {assets.length > 5 && <li className="text-xs text-slate-500">+{assets.length - 5} more</li>}
              </ul>
            </div>
          )}

          {/* Raw result toggle */}
          <details className="group">
            <summary className="text-xs text-slate-500 cursor-pointer hover:text-slate-300 transition-colors list-none flex items-center gap-1">
              <ChevronRight className="w-3 h-3 group-open:rotate-90 transition-transform" /> Raw analysis output
            </summary>
            <pre className="mt-2 p-3 bg-cyber-bg rounded-lg text-xs text-slate-400 overflow-auto border border-cyber-border max-h-60">
              {JSON.stringify(aiResult, null, 2)}
            </pre>
          </details>

          {/* Chat link */}
          <Link to="/ai"
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium rounded-lg bg-cyber-primary/10 border border-cyber-primary/30 text-cyber-primary hover:bg-cyber-primary/20 transition-colors">
            <Bot className="w-3.5 h-3.5" /> Open in AI Chat to discuss findings →
          </Link>
        </div>
      )}

      {/* ── Failed ──────────────────────────────────────────────── */}
      {aiStatus === 'failed' && (
        <div className="space-y-3">
          <div className="flex gap-2 bg-rose-500/10 border border-rose-500/20 rounded-lg p-3">
            <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-semibold text-rose-400">Analysis failed</p>
              <p className="text-xs text-rose-300/70 mt-0.5">
                {(aiResult as Record<string, unknown> | null)?.error as string
                  ?? 'The AI engine encountered an error. Check that Ollama is running and a model is loaded.'}
              </p>
            </div>
          </div>
          <button onClick={onRetry}
            className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg border border-cyber-border text-slate-400 hover:text-white hover:border-cyber-primary transition-colors">
            <RefreshCw className="w-3.5 h-3.5" /> Retry Analysis
          </button>
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ScanDetailPage() {
  const { id } = useParams<{ id: string }>()
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const scan = useSelector((s: RootState) => s.scans.selectedScan)
  const [loading, setLoading] = useState(true)
  const [aiJobId, setAiJobId] = useState<string | null>(null)
  const [aiStatus, setAiStatus] = useState<string | null>(null)
  const [aiResult, setAiResult] = useState<Record<string, unknown> | null>(null)
  const [aiStarting, setAiStarting] = useState(false)
  const [elapsedSecs, setElapsedSecs] = useState(0)
  const [exportOpen, setExportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    getScan(id).then((r) => {
      dispatch(setSelectedScan(r.data))
    }).catch(() => toast.error('Failed to load scan')).finally(() => setLoading(false))
  }, [id, dispatch])

  // Elapsed timer while AI is running
  useEffect(() => {
    if (aiStatus === 'running') {
      setElapsedSecs(0)
      timerRef.current = setInterval(() => setElapsedSecs(s => s + 1), 1000)
    } else {
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [aiStatus])

  const isLive = scan?.status === 'running' || scan?.status === 'queued'
  const [usePollingFallback, setUsePollingFallback] = useState(false)

  const { connected: wsConnected } = useScanWebSocket(id, isLive && !usePollingFallback, {
    onError: () => setUsePollingFallback(true),
  })

  usePolling(async () => {
    if (!id) return
    try {
      const r = await getScan(id)
      dispatch(updateScan(r.data))
      dispatch(setSelectedScan(r.data))
    } catch {}
  }, 5000, isLive && usePollingFallback)

  // Poll AI job status
  usePolling(async () => {
    if (!aiJobId) return
    try {
      const r = await getAnalysisStatus(aiJobId)
      const validStatuses = ['running', 'completed', 'failed']
      if (validStatuses.includes(r.data.status)) setAiStatus(r.data.status)
      if (r.data.status !== 'running') {
        setAiJobId(null)
        if (r.data.result) setAiResult(r.data.result as Record<string, unknown>)
        if (r.data.status === 'completed') toast.success('AI analysis complete!')
        if (r.data.status === 'failed') toast.error('AI analysis failed')
      }
    } catch (err) {
      console.error('AI status poll failed:', err)
      setAiJobId(null)
    }
  }, 4000, !!aiJobId)

  const handleCancel = async () => {
    if (!scan) return
    try {
      const r = await cancelScan(scan.id)
      dispatch(updateScan(r.data))
      dispatch(setSelectedScan(r.data))
      toast.success('Scan cancelled')
    } catch {
      toast.error('Failed to cancel')
    }
  }

  const handleExport = async (format: 'html' | 'json', report_type: 'full' | 'executive' | 'technical') => {
    if (!scan) return
    setExporting(true)
    setExportOpen(false)
    try {
      const genRes = await generateReport({ scan_id: scan.id, format, report_type })
      const reportId = genRes.data.id
      const dlRes = await downloadReport(reportId, format)
      if (format === 'html') {
        const blob = new Blob([dlRes.data as BlobPart], { type: 'text/html' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url; a.download = `${scan.name}-${report_type}-report.html`; a.click()
        URL.revokeObjectURL(url)
      } else {
        const blob = new Blob([JSON.stringify(dlRes.data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url; a.download = `${scan.name}-${report_type}-report.json`; a.click()
        URL.revokeObjectURL(url)
      }
      toast.success('Report downloaded')
    } catch {
      toast.error('Failed to generate report')
    } finally {
      setExporting(false)
    }
  }

  const handleAiAnalyze = async () => {
    if (!scan) return
    setAiStarting(true)
    try {
      const r = await startAnalysis({ scan_id: scan.id, target: scan.target, scan_type: scan.scan_type })
      setAiJobId(r.data.job_id)
      setAiStatus('running')
      setAiResult(null)
      toast.success('AI analysis started')
    } catch {
      toast.error('AI engine unavailable')
    } finally {
      setAiStarting(false)
    }
  }

  if (loading) return <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>
  if (!scan) return <div className="text-center py-20 text-slate-500">Scan not found</div>

  const rs = scan.result_summary
  const severities = [
    { label: 'Critical', key: 'critical', color: 'border-rose-500/30 bg-rose-500/10 text-rose-400' },
    { label: 'High',     key: 'high',     color: 'border-orange-500/30 bg-orange-500/10 text-orange-400' },
    { label: 'Medium',   key: 'medium',   color: 'border-amber-500/30 bg-amber-500/10 text-amber-400' },
    { label: 'Low',      key: 'low',      color: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-400' },
  ] as const

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/scans')} className="text-slate-400 hover:text-white transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-white">{scan.name}</h1>
              <Badge type="scan_type" value={scan.scan_type} />
              <span className="flex items-center gap-1.5">
                <StatusDot status={scan.status as ScanStatus} />
                <Badge type="status" value={scan.status} />
              </span>
              {isLive && wsConnected && <span className="flex items-center gap-1 text-xs text-cyan-400"><Wifi className="w-3 h-3" /> Live</span>}
              {isLive && !wsConnected && usePollingFallback && <span className="flex items-center gap-1 text-xs text-amber-400"><WifiOff className="w-3 h-3" /><RefreshCw className="w-3 h-3 animate-spin" /> Polling</span>}
              {isLive && !wsConnected && !usePollingFallback && <span className="flex items-center gap-1 text-xs text-cyan-400/50"><RefreshCw className="w-3 h-3 animate-spin" /> Connecting…</span>}
            </div>
            {scan.description && <p className="text-sm text-slate-500 mt-1">{scan.description}</p>}
          </div>
        </div>
        <div className="flex gap-2 flex-shrink-0">
          {scan.status === 'completed' && (
            <div className="relative">
              <button onClick={() => setExportOpen(v => !v)} disabled={exporting}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-50 transition-colors">
                <FileDown className="w-3.5 h-3.5" />
                {exporting ? 'Exporting…' : 'Export Report'}
                <ChevronDown className="w-3 h-3" />
              </button>
              {exportOpen && (
                <div className="absolute right-0 top-full mt-1 bg-cyber-surface border border-cyber-border rounded-lg shadow-xl z-20 min-w-[200px]">
                  {(['full', 'executive', 'technical'] as const).map(rt => (
                    ['html', 'json'].map(fmt => (
                      <button key={`${rt}-${fmt}`}
                        onClick={() => handleExport(fmt as 'html' | 'json', rt)}
                        className="w-full text-left px-4 py-2.5 text-xs text-slate-300 hover:bg-cyber-primary/10 hover:text-white transition-colors capitalize">
                        {rt} Report ({fmt.toUpperCase()})
                      </button>
                    ))
                  ))}
                </div>
              )}
            </div>
          )}
          {isLive && (
            <button onClick={handleCancel}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-rose-500/30 text-rose-400 hover:bg-rose-500/10 transition-colors">
              <XCircle className="w-3.5 h-3.5" /> Cancel
            </button>
          )}
        </div>
      </div>

      {/* Info grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Target',    value: scan.target },
          { label: 'Scan Type', value: scanTypeLabel[scan.scan_type] ?? scan.scan_type },
          { label: 'Created',   value: formatDate(scan.created_at) },
          { label: 'Duration',  value: formatDuration(scan.started_at, scan.completed_at) },
        ].map(({ label, value }) => (
          <div key={label} className="bg-cyber-surface border border-cyber-border rounded-xl p-4">
            <p className="text-xs text-slate-500 mb-1">{label}</p>
            <p className="text-sm font-medium text-white break-all">{value}</p>
          </div>
        ))}
      </div>

      {/* Scan error */}
      {scan.status === 'failed' && scan.error && (
        <div className="flex gap-3 bg-rose-500/10 border border-rose-500/30 rounded-xl p-4">
          <AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-rose-400 mb-1">Scan Failed</p>
            <p className="text-sm text-rose-300/80 font-mono">{scan.error}</p>
          </div>
        </div>
      )}

      {/* Scan results */}
      {scan.status === 'completed' && rs && (
        <div className="bg-cyber-surface border border-cyber-border rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-semibold text-slate-300">Scan Results</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {severities.map(({ label, key, color }) => (
              <div key={key} className={`border rounded-xl p-4 text-center ${color}`}>
                <p className="text-2xl font-bold">{rs?.[key] ?? 0}</p>
                <p className="text-xs mt-1 opacity-80">{label}</p>
              </div>
            ))}
          </div>
          {rs.ports_found !== undefined && (
            <p className="text-sm text-slate-400">Open ports found: <span className="text-cyber-primary font-semibold">{rs.ports_found}</span></p>
          )}
          <details className="group">
            <summary className="text-xs text-slate-500 cursor-pointer hover:text-slate-300 transition-colors">Raw result summary ▾</summary>
            <pre className="mt-2 p-3 bg-cyber-bg rounded-lg text-xs text-slate-400 overflow-auto border border-cyber-border">
              {JSON.stringify(rs, null, 2)}
            </pre>
          </details>
        </div>
      )}

      {/* Live scan banner */}
      {isLive && (
        <div className="flex items-center gap-3 bg-cyan-500/5 border border-cyan-500/20 rounded-xl p-4">
          <LoadingSpinner size="sm" />
          {wsConnected
            ? <p className="text-sm text-cyan-400">Scan in progress — receiving live updates via WebSocket…</p>
            : usePollingFallback
              ? <p className="text-sm text-amber-400">Scan in progress — polling every 5 seconds…</p>
              : <p className="text-sm text-cyan-400/60">Scan in progress — connecting to live stream…</p>
          }
        </div>
      )}

      {/* AI Analysis panel — always visible */}
      <AiPanel
        aiStatus={aiStatus}
        aiResult={aiResult}
        elapsedSecs={elapsedSecs}
        onStart={handleAiAnalyze}
        onRetry={() => { setAiStatus(null); setAiResult(null) }}
        starting={aiStarting}
      />
    </div>

  )
}
