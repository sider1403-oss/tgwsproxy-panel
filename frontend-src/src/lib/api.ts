import type {
  ActionResult,
  AlertsState,
  AuditResponse,
  ClientDetail,
  ClientsResponse,
  ConfigSnapshot,
  DeviceInfo,
  DiagnosticsState,
  DiagResult,
  HistoryResponse,
  KeysResponse,
  LogsResponse,
  MetricsResponse,
  Overview,
  SecurityEvent,
  SecurityOverview,
  ServiceInfo,
  SessionInfo,
  StorageInfo,
} from './types'

let csrfToken = ''

export function setCsrfToken(token: string | null | undefined) {
  csrfToken = token || ''
}

export function getCsrfToken() {
  return csrfToken
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || 'GET').toUpperCase()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init?.headers as Record<string, string> | undefined) || {}),
  }
  if (method !== 'GET' && method !== 'HEAD' && csrfToken) headers['X-CSRF-Token'] = csrfToken
  const res = await fetch(path, {
    ...init,
    method,
    headers,
    credentials: 'same-origin',
    cache: 'no-store',
  })
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    let code: string | undefined
    try {
      const data = await res.json()
      if (data?.detail) message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
      code = data?.code
    } catch {
      /* ignore */
    }
    if (res.status === 401) window.dispatchEvent(new Event('auth:unauthorized'))
    if (res.status === 403 && code === 'password_change_required') {
      window.dispatchEvent(new Event('auth:password-required'))
    }
    throw new Error(message)
  }
  return (await res.json()) as T
}

