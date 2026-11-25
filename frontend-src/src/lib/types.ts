export interface ProxyState {
  exists: boolean
  state: string
  running: boolean
  health: string | null
  uptime: number
  started_at: string | null
  restart_policy: string | null
  image: string | null
  image_id: string | null
  pid: number | null
  ports: string[]
  exit_code: number | null
  error: string | null
  version?: string | null
}

export interface Metrics {
  active_count: number
  speed_in: number
  speed_out: number
  cpu_host: number
  mem_used: number
  mem_total: number
  cpu_proxy: number
  mem_proxy: number
  rx: number
  tx: number
}

export interface ActiveConnection {
  ip: string
  port: number
  local_ip: string
  local_port: number
  state: string
  bytes_sent: number | null
  bytes_received: number | null
  first_seen: string
  duration: number
  device?: DeviceInfo
  client_id?: string
  server_id?: string
  host_ip?: string
  host_port?: number
}

export interface DeviceInfo {
  family: string
  label: string
  source: string
  detail?: string
  confidence?: string
}

export interface Totals {
  sessions: number
  clients: number
  bytes_up: number
  bytes_down: number
  bytes_total: number
  sessions_24h: number
  clients_24h: number
  bytes_up_24h: number
  bytes_down_24h: number
  bytes_total_24h: number
}

export interface ErrorCounts {
  total: number
  last_24h: number
}

export interface TrafficPoint {
  t: string
  up: number
  down: number
}

export interface ConnPoint {
  t: string
  conns: number
  up: number
  down: number
}

export interface DcRow {
  dc: number
  sessions: number
  clients?: number
  bytes: number
}

export interface ClientRow {
  client_ip: string
  sessions: number
  bytes_up: number
  bytes_down: number
  bytes_total: number
  first_seen: string | null
  last_seen: string | null
  active: boolean
  active_connections: number
  device: DeviceInfo
  key: null
  key_note: string
}

export interface ClientsResponse {
  items: ClientRow[]
  total: number
  limit: number
  offset: number
  range: string
  generated_at: string
  note: string
}

export interface ClientDetail {
  client_ip: string
  sessions: number
  bytes_up: number
  bytes_down: number
  bytes_total: number
  first_seen: string | null
  last_seen: string | null
  active: boolean
  active_connections: number
  active_items: ActiveConnection[]
  device: DeviceInfo
  dcs: Array<{ dc: number; sessions: number; bytes: number }>
  recent: Session[]
  key: null
  key_supported: boolean
  key_note: string
  range: string
  generated_at: string
  note: string
}

export interface MetricPoint {
  t: string
  [field: string]: number | string
}

export interface MetricStats {
  min: number | null
  avg: number | null
  max: number | null
  last: number | null
}

export interface MetricsResponse {
  points: MetricPoint[]
  stats: Record<string, MetricStats>
  fields: string[]
  range: string
  step: number
  history_start: string | null
  generated_at: string
  source: string
}

export interface LogEvent {
  id: number
  ts: string
  level: string
  category: string
  module?: string | null
  ip?: string | null
  message: string
}

export interface Overview {
  proxy: ProxyState
  metrics: Metrics
  totals: Totals
  errors: ErrorCounts
  warnings: ErrorCounts
  active: ActiveConnection[]
  active_error?: string | null
  series: { traffic: TrafficPoint[]; connections: ConnPoint[] }
  dc: DcRow[]
  recent_errors: LogEvent[]
  range: string
  generated_at: string
}

export interface Session {
  id: number
  client_ip: string
  client_port: number
  dc: number
  media: number
  kind: string
  closed_by: string
  bytes_up: number
  bytes_down: number
  duration: number
  started_at: string
  ended_at: string
  line: string
  device?: DeviceInfo
}

export interface HistoryResponse {
  items: Session[]
  total: number
  limit: number
  offset: number
}

export interface LogsResponse {
  items: LogEvent[]
  total: number
  limit: number
  offset: number
}

export interface KeyItem {
  id: string
  masked: string
  link_lan?: string | null
  link_external?: string | null
  enabled: boolean
  comment: string
  created_at: string | null
}

export interface KeysResponse {
  keys: KeyItem[]
  disabled: KeyItem[]
  total: number
  secret_source: string
  stats_supported: boolean
  stats_note: string
  lan_host?: string | null
  external_host?: string | null
  reveal_required?: boolean
}

