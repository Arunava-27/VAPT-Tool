import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { ArrowLeft, Bot, XCircle, RefreshCw, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'
import { getScan, getScanStatus, cancelScan } from '../../api/scans'
import { startAnalysis, getAnalysisStatus } from '../../api/ai'
import { setSelectedScan, updateScan } from '../../store/slices/scansSlice'
import type { RootState } from '../../store'
import Badge from '../../components/common/Badge'
import StatusDot from '../../components/common/StatusDot'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import { usePolling } from '../../hooks/usePolling'
import { formatDate, formatDuration, scanTypeLabel } from '../../utils/formatters'
import type { ScanStatus } from '../../types'

export default function ScanDetailPage() {
  const { id } = useParams<{ id: string }>()
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const scan = useSelector((s: RootState) => s.scans.selectedScan)
  const [loading, setLoading] = useState(true)
  const [aiJobId, setAiJobId] = useState<string | null>(null)
  const [aiStatus, setAiStatus] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    getScan(id).then((r) => {
      dispatch(setSelectedScan(r.data))
    }).catch(() => toast.error('Failed to load scan')).finally(() => setLoading(false))
  }, [id, dispatch])

  const isLive = scan?.status === 'running' || scan?.status === 'queued'

  // Poll status while running
  usePolling(async () => {
    if (!id) return
    try {
      const r = await getScanStatus(id)
      dispatch(updateScan(r.data))
      dispatch(setSelectedScan(r.data))
    } catch {}
  }, 5000, isLive)

  // Poll AI job
  usePolling(async () => {
    if (!aiJobId) return
    try {
      const r = await getAnalysisStatus(aiJobId)
      const validStatuses = ['running', 'completed', 'failed']
      if (validStatuses.includes(r.data.status)) setAiStatus(r.data.status)
      if (r.data.status !== 'running') setAiJobId(null)
    } catch (err) {
      console.error('AI status poll failed:', err)
    }
  }, 4000, !!aiJobId)

  const handleCancel = async () => {
    if (!scan) return
    try {
      const r = await cancelScan(scan.id)
      dispatch(updateScan(r.data))
      dispatch(setSelectedScan(r.data))
      toast.success('Scan cancelled')
    } catch (err) {
      console.error('Cancel failed:', err)
      toast.error('Failed to cancel')
    }
  }

  const handleAiAnalyze = async () => {
    if (!scan) return
    if (!scan.id || !scan.target) {
      toast.error('Invalid scan data')
      return
    }
    try {
      const r = await startAnalysis({ scan_id: scan.id, target: scan.target, scan_type: scan.scan_type })
      setAiJobId(r.data.job_id)
      setAiStatus('running')
      toast.success('AI analysis started')
    } catch (err) {
      console.error('AI analyze failed:', err)
      toast.error('AI engine unavailable')
    }
  }

  if (loading) return <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>
  if (!scan) return <div className="text-center py-20 text-slate-500">Scan not found</div>

  const rs = scan.result_summary
  const severities = [
    { label: 'Critical', key: 'critical', color: 'border-rose-500/30 bg-rose-500/10 text-rose-400' },
    { label: 'High', key: 'high', color: 'border-orange-500/30 bg-orange-500/10 text-orange-400' },
    { label: 'Medium', key: 'medium', color: 'border-amber-500/30 bg-amber-500/10 text-amber-400' },
    { label: 'Low', key: 'low', color: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-400' },
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
              {isLive && <span className="flex items-center gap-1 text-xs text-cyan-400"><RefreshCw className="w-3 h-3 animate-spin" /> Live</span>}
            </div>
            {scan.description && <p className="text-sm text-slate-500 mt-1">{scan.description}</p>}
          </div>
        </div>
        <div className="flex gap-2 flex-shrink-0">
          {isLive && (
            <button onClick={handleCancel}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-rose-500/30 text-rose-400 hover:bg-rose-500/10 transition-colors">
              <XCircle className="w-3.5 h-3.5" /> Cancel
            </button>
          )}
          <button onClick={handleAiAnalyze} disabled={!!aiJobId}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-cyber-primary/30 text-cyber-primary hover:bg-cyber-primary/10 disabled:opacity-50 transition-colors">
            <Bot className="w-3.5 h-3.5" />
              {aiJobId ? `AI: ${aiStatus ?? 'processing'}…` : 'AI Analyse'}
          </button>
        </div>
      </div>

      {/* Info grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Target', value: scan.target },
          { label: 'Scan Type', value: scanTypeLabel[scan.scan_type] ?? scan.scan_type },
          { label: 'Created', value: formatDate(scan.created_at) },
          { label: 'Duration', value: formatDuration(scan.started_at, scan.completed_at) },
        ].map(({ label, value }) => (
          <div key={label} className="bg-cyber-surface border border-cyber-border rounded-xl p-4">
            <p className="text-xs text-slate-500 mb-1">{label}</p>
            <p className="text-sm font-medium text-white break-all">{value}</p>
          </div>
        ))}
      </div>

      {/* Error */}
      {scan.status === 'failed' && scan.error && (
        <div className="flex gap-3 bg-rose-500/10 border border-rose-500/30 rounded-xl p-4">
          <AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-rose-400 mb-1">Scan Failed</p>
            <p className="text-sm text-rose-300/80 font-mono">{scan.error}</p>
          </div>
        </div>
      )}

      {/* Results */}
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

      {/* Running state */}
      {isLive && (
        <div className="flex items-center gap-3 bg-cyan-500/5 border border-cyan-500/20 rounded-xl p-4">
          <LoadingSpinner size="sm" />
          <p className="text-sm text-cyan-400">Scan in progress — polling every 5 seconds…</p>
        </div>
      )}
    </div>
  )
}
