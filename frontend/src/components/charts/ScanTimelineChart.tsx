import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { subDays, format } from 'date-fns'
import type { Scan } from '../../types'

interface Props { scans: Scan[] }

export default function ScanTimelineChart({ scans }: Props) {
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = subDays(new Date(), 6 - i)
    const key = format(d, 'yyyy-MM-dd')
    const label = format(d, 'MMM d')
    const count = scans.filter((s) => s.created_at?.startsWith(key) ?? false).length
    return { label, count }
  })

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={days} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e2d4a" />
        <XAxis dataKey="label" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: '#0d1426', border: '1px solid #1e2d4a', borderRadius: 8, color: '#e2e8f0' }}
          cursor={{ fill: 'rgba(0,212,255,0.05)' }}
        />
        <Bar dataKey="count" name="Scans" fill="#00d4ff" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
