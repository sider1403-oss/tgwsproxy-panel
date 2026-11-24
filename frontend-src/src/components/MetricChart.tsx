import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { MetricPoint } from '../lib/types'
import { fmtBytes, fmtSpeed, fmtTime } from '../lib/format'
import { useTheme } from '../lib/theme'

const DARK = { grid: 'rgba(148,163,184,0.18)', axis: '#8294ab', cyan: '#22d3ee', violet: '#8b5cf6', green: '#34d399', warn: '#fbbf24' }
const LIGHT = { grid: 'rgba(100,116,139,0.18)', axis: '#64748b', cyan: '#0891b2', violet: '#7c3aed', green: '#059669', warn: '#d97706' }

const COLORS = ['cyan', 'violet', 'green', 'warn'] as const

function valueLabel(kind: string, value: number): string {
  if (kind === 'memory' || kind === 'traffic') return fmtBytes(value)
  if (kind === 'speed') return fmtSpeed(value)
  if (kind === 'cpu') return `${value.toFixed(1)} %`
  return String(value)
}

export function MetricChart({
  kind,
  points,
  fields,
  labels,
  height = 300,
}: {
  kind: 'cpu' | 'memory' | 'speed'
  points: MetricPoint[]
  fields: string[]
  labels: Record<string, string>
  height?: number
}) {
  const { theme } = useTheme()
  const c = theme === 'light' ? LIGHT : DARK
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="t" tickFormatter={fmtTime} stroke={c.axis} tick={{ fontSize: 11 }} minTickGap={28} axisLine={false} tickLine={false} />
        <YAxis
          stroke={c.axis}
          tick={{ fontSize: 11 }}
          width={72}
          axisLine={false}
          tickLine={false}
          tickFormatter={(value) => valueLabel(kind, Number(value))}
        />
        <Tooltip
          content={({ active, payload, label }: any) => {
            if (!active || !payload?.length) return null
            return (
              <div className="rounded-xl border border-line bg-card px-3 py-2 text-xs shadow-xl">
                <div className="mb-1 text-muted">{new Date(label).toLocaleString('ru-RU')}</div>
                {payload.map((item: any) => (
                  <div key={item.dataKey} className="flex items-center justify-between gap-3">
                    <span className="inline-flex items-center gap-1.5 text-muted">
                      <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
                      {labels[item.dataKey] ?? item.dataKey}
                    </span>
                    <span className="font-medium text-ink">{valueLabel(kind, Number(item.value))}</span>
                  </div>
                ))}
              </div>
            )
          }}
        />
        {fields.map((field, index) => {
          const colorKey = COLORS[index % COLORS.length]
          return (
            <Line
              key={field}
              type="monotone"
              dataKey={field}
              name={labels[field] ?? field}
              stroke={c[colorKey]}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          )
        })}
      </LineChart>
    </ResponsiveContainer>
  )
}
