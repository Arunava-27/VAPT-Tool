import { formatDistanceToNow, format, differenceInSeconds } from 'date-fns'

export const timeAgo = (date?: string | null): string => {
  if (!date) return '—'
  const d = new Date(date)
  if (isNaN(d.getTime())) return '—'
  return formatDistanceToNow(d, { addSuffix: true })
}

export const formatDate = (date?: string | null): string => {
  if (!date) return '—'
  const d = new Date(date)
  if (isNaN(d.getTime())) return '—'
  return format(d, 'dd MMM yyyy, HH:mm')
}

export const formatDuration = (start?: string | null, end?: string | null): string => {
  if (!start) return '—'
  const startDate = new Date(start)
  if (isNaN(startDate.getTime())) return '—'
  const endDate = end ? new Date(end) : new Date()
  const s = differenceInSeconds(endDate, startDate)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

export const scanTypeLabel: Record<string, string> = {
  network: 'Network',
  web: 'Web App',
  cloud: 'Cloud',
  container: 'Container',
  full: 'Full Scan',
}
