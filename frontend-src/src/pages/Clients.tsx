import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Info, Search } from 'lucide-react'
import type { ClientRow, ClientsResponse } from '../lib/types'
import { api } from '../lib/api'
import { usePolling } from '../lib/hooks'
import { fmtBytes, fmtDate, fmtNum, fmtRelative } from '../lib/format'
import { Badge, Button, Card, Empty, Input, Switch, Tabs } from '../components/ui'
import { DeviceBadge } from '../components/DeviceBadge'
import { DetailHeader } from '../components/DetailHeader'

const RANGES = [
  { value: '1h', label: '1 час' },
  { value: '6h', label: '6 часов' },
  { value: '24h', label: '24 часа' },
  { value: '7d', label: '7 дней' },
  { value: 'container', label: 'С запуска' },
]
const PAGE_SIZE = 50
const SORTS: Array<{ key: string; label: string }> = [
  { key: 'client_ip', label: 'Клиент' },
  { key: 'sessions', label: 'Сессий' },
  { key: 'bytes_total', label: 'Трафик' },
  { key: 'first_seen', label: 'Первое' },
  { key: 'last_seen', label: 'Последнее' },
]

export default function Clients() {
  const [params, setParams] = useSearchParams()
  const range = params.get('range') || '24h'
  const q = params.get('q') || ''
  const active = params.get('active') === '1'
  const sort = params.get('sort') || 'last_seen'
  const order = params.get('order') === 'asc' ? 'asc' : 'desc'
  const page = Math.max(0, parseInt(params.get('page') || '0', 10) || 0)
  const [search, setSearch] = useState(q)

  const update = (changes: Record<string, string | number | null>, replace = true) => {
    const next = new URLSearchParams(params)
    Object.entries(changes).forEach(([key, value]) => {
      if (value === null || value === '') next.delete(key)
      else next.set(key, String(value))
    })
    setParams(next, { replace })
  }

  useEffect(() => {
    setSearch(q)
  }, [q])

  useEffect(() => {
    const timer = setTimeout(() => {
      if (search !== q) update({ q: search || null, page: 0 })
    }, 300)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  const { data, error, loading, setData } = usePolling<ClientsResponse>(
    () => api.clients({ range, q, active, sort, order, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    15000,
    [range, q, active, sort, order, page],
  )

  const items = useMemo(() => data?.items ?? [], [data])
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  const toggleSort = (key: string) => {
    if (sort === key) update({ order: order === 'asc' ? 'desc' : 'asc', page: 0 })
    else update({ sort: key, order: 'desc', page: 0 })
  }
  const arrow = (key: string) => (sort === key ? (order === 'asc' ? '↑' : '↓') : '')

  return (
    <div className="space-y-4">
      <DetailHeader
        title="Клиенты"
        subtitle={
          <>
            Обнаруженные IP-адреса и агрегаты по завершённым сессиям. Это не количество
            пользователей Telegram: один клиент может менять IP, а один IP — использоваться несколькими устройствами.
          </>
        }
        updatedAt={data?.generated_at}
        onRefresh={() => setData(null)}
        loading={loading && !data}
      >
        <Tabs value={range} onChange={(value) => update({ range: value, page: 0 })} items={RANGES} />
      </DetailHeader>

      <Card>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1 sm:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Поиск по IP"
              className="pl-9"
              inputMode="numeric"
            />
          </div>
          <Switch checked={active} onChange={(value) => update({ active: value ? '1' : null, page: 0 })} label="Только активные" />
          <Badge tone="muted">{data ? `${fmtNum(data.total)} IP` : '…'}</Badge>
          <Button className="ml-auto" onClick={() => setData(null)} title="Обновить">
            Обновить
          </Button>
        </div>

        {error ? <div className="mb-3 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}

        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] border-collapse">
            <thead>
              <tr className="border-b border-line/70">
                {SORTS.map((item) => (
                  <th key={item.key} className="th" aria-sort={sort === item.key ? (order === 'asc' ? 'ascending' : 'descending') : 'none'}>
                    <button type="button" className="inline-flex items-center gap-1 hover:text-ink" onClick={() => toggleSort(item.key)}>
                      {item.label} {arrow(item.key)}
                    </button>
                  </th>
                ))}
                <th className="th">Устройство</th>
                <th className="th">Сейчас</th>
                <th className="th">Ключ</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row: ClientRow) => (
                <tr key={row.client_ip} className="border-b border-line/40 transition hover:bg-ink/[0.03]">
                  <td className="td">
                    <Link to={`/clients/${encodeURIComponent(row.client_ip)}?range=${encodeURIComponent(range)}`} className="font-mono text-accent/90 hover:underline">
                      {row.client_ip}
                    </Link>
                  </td>
                  <td className="td">{fmtNum(row.sessions)}</td>
                  <td className="td">
                    <div>{fmtBytes(row.bytes_total)}</div>
                    <div className="text-[10px] text-muted">↓ {fmtBytes(row.bytes_down)} · ↑ {fmtBytes(row.bytes_up)}</div>
                  </td>
                  <td className="td text-muted" title={row.first_seen ? fmtDate(row.first_seen) : undefined}>{row.first_seen ? fmtRelative(row.first_seen) : '—'}</td>
                  <td className="td text-muted" title={row.last_seen ? fmtDate(row.last_seen) : undefined}>{row.last_seen ? fmtRelative(row.last_seen) : '—'}</td>
                  <td className="td"><DeviceBadge device={row.device} /></td>
                  <td className="td">
                    {row.active ? <Badge tone="ok">активен · {row.active_connections}</Badge> : <Badge tone="muted">нет</Badge>}
                  </td>
                  <td className="td text-muted" title={row.key_note}>не определяется</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && data && !items.length ? (
            <Empty
              title={active ? 'Активных клиентов нет' : 'Клиентов за период нет'}
              hint={active ? 'Нет активных TCP-соединений с прокси.' : 'Измените период или поиск.'}
            />
          ) : null}
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[11px] text-muted">
            {data ? `${fmtNum(data.offset + 1)}–${fmtNum(Math.min(data.offset + PAGE_SIZE, data.total))} из ${fmtNum(data.total)}` : '…'}
          </span>
          <div className="flex gap-2">
            <Button disabled={page === 0} onClick={() => update({ page: Math.max(0, page - 1) }, false)}>Назад</Button>
            <Button disabled={page + 1 >= totalPages} onClick={() => update({ page: page + 1 }, false)}>Вперёд</Button>
          </div>
        </div>
      </Card>

      <div className="flex items-start gap-2 rounded-xl border border-line/60 bg-ink/5 px-4 py-3 text-[11px] text-muted">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>
          {data?.note ?? 'Источник: завершённые сессии из журнала прокси.'} SYN-определение устройства приблизительное:
          iOS и macOS по SYN неразличимы, Android и Linux могут путаться. Ключ MTProto и DC активной сессии прокси не сообщает.
        </span>
      </div>
    </div>
  )
}
