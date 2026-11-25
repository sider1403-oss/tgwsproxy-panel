import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Activity, AlertTriangle, ArrowDownUp, Cpu, Gauge, HardDrive, KeyRound, Users } from 'lucide-react'
import type { Overview } from '../lib/types'
import { api } from '../lib/api'
import { useSse } from '../lib/hooks'
import { fmtBytes, fmtDuration, fmtNum, fmtRelative, fmtSpeed, levelTone, pct } from '../lib/format'
import { Badge, Button, Card, CardTitle, Dot, Empty, Tabs } from '../components/ui'
import { StatCard } from '../components/StatCard'
import { ConnectionsChart, DcChart, TrafficChart } from '../components/charts'
import { cn } from '../lib/utils'

const RANGES = [
  { value: '1h', label: '1 час' },
  { value: '6h', label: '6 часов' },
  { value: '24h', label: '24 часа' },
  { value: '7d', label: '7 дней' },
]

export default function Dashboard() {
  const [params, setParams] = useSearchParams()
  const paramsRange = params.get('range') || '1h'
  const range = RANGES.some((item) => item.value === paramsRange) ? paramsRange : '1h'
  const setRange = (value: string) => {
    const next = new URLSearchParams(params)
    next.set('range', value)
    setParams(next, { replace: true })
  }
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { connected } = useSse<Overview>(`/api/stream?range=${range}`, 'overview', true, (d) => {
    setData(d)
    setError(null)
  })

  useEffect(() => {
    let alive = true
    api
      .overview(range)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [range])

  useEffect(() => {
    if (connected) return
    const t = setInterval(() => {
      api
        .overview(range)
        .then((d) => setData(d))
        .catch(() => undefined)
    }, 15000)
    return () => clearInterval(t)
  }, [connected, range])

  if (!data) {
    return (
      <Card>
        <Empty
          title={error ? 'Не удалось загрузить данные' : 'Загрузка…'}
          hint={error ?? 'Панель получает телеметрию из Docker и логов прокси.'}
        />
      </Card>
    )
  }

  const p = data.proxy
  const m = data.metrics
  const running = p.running
  const memPct = pct(m.mem_used, m.mem_total)
  const traffic = data.series.traffic
  const hasTraffic = traffic.some((x) => x.up || x.down)

  return (
    <div className="space-y-4 sm:space-y-5">
      {/* hero */}
      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Link to="/service?from=dashboard" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
        <Card className="relative cursor-pointer overflow-hidden transition duration-150 hover:border-accent/40 hover:shadow-lg">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(500px_180px_at_15%_0%,rgba(34,211,238,0.10),transparent_70%)]" />
          <div className="relative flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2.5">
                <Dot tone={running ? (p.health === 'healthy' ? 'ok' : 'warn') : 'bad'} live={running} />
                <span className="text-lg font-semibold">
                  {running ? 'TGWSProxy работает' : 'TGWSProxy остановлен'}
                </span>
                <Badge tone={p.health === 'healthy' ? 'ok' : running ? 'warn' : 'bad'}>
                  {p.health ?? p.state}
                </Badge>
              </div>
              <div className="mt-2 text-xs text-muted">
                контейнер <span className="font-mono text-ink/80">tgwsproxy</span> · версия{' '}
                <span className="text-ink/80">{p.version ?? '—'}</span> ·{' '}
                {p.ports.join(', ') || 'порт не опубликован'}
              </div>
              <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
                <div>
                  <div className="text-muted">Время работы</div>
                  <div className="mt-0.5 font-medium">{fmtDuration(p.uptime)}</div>
                </div>
                <div>
                  <div className="text-muted">Запущен</div>
                  <div className="mt-0.5 font-medium">{fmtRelative(p.started_at)}</div>
                </div>
                <div>
                  <div className="text-muted">Restart policy</div>
                  <div className="mt-0.5 font-medium">{p.restart_policy ?? '—'}</div>
                </div>
                <div>
                  <div className="text-muted">Образ</div>
                  <div className="mt-0.5 truncate font-mono text-[11px]">{p.image}</div>
                </div>
                <div>
                  <div className="text-muted">CPU прокси</div>
                  <div className="mt-0.5 font-medium">{m.cpu_proxy.toFixed(2)} %</div>
                </div>
                <div>
                  <div className="text-muted">RAM прокси</div>
                  <div className="mt-0.5 font-medium">{fmtBytes(m.mem_proxy)}</div>
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-[11px] uppercase tracking-wider text-muted">активные сессии</div>
              <div className="mt-1 text-4xl font-semibold tracking-tight text-accent">{fmtNum(m.active_count)}</div>
              <div className="mt-1 text-[11px] text-muted">всего клиентов: {fmtNum(data.totals.clients_24h)}</div>
              <div className="mt-3 flex items-center justify-end gap-2 text-[11px] text-muted">
                <span className={cn('h-1.5 w-1.5 rounded-full', connected ? 'bg-ok' : 'bg-warn')} />
                {connected ? 'обновление в реальном времени' : 'обновление опросом'}
              </div>
            </div>
          </div>
        </Card>
        </Link>

        <Link to="/traffic?range=24h" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
        <Card className="h-full cursor-pointer transition duration-150 hover:border-accent/40 hover:shadow-lg">
          <CardTitle right={<Gauge className="h-4 w-4 text-muted" />}>Трафик</CardTitle>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[11px] text-muted">Передано клиентам (↓)</div>
              <div className="mt-1 text-xl font-semibold text-accent">{fmtBytes(data.totals.bytes_down_24h)}</div>
              <div className="mt-1 text-[11px] text-muted">{fmtSpeed(m.speed_out)}</div>
            </div>
            <div>
              <div className="text-[11px] text-muted">Получено от клиентов (↑)</div>
              <div className="mt-1 text-xl font-semibold text-accent2">{fmtBytes(data.totals.bytes_up_24h)}</div>
              <div className="mt-1 text-[11px] text-muted">{fmtSpeed(m.speed_in)}</div>
            </div>
          </div>
          <div className="mt-4 rounded-xl border border-line/70 bg-ink/5 px-3 py-2.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted">Всего за 24 часа</span>
              <span className="font-medium">{fmtBytes(data.totals.bytes_total_24h)}</span>
            </div>
            <div className="mt-2 flex items-center justify-between text-xs">
              <span className="text-muted">Сессий за 24 часа</span>
              <span className="font-medium">{fmtNum(data.totals.sessions_24h)}</span>
            </div>
            <div className="mt-2 flex items-center justify-between text-xs">
              <span className="text-muted">С запуска контейнера</span>
              <span className="font-medium">{fmtBytes(data.totals.bytes_total)}</span>
            </div>
            <div className="mt-1 text-[10px] text-muted/70">сессий с запуска: {fmtNum(data.totals.sessions)}</div>
          </div>
        </Card>
        </Link>
      </div>

      {/* stats */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard
          to="/connections?tab=active&from=dashboard"
          label="Активные подключения"
          value={data.active_error ? '—' : fmtNum(m.active_count)}
          sub={data.active_error ? 'ошибка получения данных' : 'TCP-сессии клиентов'}
          icon={<Activity className="h-4 w-4" />}
          tone={data.active_error ? 'bad' : 'accent'}
        />
        <StatCard to="/clients?range=24h" label="Всего клиентов" value={fmtNum(data.totals.clients_24h)} sub={`за 24 ч · с запуска ${fmtNum(data.totals.clients)}`} icon={<Users className="h-4 w-4" />} />
        <StatCard
          to="/logs?level=ERROR&range=24h&from=dashboard"
          label="Ошибки"
          value={fmtNum(data.errors.last_24h)}
          sub={`за 24 ч · в журнале ${fmtNum(data.errors.total)}`}
          icon={<AlertTriangle className="h-4 w-4" />}
          tone={data.errors.last_24h > 0 ? 'bad' : 'default'}
        />
        <StatCard
          to="/logs?level=WARN&range=24h&from=dashboard"
          label="Предупреждения"
          value={fmtNum(data.warnings?.last_24h ?? 0)}
          sub={`за 24 ч · в журнале ${fmtNum(data.warnings?.total ?? 0)}`}
          icon={<AlertTriangle className="h-4 w-4" />}
          tone={(data.warnings?.last_24h ?? 0) > 0 ? 'warn' : 'default'}
        />
        <StatCard to={`/metrics/cpu?range=${range}`} label="CPU LXC" value={`${m.cpu_host.toFixed(1)} %`} sub={`1 vCPU · RAM ${memPct}%`} icon={<Cpu className="h-4 w-4" />} />
        <StatCard to={`/metrics/memory?range=${range}`} label="RAM сервера" value={fmtBytes(m.mem_used)} sub={`из ${fmtBytes(m.mem_total)}`} icon={<HardDrive className="h-4 w-4" />} />
        <StatCard to={`/metrics/speed?dir=in&range=${range}`} label="Скорость входящая" value={fmtSpeed(m.speed_in)} sub="в сторону прокси" icon={<ArrowDownUp className="h-4 w-4" />} />
        <StatCard to={`/metrics/speed?dir=out&range=${range}`} label="Скорость исходящая" value={fmtSpeed(m.speed_out)} sub="от прокси клиентам" icon={<ArrowDownUp className="h-4 w-4" />} />
      </div>

      {/* charts */}
      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardTitle
            right={
              <Tabs value={range} onChange={setRange} items={RANGES} />
            }
          >
            Сетевой трафик по сессиям
          </CardTitle>
          {hasTraffic ? (
            <TrafficChart data={traffic} />
          ) : (
            <Empty title="Нет данных за выбранный период" hint="Трафик строится по записям о завершённых сессиях из логов прокси." />
          )}
          <div className="mt-2 text-[11px] text-muted">
            Источник: лог контейнера (строки «session closed»). Значения округлены прокси до 0,1 КБ.
          </div>
        </Card>

        <Link to={`/dc?range=${range}`} className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
        <Card className="h-full cursor-pointer transition duration-150 hover:border-accent/40 hover:shadow-lg">
          <CardTitle>Распределение по DC</CardTitle>
          {data.dc.length ? <DcChart data={data.dc} /> : <Empty title="Нет сессий" />}
          <div className="mt-2 space-y-1.5">
            {data.dc.slice(0, 5).map((d) => (
              <div key={d.dc} className="flex items-center justify-between text-xs">
                <span className="text-muted">DC{d.dc}</span>
                <span>
                  {fmtNum(d.sessions)} сессий · {fmtBytes(d.bytes)}
                </span>
              </div>
            ))}
          </div>
        </Card>
        </Link>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Link to="/connections?tab=active&from=dashboard" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
        <Card className="h-full cursor-pointer transition duration-150 hover:border-accent/40 hover:shadow-lg">
          <CardTitle right={<span className="text-[11px] text-muted">с момента запуска панели</span>}>
            Активные подключения
          </CardTitle>
          {data.series.connections.length ? (
            <ConnectionsChart data={data.series.connections} />
          ) : (
            <Empty title="Накапливаем данные" hint="График заполняется по мере работы панели (каждые 5 секунд)." />
          )}
        </Card>
        </Link>

        <Link to="/logs?level=WARN,ERROR&range=24h&from=dashboard" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
        <Card className="h-full cursor-pointer transition duration-150 hover:border-accent/40 hover:shadow-lg">
          <CardTitle right={<Badge tone="warn">последние события</Badge>}>Предупреждения и ошибки</CardTitle>
          {data.recent_errors.length ? (
            <div className="space-y-2">
              {data.recent_errors.map((e) => (
                <div key={e.id} className="rounded-xl border border-line/60 bg-ink/5 px-3 py-2">
                  <div className="flex items-center gap-2 text-[11px] text-muted">
                    <Badge tone={levelTone(e.level)}>{e.level}</Badge>
                    <span>{fmtRelative(e.ts)}</span>
                    {e.ip ? <span className="font-mono">{e.ip}</span> : null}
                  </div>
                  <div className="mt-1 line-clamp-2 text-xs text-ink/80">{e.message}</div>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="Ошибок нет" hint="В логах прокси нет предупреждений за доступный период." />
          )}
        </Card>
        </Link>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
        <span>
          Данные обновлены: {fmtRelative(data.generated_at)} · источник: docker logs, /proc, ss (netns контейнера)
        </span>
        <Button variant="ghost" onClick={() => api.overview(range).then(setData)} className="!py-1.5 text-xs">
          Обновить
        </Button>
      </div>
    </div>
  )
}
