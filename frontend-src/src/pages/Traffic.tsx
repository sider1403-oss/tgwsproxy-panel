import { Link, useSearchParams } from 'react-router-dom'
import { Info } from 'lucide-react'
import type { ClientsResponse, Overview } from '../lib/types'
import { api } from '../lib/api'
import { usePolling } from '../lib/hooks'
import { fmtBytes, fmtNum } from '../lib/format'
import { Badge, Card, CardTitle, Empty, Tabs } from '../components/ui'
import { TrafficChart } from '../components/charts'
import { DetailHeader } from '../components/DetailHeader'

const RANGES = [
  { value: '1h', label: '1 час' },
  { value: '6h', label: '6 часов' },
  { value: '24h', label: '24 часа' },
  { value: '7d', label: '7 дней' },
]

export default function Traffic() {
  const [params, setParams] = useSearchParams()
  const range = params.get('range') || '24h'
  const setRange = (value: string) => {
    const next = new URLSearchParams(params)
    next.set('range', value)
    setParams(next, { replace: true })
  }
  const { data, error, loading, setData } = usePolling<Overview>(() => api.overview(range), 15000, [range])
  const { data: top } = usePolling<ClientsResponse>(
    () => api.clients({ range, sort: 'bytes_total', order: 'desc', limit: 10 }),
    20000,
    [range],
  )
  const hasTraffic = Boolean(data?.series.traffic.some((point) => point.up || point.down))

  return (
    <div className="space-y-4">
      <DetailHeader
        title="Трафик"
        subtitle="Суммы по завершённым сессиям из журнала прокси. Активные сессии попадут в сумму только после закрытия."
        updatedAt={data?.generated_at}
        onRefresh={() => setData(null)}
        loading={loading && !data}
      >
        <Tabs value={range} onChange={setRange} items={RANGES} />
      </DetailHeader>

      {error ? <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">↓ клиентам</div>
          <div className="mt-1 text-xl font-semibold text-accent">{fmtBytes(data?.totals.bytes_down ?? 0)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">↑ от клиентов</div>
          <div className="mt-1 text-xl font-semibold text-accent2">{fmtBytes(data?.totals.bytes_up ?? 0)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Всего за период</div>
          <div className="mt-1 text-xl font-semibold">{fmtBytes(data?.totals.bytes_total ?? 0)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Сессий / IP</div>
          <div className="mt-1 text-xl font-semibold">{fmtNum(data?.totals.sessions ?? 0)} <span className="text-sm font-normal text-muted">/ {fmtNum(data?.totals.clients ?? 0)}</span></div>
        </Card>
      </div>

      <Card>
        <CardTitle right={<Badge tone="muted">{range}</Badge>}>Динамика трафика</CardTitle>
        {hasTraffic ? (
          <TrafficChart data={data!.series.traffic} />
        ) : (
          <Empty title="Нет данных за период" hint="Трафик строится по записям о завершённых сессиях. Выберите другой период." />
        )}
        <div className="mt-2 text-[11px] text-muted">
          Источник: строки «session closed» из лога контейнера. Прокси округляет объёмы до 0,1 КБ.
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle right={<Link to={`/dc?range=${range}`} className="text-xs text-accent hover:underline">Подробнее</Link>}>По DC</CardTitle>
          {data?.dc.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[420px] border-collapse">
                <thead>
                  <tr className="border-b border-line/70">
                    <th className="th">DC</th>
                    <th className="th">Сессий</th>
                    <th className="th">IP</th>
                    <th className="th text-right">Трафик</th>
                  </tr>
                </thead>
                <tbody>
                  {data.dc.map((row) => (
                    <tr key={row.dc} className="border-b border-line/40">
                      <td className="td">DC{row.dc}</td>
                      <td className="td">{fmtNum(row.sessions)}</td>
                      <td className="td text-muted">{fmtNum(row.clients ?? 0)}</td>
                      <td className="td text-right">{fmtBytes(row.bytes)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="Нет сессий" />
          )}
        </Card>

        <Card>
          <CardTitle>Топ клиентов по трафику</CardTitle>
          {top?.items.length ? (
            <div className="space-y-1.5">
              {top.items.map((row, index) => (
                <div key={row.client_ip} className="flex items-center gap-2 rounded-lg border border-line/50 bg-ink/5 px-3 py-2 text-xs">
                  <span className="w-5 text-muted">{index + 1}</span>
                  <Link to={`/clients/${encodeURIComponent(row.client_ip)}?range=${range}`} className="font-mono text-accent/90 hover:underline">
                    {row.client_ip}
                  </Link>
                  <span className="ml-auto">{fmtBytes(row.bytes_total)}</span>
                  <span className="w-16 text-right text-muted">{fmtNum(row.sessions)} сес.</span>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="Нет данных" />
          )}
        </Card>
      </div>

      <div className="flex items-start gap-2 rounded-xl border border-line/60 bg-ink/5 px-4 py-3 text-[11px] text-muted">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>
          «Клиенты» здесь — уникальные IP из завершённых сессий, а не пользователи Telegram.
          Ключ MTProto прокси не сообщает; per-key статистика недоступна.
        </span>
      </div>
    </div>
  )
}
