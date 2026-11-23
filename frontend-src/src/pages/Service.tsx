import { useState } from 'react'
import { CheckCircle2, FileCode2, HardDrive, History, Play, Power, RefreshCw, RotateCcw, ScrollText, Square, XCircle } from 'lucide-react'
import type { ActionResult, AuditResponse, ConfigSnapshot, ServiceInfo, StorageInfo } from '../lib/types'
import { api } from '../lib/api'
import { usePolling } from '../lib/hooks'
import { fmtBytes, fmtDate, fmtDuration } from '../lib/format'
import { Badge, Button, Card, CardTitle, ConfirmDialog, Dialog, Empty, useToast } from '../components/ui'
import { cn } from '../lib/utils'

const ACTION_LABELS: Record<string, string> = {
  'service.start': 'Запуск прокси',
  'service.stop': 'Остановка прокси',
  'service.restart': 'Перезапуск прокси',
  'service.check': 'Проверка состояния',
  'config.apply': 'Применение конфигурации',
  'config.restore': 'Восстановление конфигурации',
  'key.add': 'Создание ключа',
  'key.disable': 'Отключение ключа',
  'key.enable': 'Включение ключа',
  'key.delete': 'Удаление ключа',
  'key.comment': 'Комментарий ключа',
  'connection.kill': 'Разрыв соединения',
  'alerts.settings': 'Настройки уведомлений',
  'alerts.test': 'Тест уведомлений',
  'diagnostics.check': 'Быстрая диагностика',
  'diagnostics.probe': 'Сквозная проверка',
}

