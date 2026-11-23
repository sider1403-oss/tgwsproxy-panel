import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, getCsrfToken, setCsrfToken } from './api'
import type { AuthStatus, AuthUser } from './types'

type AuthContextValue = {
  loading: boolean
  user: AuthUser | null
  setupRequired: boolean
  csrf: string
  refresh: () => Promise<void>
  login: (username: string, password: string) => Promise<void>
  setup: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  changePassword: (current: string, next: string) => Promise<void>
}

const AuthCtx = createContext<AuthContextValue | null>(null)

async function readError(res: Response): Promise<string> {
  try {
    const data = await res.json()
    if (data?.detail) return String(data.detail)
  } catch {
    /* ignore */
  }
  return `HTTP ${res.status}`
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true)
  const [user, setUser] = useState<AuthUser | null>(null)
  const [setupRequired, setSetupRequired] = useState(false)
  const [csrf, setCsrf] = useState('')

  const apply = useCallback((data: AuthStatus) => {
    setCsrfToken(data.csrf)
    setCsrf(data.csrf || '')
    setUser(data.user)
    setSetupRequired(!!data.setup_required)
  }, [])

  const refresh = useCallback(async () => {
    const res = await fetch('/api/auth/status', { credentials: 'same-origin', cache: 'no-store' })
    if (!res.ok) {
      setUser(null)
      setLoading(false)
      return
    }
    apply((await res.json()) as AuthStatus)
    setLoading(false)
  }, [apply])

  useEffect(() => {
    void refresh()
    const onUnauthorized = () => {
      setUser(null)
      setSetupRequired(false)
    }
    const onPasswordRequired = () => {
      void refresh()
    }
    window.addEventListener('auth:unauthorized', onUnauthorized)
    window.addEventListener('auth:password-required', onPasswordRequired)
    return () => {
      window.removeEventListener('auth:unauthorized', onUnauthorized)
      window.removeEventListener('auth:password-required', onPasswordRequired)
    }
  }, [refresh])

  const login = useCallback(async (username: string, password: string) => {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) throw new Error(await readError(res))
    const data = await res.json()
    setCsrfToken(data.csrf)
    setCsrf(data.csrf || '')
    setUser(data.user)
    setSetupRequired(false)
  }, [])

  const setup = useCallback(async (username: string, password: string) => {
    const res = await fetch('/api/auth/setup', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) throw new Error(await readError(res))
    const data = await res.json()
    setCsrfToken(data.csrf)
    setCsrf(data.csrf || '')
    setUser(data.user)
    setSetupRequired(false)
  }, [])

  const logout = useCallback(async () => {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
      })
    } finally {
      setCsrfToken('')
      setCsrf('')
      setUser(null)
    }
  }, [])

  const changePassword = useCallback(async (current: string, next: string) => {
    await api.changePassword(current, next)
    await refresh()
  }, [refresh])

  const value = useMemo(
    () => ({ loading, user, setupRequired, csrf, refresh, login, setup, logout, changePassword }),
    [loading, user, setupRequired, csrf, refresh, login, setup, logout, changePassword],
  )

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

export function useAuth() {
  const value = useContext(AuthCtx)
  if (!value) throw new Error('AuthProvider is missing')
  return value
}
