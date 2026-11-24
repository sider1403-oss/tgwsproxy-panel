import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useState } from 'react'
import {
  Activity,
  BellRing,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Power,
  ScrollText,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  Stethoscope,
  Sun,
  X,
} from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useNow, usePolling } from '../lib/hooks'
import { useTheme } from '../lib/theme'
import { cn } from '../lib/utils'
import { fmtDuration } from '../lib/format'
import { Dot } from './ui'

const NAV = [
  { to: '/', label: 'Дашборд', icon: LayoutDashboard, end: true },
  { to: '/connections', label: 'Подключения', icon: Activity },
  { to: '/keys', label: 'Ключи', icon: KeyRound },
  { to: '/logs', label: 'Логи', icon: ScrollText },
  { to: '/service', label: 'Сервис', icon: Power },
  { to: '/diagnostics', label: 'Диагностика', icon: Stethoscope },
  { to: '/alerts', label: 'Уведомления', icon: BellRing },
  { to: '/security', label: 'Безопасность', icon: Shield },
  { to: '/config', label: 'Конфигурация', icon: SlidersHorizontal },
]

const TITLES: Record<string, string> = {
  '/': 'Дашборд',
  '/connections': 'Подключения',
  '/clients': 'Клиенты',
  '/traffic': 'Трафик',
  '/dc': 'DC',
  '/keys': 'Ключи доступа',
  '/logs': 'Логи',
  '/service': 'Управление сервисом',
  '/diagnostics': 'Диагностика канала',
  '/alerts': 'Уведомления',
  '/security': 'Безопасность',
  '/config': 'Конфигурация',
}

export default function Layout() {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const now = useNow(1000)
  const { theme, toggle } = useTheme()
  const { user, logout } = useAuth()
  const { data } = usePolling(() => api.service(), 10000)
  const state = data?.state
  const running = state?.running
  const title = TITLES[location.pathname]
    ?? (location.pathname.startsWith('/clients/') ? 'Клиент' : location.pathname.startsWith('/metrics/') ? 'Метрики' : 'Панель')

  return (
    <div className="min-h-screen lg:flex">
      {open ? <div className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm lg:hidden" onClick={() => setOpen(false)} /> : null}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-line/70 bg-panel/95 backdrop-blur transition-transform lg:static lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="grid h-10 w-10 place-items-center rounded-xl border border-accent/30 bg-accent/10">
            <ShieldCheck className="h-5 w-5 text-accent" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold tracking-wide">TGWSProxy</div>
            <div className="text-[11px] text-muted">панель управления</div>
          </div>
          <button className="ml-auto rounded-lg p-1.5 text-muted hover:bg-ink/5 lg:hidden" onClick={() => setOpen(false)}>
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 px-3">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition',
                  isActive ? 'border border-accent/20 bg-accent/10 text-accent' : 'border border-transparent text-muted hover:bg-ink/5 hover:text-ink',
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-line/70 px-5 py-4 text-[11px] text-muted">
          <div className="mb-3 flex items-center gap-2">
            <div className="grid h-7 w-7 place-items-center rounded-lg border border-line bg-ink/5">
              <ShieldCheck className="h-3.5 w-3.5 text-accent" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs font-medium text-ink/90">{user?.username}</div>
              <div className="text-[10px]">администратор</div>
            </div>
            <button
              type="button"
              onClick={() => void logout()}
              title="Выйти"
              aria-label="Выйти"
              className="rounded-lg border border-line p-1.5 text-muted transition hover:bg-bad/10 hover:text-bad"
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex items-center gap-2">
            <Dot tone={running ? (state?.health === 'healthy' ? 'ok' : 'warn') : 'bad'} live={!!running} />
            <span className="truncate">
              {running ? `работает · ${fmtDuration(state?.uptime)}` : 'остановлен'}
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span>v{data?.version ?? '—'}</span>
            <span className="font-mono">{typeof window !== 'undefined' ? window.location.host : 'localhost:8090'}</span>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-line/60 bg-panel/80 backdrop-blur">
          <div className="flex items-center gap-3 px-4 py-3.5 sm:px-6">
            <button className="rounded-lg border border-line p-2 text-muted lg:hidden" onClick={() => setOpen(true)}>
              <Menu className="h-4 w-4" />
            </button>
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold sm:text-lg">{title}</h1>
              <p className="hidden text-[11px] text-muted sm:block">
                {new Date(now).toLocaleString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </p>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={toggle}
                title={theme === 'light' ? 'Включить тёмную тему' : 'Включить светлую тему'}
                aria-label={theme === 'light' ? 'Включить тёмную тему' : 'Включить светлую тему'}
                className="rounded-lg border border-line bg-card/60 p-2 text-muted transition hover:bg-ink/5 hover:text-ink"
              >
                {theme === 'light' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
              </button>
              <span
                className={cn(
                  'chip',
                  running
                    ? 'border-ok/30 bg-ok/10 text-ok'
                    : 'border-bad/30 bg-bad/10 text-bad',
                )}
              >
                <Dot tone={running ? 'ok' : 'bad'} live={!!running} />
                {running ? (state?.health === 'healthy' ? 'healthy' : state?.health || 'running') : 'stopped'}
              </span>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-5 sm:px-6 sm:py-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
