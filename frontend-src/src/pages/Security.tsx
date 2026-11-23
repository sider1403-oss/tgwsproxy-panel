import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { AlertTriangle, CheckCircle2, KeyRound, Laptop, Lock, LogOut, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fmtDate } from '../lib/format'
import { Badge, Button, Card, CardTitle, Empty, Field, Input, useToast } from '../components/ui'
import type { SecurityEvent, SecurityOverview, SessionInfo } from '../lib/types'

const EVENT_LABEL: Record<string, string> = {
  login_success: 'Успешный вход',
  login_failed: 'Неудачный вход',
  login_blocked: 'Блокировка входа',
  logout: 'Выход',
  setup_admin: 'Создан администратор',
  setup_failed: 'Ошибка настройки',
  setup_blocked: 'Блокировка настройки',
  password_changed: 'Пароль изменён',
  password_change_failed: 'Неверный текущий пароль',
  password_reset_cli: 'Сброс пароля через CLI',
  session_revoked: 'Сессия завершена',
  sessions_revoked_all: 'Завершены сессии',
  sessions_revoked_others: 'Завершены остальные сессии',
  sessions_revoked_everywhere: 'Завершены все сессии',
  unauthorized_api: 'Доступ к API без авторизации',
  csrf_failed: 'Отклонён CSRF',
  admin_action: 'Административное действие',
  secret_revealed: 'Просмотр секрета',
  secret_reveal_failed: 'Неудачный просмотр секрета',
  backup_downloaded: 'Скачана резервная копия',
  backup_download_failed: 'Неудачное скачивание копии',
}

function eventTone(event: string): 'ok' | 'bad' | 'warn' | 'info' | 'muted' {
  if (/failed|unauthorized|blocked|csrf/i.test(event)) return 'bad'
  if (/revoked|logout|password_changed|setup_admin|backup_downloaded|login_success/i.test(event)) return 'ok'
  if (/secret|admin_action/i.test(event)) return 'warn'
  return 'muted'
}

