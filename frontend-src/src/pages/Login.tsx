import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Eye, EyeOff, ShieldCheck } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { Button, Field, Input } from '../components/ui'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await login(username.trim(), password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось войти')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-bg flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-[420px]">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-2xl border border-accent/30 bg-accent/10">
            <ShieldCheck className="h-5 w-5 text-accent" />
          </div>
          <div>
            <div className="text-base font-semibold tracking-wide">TGWSProxy</div>
            <div className="text-[11px] text-muted">панель управления</div>
          </div>
        </div>

        <div className="surface p-6 sm:p-7">
          <h1 className="text-xl font-semibold">Вход в панель</h1>
          <p className="mt-1 text-xs text-muted">Доступ только для администратора.</p>

          {error ? (
            <div className="mt-4 rounded-xl border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div>
          ) : null}

          <form className="mt-5 space-y-4" onSubmit={submit}>
            <Field label="Логин">
              <Input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
                placeholder="ваш логин"
              />
            </Field>
            <Field label="Пароль">
              <div className="relative">
                <Input
                  type={show ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  className="pr-10"
                  placeholder="••••••••••••"
                />
                <button
                  type="button"
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted hover:text-ink"
                  onClick={() => setShow((v) => !v)}
                  aria-label={show ? 'Скрыть пароль' : 'Показать пароль'}
                >
                  {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </Field>
            <Button type="submit" variant="primary" className="w-full" loading={busy} disabled={!username || !password}>
              Войти
            </Button>
          </form>

          <div className="mt-5 border-t border-line/60 pt-4 text-[11px] leading-relaxed text-muted">
            Публичной регистрации нет. Первый администратор создаётся через защищённую
            первоначальную настройку или CLI.
          </div>
        </div>
      </div>
    </div>
  )
}
