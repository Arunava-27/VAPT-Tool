import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { severityColor } from '../../utils/severity'
import type { Severity } from '../../types'

interface Props {
  data: Record<string, number>
}

const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'informational']

export default function SeverityPieChart({ data }: Props) {
  const chartData = SEVERITIES
    .filter((s) => (data[s] ?? 0) > 0)
    .map((s) => ({ name: s.charAt(0).toUpperCase() + s.slice(1), value: data[s] ?? 0, key: s }))

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
        No vulnerability data
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie data={chartData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3} dataKey="value">
          {chartData.map((entry) => (
            <Cell key={entry.key} fill={severityColor[entry.key as Severity]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ background: '#0d1426', border: '1px solid #1e2d4a', borderRadius: 8, color: '#e2e8f0' }}
          formatter={(v: number) => [v, '']}
        />
        <Legend iconType="circle" iconSize={8} formatter={(v) => <span className="text-xs text-slate-400">{v}</span>} />
      </PieChart>
    </ResponsiveContainer>
  )
}