export default function Security({ forced = false }: { forced?: boolean }) {
  const { user, changePassword } = useAuth()
  const toast = useToast()
  const [overview, setOverview] = useState<SecurityOverview | null>(null)
  const [events, setEvents] = useState<SecurityEvent[]>([])
  const [attempts, setAttempts] = useState<Array<{ ts: string; ip: string; username: string }>>([])
  const [loading, setLoading] = useState(!forced)
  const [error, setError] = useState('')

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [revoking, setRevoking] = useState('')

  const load = useCallback(async () => {
    if (forced) return
    setError('')
    try {
      const [o, e, a] = await Promise.all([api.securityOverview(), api.securityEvents(100), api.securityAttempts(30)])
      setOverview(o)
      setEvents(e.events)
      setAttempts(a.attempts)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить данные безопасности')
    } finally {
      setLoading(false)
    }
  }, [forced])

  useEffect(() => {
    void load()
  }, [load])

  const submitPassword = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (next !== confirm) {
      setError('Новые пароли не совпадают')
      return
    }
    setBusy(true)
    try {
      await changePassword(current, next)
      setCurrent('')
      setNext('')
      setConfirm('')
      toast.push('ok', forced ? 'Пароль изменён. Панель разблокирована.' : 'Пароль изменён; остальные сессии завершены.')
      if (!forced) await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сменить пароль')
    } finally {
      setBusy(false)
    }
  }

  const revoke = async (s: SessionInfo) => {
    setRevoking(s.id)
    try {
      await api.revokeSession(s.id)
      toast.push('ok', 'Сессия завершена')
      await load()
    } catch (err) {
      toast.push('bad', err instanceof Error ? err.message : 'Не удалось завершить сессию')
    } finally {
      setRevoking('')
    }
  }

  const revokeOthers = async () => {
    try {
      const r = await api.revokeOtherSessions()
      toast.push('ok', `Завершено сессий: ${r.revoked}`)
      await load()
    } catch (err) {
      toast.push('bad', err instanceof Error ? err.message : 'Не удалось завершить сессии')
    }
  }

  const revokeAll = async () => {
    if (!window.confirm('Завершить все сессии, включая текущую? Потребуется войти заново.')) return
    try {
      const r = await api.revokeAllSessions()
      toast.push('ok', `Завершено сессий: ${r.revoked}`)
      window.location.reload()
    } catch (err) {
      toast.push('bad', err instanceof Error ? err.message : 'Не удалось завершить сессии')
    }
  }

  const passwordCard = (
    <Card>
      <CardTitle right={<Lock className="h-4 w-4 text-accent" />}>Смена пароля</CardTitle>
      <form className="space-y-3" onSubmit={submitPassword}>
        <Field label="Текущий пароль">
          <Input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
        </Field>
        <Field label="Новый пароль" hint="Минимум 12 символов, буквы и цифры.">
          <Input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required />
        </Field>
        <Field label="Повторите новый пароль">
          <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
        </Field>
        <Button type="submit" variant="primary" loading={busy} disabled={!current || !next || !confirm}>
          Изменить пароль
        </Button>
        <div className="text-[11px] text-muted">После смены все остальные активные сессии завершаются.</div>
      </form>
    </Card>
  )

  if (forced) {
    return (
      <div className="auth-bg flex min-h-screen items-center justify-center px-4 py-10">
        <div className="w-full max-w-[460px]">
          <div className="mb-5 flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-2xl border border-warn/30 bg-warn/10">
              <ShieldCheck className="h-5 w-5 text-warn" />
            </div>
            <div>
              <div className="text-base font-semibold">Требуется смена пароля</div>
              <div className="text-[11px] text-muted">Первый вход с временным паролем</div>
            </div>
          </div>
          {error ? <div className="mb-3 rounded-xl border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}
          {passwordCard}
          <div className="mt-3 text-[11px] leading-relaxed text-muted">
            Пока пароль не изменён, остальные разделы панели недоступны.
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <ShieldCheck className="h-5 w-5 text-accent" />
        <div>
          <div className="text-sm font-semibold">Безопасность</div>
          <div className="text-[11px] text-muted">
            {user?.username} · последний вход: {overview?.last_login_at ? fmtDate(overview.last_login_at) : user?.last_login_at ? fmtDate(user.last_login_at) : '—'}
            {overview?.last_login_ip ? ` · ${overview.last_login_ip}` : ''}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button onClick={() => void load()} title="Обновить">
            <RefreshCw className="h-4 w-4" /> Обновить
          </Button>
        </div>
      </div>

      {error ? <div className="rounded-xl border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <Card className="!p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Активные сессии</div>
          <div className="mt-1 text-2xl font-semibold">{overview?.active_sessions ?? '—'}</div>
        </Card>
        <Card className="!p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Неудачные входы за 24 ч</div>
          <div className="mt-1 text-2xl font-semibold">{overview?.failed_24h ?? '—'}</div>
        </Card>
        <Card className="!p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Последняя неудача</div>
          <div className="mt-1 text-xs text-muted">
            {overview?.last_failed ? `${fmtDate(overview.last_failed.ts)} · ${overview.last_failed.ip}` : 'нет'}
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {passwordCard}

        <Card>
          <CardTitle
            right={
              <Button variant="warn" className="!px-2.5 !py-1.5 text-xs" onClick={() => void revokeOthers()} disabled={!overview || overview.active_sessions <= 1}>
                <LogOut className="h-3.5 w-3.5" /> Завершить остальные
              </Button>
            }
          >
            Активные сессии
          </CardTitle>
          {loading ? <div className="py-6 text-center text-xs text-muted">Загрузка…</div> : null}
          {!loading && !overview?.sessions.length ? <Empty title="Сессий нет" /> : null}
          <div className="space-y-2">
            {overview?.sessions.map((s) => (
              <div key={s.id} className="rounded-xl border border-line/60 bg-ink/5 px-3 py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <Laptop className="h-4 w-4 text-muted" />
                  <span className="font-mono text-xs">{s.ip || '—'}</span>
                  {s.current ? <Badge tone="ok">текущая</Badge> : <Badge tone="muted">сессия</Badge>}
                  <span className="ml-auto text-[10px] text-muted">до {fmtDate(s.expires_at)}</span>
                </div>
                <div className="mt-1 truncate text-[10px] text-muted" title={s.user_agent || ''}>
                  {s.user_agent || 'user-agent не передан'}
                </div>
                <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-muted">
                  <span>создана {fmtDate(s.created_at)} · активность {fmtDate(s.last_seen)}</span>
                  {!s.current ? (
                    <button className="text-bad hover:underline" onClick={() => void revoke(s)} disabled={revoking === s.id}>
                      <Trash2 className="mr-1 inline h-3 w-3" />
                      {revoking === s.id ? '…' : 'завершить'}
                    </button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 border-t border-line/60 pt-3">
            <button className="text-[11px] text-bad hover:underline" onClick={() => void revokeAll()}>
              Завершить все сессии, включая текущую
            </button>
          </div>
        </Card>
      </div>

      <Card>
        <CardTitle right={<KeyRound className="h-4 w-4 text-muted" />}>Журнал безопасности</CardTitle>
        <div className="max-h-[420px] overflow-auto">
          <table className="w-full min-w-[760px] border-collapse">
            <thead>
              <tr>
                <th className="th">Время</th>
                <th className="th">Событие</th>
                <th className="th">Пользователь</th>
                <th className="th">IP</th>
                <th className="th">Детали</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => (
                <tr key={ev.id} className="border-b border-line/40">
                  <td className="td whitespace-nowrap text-muted">{fmtDate(ev.ts)}</td>
                  <td className="td"><Badge tone={eventTone(ev.event)}>{EVENT_LABEL[ev.event] || ev.event}</Badge></td>
                  <td className="td text-muted">{ev.username || '—'}</td>
                  <td className="td font-mono text-[11px] text-muted">{ev.ip || '—'}</td>
                  <td className="td max-w-[320px] truncate text-[11px] text-muted" title={ev.detail || ''}>{ev.detail || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!events.length && !loading ? <Empty title="Событий пока нет" /> : null}
        </div>
      </Card>

      <Card>
        <CardTitle right={<AlertTriangle className="h-4 w-4 text-warn" />}>Неудачные попытки входа</CardTitle>
        {!attempts.length ? <Empty title="Неудачных попыток нет" /> : null}
        <div className="space-y-1.5">
          {attempts.map((a, i) => (
            <div key={`${a.ts}-${i}`} className="flex flex-wrap items-center gap-2 rounded-lg border border-line/50 px-3 py-2 text-xs">
              <span className="text-muted">{fmtDate(a.ts)}</span>
              <span className="font-mono">{a.ip}</span>
              <span className="text-muted">логин: {a.username || '—'}</span>
            </div>
          ))}
        </div>
      </Card>

      <div className="flex items-center gap-2 rounded-xl border border-line/60 bg-ink/5 px-3 py-2 text-[11px] text-muted">
        <CheckCircle2 className="h-3.5 w-3.5 text-ok" />
        Пароли хранятся только в виде Argon2id-хешей; cookie сессии — HttpOnly и SameSite=Lax.
      </div>
    </div>
  )
}
