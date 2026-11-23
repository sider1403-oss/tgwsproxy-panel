import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ConnPoint, DcRow, TrafficPoint } from '../lib/types'
import { fmtBytes, fmtSpeed, fmtTime } from '../lib/format'
import { useTheme } from '../lib/theme'

const DARK = {
  grid: 'rgba(148, 163, 184, 0.18)',
  axis: '#8294ab',
  cyan: '#22d3ee',
  violet: '#8b5cf6',
  green: '#34d399',
  warn: '#fbbf24',
  bad: '#f87171',
  cursor: 'rgba(255, 255, 255, 0.03)',
}

const LIGHT = {
  grid: 'rgba(100, 116, 139, 0.18)',
  axis: '#64748b',
  cyan: '#0891b2',
  violet: '#7c3aed',
  green: '#059669',
  warn: '#d97706',
  bad: '#dc2626',
  cursor: 'rgba(15, 23, 42, 0.05)',
}

function palette(theme: string) {
  return theme === 'light' ? LIGHT : DARK
}

function ChartTip({ active, payload, label, bytes = true }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-line bg-card px-3 py-2 text-xs shadow-xl">
      <div className="mb-1 text-muted">{new Date(label).toLocaleString('ru-RU')}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color || p.stroke || p.fill }} />
          <span className="text-muted">{p.name}</span>
          <span className="font-medium text-ink">
            {p.dataKey === 'conns' ? p.value : bytes ? fmtBytes(p.value) : fmtSpeed(p.value)}
          </span>
        </div>
      ))}
    </div>
  )
}

export function TrafficChart({ data }: { data: TrafficPoint[] }) {
  const { theme } = useTheme()
  const c = palette(theme)
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="gDown" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={c.cyan} stopOpacity={0.35} />
            <stop offset="100%" stopColor={c.cyan} stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="gUp" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={c.violet} stopOpacity={0.35} />
            <stop offset="100%" stopColor={c.violet} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="t" tickFormatter={fmtTime} stroke={c.axis} tick={{ fontSize: 11 }} minTickGap={28} axisLine={false} tickLine={false} />
        <YAxis stroke={c.axis} tick={{ fontSize: 11 }} tickFormatter={(v) => fmtBytes(v, 0)} width={64} axisLine={false} tickLine={false} />
        <Tooltip content={<ChartTip />} />
        <Area type="monotone" dataKey="down" name="Получено (↓)" stroke={c.cyan} strokeWidth={2} fill="url(#gDown)" />
        <Area type="monotone" dataKey="up" name="Передано (↑)" stroke={c.violet} strokeWidth={2} fill="url(#gUp)" />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function ConnectionsChart({ data }: { data: ConnPoint[] }) {
  const { theme } = useTheme()
  const c = palette(theme)
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="t" tickFormatter={fmtTime} stroke={c.axis} tick={{ fontSize: 11 }} minTickGap={30} axisLine={false} tickLine={false} />
        <YAxis stroke={c.axis} tick={{ fontSize: 11 }} allowDecimals={false} width={36} axisLine={false} tickLine={false} />
        <Tooltip content={<ChartTip bytes={false} />} />
        <Line type="monotone" dataKey="conns" name="Активные сессии" stroke={c.green} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function DcChart({ data }: { data: DcRow[] }) {
  const { theme } = useTheme()
  const c = palette(theme)
  const colors = [c.cyan, c.violet, c.green, c.warn, c.bad]
  const rows = data.map((d) => ({ name: `DC${d.dc}`, bytes: d.bytes, sessions: d.sessions }))
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="name" stroke={c.axis} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis stroke={c.axis} tick={{ fontSize: 11 }} tickFormatter={(v) => fmtBytes(v, 0)} width={64} axisLine={false} tickLine={false} />
        <Tooltip content={<ChartTip />} cursor={{ fill: c.cursor }} />
        <Bar dataKey="bytes" name="Трафик" radius={[6, 6, 0, 0]}>
          {rows.map((_, i) => (
            <Cell key={i} fill={colors[i % colors.length]} fillOpacity={theme === 'light' ? 0.75 : 0.65} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
