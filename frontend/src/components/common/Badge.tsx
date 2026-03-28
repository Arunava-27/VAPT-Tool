import clsx from 'clsx'
import type { Severity, ScanStatus } from '../../types'
import { severityBg, statusColor } from '../../utils/severity'

interface Props {
  type: 'severity' | 'status' | 'scan_type'
  value: string
  className?: string
}

const scanTypeBg: Record<string, string> = {
  network: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  web: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  cloud: 'bg-sky-500/20 text-sky-400 border-sky-500/30',
  container: 'bg-teal-500/20 text-teal-400 border-teal-500/30',
  full: 'bg-violet-500/20 text-violet-400 border-violet-500/30',
}

export default function Badge({ type, value, className }: Props) {
  // Guard: value may be undefined at runtime despite the type
  if (!value) return null

  let cls = ''
  let label = value

  if (type === 'severity') {
    cls = severityBg[value as Severity] ?? 'bg-slate-500/20 text-slate-400'
    label = value.charAt(0).toUpperCase() + value.slice(1)
  } else if (type === 'status') {
    cls = statusColor[value as ScanStatus] ?? 'bg-slate-500/20 text-slate-400'
    label = value.charAt(0).toUpperCase() + value.slice(1)
  } else if (type === 'scan_type') {
    cls = scanTypeBg[value] ?? 'bg-slate-500/20 text-slate-400'
    label = value === 'web' ? 'Web App' : value.charAt(0).toUpperCase() + value.slice(1)
  }

  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded border text-xs font-medium', cls, className)}>
      {label}
    </span>
  )
}
