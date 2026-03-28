import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { Activity, CheckCircle, XCircle, Clock, Plus } from 'lucide-react'
import { listScans } from '../../api/scans'
import { setScans } from '../../store/slices/scansSlice'
import type { RootState } from '../../store'
import Badge from '../../components/common/Badge'
import SeverityPieChart from '../../components/charts/SeverityPieChart'
import ScanTimelineChart from '../../components/charts/ScanTimelineChart'
import { timeAgo } from '../../utils/formatters'
import type { Scan } from '../../types'

function StatCard({ label, value, icon: Icon, color }: { label: string; value: number; icon: React.ElementType; color: string }) {
  return (
    <div className="bg-cyber-surface border border-cyber-border rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</p>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${color}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <p className="text-3xl font-bold text-white">{value}</p>
    </div>
  )
}

export default function DashboardPage() {
  const dispatch = useDispatch()
  const scans = useSelector((s: RootState) => s.scans.scans)

  useEffect(() => {
    listScans({ limit: 100 }).then((r) => {
      const scans = r.data?.scans ?? []
      dispatch(setScans({ scans, total: r.data?.total ?? scans.length }))
    }).catch(() => {})
  }, [dispatch])

  const total = scans.length
  const running = scans.filter((s) => s.status === 'running' || s.status === 'queued').length
  const completed = scans.filter((s) => s.status === 'completed').length
  const failed = scans.filter((s) => s.status === 'failed').length

  // Aggregate severity counts from completed scans
  const severityCounts = scans
    .filter((s) => s.result_summary)
    .reduce<Record<string, number>>((acc, s) => {
      const rs = s.result_summary!
      acc.critical = (acc.critical ?? 0) + (rs.critical ?? 0)
      acc.high = (acc.high ?? 0) + (rs.high ?? 0)
      acc.medium = (acc.medium ?? 0) + (rs.medium ?? 0)
      acc.low = (acc.low ?? 0) + (rs.low ?? 0)
      acc.informational = (acc.informational ?? 0) + (rs.informational ?? 0)
      return acc
    }, {})

  const recent = [...scans].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 5)

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Scans" value={total} icon={Activity} color="bg-cyan-500/10 text-cyber-primary" />
        <StatCard label="Running" value={running} icon={Clock} color="bg-amber-500/10 text-amber-400" />
        <StatCard label="Completed" value={completed} icon={CheckCircle} color="bg-emerald-500/10 text-emerald-400" />
        <StatCard label="Failed" value={failed} icon={XCircle} color="bg-rose-500/10 text-rose-400" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-cyber-surface border border-cyber-border rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">Vulnerability Severity</h2>
          <SeverityPieChart data={severityCounts} />
        </div>
        <div className="bg-cyber-surface border border-cyber-border rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">Scans — Last 7 Days</h2>
          <ScanTimelineChart scans={scans} />
        </div>
      </div>

      {/* Recent scans */}
      <div className="bg-cyber-surface border border-cyber-border rounded-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-cyber-border">
          <h2 className="text-sm font-semibold text-slate-300">Recent Scans</h2>
          <Link to="/scans/new"
            className="flex items-center gap-1.5 text-xs font-medium text-cyber-primary hover:text-cyan-300 transition-colors">
            <Plus className="w-3.5 h-3.5" /> New Scan
          </Link>
        </div>
        {recent.length === 0 ? (
          <p className="text-center text-slate-500 text-sm py-10">No scans yet. <Link to="/scans/new" className="text-cyber-primary hover:underline">Start your first scan</Link></p>
        ) : (
          <div className="divide-y divide-cyber-border">
            {recent.map((scan: Scan) => (
              <Link key={scan.id} to={`/scans/${scan.id}`}
                className="flex items-center gap-4 px-5 py-3.5 hover:bg-cyber-border/30 transition-colors">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white truncate">{scan.name}</p>
                  <p className="text-xs text-slate-500 truncate">{scan.target}</p>
                </div>
                <Badge type="scan_type" value={scan.scan_type} />
                <Badge type="status" value={scan.status} />
                <span className="text-xs text-slate-500 whitespace-nowrap">{timeAgo(scan.created_at)}</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
