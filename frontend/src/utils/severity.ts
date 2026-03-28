import type { Severity, ScanStatus } from '../types'

export const severityColor: Record<Severity, string> = {
  critical: '#ff4466',
  high: '#ff6b35',
  medium: '#ffaa00',
  low: '#00d4ff',
  informational: '#64748b',
}

export const severityBg: Record<Severity, string> = {
  critical: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
  high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  medium: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  low: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  informational: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
}

export const statusColor: Record<ScanStatus, string> = {
  pending: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  queued: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  running: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  completed: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  failed: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
  cancelled: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
}

export const statusDot: Record<ScanStatus, string> = {
  pending: 'bg-amber-400',
  queued: 'bg-amber-400',
  running: 'bg-cyan-400 animate-pulse',
  completed: 'bg-emerald-400',
  failed: 'bg-rose-400',
  cancelled: 'bg-slate-400',
}
