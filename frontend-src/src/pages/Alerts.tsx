import { useEffect, useState } from 'react'
import { BellRing, Save, Send, ShieldAlert, Trash2 } from 'lucide-react'
import type { AlertsState } from '../lib/types'
import { api } from '../lib/api'
import { usePolling } from '../lib/hooks'
import { fmtDate } from '../lib/format'
import { Badge, Button, Card, CardTitle, Field, Input, Spinner, Switch, useToast } from '../components/ui'
import { cn } from '../lib/utils'

interface FormState {
  enabled: boolean
  token: string
  chatId: string
  webhook: string
  proxyDown: boolean
  diagFail: boolean
  warnings: string
  noSessions: string
  cooldown: string
}

const EMPTY: FormState = {
  enabled: false,
  token: '',
  chatId: '',
  webhook: '',
  proxyDown: true,
  diagFail: true,
  warnings: '60',
  noSessions: '0',
  cooldown: '30',
}

export default function Alerts() {
  const { data, error, loading, setData } = usePolling<AlertsState>(() => api.alerts(), 30000, [])
  const [form, setForm] = useState<FormState>(EMPTY)
  const [initialized, setInitialized] = useState(false)
  const [busy, setBusy] = useState<'save' | 'test' | 'clear' | null>(null)
  const { push } = useToast()

  useEffect(() => {
    if (!data || initialized) return
    setForm({
      enabled: data.settings.enabled,
      token: '',
      chatId: data.settings.telegram_chat_id,
      webhook: data.settings.webhook_url,
      proxyDown: data.settings.rules.proxy_down,
      diagFail: data.settings.rules.diag_fail,
      warnings: String(data.settings.rules.warnings_10m),
      noSessions: String(data.settings.rules.no_sessions_minutes),
      cooldown: String(data.settings.cooldown_minutes),
    })
    setInitialized(true)
  }, [data, initialized])

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }))

  const payload = () => ({
    enabled: form.enabled,
    telegram_token: form.token || undefined,
    telegram_chat_id: form.chatId,
    webhook_url: form.webhook,
    rules: {
      proxy_down: form.proxyDown,
      diag_fail: form.diagFail,
      warnings_10m: Number(form.warnings || 0),
      no_sessions_minutes: Number(form.noSessions || 0),
    },
    cooldown_minutes: Number(form.cooldown || 30),
  })

  const save = async (extra: Record<string, unknown> = {}) => {
    setBusy('save')
    try {
      const r = await api.saveAlerts({ ...payload(), ...extra })
      setForm((f) => ({ ...f, token: '' }))
      setData(await api.alerts())
      push('ok', 'Настройки уведомлений сохранены')
      return r
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
      return null
    } finally {
      setBusy(null)
    }
  }

  const test = async () => {
    setBusy('test')
    try {
      const r = await api.testAlerts()
      if (r.ok) {
        const channels = r.results.filter((x) => x.ok).map((x) => x.channel).join(', ')
        push('ok', `Тестовое уведомление отправлено${channels ? `: ${channels}` : ''}`)
      } else {
        push('bad', r.error || 'Не удалось отправить уведомление')
      }
      setData(await api.alerts())
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const clearToken = async () => {
    setBusy('clear')
    try {
      await save({ clear_token: true })
    } finally {
      setBusy(null)
    }
  }

  const s = data?.settings

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Уведомления о проблемах</h2>
          <p className="text-[11px] text-muted">Telegram-бот и/или webhook. Настройки хранятся на сервере с правами 600.</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={s?.enabled ? (s.configured ? 'ok' : 'warn') : 'muted'}>
            {s?.enabled ? (s.configured ? 'включены' : 'включены, канал не настроен') : 'выключены'}
          </Badge>
          <Button onClick={() => void test()} loading={busy === 'test'} disabled={busy !== null}>
            <Send className="h-4 w-4" /> Тест
          </Button>
          <Button variant="primary" onClick={() => void save()} loading={busy === 'save'} disabled={busy !== null}>
            <Save className="h-4 w-4" /> Сохранить
          </Button>
        </div>
      </div>

      {error ? <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}

      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Card>
          <CardTitle right={<Switch checked={form.enabled} onChange={(v) => set('enabled', v)} label={form.enabled ? 'включено' : 'выключено'} />}>
            Каналы доставки
          </CardTitle>
          <div className="space-y-3">
            <Field
              label="Telegram bot token"
              hint={s?.telegram_token_set ? `сохранён: ${s.telegram_token_masked}. Оставьте поле пустым, чтобы не менять.` : 'токен от @BotFather'}
            >
              <Input
                type="password"
                value={form.token}
                onChange={(e) => set('token', e.target.value)}
                placeholder={s?.telegram_token_set ? '•••••••• (сохранён)' : '123456789:AA…'}
                autoComplete="off"
              />
            </Field>
            <Field label="Telegram chat_id" hint="ID чата или канала, куда писать; бот должен иметь доступ">
              <Input value={form.chatId} onChange={(e) => set('chatId', e.target.value)} placeholder="например 123456789" />
            </Field>
            <Field label="Webhook URL (необязательно)" hint="POST JSON: source, level, rule, message, text, ts">
              <Input value={form.webhook} onChange={(e) => set('webhook', e.target.value)} placeholder="https://example.local/hooks/tgws" />
            </Field>
            {s?.telegram_token_set ? (
              <Button variant="danger" className="!py-1.5 text-xs" onClick={() => void clearToken()} loading={busy === 'clear'}>
                <Trash2 className="h-3.5 w-3.5" /> Удалить сохранённый токен
              </Button>
            ) : null}
            <div className="rounded-lg border border-line/60 bg-ink/5 px-3 py-2 text-[11px] text-muted">
              Для Telegram-бота нужны токен и chat_id. Проверка «Тест» использует уже сохранённые настройки —
              сначала сохраните форму, затем отправьте тест.
            </div>
          </div>
        </Card>

        <Card>
          <CardTitle right={<ShieldAlert className="h-4 w-4 text-muted" />}>Правила</CardTitle>
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3 rounded-lg border border-line/60 bg-ink/5 px-3 py-2">
              <div>
                <div className="text-sm">Прокси не работает</div>
                <div className="text-[11px] text-muted">остановлен более 60 секунд</div>
              </div>
              <Switch checked={form.proxyDown} onChange={(v) => set('proxyDown', v)} />
            </div>
            <div className="flex items-center justify-between gap-3 rounded-lg border border-line/60 bg-ink/5 px-3 py-2">
              <div>
                <div className="text-sm">Диагностика не пройдена</div>
                <div className="text-[11px] text-muted">канал недоступен по данным быстрой проверки</div>
              </div>
              <Switch checked={form.diagFail} onChange={(v) => set('diagFail', v)} />
            </div>
            <Field label="Предупреждений за 10 минут" hint="0 — не проверять">
              <Input type="number" min={0} value={form.warnings} onChange={(e) => set('warnings', e.target.value)} />
            </Field>
            <Field label="Нет сессий, минут" hint="0 — не проверять (тихие часы могут давать ложные срабатывания)">
              <Input type="number" min={0} value={form.noSessions} onChange={(e) => set('noSessions', e.target.value)} />
            </Field>
            <Field label="Пауза между повторами, минут" hint="антидребезг для каждого правила">
              <Input type="number" min={0} max={1440} value={form.cooldown} onChange={(e) => set('cooldown', e.target.value)} />
            </Field>
            <div className="text-[11px] text-muted">
              Уведомление о восстановлении прокси отправляется отдельно. События применения конфигурации и
              ошибок сервиса отправляются всегда (при включённых уведомлениях).
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <CardTitle right={loading ? <Spinner /> : <Badge tone="muted">{data?.history.length ?? 0}</Badge>}>
          История уведомлений
        </CardTitle>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse">
            <thead>
              <tr className="border-b border-line/70">
                <th className="th">Время</th>
                <th className="th">Правило</th>
                <th className="th">Сообщение</th>
                <th className="th">Доставлено</th>
              </tr>
            </thead>
            <tbody>
              {(data?.history ?? []).map((h) => (
                <tr key={h.id} className="border-b border-line/40">
                  <td className="td whitespace-nowrap text-muted">{fmtDate(h.ts)}</td>
                  <td className="td">
                    <Badge tone={h.rule === 'test' ? 'info' : 'muted'}>{h.rule}</Badge>
                  </td>
                  <td className="td text-ink/85">
                    {h.message}
                    {h.error ? <div className="mt-1 font-mono text-[10px] text-bad">{h.error}</div> : null}
                  </td>
                  <td className="td">
                    <span className={cn('text-xs', h.delivered ? 'text-ok' : 'text-bad')}>{h.delivered ? 'да' : 'нет'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data?.history.length ? (
            <div className="px-4 py-10 text-center text-sm text-muted">
              <BellRing className="mx-auto mb-2 h-6 w-6 opacity-60" />
              Уведомлений пока не было
            </div>
          ) : null}
        </div>
      </Card>
    </div>
  )
}
