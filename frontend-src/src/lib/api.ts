import type {
  ActionResult,
  AlertsState,
  AuditResponse,
  ConfigSnapshot,
  DeviceInfo,
  DiagnosticsState,
  DiagResult,
  HistoryResponse,
  KeysResponse,
  LogsResponse,
  Overview,
  ServiceInfo,
  StorageInfo,
} from './types'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
    cache: 'no-store',
  })
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const data = await res.json()
      if (data?.detail) message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* ignore */
    }
    throw new Error(message)
  }
  return (await res.json()) as T
}

export const api = {
  overview: (range = '1h') => req<Overview>(`/api/overview?range=${range}`),
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
  setComment: (key: string, comment: string) =>
    req<{ ok: boolean; comment: string }>(`/api/keys/${key}`, { method: 'PATCH', body: JSON.stringify({ comment }) }),
  disableKey: (key: string) => req<ActionResult>(`/api/keys/${key}/disable`, { method: 'POST' }),
  enableKey: (key: string) => req<ActionResult>(`/api/keys/${key}/enable`, { method: 'POST' }),
  deleteKey: (key: string) => req<ActionResult>(`/api/keys/${key}`, { method: 'DELETE' }),
  config: () => req<ConfigSnapshot>('/api/config'),
  saveConfig: (payload: { environment?: Record<string, string>; dc_targets?: { dc: string; ip: string }[] }) =>
    req<ActionResult>('/api/config', { method: 'PUT', body: JSON.stringify(payload) }),
  backups: () => req<{ items: any[] }>('/api/config/backups'),
  restore: (name: string) =>
    req<ActionResult>('/api/config/restore', { method: 'POST', body: JSON.stringify({ name }) }),
  downloadBackup: (name: string) => `/api/config/backups/${encodeURIComponent(name)}/download`,
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
}
