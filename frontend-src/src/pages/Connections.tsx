import { useEffect, useMemo, useState } from 'react'
import { ArrowDownToLine, ArrowUpFromLine, Info, RefreshCw, Search, Skull } from 'lucide-react'
import type { ActiveConnection, HistoryResponse, Session } from '../lib/types'
import { api } from '../lib/api'
import { usePolling } from '../lib/hooks'
import { fmtBytes, fmtDate, fmtDuration, fmtNum, fmtRelative } from '../lib/format'
import { Badge, Button, Card, ConfirmDialog, Dialog, Empty, Field, Input, Select, Tabs, useToast } from '../components/ui'
import { DeviceBadge } from '../components/DeviceBadge'
import { cn } from '../lib/utils'

export default function Connections() {
  const [tab, setTab] = useState<'active' | 'history'>('active')
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs
          value={tab}
          onChange={(v) => setTab(v as 'active' | 'history')}
          items={[
            { value: 'active', label: 'Активные' },
            { value: 'history', label: 'История' },
          ]}
        />
        <div className="text-[11px] text-muted">Данные: сетевой namespace контейнера + журнал сессий прокси</div>
      </div>
      {tab === 'active' ? <ActiveTab /> : <HistoryTab />}
    </div>
  )
}

function ActiveTab() {
  const [search, setSearch] = useState('')
  const [target, setTarget] = useState<ActiveConnection | null>(null)
  const [details, setDetails] = useState<ActiveConnection | null>(null)
  const [deviceTarget, setDeviceTarget] = useState<ActiveConnection | null>(null)
  const [deviceFamily, setDeviceFamily] = useState('')
  const [deviceSaving, setDeviceSaving] = useState(false)
  const [killing, setKilling] = useState(false)
  const [sortKey, setSortKey] = useState<'ip' | 'first_seen' | 'duration' | 'bytes_sent' | 'bytes_received'>('first_seen')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const { push } = useToast()
  const { data, error, loading, setData } = usePolling(() => api.active(), 2000, [])

  const items: ActiveConnection[] = useMemo(() => {
    const list = (data?.items ?? []) as ActiveConnection[]
    const q = search.trim()
    const filtered = q ? list.filter((c) => c.ip.includes(q) || String(c.port).includes(q)) : list
    const sorted = [...filtered].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'ip') cmp = a.ip.localeCompare(b.ip)
      else cmp = Number((a[sortKey] as number | null) ?? 0) - Number((b[sortKey] as number | null) ?? 0)
      return sortDir === 'asc' ? cmp : -cmp
    })
    return sorted
  }, [data, search, sortKey, sortDir])

  const toggleSort = (key: typeof sortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortKey(key)
      setSortDir('desc')
    }
  }
  const arrow = (key: typeof sortKey) => (sortKey === key ? (sortDir === 'asc' ? '↑' : '↓') : '')

  const openDevice = (c: ActiveConnection) => {
    setDeviceTarget(c)
    setDeviceFamily(c.device?.source === 'manual' ? c.device.family : '')
  }

  const saveDevice = async () => {
    if (!deviceTarget || !deviceFamily) return
    setDeviceSaving(true)
    try {
      const r = await api.setDevice(deviceTarget.ip, deviceFamily)
      push('ok', `Устройство для ${deviceTarget.ip}: ${r.device.label}`)
      setDeviceTarget(null)
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setDeviceSaving(false)
    }
  }

  const resetDevice = async () => {
    if (!deviceTarget) return
    setDeviceSaving(true)
    try {
      await api.resetDevice(deviceTarget.ip)
      push('ok', 'Ручная метка сброшена, снова автоопределение')
      setDeviceTarget(null)
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setDeviceSaving(false)
    }
  }

  const kill = async () => {
    if (!target) return
    setKilling(true)
    try {
      const res = await api.kill(target.ip, target.port)
      push('ok', res.message)
      setData({ ...(data as any), items: ((data?.items ?? []) as ActiveConnection[]).filter((c) => !(c.ip === target.ip && c.port === target.port)) })
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setKilling(false)
      setTarget(null)
    }
  }

  return (
    <>
      <Card>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Поиск по IP или порту" className="pl-9" />
          </div>
          <Badge tone="info">{loading ? 'обновление…' : `${items.length} сессий`}</Badge>
          <Button className="ml-auto" onClick={() => setData(null)} title="Перезапросить">
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            Обновить
          </Button>
        </div>

        {error ? <div className="mb-3 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}

        <div className="overflow-x-auto">
          <table className="w-full min-w-[1000px] border-collapse">
            <thead>
              <tr className="border-b border-line/70">
                <th className="th cursor-pointer" onClick={() => toggleSort('ip')}>IP {arrow('ip')}</th>
                <th className="th">Устройство</th>
                <th className="th">Порт</th>
                <th className="th">Ключ</th>
                <th className="th cursor-pointer" onClick={() => toggleSort('first_seen')}>Обнаружено {arrow('first_seen')}</th>
                <th className="th cursor-pointer" onClick={() => toggleSort('duration')}>Время {arrow('duration')}</th>
                <th className="th cursor-pointer" onClick={() => toggleSort('bytes_sent')}>↓ клиенту {arrow('bytes_sent')}</th>
                <th className="th cursor-pointer" onClick={() => toggleSort('bytes_received')}>↑ от клиента {arrow('bytes_received')}</th>
                <th className="th">Статус</th>
                <th className="th text-right">Действия</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr
                  key={`${c.ip}:${c.port}`}
                  onClick={() => setDetails(c)}
                  className="cursor-pointer border-b border-line/40 transition hover:bg-ink/[0.03]"
                >
                  <td className="td font-mono text-accent/90">{c.ip}</td>
                  <td className="td" onClick={(e) => e.stopPropagation()}>
                    <DeviceBadge device={c.device} onClick={() => openDevice(c)} />
                  </td>
                  <td className="td font-mono text-muted">{c.port}</td>
                  <td className="td text-muted" title="Прокси не сообщает, каким ключом авторизован клиент">—</td>
                  <td className="td text-muted" title={fmtDate(c.first_seen)}>
                    {fmtRelative(c.first_seen)}
                  </td>
                  <td className="td">{fmtDuration(c.duration)}</td>
                  <td className="td">{c.bytes_sent !== null ? fmtBytes(c.bytes_sent) : '—'}</td>
                  <td className="td">{c.bytes_received !== null ? fmtBytes(c.bytes_received) : '—'}</td>
                  <td className="td">
                    <Badge tone="ok">ESTAB</Badge>
                  </td>
                  <td className="td text-right">
                    <Button
                      variant="danger"
                      className="!px-2.5 !py-1.5 text-xs"
                      onClick={(e) => {
                        e.stopPropagation()
                        setTarget(c)
                      }}
                    >
                      <Skull className="h-3.5 w-3.5" />
                      Отключить
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!items.length && !loading ? (
            <Empty title="Активных подключений нет" hint="Telegram открывает короткоживущие сессии; таблица обновляется каждые 2 секунды." />
          ) : null}
        </div>

        <div className="mt-3 flex items-start gap-2 rounded-lg border border-line/60 bg-ink/5 px-3 py-2 text-[11px] text-muted">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{data?.note ?? 'Прокси не сообщает ключ и DC для активной сессии.'} Устройство определяется приблизительно по TCP SYN (Windows / Apple / Android / Linux) — нажмите на значок, чтобы указать точный тип вручную. Если клиент в LAN подключается через публичный IP, роутер может подменять источник на IP шлюза (hairpin NAT) — для устройств в локальной сети используйте LAN-ссылку из раздела «Ключи».</span>
        </div>
      </Card>

      <Dialog open={!!details} onClose={() => setDetails(null)} title="Детали активного подключения" wide>
        {details ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Detail label="IP клиента" value={details.ip} />
              <Detail label="Устройство" value={details.device ? `${details.device.label}${details.device.source === 'syn' ? ' (SYN)' : details.device.source === 'manual' ? ' (вручную)' : ''}` : '—'} />
              <Detail label="Порт клиента" value={String(details.port)} />
              <Detail label="Локальный адрес" value={`${details.local_ip}:${details.local_port}`} />
              <Detail label="Состояние" value={details.state} />
              <Detail label="Обнаружено" value={fmtDate(details.first_seen)} />
              <Detail label="Длительность" value={fmtDuration(details.duration)} />
              <Detail label="Отправлено клиенту" value={details.bytes_sent !== null ? fmtBytes(details.bytes_sent) : 'н/д'} />
              <Detail label="Получено от клиента" value={details.bytes_received !== null ? fmtBytes(details.bytes_received) : 'н/д'} />
            </div>
            <div className="rounded-lg border border-line/60 bg-ink/5 px-3 py-2 text-[11px] text-muted">
              Ключ и DC активной сессии прокси не сообщает: они определяются только после записи строки
              «session closed» в журнал. Счётчики трафика — TCP-уровня (tcp_info), могут быть недоступны для простаивающих сокетов.
            </div>
          </div>
        ) : null}
      </Dialog>

      <Dialog
        open={!!deviceTarget}
        onClose={() => setDeviceTarget(null)}
        title="Устройство клиента"
        footer={
          <>
            <Button onClick={() => void resetDevice()} loading={deviceSaving}>Сбросить</Button>
            <Button onClick={() => setDeviceTarget(null)} disabled={deviceSaving}>Отмена</Button>
            <Button variant="primary" onClick={() => void saveDevice()} loading={deviceSaving} disabled={!deviceFamily}>
              Сохранить
            </Button>
          </>
        }
      >
        {deviceTarget ? (
          <div className="space-y-3">
            <div className="rounded-lg border border-line/60 bg-ink/5 px-3 py-2 text-xs">
              <div className="font-mono text-accent/90">{deviceTarget.ip}</div>
              <div className="mt-1 text-muted">
                {deviceTarget.device?.source === 'syn'
                  ? `Автоопределение: ${deviceTarget.device.label} (приблизительно по TCP SYN)`
                  : deviceTarget.device?.source === 'manual'
                    ? `Сейчас указано вручную: ${deviceTarget.device.label}`
                    : 'Автоопределение пока нет данных для этого IP'}
              </div>
              {deviceTarget.device?.detail ? <div className="mt-1 text-[10px] text-muted/80">{deviceTarget.device.detail}</div> : null}
            </div>
            <Field label="Тип устройства (вручную)" hint="Ручная метка имеет приоритет над автоопределением и сохраняется в БД панели">
              <Select value={deviceFamily} onChange={(e) => setDeviceFamily(e.target.value)}>
                <option value="">автоопределение</option>
                <option value="android">Android</option>
                <option value="ios">iOS</option>
                <option value="macos">macOS</option>
                <option value="windows">Windows</option>
                <option value="linux">Linux</option>
                <option value="other">Другое</option>
              </Select>
            </Field>
            <div className="rounded-lg border border-warn/25 bg-warn/[0.06] px-3 py-2 text-[11px] leading-relaxed text-warn/90">
              Прокси не передаёт модель устройства: MTProto-трафик зашифрован. Автоопределение — это
              пассивный отпечаток TCP SYN. Windows обычно определяется надёжно; iOS и macOS по SYN
              неразличимы, Android и Linux могут путаться. Для точности укажите тип вручную.
            </div>
          </div>
        ) : null}
      </Dialog>

      <ConfirmDialog
        open={!!target}
        title="Принудительно отключить соединение?"
        text={
          <>
            TCP-сессия <span className="font-mono text-ink">{target?.ip}:{target?.port}</span> будет сброшена (RST) внутри
            namespace контейнера. Клиент переподключится автоматически.
          </>
        }
        confirmLabel="Отключить"
        danger
        loading={killing}
        onClose={() => setTarget(null)}
        onConfirm={() => void kill()}
      />
    </>
  )
}

