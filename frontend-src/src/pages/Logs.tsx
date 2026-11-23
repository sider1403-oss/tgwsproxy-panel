import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Download, Info, Pause, Play, Search } from 'lucide-react'
import type { LogEvent } from '../lib/types'
import { api } from '../lib/api'
import { useSse } from '../lib/hooks'
import { categoryLabel, fmtDate, levelTone } from '../lib/format'
import { Badge, Button, Card, Dialog, Empty, Input, Select, Switch, useToast } from '../components/ui'
import { cn } from '../lib/utils'

const PAGE = 100

export default function Logs() {
  const [level, setLevel] = useState('ALL')
  const [category, setCategory] = useState('ALL')
  const [q, setQ] = useState('')
  const [range, setRange] = useState('6h')
  const [offset, setOffset] = useState(0)
  const [items, setItems] = useState<LogEvent[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [live, setLive] = useState(true)
  const [selected, setSelected] = useState<LogEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { push } = useToast()
  const maxIdRef = useRef(0)

  const filters = { level: level === 'ALL' ? '' : level, category: category === 'ALL' ? '' : category, q, range }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await api.logs({ ...filters, limit: PAGE, offset })
      setItems(d.items)
      setTotal(d.total)
      maxIdRef.current = Math.max(0, ...d.items.map((x) => x.id))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, category, q, range, offset])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setOffset(0)
  }, [level, category, range, q])

  const streamUrl = useMemo(() => {
    const params = new URLSearchParams()
    if (level !== 'ALL') params.set('level', level)
    if (q) params.set('q', q)
    params.set('after_id', '0')
    return `/api/logs/stream?${params.toString()}`
  }, [level, q])

  const { connected } = useSse<LogEvent>(streamUrl, 'log', live, (ev) => {
    if (category !== 'ALL' && ev.category !== category) return
    setItems((prev) => {
      if (prev.some((x) => x.id === ev.id)) return prev
      const next = [ev, ...prev]
      return next.length > 400 ? next.slice(0, 400) : next
    })
    setTotal((t) => t + 1)
  })

  const exportFile = (format: 'txt' | 'csv') => {
    const params: Record<string, string> = { format, range }
    if (level !== 'ALL') params.level = level
    if (category !== 'ALL') params.category = category
    if (q) params.q = q
    window.open(api.logsExportUrl(params), '_blank')
    push('info', 'Экспорт запущен')
  }

  const pages = Math.max(1, Math.ceil(total / PAGE))
  const page = Math.floor(offset / PAGE) + 1

  return (
    <div className="space-y-4">
      <Card>
        <div className="grid gap-2 lg:grid-cols-[130px_150px_1fr_140px_auto]">
          <Select value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="ALL">все уровни</option>
            <option value="INFO">INFO</option>
            <option value="WARN">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="DEBUG">DEBUG</option>
          </Select>
          <Select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="ALL">все категории</option>
            <option value="session">сессии</option>
            <option value="upstream">upstream / CF</option>
            <option value="error">ошибки</option>
            <option value="system">система</option>
            <option value="info">инфо</option>
          </Select>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по тексту сообщения" className="pl-9" />
          </div>
          <Select value={range} onChange={(e) => setRange(e.target.value)}>
            <option value="1h">за 1 час</option>
            <option value="6h">за 6 часов</option>
            <option value="24h">за 24 часа</option>
            <option value="7d">за 7 дней</option>
          </Select>
          <div className="flex items-center justify-end gap-2">
            <Switch checked={live} onChange={setLive} label="Live" />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge tone={connected ? 'ok' : 'muted'}>
            {live ? (connected ? 'поток активен' : 'подключение…') : 'поток остановлен'}
          </Badge>
          <Badge tone="muted">{total.toLocaleString('ru-RU')} записей</Badge>
          <span className="text-[11px] text-muted">уровни и категории — из журнала контейнера; секреты маскируются</span>
          <div className="ml-auto flex gap-2">
            <Button className="!py-1.5 text-xs" onClick={() => exportFile('txt')}>
              <Download className="h-3.5 w-3.5" /> TXT
            </Button>
            <Button className="!py-1.5 text-xs" onClick={() => exportFile('csv')}>
              <Download className="h-3.5 w-3.5" /> CSV
            </Button>
            <Button className="!py-1.5 text-xs" onClick={() => (live ? setLive(false) : setLive(true))}>
              {live ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
              {live ? 'Пауза' : 'Продолжить'}
            </Button>
          </div>
        </div>

        {error ? <div className="mt-3 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}
      </Card>

      <Card className="!p-0">
        <div className="max-h-[65vh] overflow-auto">
          <table className="w-full min-w-[900px] border-collapse">
            <thead className="sticky top-0 z-10 bg-card">
              <tr className="border-b border-line/70">
                <th className="th w-[170px]">Время</th>
                <th className="th w-[78px]">Уровень</th>
                <th className="th w-[110px]">Категория</th>
                <th className="th w-[130px]">IP</th>
                <th className="th">Сообщение</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id} onClick={() => setSelected(e)} className="cursor-pointer border-b border-line/30 transition hover:bg-ink/[0.03]">
                  <td className="td whitespace-nowrap font-mono text-[11px] text-muted">{fmtDate(e.ts)}</td>
                  <td className="td"><Badge tone={levelTone(e.level)}>{e.level}</Badge></td>
                  <td className="td text-xs text-muted">{categoryLabel(e.category)}</td>
                  <td className="td font-mono text-[11px] text-accent/80">{e.ip ?? '—'}</td>
                  <td className="td">
                    <div className={cn('line-clamp-1 max-w-[720px] font-mono text-[11px]', e.level === 'WARN' && 'text-warn/90', e.level === 'ERROR' && 'text-bad/90')}>
                      {e.message}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!items.length && !loading ? <Empty title="Записей нет" hint="Измените период или фильтры." /> : null}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line/70 px-4 py-3">
          <span className="text-[11px] text-muted">
            {loading ? 'Загрузка…' : `страница ${page} из ${pages}`}
          </span>
          <div className="flex gap-2">
            <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Назад</Button>
            <Button disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Вперёд</Button>
          </div>
        </div>
      </Card>

      <div className="flex items-start gap-2 rounded-xl border border-line/60 bg-ink/5 px-4 py-3 text-[11px] text-muted">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <div>
          Источник: Docker json-file контейнера tgwsproxy (ротация 3×10 МБ). Панель импортирует записи с момента запуска контейнера
          и хранит их в собственной БД до 7 дней. Авторизация ключом в логах прокси не фиксируется — события входа/выхода
          клиента видны только как строки сессий (session closed).
        </div>
      </div>

      <Dialog open={!!selected} onClose={() => setSelected(null)} title="Запись журнала" wide>
        {selected ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={levelTone(selected.level)}>{selected.level}</Badge>
              <Badge tone="muted">{categoryLabel(selected.category)}</Badge>
              <span className="text-[11px] text-muted">{fmtDate(selected.ts)}</span>
              {selected.ip ? <span className="font-mono text-[11px] text-accent/80">{selected.ip}</span> : null}
            </div>
            <div>
              <div className="label">Модуль</div>
              <div className="font-mono text-xs text-muted">{selected.module ?? '—'}</div>
            </div>
            <div>
              <div className="label">Сообщение</div>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-ink/[0.08] p-3 text-[11px] leading-relaxed text-ink/85">
                {selected.message}
              </pre>
            </div>
          </div>
        ) : null}
      </Dialog>
    </div>
  )
}
