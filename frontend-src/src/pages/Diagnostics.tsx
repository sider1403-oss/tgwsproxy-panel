import { useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronRight, CircleSlash, Clock, Loader2, Play, RefreshCw, ShieldCheck, XCircle, Zap } from 'lucide-react'
import type { DiagCheck, DiagResult, DiagnosticsState } from '../lib/types'
import { api } from '../lib/api'
import { usePolling } from '../lib/hooks'
import { fmtDate, fmtDuration, fmtRelative } from '../lib/format'
import { Badge, Button, Card, CardTitle, ConfirmDialog, Dialog, Empty, Spinner, useToast } from '../components/ui'
import { cn } from '../lib/utils'

function statusMeta(status: string) {
  if (status === 'ok') return { tone: 'ok' as const, icon: CheckCircle2, label: 'OK' }
  if (status === 'warn') return { tone: 'warn' as const, icon: AlertTriangle, label: 'ВНИМАНИЕ' }
  if (status === 'fail') return { tone: 'bad' as const, icon: XCircle, label: 'ОШИБКА' }
  return { tone: 'muted' as const, icon: CircleSlash, label: 'ПРОПУЩЕНО' }
}

export default function Diagnostics() {
  const { data, error, loading, setData } = usePolling<DiagnosticsState>(() => api.diagnostics(), 25000, [])
  const [busy, setBusy] = useState<'quick' | 'probe' | null>(null)
  const [confirmProbe, setConfirmProbe] = useState(false)
  const [outputOpen, setOutputOpen] = useState(false)
  const { push } = useToast()

  const quick = data?.quick ?? null
  const probe = data?.probe ?? null
  const checks: DiagCheck[] = quick?.checks ?? []
  const cf = checks.find((c) => c.id === 'cf')

  const refresh = async () => {
    try {
      setData(await api.diagnostics())
    } catch {
      /* ignored, polling will retry */
    }
  }

  const runQuick = async () => {
    setBusy('quick')
    try {
      const r = await api.diagQuick()
      push(r.status === 'fail' ? 'bad' : r.status === 'warn' ? 'warn' : 'ok', r.summary)
      await refresh()
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const runProbe = async () => {
    setConfirmProbe(false)
    setBusy('probe')
    try {
      const r = await api.diagProbe()
      push(r.ok ? 'ok' : r.status === 'warn' ? 'warn' : 'bad', r.summary)
      await refresh()
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const overall = quick ? statusMeta(quick.status) : null
  const OverallIcon = overall?.icon

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
        <Card className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(500px_180px_at_10%_0%,rgba(34,211,238,0.08),transparent_70%)]" />
          <div className="relative flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-lg font-semibold">Канал прокси</span>
                {quick ? (
                  <Badge tone={overall!.tone}>
                    {OverallIcon ? <OverallIcon className="h-3.5 w-3.5" /> : null}
                    {overall!.label}
                  </Badge>
                ) : (
                  <Badge tone="muted">нет данных</Badge>
                )}
                {data?.ops.busy ? <Badge tone="warn">выполняется: {data.ops.current}</Badge> : null}
              </div>
              <div className="mt-2 max-w-xl text-sm text-ink/80">
                {quick ? quick.summary : 'Быстрая проверка ещё не запускалась. Она проверяет контейнер, порт, конфигурацию, CF-домены и доступность DC.'}
              </div>
              {quick ? (
                <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-muted">
                  <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" /> {fmtRelative(quick.ts)}</span>
                  <span>длительность {fmtDuration((quick.duration_ms ?? 0) / 1000)}</span>
                  <span>{checks.find((c) => c.id === 'dc')?.detail ?? 'прямой доступ к DC проверяется отдельно'}</span>
                </div>
              ) : null}
            </div>
            <div className="flex flex-col gap-2">
              <Button variant="primary" onClick={() => void runQuick()} loading={busy === 'quick'} disabled={busy !== null}>
                <RefreshCw className="h-4 w-4" /> Быстрая проверка
              </Button>
              <Badge tone="muted">Сквозная проверка отключена</Badge>
            </div>
          </div>
          {error ? <div className="mt-3 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}
        </Card>

        <Card>
          <CardTitle right={<ShieldCheck className="h-4 w-4 text-muted" />}>Что проверяется</CardTitle>
          <ul className="space-y-1.5 text-xs text-muted">
            <li>• контейнер, health, uptime</li>
            <li>• TCP-порт прокси</li>
            <li>• валидность docker-compose</li>
            <li>• DNS и TCP до CF-доменов (ws:// порт 80 при <span className="font-mono">TG_CF_DISABLE_TLS</span>)</li>
            <li>• прямой доступ к DC (ожидаемо заблокирован)</li>
            <li>• предупреждения и сессии за 10 минут</li>
            <li>• сквозная проверка отключена: временные контейнеры запрещены</li>
          </ul>
        </Card>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {checks.map((c) => {
          const meta = statusMeta(c.status)
          const Icon = meta.icon
          return (
            <Card key={c.id} className="p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-[11px] uppercase tracking-wider text-muted">{c.label}</div>
                  <div className="mt-1 text-sm text-ink/90">{c.detail}</div>
                  {c.latency_ms != null ? <div className="mt-1 text-[11px] text-muted">{c.latency_ms} мс</div> : null}
                </div>
                <Badge tone={meta.tone}><Icon className="h-3.5 w-3.5" /></Badge>
              </div>
              {c.id === 'cf' && c.items?.length ? (
                <div className="mt-3 max-h-36 overflow-auto rounded-lg border border-line/60 bg-ink/5">
                  <table className="w-full text-[11px]">
                    <tbody>
                      {c.items.map((it: any, i: number) => (
                        <tr key={i} className="border-b border-line/30 last:border-0">
                          <td className="px-2 py-1 font-mono text-muted">{it.host}</td>
                          <td className="px-2 py-1 text-right">{it.port ?? '—'}</td>
                          <td className={cn('px-2 py-1 text-right', it.ok ? 'text-ok' : 'text-bad')}>{it.ok ? `${it.latency_ms ?? '?'} мс` : it.error || 'FAIL'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
              {c.id === 'dc' && c.items?.length ? (
                <div className="mt-3 space-y-1 text-[11px] text-muted">
                  {c.items.map((it: any, i: number) => (
                    <div key={i} className="flex items-center justify-between">
                      <span>DC{it.dc} · {it.ip}</span>
                      <span className={it.ok ? 'text-ok' : 'text-warn'}>{it.ok ? `${it.latency_ms} мс` : 'timeout'}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </Card>
          )
        })}
        {!checks.length && !loading ? (
          <Card className="sm:col-span-2 xl:col-span-3"><Empty title="Нет результатов" hint="Запустите быструю проверку." /></Card>
        ) : null}
      </div>

      <Card>
        <CardTitle
          right={
            probe ? (
              <Badge tone={statusMeta(probe.status).tone}>
                {probe.status === 'ok' ? 'ПРОЙДЕНО' : probe.status === 'warn' ? 'ЧАСТИЧНО' : 'НЕ ПРОЙДЕНО'}
              </Badge>
            ) : (
              <Badge tone="muted">не запускалась</Badge>
            )
          }
        >
          Сквозная проверка (MTProto через CF)
        </CardTitle>
        {probe ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-muted">
              <span>{probe.summary}</span>
              <span>{fmtDate(probe.ts)}</span>
              <span>{fmtDuration((probe.duration_ms ?? 0) / 1000)}</span>
              {probe.domains?.length ? <span>целей: {probe.domains.length}</span> : null}
              {probe.output ? (
                <button className="link inline-flex items-center gap-1 text-xs" onClick={() => setOutputOpen(true)}>
                  полный вывод <ChevronRight className="h-3 w-3" />
                </button>
              ) : null}
            </div>
            {probe.domains?.length ? (
              <div className="max-h-56 overflow-auto rounded-xl border border-line/60 bg-ink/5">
                <table className="w-full min-w-[420px] text-[11px]">
                  <tbody>
                    {probe.domains.map((d, i) => (
                      <tr key={i} className="border-b border-line/30 last:border-0">
                        <td className="px-3 py-1.5 font-mono text-muted">{d.host}</td>
                        <td className={cn('px-3 py-1.5 text-right', d.status === 'ok' ? 'text-ok' : d.status === 'fail' ? 'text-bad' : 'text-warn')}>
                          {d.status.toUpperCase()}{d.latency_ms != null ? ` · ${d.latency_ms} мс` : ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ) : (
          <Empty title="Сквозная проверка отключена" hint="В целях безопасности панель больше не создаёт временные контейнеры. История старых проверок сохранена; быстрая проверка работает." />
        )}
      </Card>

      <Card>
        <CardTitle right={loading ? <Spinner /> : null}>История проверок</CardTitle>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse">
            <thead>
              <tr className="border-b border-line/70">
                <th className="th">Время</th>
                <th className="th">Тип</th>
                <th className="th">Статус</th>
                <th className="th">Результат</th>
                <th className="th text-right">Длительность</th>
              </tr>
            </thead>
            <tbody>
              {(data?.history ?? []).map((h, i) => {
                const meta = statusMeta(h.status)
                return (
                  <tr key={`${h.ts}-${i}`} className="border-b border-line/40">
                    <td className="td whitespace-nowrap text-muted">{fmtDate(h.ts)}</td>
                    <td className="td">{h.kind === 'probe' ? 'сквозная' : 'быстрая'}</td>
                    <td className="td"><Badge tone={meta.tone}>{h.status.toUpperCase()}</Badge></td>
                    <td className="td text-muted">{h.summary}</td>
                    <td className="td text-right text-muted">{fmtDuration((h.duration_ms ?? 0) / 1000)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {!data?.history.length ? <Empty title="История пуста" /> : null}
        </div>
      </Card>

      <ConfirmDialog
        open={confirmProbe}
        title="Запустить сквозную проверку?"
        text={
          <>
            Будет запущен <b>временный</b> контейнер прокси без публикации порта: он поднимет listener на localhost,
            пройдёт по CF-доменам и сделает реальный MTProto-запрос. Рабочий контейнер и конфигурация не изменяются.
            Проверка занимает до ~30 секунд.
          </>
        }
        confirmLabel="Запустить"
        loading={busy === 'probe'}
        onClose={() => setConfirmProbe(false)}
        onConfirm={() => void runProbe()}
      />

      <Dialog open={outputOpen} onClose={() => setOutputOpen(false)} title="Полный вывод сквозной проверки" wide footer={<Button onClick={() => setOutputOpen(false)}>Закрыть</Button>}>
        <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-ink/10 p-3 font-mono text-[11px] leading-relaxed text-ink/80">
          {probe?.output || '—'}
        </pre>
      </Dialog>
    </div>
  )
}