export const api = {
  overview: (range = '1h') => req<Overview>(`/api/overview?range=${range}`),
  clients: (params: Record<string, string | number | boolean>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== '' && v !== undefined && v !== null) qs.set(k, String(v))
    })
    return req<ClientsResponse>(`/api/clients?${qs.toString()}`)
  },
  client: (ip: string, params: Record<string, string | number>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== '' && v !== undefined && v !== null) qs.set(k, String(v))
    })
    return req<ClientDetail>(`/api/clients/${encodeURIComponent(ip)}?${qs.toString()}`)
  },
  metrics: (params: Record<string, string | number>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== '' && v !== undefined && v !== null) qs.set(k, String(v))
    })
    return req<MetricsResponse>(`/api/metrics/history?${qs.toString()}`)
  },
  service: () => req<ServiceInfo>('/api/service'),
  serviceAction: (action: string) =>
    req<ActionResult>('/api/service/action', { method: 'POST', body: JSON.stringify({ action }) }),
  serviceLogs: (lines = 200) => req<{ ok: boolean; text: string; lines: number }>(`/api/service/logs?lines=${lines}`),
  active: () => req<{ items: any[]; count: number; note: string; updated_at: string }>('/api/connections/active'),
  kill: (ip: string, port: number) =>
    req<{ ok: boolean; message: string; still_present: boolean }>('/api/connections/kill', {
      method: 'POST',
      body: JSON.stringify({ ip, port }),
    }),
  history: (params: Record<string, string | number>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== '' && v !== undefined && v !== null) qs.set(k, String(v))
    })
    return req<HistoryResponse>(`/api/connections/history?${qs.toString()}`)
  },
  logs: (params: Record<string, string | number>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== '' && v !== undefined && v !== null) qs.set(k, String(v))
    })
    return req<LogsResponse>(`/api/logs?${qs.toString()}`)
  },
  logsExportUrl: (params: Record<string, string>) => {
    const qs = new URLSearchParams(params)
    return `/api/logs/export?${qs.toString()}`
  },
  keys: () => req<KeysResponse>('/api/keys'),
  addKey: (comment: string) =>
    req<ActionResult>('/api/keys', { method: 'POST', body: JSON.stringify({ comment }) }),
  setComment: (id: string, comment: string) =>
    req<{ ok: boolean; comment: string }>(`/api/keys/${id}`, { method: 'PATCH', body: JSON.stringify({ comment }) }),
  disableKey: (id: string) => req<ActionResult>(`/api/keys/${id}/disable`, { method: 'POST' }),
  enableKey: (id: string) => req<ActionResult>(`/api/keys/${id}/enable`, { method: 'POST' }),
  deleteKey: (id: string) => req<ActionResult>(`/api/keys/${id}`, { method: 'DELETE' }),
  revealKey: (id: string, password: string) =>
    req<{ id: string; key: string; masked: string; link_lan: string | null; link_external: string | null }>(
      `/api/keys/${id}/reveal`,
      { method: 'POST', body: JSON.stringify({ password }) },
    ),
  keyStats: (id: string) =>
    req<{ supported: boolean; reason: string; alternatives?: string[] }>(`/api/keys/${id}/stats`),
  config: () => req<ConfigSnapshot>('/api/config'),
  saveConfig: (payload: { environment?: Record<string, string>; dc_targets?: { dc: string; ip: string }[] }) =>
    req<ActionResult>('/api/config', { method: 'PUT', body: JSON.stringify(payload) }),
  backups: () => req<{ items: any[] }>('/api/config/backups'),
  restore: (name: string) =>
    req<ActionResult>('/api/config/restore', { method: 'POST', body: JSON.stringify({ name }) }),
  downloadBackup: async (name: string, password: string) => {
    const res = await fetch(`/api/config/backups/${encodeURIComponent(name)}/download`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}) },
      body: JSON.stringify({ password }),
    })
    if (!res.ok) {
      let message = `HTTP ${res.status}`
      try {
        const data = await res.json()
        if (data?.detail) message = String(data.detail)
      } catch {
        /* ignore */
      }
      throw new Error(message)
    }
    return await res.blob()
  },
  diagnostics: () => req<DiagnosticsState>('/api/diagnostics'),
  diagQuick: () => req<DiagResult>('/api/diagnostics/check', { method: 'POST' }),
  diagProbe: () => req<DiagResult>('/api/diagnostics/probe', { method: 'POST' }),
  alerts: () => req<AlertsState>('/api/alerts'),
  saveAlerts: (payload: Record<string, unknown>) =>
    req<{ ok: boolean; settings: AlertsState['settings'] }>('/api/alerts', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  testAlerts: () => req<{ ok: boolean; error?: string; results: Array<{ channel: string; ok: boolean; error: string | null }> }>('/api/alerts/test', { method: 'POST' }),
  audit: (limit = 100) => req<AuditResponse>(`/api/audit?limit=${limit}`),
  storage: () => req<StorageInfo>('/api/storage'),
  setDevice: (ip: string, family: string) =>
    req<{ ok: boolean; device: DeviceInfo }>(`/api/devices/${encodeURIComponent(ip)}`, {
      method: 'PUT',
      body: JSON.stringify({ family }),
    }),
  resetDevice: (ip: string) =>
    req<{ ok: boolean; device: DeviceInfo }>(`/api/devices/${encodeURIComponent(ip)}`, {
      method: 'DELETE',
    }),
  device: (ip: string) => req<DeviceInfo>(`/api/devices/${encodeURIComponent(ip)}`),
  changePassword: (current_password: string, new_password: string) =>
    req<{ ok: boolean; revoked_other: number }>('/api/auth/password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    }),
  securityOverview: () => req<SecurityOverview>('/api/security/overview'),
  securitySessions: () => req<{ sessions: SessionInfo[] }>('/api/security/sessions'),
  revokeSession: (id: string) =>
    req<{ ok: boolean; current: boolean }>(`/api/security/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  revokeOtherSessions: () =>
    req<{ ok: boolean; revoked: number }>('/api/security/sessions/revoke-others', { method: 'POST' }),
  revokeAllSessions: () =>
    req<{ ok: boolean; revoked: number }>('/api/security/sessions/revoke-all', { method: 'POST' }),
  securityEvents: (limit = 100) => req<{ events: SecurityEvent[] }>(`/api/security/events?limit=${limit}`),
  securityAttempts: (limit = 50) =>
    req<{ attempts: Array<{ ts: string; ip: string; username: string }> }>(`/api/security/attempts?limit=${limit}`),
}
