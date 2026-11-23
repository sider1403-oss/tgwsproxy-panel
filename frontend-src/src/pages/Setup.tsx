import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, Terminal } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { Button, Field, Input } from '../components/ui'

export default function Setup() {
  const { setup, setupCodeHint } = useAuth()
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (password !== confirm) {
      setError('Пароли не совпадают')
      return
    }
    if (password.length < 12) {
      setError('Пароль должен быть не короче 12 символов')
      return
    }
    setBusy(true)
    try {
      await setup(code.trim(), username.trim(), password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось завершить настройку')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-bg flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-[520px]">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-2xl border border-accent/30 bg-accent/10">
            <ShieldCheck className="h-5 w-5 text-accent" />
          </div>
          <div>
            <div className="text-base font-semibold tracking-wide">TGWSProxy</div>
            <div className="text-[11px] text-muted">первоначальная настройка</div>
          </div>
        </div>

        <div className="surface p-6 sm:p-7">
          <h1 className="text-xl font-semibold">Создание администратора</h1>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            Администратор ещё не создан. Введите одноразовый код настройки — он находится
            в файле на сервере, доступном только root.
          </p>

          <div className="mt-4 flex items-start gap-2 rounded-xl border border-line/60 bg-ink/5 px-3 py-2.5 text-[11px] text-muted">
            <Terminal className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <div>
              Код: <span className="font-mono text-ink/80">{setupCodeHint || '/opt/tgws-panel/config/setup_code'}</span>
              <br />
              Прочитайте по SSH: <span className="font-mono">sudo cat /opt/tgws-panel/config/setup_code</span>
            </div>
          </div>

          {error ? (
            <div className="mt-4 rounded-xl border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div>
          ) : null}

          <form className="mt-5 space-y-4" onSubmit={submit}>
            <Field label="Код первоначальной настройки">
              <Input value={code} onChange={(e) => setCode(e.target.value)} required autoFocus autoComplete="off" />
            </Field>
            <Field label="Логин администратора" hint="Не используйте стандартные admin/root.">
              <Input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoComplete="username"
                placeholder="например, alex"
              />
            </Field>
            <Field label="Пароль" hint="Минимум 12 символов, буквы и цифры.">
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="new-password" />
            </Field>
            <Field label="Повторите пароль">
              <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required autoComplete="new-password" />
            </Field>
            <Button type="submit" variant="primary" className="w-full" loading={busy} disabled={!code || !username || !password || !confirm}>
              Создать администратора
            </Button>
          </form>

          <div className="mt-5 border-t border-line/60 pt-4 text-[11px] leading-relaxed text-muted">
            После создания администратора эта страница отключится. Регистрация пользователей
            через интерфейс недоступна.
          </div>
        </div>
      </div>
    </div>
  )
}