export default function Service() {
  const { data, error, loading } = usePolling<ServiceInfo>(() => api.service(), 5000, [])
  const { data: auditData } = usePolling<AuditResponse>(() => api.audit(50), 15000, [])
  const { data: storage } = usePolling<StorageInfo>(() => api.storage(), 30000, [])
  const [busy, setBusy] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<'stop' | 'restart' | null>(null)
  const [result, setResult] = useState<ActionResult | null>(null)
  const [logOpen, setLogOpen] = useState(false)
  const [logs, setLogs] = useState('')
  const [configOpen, setConfigOpen] = useState(false)
  const [config, setConfig] = useState<ConfigSnapshot | null>(null)
  const { push } = useToast()

  const st = data?.state
  const running = st?.running

  const act = async (action: 'start' | 'stop' | 'restart' | 'check') => {
    setBusy(action)
    setResult(null)
    try {
      const r = await api.serviceAction(action)
      setResult(r)
      if (r.ok) push('ok', action === 'check' ? 'Проверка пройдена' : 'Операция выполнена')
      else push('bad', r.error || 'Операция завершилась с ошибкой')
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setResult({ ok: false, error: msg })
      push('bad', msg)
    } finally {
      setBusy(null)
      setConfirm(null)
    }
  }

  const openLogs = async () => {
    setLogOpen(true)
    setLogs('загрузка…')
    try {
      const r = await api.serviceLogs(300)
      setLogs(r.text || 'пусто')
    } catch (e) {
      setLogs(e instanceof Error ? e.message : String(e))
    }
  }

  const openConfig = async () => {
    setConfigOpen(true)
    setConfig(null)
    try {
      setConfig(await api.config())
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardTitle right={<Badge tone={running ? 'ok' : 'bad'}>{running ? st?.state : 'stopped'}</Badge>}>Состояние сервиса</CardTitle>
          {error ? <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}
          {st ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Info label="Health" value={st.health ?? '—'} tone={st.health === 'healthy' ? 'ok' : 'warn'} />
              <Info label="Время работы" value={fmtDuration(st.uptime)} />
              <Info label="Версия" value={data?.version ?? '—'} />
              <Info label="PID контейнера" value={st.pid ? String(st.pid) : '—'} />
              <Info label="Restart policy" value={st.restart_policy ?? '—'} />
              <Info label="Порт" value={data?.port_check.ok ? 'отвечает' : data?.port_check.message ?? '—'} tone={data?.port_check.ok ? 'ok' : 'bad'} />
              <Info label="Образ" value={st.image ?? '—'} wide />
              <Info label="Опубликованные порты" value={st.ports.join(', ') || '—'} wide />
              <Info label="Запущен" value={fmtDate(st.started_at)} wide />
            </div>
          ) : (
            <Empty title="Загрузка состояния…" />
          )}
        </Card>

        <Card>
          <CardTitle>Управление</CardTitle>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="primary" onClick={() => void act('start')} loading={busy === 'start'} disabled={!!running}>
              <Play className="h-4 w-4" /> Запустить
            </Button>
            <Button variant="danger" onClick={() => setConfirm('stop')} loading={busy === 'stop'} disabled={!running}>
              <Square className="h-4 w-4" /> Остановить
            </Button>
            <Button variant="warn" onClick={() => setConfirm('restart')} loading={busy === 'restart'} disabled={!running}>
              <RotateCcw className="h-4 w-4" /> Перезапустить
            </Button>
            <Button onClick={() => void act('check')} loading={busy === 'check'}>
              <CheckCircle2 className="h-4 w-4" /> Проверить
            </Button>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <Button onClick={() => void openConfig()}>
              <FileCode2 className="h-4 w-4" /> Конфигурация
            </Button>
            <Button onClick={() => void openLogs()}>
              <ScrollText className="h-4 w-4" /> Логи Docker
            </Button>
          </div>
          <div className="mt-4 rounded-lg border border-warn/20 bg-warn/[0.05] px-3 py-2 text-[11px] leading-relaxed text-warn/90">
            Остановка и перезапуск прерывают все активные сессии. Telegram переподключится автоматически.
          </div>
        </Card>
      </div>

      {result ? (
        <Card>
          <CardTitle
            right={
              <Badge tone={result.ok ? 'ok' : 'bad'}>
                {result.ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                {result.ok ? 'успешно' : 'ошибка'}
              </Badge>
            }
          >
            Результат операции{result.action ? `: ${result.action}` : ''}
            {result.duration_ms ? <span className="ml-2 text-[11px] font-normal text-muted">{result.duration_ms} мс</span> : null}
          </CardTitle>
          {result.error ? <div className="mb-3 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 font-mono text-[11px] text-bad">{result.error}</div> : null}
          {result.rollback ? <div className="mb-3 rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-[11px] text-warn">{result.rollback}</div> : null}
          {result.output ? (
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-ink/[0.08] p-3 font-mono text-[11px] text-ink/80">{result.output}</pre>
          ) : null}
        </Card>
      ) : null}

      <Card>
        <CardTitle right={<Badge tone="muted">{auditData?.total ?? 0}</Badge>}>Журнал действий</CardTitle>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] border-collapse">
            <thead>
              <tr className="border-b border-line/70">
                <th className="th">Время</th>
                <th className="th">Действие</th>
                <th className="th">Объект</th>
                <th className="th">Результат</th>
                <th className="th">IP</th>
                <th className="th text-right">Длительность</th>
              </tr>
            </thead>
            <tbody>
              {(auditData?.items ?? []).map((a) => (
                <tr key={a.id} className="border-b border-line/40" title={a.detail ?? undefined}>
                  <td className="td whitespace-nowrap text-muted">{fmtDate(a.ts)}</td>
                  <td className="td">{ACTION_LABELS[a.action] ?? a.action}</td>
                  <td className="td font-mono text-[11px] text-muted">{a.target ?? '—'}</td>
                  <td className="td">
                    <Badge tone={a.ok ? 'ok' : 'bad'}>{a.ok ? 'успешно' : 'ошибка'}</Badge>
                  </td>
                  <td className="td font-mono text-[11px] text-muted">{a.ip ?? '—'}</td>
                  <td className="td text-right text-muted">{a.duration_ms != null ? `${a.duration_ms} мс` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!auditData?.items.length ? <Empty title="Действий пока не было" hint="Здесь появятся запуск/остановка, применение конфигурации, операции с ключами и разрывы соединений." /> : null}
        </div>
        <div className="mt-2 flex items-center gap-2 text-[11px] text-muted">
          <History className="h-3.5 w-3.5" />
          Хранится 30 дней. Содержимое изменений — во всплывающей подсказке (наведите на строку).
        </div>
      </Card>

      <Card>
        <CardTitle
          right={
            storage ? (
              <Badge tone={storage.disk.percent > 85 ? 'warn' : 'ok'}>
                <HardDrive className="h-3.5 w-3.5" /> {storage.disk.percent}% диска
              </Badge>
            ) : null
          }
        >
          Хранилище и лимиты логов
        </CardTitle>
        {storage ? (
          <div className="space-y-3">
            <div>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="text-muted">Диск /</span>
                <span>
                  {fmtBytes(storage.disk.used)} из {fmtBytes(storage.disk.total)} · свободно {fmtBytes(storage.disk.free)}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-ink/10">
                <div
                  className={cn('h-2 rounded-full transition-all', storage.disk.percent > 85 ? 'bg-bad' : 'bg-accent')}
                  style={{ width: `${Math.min(100, storage.disk.percent)}%` }}
                />
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <StorageLine label="База панели (SQLite + WAL)" value={fmtBytes(storage.db.total)} limit={`мягкий лимит ${storage.limits.db_soft_limit_mb} МБ`} />
              <StorageLine
                label="panel.log"
                value={fmtBytes(storage.panel_log.total)}
                limit={`${storage.limits.panel_log_max_mb} МБ × ${storage.limits.panel_log_backups + 1} файл(а)`}
              />
              <StorageLine
                label="Docker-лог прокси"
                value={fmtBytes(storage.docker_log.bytes)}
                limit={`лимит ${storage.limits.docker_log_max_mb} МБ (10 МБ × 3)`}
              />
              <StorageLine
                label="Резервные копии"
                value={`${storage.backups.count} шт · ${fmtBytes(storage.backups.bytes)}`}
                limit={`хранится последних ${storage.limits.backups_keep}`}
              />
            </div>
            <div className="rounded-lg border border-line/60 bg-ink/5 px-3 py-2 text-[11px] leading-relaxed text-muted">
              Хранение: сессии — {storage.limits.sessions_days} дней (не более {storage.limits.sessions_max}), события и
              сэмплы — {storage.limits.events_days} дней, аудит — {storage.limits.audit_days} дней. Journald ограничен{' '}
              {storage.limits.journal_max_mb} МБ (drop-in `/etc/systemd/journald.conf.d/99-tgws-panel.conf`), access-логи
              uvicorn отключены.
            </div>
          </div>
        ) : (
          <div className="py-6 text-center text-sm text-muted">Загрузка…</div>
        )}
      </Card>

      <ConfirmDialog
        open={!!confirm}
        title={confirm === 'stop' ? 'Остановить прокси?' : 'Перезапустить прокси?'}
        text={
          <>
            Все активные подключения будут разорваны. {confirm === 'stop' ? 'Контейнер останется остановленным до ручного запуска.' : 'Контейнер будет перезапущен через docker compose.'}
          </>
        }
        confirmLabel={confirm === 'stop' ? 'Остановить' : 'Перезапустить'}
        danger
        loading={!!busy}
        onClose={() => setConfirm(null)}
        onConfirm={() => confirm && void act(confirm)}
      />

      <Dialog open={logOpen} onClose={() => setLogOpen(false)} title="Логи контейнера (docker logs)" wide footer={<Button onClick={() => setLogOpen(false)}>Закрыть</Button>}>
        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-ink/10 p-3 font-mono text-[11px] leading-relaxed text-ink/80">
          {logs}
        </pre>
      </Dialog>

      <Dialog open={configOpen} onClose={() => setConfigOpen(false)} title="Текущая конфигурация" wide footer={<Button onClick={() => setConfigOpen(false)}>Закрыть</Button>}>
        {config ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
              <Info label="Образ" value={config.image} />
              <Info label="Контейнер" value={config.container_name} />
              <Info label="Restart" value={config.restart} />
              <Info label="Порты" value={config.ports.join(', ')} />
              <Info label="DC targets" value={config.dc_targets.map((t) => `DC${t.dc}: ${t.ip}`).join(', ') || '—'} wide />
            </div>
            <div>
              <div className="label">Переменные окружения (секрет замаскирован)</div>
              <div className="max-h-64 overflow-auto rounded-xl border border-line bg-ink/[0.07]">
                <table className="w-full text-[11px]">
                  <tbody>
                    {Object.entries(config.environment).map(([k, v]) => (
                      <tr key={k} className="border-b border-line/30">
                        <td className="px-3 py-1.5 font-mono text-muted">{k}</td>
                        <td className="px-3 py-1.5 font-mono text-ink/85">{v}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div>
              <div className="label">Команда запуска</div>
              <pre className="overflow-auto rounded-xl border border-line bg-ink/[0.07] p-3 font-mono text-[11px] text-ink/80">{config.command.join(' ')}</pre>
            </div>
          </div>
        ) : (
          <div className="py-8 text-center text-sm text-muted">Загрузка…</div>
        )}
      </Dialog>
    </div>
  )
}

function StorageLine({ label, value, limit }: { label: string; value: string; limit: string }) {
  return (
    <div className="rounded-lg border border-line/60 bg-ink/5 px-3 py-2">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="text-muted">{label}</span>
        <span className="font-medium">{value}</span>
      </div>
      <div className="mt-0.5 text-[10px] text-muted/80">{limit}</div>
    </div>
  )
}

function Info({ label, value, tone, wide }: { label: string; value: string; tone?: 'ok' | 'bad' | 'warn'; wide?: boolean }) {
  return (
    <div className={cn('rounded-xl border border-line/60 bg-ink/5 px-3 py-2', wide && 'col-span-2 sm:col-span-3')}>
      <div className="text-[10px] uppercase tracking-wider text-muted">{label}</div>
      <div
        className={cn(
          'mt-0.5 break-all text-xs font-medium',
          tone === 'ok' && 'text-ok',
          tone === 'bad' && 'text-bad',
          tone === 'warn' && 'text-warn',
        )}
      >
        {value}
      </div>
    </div>
  )
}
