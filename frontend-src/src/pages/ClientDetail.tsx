import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Info } from 'lucide-react'
import type { ClientDetail as ClientDetailData } from '../lib/types'
import { api } from '../lib/api'
import { usePolling } from '../lib/hooks'
import { fmtBytes, fmtDate, fmtDuration, fmtNum, fmtRelative } from '../lib/format'
import { Badge, Card, CardTitle, Empty, Tabs } from '../components/ui'
import { DeviceBadge } from '../components/DeviceBadge'
import { DetailHeader } from '../components/DetailHeader'

const RANGES = [
  { value: '24h', label: '24 часа' },
  { value: '7d', label: '7 дней' },
  { value: 'container', label: 'С запуска' },
]

export default function ClientDetail() {
  const { ip = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const range = params.get('range') || '7d'
  const { data, error, loading, setData } = usePolling<ClientDetailData>(
    () => api.client(ip, { range }),
    15000,
    [ip, range],
  )

  return (
    <div className="space-y-4">
      <DetailHeader
        title={ip || 'Клиент'}
        subtitle={
          data ? (
            <span className="inline-flex flex-wrap items-center gap-2">
              <DeviceBadge device={data.device} />
              <span>{data.active ? `активен · ${data.active_connections} TCP` : 'активных TCP нет'}</span>
              {data.first_seen ? <span>первое обнаружение {fmtRelative(data.first_seen)}</span> : null}
            </span>
          ) : (
            'Карточка клиента: сводка по завершённым сессиям и текущим TCP-соединениям.'
          )
        }
        backTo={`/clients?range=${encodeURIComponent(range)}`}
        backLabel="К клиентам"
        updatedAt={data?.generated_at}
        onRefresh={() => setData(null)}
        loading={loading && !data}
      >
        <Tabs value={range} onChange={(value) => setParams({ range: value }, { replace: true })} items={RANGES} />
      </DetailHeader>

      {error ? <Card><Empty title="Не удалось загрузить клиента" hint={error} /></Card> : null}

      {data ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Card className="p-4">
              <div className="text-[11px] uppercase tracking-wider text-muted">Сессий</div>
              <div className="mt-1 text-2xl font-semibold">{fmtNum(data.sessions)}</div>
            </Card>
            <Card className="p-4">
              <div className="text-[11px] uppercase tracking-wider text-muted">Трафик</div>
              <div className="mt-1 text-xl font-semibold">{fmtBytes(data.bytes_total)}</div>
              <div className="text-[10px] text-muted">↓ {fmtBytes(data.bytes_down)} · ↑ {fmtBytes(data.bytes_up)}</div>
            </Card>
            <Card className="p-4">
              <div className="text-[11px] uppercase tracking-wider text-muted">Первое обнаружение</div>
              <div className="mt-1 text-sm font-medium">{data.first_seen ? fmtDate(data.first_seen) : '—'}</div>
            </Card>
            <Card className="p-4">
              <div className="text-[11px] uppercase tracking-wider text-muted">Последняя сессия</div>
              <div className="mt-1 text-sm font-medium">{data.last_seen ? fmtDate(data.last_seen) : '—'}</div>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
            <Card>
              <CardTitle right={<Badge tone={data.active ? 'ok' : 'muted'}>{data.active ? `${data.active_connections} TCP` : 'нет активных'}</Badge>}>
                Активные TCP-соединения
              </CardTitle>
              {data.active_items.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[620px] border-collapse">
                    <thead>
                      <tr className="border-b border-line/70">
                        <th className="th">Порт клиента</th>
                        <th className="th">Локальный адрес</th>
                        <th className="th">Обнаружено</th>
                        <th className="th">Длительность</th>
                        <th className="th">↓ / ↑</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.active_items.map((item) => (
                        <tr key={`${item.ip}:${item.port}`} className="border-b border-line/40">
                          <td className="td font-mono">{item.port}</td>
                          <td className="td font-mono text-muted">{item.local_ip}:{item.local_port}</td>
                          <td className="td text-muted">{fmtRelative(item.first_seen)}</td>
                          <td className="td">{fmtDuration(item.duration)}</td>
                          <td className="td">{item.bytes_sent != null ? fmtBytes(item.bytes_sent) : 'н/д'} / {item.bytes_received != null ? fmtBytes(item.bytes_received) : 'н/д'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="Активных TCP нет" hint="Telegram открывает короткоживущие соединения; проверьте позже." />
              )}
            </Card>

            <Card>
              <CardTitle>Распределение по DC</CardTitle>
              {data.dcs.length ? (
                <div className="space-y-2">
                  {data.dcs.map((dc) => (
                    <div key={dc.dc} className="flex items-center justify-between rounded-lg border border-line/60 bg-ink/5 px-3 py-2 text-xs">
                      <span>DC{dc.dc}</span>
                      <span className="text-muted">{fmtNum(dc.sessions)} сессий · {fmtBytes(dc.bytes)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty title="Нет данных по DC" hint="DC определяется только после закрытия сессии." />
              )}
            </Card>
          </div>

          <Card>
            <CardTitle
              right={
                <Link to={`/connections?tab=history&ip=${encodeURIComponent(ip)}&range=7d`} className="text-xs text-accent hover:underline">
                  Вся история по IP
                </Link>
              }
            >
              Последние сессии
            </CardTitle>
            {data.recent.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[820px] border-collapse">
                  <thead>
                    <tr className="border-b border-line/70">
                      <th className="th">Завершена</th>
                      <th className="th">DC</th>
                      <th className="th">Транспорт</th>
                      <th className="th">Закрыта</th>
                      <th className="th">Длительность</th>
                      <th className="th">↓</th>
                      <th className="th">↑</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent.map((session) => (
                      <tr key={session.id} className="border-b border-line/40">
                        <td className="td text-muted">{fmtDate(session.ended_at)}</td>
                        <td className="td">DC{session.dc}{session.media ? 'm' : ''}</td>
                        <td className="td text-muted">{session.kind}</td>
                        <td className="td"><Badge tone={session.closed_by === 'client' ? 'info' : 'warn'}>{session.closed_by === 'client' ? 'клиент' : 'upstream'}</Badge></td>
                        <td className="td">{fmtDuration(session.duration)}</td>
                        <td className="td">{fmtBytes(session.bytes_down)}</td>
                        <td className="td">{fmtBytes(session.bytes_up)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="Сессий нет" hint="За выбранный период завершённых сессий не найдено." />
            )}
          </Card>

          <div className="flex items-start gap-2 rounded-xl border border-line/60 bg-ink/5 px-4 py-3 text-[11px] text-muted">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{data.key_note} {data.note} Устройство определяется по TCP SYN приблизительно.</span>
          </div>
        </>
      ) : null}
    </div>
  )
}
