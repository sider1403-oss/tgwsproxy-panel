import { Link, useSearchParams } from 'react-router-dom'
import { Info } from 'lucide-react'
import type { Overview } from '../lib/types'
import { api } from '../lib/api'
import { usePolling } from '../lib/hooks'
import { fmtBytes, fmtNum } from '../lib/format'
import { Badge, Card, CardTitle, Empty, Tabs } from '../components/ui'
import { DcChart } from '../components/charts'
import { DetailHeader } from '../components/DetailHeader'

const RANGES = [
  { value: '1h', label: '1 час' },
  { value: '6h', label: '6 часов' },
  { value: '24h', label: '24 часа' },
  { value: '7d', label: '7 дней' },
]

export default function Dc() {
  const [params, setParams] = useSearchParams()
  const range = params.get('range') || '24h'
  const setRange = (value: string) => {
    const next = new URLSearchParams(params)
    next.set('range', value)
    setParams(next, { replace: true })
  }
  const { data, error, loading, setData } = usePolling<Overview>(() => api.overview(range), 15000, [range])
  const totalBytes = (data?.dc ?? []).reduce((sum, row) => sum + row.bytes, 0)

  return (
    <div className="space-y-4">
      <DetailHeader
        title="Распределение по DC"
        subtitle="DC определяется только из завершённой сессии. Для активных TCP-соединений DC неизвестен."
        updatedAt={data?.generated_at}
        onRefresh={() => setData(null)}
        loading={loading && !data}
      >
        <Tabs value={range} onChange={setRange} items={RANGES} />
      </DetailHeader>

      {error ? <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}

      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Card>
          <CardTitle right={<Badge tone="muted">{data?.dc.length ?? 0} DC</Badge>}>Трафик по DC</CardTitle>
          {data?.dc.length ? <DcChart data={data.dc} /> : <Empty title="Нет сессий за период" />}
        </Card>

        <Card>
          <CardTitle>Сводка</CardTitle>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] border-collapse">
              <thead>
                <tr className="border-b border-line/70">
                  <th className="th">DC</th>
                  <th className="th">Сессий</th>
                  <th className="th">IP</th>
                  <th className="th">Трафик</th>
                  <th className="th text-right">Доля</th>
                </tr>
              </thead>
              <tbody>
                {(data?.dc ?? []).map((row) => (
                  <tr key={row.dc} className="border-b border-line/40 transition hover:bg-ink/[0.03]">
                    <td className="td">
                      <Link
                        to={`/connections?tab=history&dc=${row.dc}&range=${range}`}
                        className="text-accent hover:underline"
                      >
                        DC{row.dc}
                      </Link>
                    </td>
                    <td className="td">{fmtNum(row.sessions)}</td>
                    <td className="td text-muted">{fmtNum(row.clients ?? 0)}</td>
                    <td className="td">{fmtBytes(row.bytes)}</td>
                    <td className="td text-right text-muted">{totalBytes ? `${((row.bytes / totalBytes) * 100).toFixed(1)}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!data?.dc.length ? <Empty title="Нет данных" hint="За выбранный период завершённых сессий нет." /> : null}
        </Card>
      </div>

      <div className="flex items-start gap-2 rounded-xl border border-line/60 bg-ink/5 px-4 py-3 text-[11px] text-muted">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>
          DC — дата-центр Telegram из строки закрытия сессии. «IP» — уникальные адреса, не пользователи.
          Активные подключения не распределяются по DC, пока прокси не закроет сессию.
        </span>
      </div>
    </div>
  )
}
