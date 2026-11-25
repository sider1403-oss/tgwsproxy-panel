import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Info } from 'lucide-react'
import type { MetricsResponse } from '../lib/types'
import { api } from '../lib/api'
import { usePolling } from '../lib/hooks'
import { fmtBytes, fmtDate, fmtNum, fmtSpeed } from '../lib/format'
import { Badge, Card, CardTitle, Empty, Tabs } from '../components/ui'
import { DetailHeader } from '../components/DetailHeader'
import { MetricChart } from '../components/MetricChart'

const RANGES = [
  { value: '1h', label: '1 час' },
  { value: '6h', label: '6 часов' },
  { value: '24h', label: '24 часа' },
  { value: '7d', label: '7 дней' },
]

const KINDS = {
  cpu: {
    title: 'CPU LXC',
    fields: ['cpu_host', 'cpu_proxy'],
    labels: { cpu_host: 'CPU LXC', cpu_proxy: 'CPU прокси' },
    note: 'CPU LXC — cgroup контейнера, не host CPU. CPU прокси — процесс контейнера из /proc/<pid>/stat.',
  },
  memory: {
    title: 'RAM сервера',
    fields: ['mem_used', 'mem_proxy'],
    labels: { mem_used: 'Использовано', mem_proxy: 'RSS прокси' },
    note: 'Источник: /proc/meminfo (LXC/сервер) и RSS процесса контейнера. Общий объём RAM хранится только в текущем состоянии, не в истории сэмплов.',
  },
  speed: {
    title: 'Скорость',
    fields: ['speed_in', 'speed_out'],
    labels: { speed_in: 'Входящая', speed_out: 'Исходящая' },
    note: 'Скорость — дельта счётчиков eth0 контейнера за интервал. Не биллинг и не точная сумма по клиентам.',
  },
} as const

type Kind = keyof typeof KINDS

function value(kind: Kind, field: string, raw: number | null | undefined): string {
  if (raw == null) return '—'
  if (kind === 'cpu') return `${raw.toFixed(2)} %`
  if (kind === 'memory') return fmtBytes(raw)
  return fmtSpeed(raw)
}

export default function Metrics() {
  const { kind: rawKind = '' } = useParams()
  const kind = (rawKind in KINDS ? rawKind : 'cpu') as Kind
  const meta = KINDS[kind] as { title: string; fields: readonly string[]; labels: Record<string, string>; note: string }
  const [params, setParams] = useSearchParams()
  const range = params.get('range') || '1h'
  const dir = params.get('dir') === 'out' ? 'out' : 'in'
  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.set(key, value)
    setParams(next, { replace: true })
  }

  const { data, error, loading, setData } = usePolling<MetricsResponse>(
    () => api.metrics({ range, fields: meta.fields.join(',') }),
    30000,
    [range, kind],
  )

  if (!(rawKind in KINDS)) {
    return <Card><Empty title="Неизвестная метрика" hint="Доступны: CPU, память и скорость." /></Card>
  }

  const points = data?.points ?? []
  const primaryField = kind === 'speed' ? (dir === 'out' ? 'speed_out' : 'speed_in') : meta.fields[0]

  return (
    <div className="space-y-4">
      <DetailHeader
        title={kind === 'speed' ? `Скорость ${dir === 'out' ? 'исходящая' : 'входящая'}` : meta.title}
        subtitle={meta.note}
        updatedAt={data?.generated_at}
        onRefresh={() => setData(null)}
        loading={loading && !data}
      >
        <div className="flex flex-wrap items-center gap-2">
          <Tabs value={range} onChange={(value) => setParam('range', value)} items={RANGES} />
          {kind === 'speed' ? (
            <Tabs
              value={dir}
              onChange={(value) => setParam('dir', value)}
              items={[
                { value: 'in', label: 'Входящая' },
                { value: 'out', label: 'Исходящая' },
              ]}
            />
          ) : null}
        </div>
      </DetailHeader>

      {error ? <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Сейчас</div>
          <div className="mt-1 text-xl font-semibold">{value(kind, primaryField, data?.stats[primaryField]?.last)}</div>
          <div className="text-[10px] text-muted">{meta.labels[primaryField]}</div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Среднее</div>
          <div className="mt-1 text-xl font-semibold">{value(kind, primaryField, data?.stats[primaryField]?.avg)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Максимум</div>
          <div className="mt-1 text-xl font-semibold">{value(kind, primaryField, data?.stats[primaryField]?.max)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Точек</div>
          <div className="mt-1 text-xl font-semibold">{fmtNum(points.length)}</div>
        </Card>
      </div>

      <Card>
        <CardTitle right={<Badge tone="muted">{data ? `${points.length} точек · шаг ${data.step} с` : '…'}</Badge>}>
          {meta.title}
        </CardTitle>
        {points.length ? (
          <MetricChart kind={kind} points={points} fields={[...meta.fields]} labels={meta.labels} />
        ) : (
          <Empty
            title={loading ? 'Загрузка…' : 'Нет данных за период'}
            hint={
              data?.history_start
                ? `История сэмплов начинается с ${fmtDate(data.history_start)}. За выбранный период данных нет.`
                : 'Панель собирает сэмплы каждые 5 секунд; история появится после первого интервала.'
            }
          />
        )}
        {kind === 'speed' ? (
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-muted">
            <span>Входящая: <b className="text-ink/80">{value(kind, 'speed_in', data?.stats.speed_in?.last)}</b></span>
            <span>Исходящая: <b className="text-ink/80">{value(kind, 'speed_out', data?.stats.speed_out?.last)}</b></span>
            <Link to={`/traffic?range=${range}`} className="text-accent hover:underline">Подробнее о трафике</Link>
          </div>
        ) : null}
      </Card>

      <div className="flex items-start gap-2 rounded-xl border border-line/60 bg-ink/5 px-4 py-3 text-[11px] text-muted">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>
          {meta.note} Данные округлены при выборке; график не заменяет точный биллинг.
          {data?.history_start ? ` Доступная история: с ${fmtDate(data.history_start)}.` : ''}
        </span>
      </div>
    </div>
  )
}
