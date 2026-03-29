import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { Plus, Search, Eye, XCircle, ScanSearch } from 'lucide-react'
import toast from 'react-hot-toast'
import { listScans, cancelScan } from '../../api/scans'
import { setScans, updateScan } from '../../store/slices/scansSlice'
import type { RootState } from '../../store'
import Badge from '../../components/common/Badge'
import StatusDot from '../../components/common/StatusDot'
import EmptyState from '../../components/common/EmptyState'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import { timeAgo, scanTypeLabel } from '../../utils/formatters'
import type { Scan, ScanStatus } from '../../types'

const STATUS_FILTERS: { label: string; value: string }[] = [
  { label: 'All', value: '' },
  { label: 'Running', value: 'running' },
  { label: 'Completed', value: 'completed' },
  { label: 'Failed', value: 'failed' },
  { label: 'Queued', value: 'queued' },
]

export default function ScansPage() {
  const dispatch = useDispatch()
  const { scans, isLoading } = useSelector((s: RootState) => s.scans)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 15

  useEffect(() => {
    listScans({ limit: 200 }).then((r) => {
      const scans = r.data?.scans ?? []
      dispatch(setScans({ scans, total: r.data?.total ?? scans.length }))
    }).catch((err) => {
      console.error('Failed to load scans:', err)
      toast.error('Failed to load scans')
    })
  }, [dispatch])

  const filtered = scans
    .filter((s) => (!statusFilter || s.status === statusFilter))
    .filter((s) => (!search || s.name.toLowerCase().includes(search.toLowerCase()) || s.target.toLowerCase().includes(search.toLowerCase())))

  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)

  const handleCancel = async (scan: Scan, e: React.MouseEvent) => {
    e.preventDefault()
    try {
      const r = await cancelScan(scan.id)
      dispatch(updateScan(r.data))
      toast.success('Scan cancelled')
    } catch {
      toast.error('Failed to cancel scan')
    }
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Security Scans</h1>
          <p className="text-sm text-slate-500 mt-0.5">{filtered.length} scan{filtered.length !== 1 ? 's' : ''}</p>
        </div>
        <Link to="/scans/new"
          className="flex items-center gap-2 bg-cyber-primary text-cyber-bg text-sm font-semibold px-4 py-2 rounded-lg hover:bg-cyan-300 transition-colors">
          <Plus className="w-4 h-4" /> New Scan
        </Link>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
          <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(0) }}
            placeholder="Search scans…"
            aria-label="Search scans"
            className="bg-cyber-surface border border-cyber-border rounded-lg pl-8 pr-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyber-primary w-56" />
        </div>
        <div className="flex gap-1">
          {STATUS_FILTERS.map((f) => (
            <button key={f.value} onClick={() => { setStatusFilter(f.value); setPage(0) }}
              className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                statusFilter === f.value
                  ? 'bg-cyber-primary/10 text-cyber-primary border border-cyber-primary/30'
                  : 'bg-cyber-surface border border-cyber-border text-slate-400 hover:text-white'
              }`}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-cyber-surface border border-cyber-border rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
        ) : paginated.length === 0 ? (
          <EmptyState icon={ScanSearch} title="No scans found"
            description={search || statusFilter ? 'Try adjusting your filters' : 'Create your first security scan'}
            action={<Link to="/scans/new" className="text-sm text-cyber-primary hover:underline">New Scan →</Link>} />
        ) : (
          <>
            <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-cyber-border">
                  {['Name', 'Type', 'Target', 'Status', 'Created', 'Actions'].map((h) => (
                    <th key={h} className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide px-5 py-3">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-cyber-border">
                {paginated.map((scan) => (
                  <tr key={scan.id} className="hover:bg-cyber-border/20 transition-colors">
                    <td className="px-5 py-3.5">
                      <p className="font-medium text-white">{scan.name}</p>
                    </td>
                    <td className="px-5 py-3.5">
                      <Badge type="scan_type" value={scan.scan_type} />
                    </td>
                    <td className="px-5 py-3.5 text-slate-400 max-w-[180px] truncate">{scan.target}</td>
                    <td className="px-5 py-3.5">
                      <span className="flex items-center gap-2">
                        <StatusDot status={scan.status as ScanStatus} />
                        <Badge type="status" value={scan.status} />
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 whitespace-nowrap">{timeAgo(scan.created_at)}</td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <Link to={`/scans/${scan.id}`}
                          className="flex items-center gap-1 text-xs text-cyber-primary hover:text-cyan-300 transition-colors">
                          <Eye className="w-3.5 h-3.5" /> View
                        </Link>
                        {(scan.status === 'running' || scan.status === 'queued') && (
                          <button onClick={(e) => handleCancel(scan, e)}
                            className="flex items-center gap-1 text-xs text-rose-400 hover:text-rose-300 transition-colors">
                            <XCircle className="w-3.5 h-3.5" /> Cancel
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-5 py-3 border-t border-cyber-border">
                <span className="text-xs text-slate-500">Page {page + 1} of {totalPages}</span>
                <div className="flex gap-2">
                  <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
                    className="px-3 py-1.5 text-xs rounded-lg border border-cyber-border text-slate-400 disabled:opacity-40 hover:text-white hover:border-cyber-primary transition-colors">
                    Previous
                  </button>
                  <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}
                    className="px-3 py-1.5 text-xs rounded-lg border border-cyber-border text-slate-400 disabled:opacity-40 hover:text-white hover:border-cyber-primary transition-colors">
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
