import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { Activity, CheckCircle, XCircle, Clock, Plus, Monitor, Shield, Wifi, ChevronRight, AlertTriangle } from 'lucide-react'
import { listScans } from '../../api/scans'
import { setScans } from '../../store/slices/scansSlice'
import type { RootState } from '../../store'
import Badge from '../../components/common/Badge'
import SeverityPieChart from '../../components/charts/SeverityPieChart'
import ScanTimelineChart from '../../components/charts/ScanTimelineChart'
import { timeAgo } from '../../utils/formatters'
import type { Scan } from '../../types'
import { getNodes, getHostAgentStatus, getAllVulnerabilities } from '../../api/network'
import type { NetworkNode, HostVulnerability } from '../../api/network'

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

function SevDot({ sev }: { sev: string }) {
  const colors: Record<string, string> = {
    critical: 'bg-rose-500', high: 'bg-orange-500', medium: 'bg-amber-500', low: 'bg-yellow-500', info: 'bg-slate-500',
  }
  return <span className={`inline-block w-1.5 h-1.5 rounded-full ${colors[sev] ?? 'bg-slate-500'}`} />
}

function MyDeviceWidget() {
  const [myNodes, setMyNodes] = useState<NetworkNode[]>([])
  const [vulns, setVulns] = useState<HostVulnerability[]>([])
  const [hostname, setHostname] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [agentRes, nodesRes, vulnsRes] = await Promise.allSettled([
          getHostAgentStatus(),
          getNodes(),
          getAllVulnerabilities(),
        ])
        const agentHostname = agentRes.status === 'fulfilled' ? agentRes.value.data.hostname : null
        setHostname(agentHostname)

        if (nodesRes.status === 'fulfilled') {
          const allNodes = nodesRes.value.data
          // Match nodes that belong to this machine
          const mine = allNodes.filter(n =>
            (agentHostname && n.hostname && n.hostname.toLowerCase().includes(agentHostname.toLowerCase())) ||
            n.hostname === 'host.docker.internal'
          )
          setMyNodes(mine)
        }
        if (vulnsRes.status === 'fulfilled') setVulns(vulnsRes.value.data)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="bg-cyber-surface border border-cyan-500/20 rounded-xl p-5 animate-pulse">
        <div className="h-4 w-32 bg-slate-700 rounded mb-3" />
        <div className="h-8 w-full bg-slate-800 rounded" />
      </div>
    )
  }

  // Aggregate vuln counts across all my nodes
  const myNodeIds = new Set(myNodes.map(n => n.id))
  const myVulns = vulns.filter(v => myNodeIds.has(v.node_id))
  const critical = myVulns.filter(v => v.severity === 'critical').length
  const high = myVulns.filter(v => v.severity === 'high').length
  const medium = myVulns.filter(v => v.severity === 'medium').length
  const totalPorts = myNodes.reduce((s, n) => s + (n.open_ports?.length ?? 0), 0)
  const maxRisk = myNodes.reduce((m, n) => Math.max(m, n.risk_score ?? 0), 0)

  const riskColor = maxRisk >= 80 ? 'text-rose-400' : maxRisk >= 60 ? 'text-orange-400' : maxRisk >= 30 ? 'text-amber-400' : 'text-emerald-400'

  return (
    <div className="bg-cyber-surface border border-cyan-500/30 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-cyan-500/20 bg-cyan-500/5">
        <div className="flex items-center gap-2">
          <Monitor className="w-4 h-4 text-cyan-400" />
          <h2 className="text-sm font-semibold text-cyan-300">This Device</h2>
          {hostname && <span className="text-xs text-slate-400 font-mono">{hostname}</span>}
          <span className="px-1.5 py-0.5 rounded bg-cyan-500/15 border border-cyan-500/30 text-cyan-400 text-[10px] font-bold">YOU</span>
        </div>
        <Link to="/network" className="flex items-center gap-1 text-xs text-slate-400 hover:text-cyan-300 transition-colors">
          View in Network <ChevronRight className="w-3 h-3" />
        </Link>
      </div>

      {myNodes.length === 0 ? (
        <div className="px-5 py-6 text-center">
          <Wifi className="w-8 h-8 mx-auto mb-2 text-slate-600" />
          <p className="text-sm text-slate-500">No network scan yet</p>
          <p className="text-xs text-slate-600 mt-1">Run a network discovery from the Network page to see your device here.</p>
          <Link to="/network" className="inline-block mt-3 text-xs text-cyan-400 hover:underline">Go to Network →</Link>
        </div>
      ) : (
        <div className="divide-y divide-cyber-border/50">
          {myNodes.map(node => {
            const nodeVulns = vulns.filter(v => v.node_id === node.id)
            const nc = nodeVulns.filter(v => v.severity === 'critical').length
            const nh = nodeVulns.filter(v => v.severity === 'high').length
            const nm = nodeVulns.filter(v => v.severity === 'medium').length
            const risk = node.risk_score ?? 0
            const rc = risk >= 80 ? 'text-rose-400' : risk >= 60 ? 'text-orange-400' : risk >= 30 ? 'text-amber-400' : 'text-emerald-400'
            return (
              <div key={node.id} className="px-5 py-3 flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-semibold text-cyan-300">{node.ip_address}</span>
                    <span className={`w-1.5 h-1.5 rounded-full ${node.status === 'active' ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                  </div>
                  {node.hostname && <p className="text-xs text-slate-500 truncate">{node.hostname}</p>}
                </div>
                <div className="flex items-center gap-3 text-xs shrink-0">
                  <span className="text-slate-400"><span className="text-white font-medium">{node.open_ports?.length ?? 0}</span> ports</span>
                  {nc > 0 && <span className="flex items-center gap-1"><SevDot sev="critical" /><span className="text-rose-400 font-bold">{nc}</span></span>}
                  {nh > 0 && <span className="flex items-center gap-1"><SevDot sev="high" /><span className="text-orange-400">{nh}</span></span>}
                  {nm > 0 && <span className="flex items-center gap-1"><SevDot sev="medium" /><span className="text-amber-400">{nm}</span></span>}
                  {nc === 0 && nh === 0 && nm === 0 && <span className="text-emerald-400 flex items-center gap-1"><CheckCircle className="w-3 h-3" />Clean</span>}
                  {risk > 0 && <span className={`font-bold ${rc}`}>Risk {risk}</span>}
                </div>
              </div>
            )
          })}
          {/* Summary row */}
          <div className="px-5 py-3 bg-cyber-bg/50 flex items-center gap-4 text-xs text-slate-400">
            <div className="flex items-center gap-1.5"><Wifi className="w-3.5 h-3.5" />{myNodes.length} adapter{myNodes.length !== 1 ? 's' : ''}</div>
            <div className="flex items-center gap-1.5"><Shield className="w-3.5 h-3.5" />{totalPorts} open port{totalPorts !== 1 ? 's' : ''}</div>
            {(critical + high) > 0 && (
              <div className="flex items-center gap-1.5 text-rose-400"><AlertTriangle className="w-3.5 h-3.5" />{critical + high} critical/high vuln{(critical + high) !== 1 ? 's' : ''}</div>
            )}
            {maxRisk > 0 && <div className={`ml-auto font-semibold ${riskColor}`}>Max Risk Score: {maxRisk}</div>}
          </div>
        </div>
      )}
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
    }).catch((err) => {
      console.error('Failed to load dashboard scans:', err)
    })
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

      {/* My Device */}
      <MyDeviceWidget />

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