function HistoryTab() {
  const [ip, setIp] = useState('')
  const [range, setRange] = useState('24h')
  const [closedBy, setClosedBy] = useState('')
  const [dc, setDc] = useState('')
  const [sort, setSort] = useState('ended_at')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Session | null>(null)
  const limit = 25

  const { data, error, loading } = usePolling<HistoryResponse>(
    () => api.history({ ip, range, closed_by: closedBy, dc, sort, order, limit, offset }),
    15000,
    [ip, range, closedBy, dc, sort, order, offset],
  )

  useEffect(() => {
    setOffset(0)
  }, [ip, range, closedBy, dc])

  const sortBy = (col: string) => {
    if (sort === col) setOrder(order === 'asc' ? 'desc' : 'asc')
    else {
      setSort(col)
      setOrder('desc')
    }
  }

  const sortIcon = (col: string) => (sort === col ? (order === 'asc' ? '↑' : '↓') : '')

  return (
    <>
      <Card>
        <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input value={ip} onChange={(e) => setIp(e.target.value)} placeholder="IP клиента" className="pl-9" />
          </div>
          <Select value={range} onChange={(e) => setRange(e.target.value)}>
            <option value="1h">за 1 час</option>
            <option value="6h">за 6 часов</option>
            <option value="24h">за 24 часа</option>
            <option value="7d">за 7 дней</option>
          </Select>
          <Select value={closedBy} onChange={(e) => setClosedBy(e.target.value)}>
            <option value="">закрыто кем: любым</option>
            <option value="client">клиентом</option>
            <option value="upstream">upstream</option>
          </Select>
          <Select value={dc} onChange={(e) => setDc(e.target.value)}>
            <option value="">все DC</option>
            {[1, 2, 3, 4, 5].map((d) => (
              <option key={d} value={d}>
                DC{d}
              </option>
            ))}
          </Select>
          <div className="flex items-center justify-end gap-2">
            <Badge tone="muted">{data ? `${fmtNum(data.total)} записей` : '…'}</Badge>
          </div>
        </div>

        {error ? <div className="mb-3 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}

        <div className="mb-3 rounded-lg border border-line/60 bg-ink/5 px-3 py-2 text-[11px] text-muted">
          IP показан таким, каким его видел прокси. Если устройство в LAN подключается к публичному
          адресу через роутер, hairpin NAT может заменить источник на IP шлюза (например,
          <span className="font-mono"> 192.168.50.1</span>) — используйте LAN-ссылку в разделе «Ключи».
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[1060px] border-collapse">
            <thead>
              <tr className="border-b border-line/70">
                <th className="th cursor-pointer" onClick={() => sortBy('client_ip')}>Клиент {sortIcon('client_ip')}</th>
                <th className="th">Устройство</th>
                <th className="th cursor-pointer" onClick={() => sortBy('dc')}>DC {sortIcon('dc')}</th>
                <th className="th">Тип</th>
                <th className="th">Закрыто</th>
                <th className="th cursor-pointer" onClick={() => sortBy('ended_at')}>Завершение {sortIcon('ended_at')}</th>
                <th className="th cursor-pointer" onClick={() => sortBy('duration')}>Длительность {sortIcon('duration')}</th>
                <th className="th cursor-pointer" onClick={() => sortBy('bytes_down')}>
                  <span className="inline-flex items-center gap-1"><ArrowDownToLine className="h-3 w-3" />{sortIcon('bytes_down')}</span>
                </th>
                <th className="th cursor-pointer" onClick={() => sortBy('bytes_up')}>
                  <span className="inline-flex items-center gap-1"><ArrowUpFromLine className="h-3 w-3" />{sortIcon('bytes_up')}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((s) => (
                <tr key={s.id} onClick={() => setSelected(s)} className="cursor-pointer border-b border-line/40 transition hover:bg-ink/[0.03]">
                  <td className="td font-mono text-accent/90">
                    {s.client_ip}
                    <span className="text-muted">:{s.client_port}</span>
                  </td>
                  <td className="td"><DeviceBadge device={s.device} /></td>
                  <td className="td">DC{s.dc}{s.media ? 'm' : ''}</td>
                  <td className="td text-muted">{s.kind}</td>
                  <td className="td">
                    <Badge tone={s.closed_by === 'client' ? 'info' : 'warn'}>{s.closed_by === 'client' ? 'клиент' : 'upstream'}</Badge>
                  </td>
                  <td className="td text-muted" title={fmtDate(s.ended_at)}>{fmtDate(s.ended_at)}</td>
                  <td className="td">{fmtDuration(s.duration)}</td>
                  <td className="td">{fmtBytes(s.bytes_down)}</td>
                  <td className="td">{fmtBytes(s.bytes_up)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && data && !data.items.length ? <Empty title="Записей нет" hint="Измените период или фильтры." /> : null}
        </div>

        <div className="mt-4 flex items-center justify-between gap-2">
          <span className="text-[11px] text-muted">
            {data ? `${data.offset + 1}–${Math.min(data.offset + data.limit, data.total)} из ${fmtNum(data.total)}` : '…'}
          </span>
          <div className="flex gap-2">
            <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Назад</Button>
            <Button disabled={!data || offset + limit >= data.total} onClick={() => setOffset(offset + limit)}>Вперёд</Button>
          </div>
        </div>
      </Card>

      <Dialog open={!!selected} onClose={() => setSelected(null)} title="Детали сессии" wide>
        {selected ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Detail label="Клиент" value={`${selected.client_ip}:${selected.client_port}`} />
              <Detail label="Устройство" value={selected.device ? `${selected.device.label}${selected.device.source === 'syn' ? ' (SYN)' : selected.device.source === 'manual' ? ' (вручную)' : ''}` : '—'} />
              <Detail label="DC" value={`DC${selected.dc}${selected.media ? ' media' : ''}`} />
              <Detail label="Транспорт" value={selected.kind} />
              <Detail label="Закрыто" value={selected.closed_by === 'client' ? 'клиентом' : 'upstream'} />
              <Detail label="Начало" value={fmtDate(selected.started_at)} />
              <Detail label="Конец" value={fmtDate(selected.ended_at)} />
              <Detail label="Длительность" value={fmtDuration(selected.duration)} />
              <Detail label="Трафик" value={`↓ ${fmtBytes(selected.bytes_down)} · ↑ ${fmtBytes(selected.bytes_up)}`} />
            </div>
            <div>
              <div className="label">Строка лога</div>
              <pre className="max-h-64 overflow-auto rounded-xl border border-line bg-ink/[0.08] p-3 text-[11px] text-ink/80">{selected.line}</pre>
            </div>
          </div>
        ) : null}
      </Dialog>
    </>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line/60 bg-ink/5 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-0.5 text-xs font-medium text-ink/90">{value}</div>
    </div>
  )
}