export interface ActionResult {
  ok: boolean
  action?: string
  duration_ms?: number
  output?: string
  error?: string
  message?: string
  backup?: string
  rollback?: string
  state?: ProxyState
  port_check?: string
  warnings?: string[]
  key?: string
  id?: string
  link?: string
  link_lan?: string | null
  link_external?: string | null
}

export interface AuthUser {
  username: string
  must_change_password: boolean
  last_login_at?: string | null
  last_login_ip?: string | null
}

export interface AuthStatus {
  setup_required: boolean
  authenticated: boolean
  user: AuthUser | null
  csrf: string
}

export interface SessionInfo {
  id: string
  ip: string | null
  user_agent: string | null
  created_at: string
  last_seen: string
  expires_at: string
  revoked: boolean
  current: boolean
}

export interface SecurityEvent {
  id: number
  ts: string
  event: string
  username: string | null
  ip: string | null
  user_agent: string | null
  detail: string | null
}

export interface SecurityOverview {
  username: string
  last_login_at: string | null
  last_login_ip: string | null
  failed_24h: number
  active_sessions: number
  last_failed: { ts: string; ip: string; username: string } | null
  current_session: string
  sessions: SessionInfo[]
}

export interface ServiceInfo {
  state: ProxyState
  version: string | null
  port_check: { ok: boolean; message: string }
  updated_at: string
}

export interface EnvSchemaItem {
  type: string
  label: string
  group: string
  min?: number
  max?: number
}

export interface BackupItem {
  name: string
  created_at: string | null
  tag: string | null
  size: number
}

export interface ConfigSnapshot {
  compose_raw: string
  environment: Record<string, string>
  editable_env: Record<string, string>
  unknown_env: string[]
  schema: Record<string, EnvSchemaItem>
  image: string
  container_name: string
  restart: string
  ports: string[]
  command: string[]
  dc_targets: { dc: string; ip: string }[]
  env_file: { path: string; exists: boolean; keys: string[] }
  secret_source: string
  backups: BackupItem[]
}

export interface DiagCheck {
  id: string
  label: string
  status: 'ok' | 'warn' | 'fail' | 'skip' | string
  latency_ms?: number | null
  detail: string
  items?: Array<Record<string, any>>
}

export interface DiagDomain {
  host: string
  status: string
  latency_ms: number | null
}

export interface DiagResult {
  ts: string
  kind: 'quick' | 'probe' | string
  ok: boolean
  status: string
  summary: string
  duration_ms: number
  checks?: DiagCheck[]
  domains?: DiagDomain[]
  output?: string
  exit_code?: number
  probe_port?: number
}

export interface DiagnosticsState {
  quick: DiagResult | null
  probe: DiagResult | null
  history: DiagResult[]
  ops: { busy: boolean; current: string | null }
}

export interface AuditEntry {
  id: number
  ts: string
  action: string
  target: string | null
  ok: boolean
  ip: string | null
  duration_ms: number | null
  detail: string | null
}

export interface AuditResponse {
  items: AuditEntry[]
  total: number
}

export interface AlertSettings {
  enabled: boolean
  telegram_chat_id: string
  telegram_token_set: boolean
  telegram_token_masked: string
  webhook_url: string
  rules: {
    proxy_down: boolean
    warnings_10m: number
    no_sessions_minutes: number
    diag_fail: boolean
  }
  cooldown_minutes: number
  configured: boolean
}

export interface AlertLogEntry {
  id: number
  ts: string
  rule: string
  level: string
  message: string
  delivered: boolean
  error: string | null
}

export interface AlertsState {
  settings: AlertSettings
  history: AlertLogEntry[]
}

export interface StorageInfo {
  db: { main: number; wal: number; shm: number; total: number }
  panel_log: { total: number; files: Array<{ name: string; bytes: number }> }
  backups: { count: number; bytes: number }
  docker_log: { bytes: number; files: number }
  disk: { total: number; used: number; free: number; percent: number }
  limits: {
    panel_log_max_mb: number
    panel_log_backups: number
    db_soft_limit_mb: number
    sessions_days: number
    sessions_max: number
    events_days: number
    events_max: number
    audit_days: number
    backups_keep: number
    docker_log_max_mb: number
    journal_max_mb: number
  }
  updated_at: string
}
