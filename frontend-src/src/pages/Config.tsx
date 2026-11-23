import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Download, Plus, Save, Trash2, Undo2 } from 'lucide-react'
import type { ActionResult, ConfigSnapshot } from '../lib/types'
import { api } from '../lib/api'
import { fmtDate } from '../lib/format'
import { Badge, Button, Card, CardTitle, ConfirmDialog, CopyBtn, Dialog, Empty, Field, Input, Select, Switch, Tabs, Textarea, useToast } from '../components/ui'
import { cn } from '../lib/utils'

const GROUP_TITLES: Record<string, string> = {
  network: 'Сеть и прослушивание',
  cloudflare: 'Cloudflare и fallback',
  limits: 'Лимиты и таймауты',
  debug: 'Отладка',
  socks: 'SOCKS5',
  advanced: 'Дополнительно',
}

const HINTS: Record<string, string> = {
  TG_CF_DISABLE_TLS: 'Отключает TLS до Cloudflare: этот участок идёт открытым ws:// — снижает защищённость.',
  TG_LISTEN_FAKETLS_DOMAIN: 'Домен маскировки входящего FakeTLS; входит в ссылку tg://.',
  TG_POOL_SIZE: 'Сколько WebSocket-соединений держать прогретыми на DC.',
  TG_CLIENT_IDLE_TIMEOUT: '0 — не закрывать сессии по неактивности.',
  TG_VERBOSE: 'Включает DEBUG-логи: больше объём и нагрузка.',
  TG_DEFAULT_DOMAINS: 'Загружать список CF-доменов с GitHub при старте.',
  TG_LINK_IP: 'Публичный/LAN-адрес, который попадёт в ссылку tg://.',
}

export default function Config() {
  const [snap, setSnap] = useState<ConfigSnapshot | null>(null)
  const [tab, setTab] = useState('params')
  const [values, setValues] = useState<Record<string, string>>({})
  const [targets, setTargets] = useState<{ dc: string; ip: string }[]>([])
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ActionResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [restoreName, setRestoreName] = useState<string | null>(null)
  const { push } = useToast()

  const load = async () => {
    try {
      const s = await api.config()
      setSnap(s)
      setValues({ ...s.editable_env })
      setTargets(s.dc_targets)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const changed = useMemo(() => {
    if (!snap) return {} as Record<string, string>
    const out: Record<string, string> = {}
    Object.entries(values).forEach(([k, v]) => {
      if ((snap.editable_env[k] ?? '') !== v) out[k] = v
    })
    return out
  }, [values, snap])

  const targetsChanged = useMemo(() => {
    if (!snap) return false
    return JSON.stringify(snap.dc_targets) !== JSON.stringify(targets.filter((t) => t.dc && t.ip))
  }, [targets, snap])

  const dirty = Object.keys(changed).length > 0 || targetsChanged

  const apply = async () => {
    setBusy(true)
    setResult(null)
    try {
      const r = await api.saveConfig({ environment: changed, dc_targets: targets.filter((t) => t.dc && t.ip) })
      setResult(r)
      if (r.ok) {
        push('ok', 'Конфигурация применена')
        await load()
      } else {
        push('bad', r.error || 'Не удалось применить конфигурацию')
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setResult({ ok: false, error: msg })
      push('bad', msg)
    } finally {
      setBusy(false)
      setConfirm(false)
    }
  }

  const restore = async () => {
    if (!restoreName) return
    setBusy(true)
    try {
      const r = await api.restore(restoreName)
      setResult(r)
      if (r.ok) {
        push('ok', 'Резервная копия восстановлена')
        await load()
      } else {
        push('bad', r.error || 'Ошибка восстановления')
      }
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
      setRestoreName(null)
    }
  }

  if (!snap) {
    return <Card>{error ? <Empty title="Не удалось загрузить конфигурацию" hint={error} /> : <Empty title="Загрузка конфигурации…" />}</Card>
  }

  const groups = Object.entries(snap.schema).reduce<Record<string, [string, (typeof snap.schema)[string]][]>>((acc, [k, v]) => {
    if (!(k in snap.editable_env)) return acc
    ;(acc[v.group] ||= []).push([k, v])
    return acc
  }, {})

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs
          value={tab}
          onChange={setTab}
          items={[
            { value: 'params', label: 'Параметры' },
            { value: 'dc', label: 'DC targets' },
            { value: 'compose', label: 'compose-файл' },
            { value: 'backups', label: 'Резервные копии' },
          ]}
        />
        <div className="flex items-center gap-2">
          {dirty ? <Badge tone="warn">есть неприменённые изменения</Badge> : <Badge tone="ok">без изменений</Badge>}
          <Button onClick={() => void load()} disabled={busy}>Обновить</Button>
          <Button variant="primary" onClick={() => setConfirm(true)} disabled={!dirty || busy}>
            <Save className="h-4 w-4" /> Применить
          </Button>
        </div>
      </div>

      {error ? <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}

      <div className="flex items-start gap-2 rounded-xl border border-line/60 bg-ink/5 px-4 py-3 text-[11px] text-muted">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" />
        <div>
          Изменения применяются через <span className="font-mono text-ink/80">docker compose up -d</span> с пересозданием контейнера. Перед записью
          автоматически создаётся резервная копия compose-файла и .env; проверка выполняется командой <span className="font-mono text-ink/80">docker compose config -q</span>,
          при ошибке конфигурация откатывается. Секрет изменяется только в разделе «Ключи».
        </div>
      </div>

      {tab === 'params' ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {Object.entries(groups).map(([group, items]) => (
            <Card key={group}>
              <CardTitle>{GROUP_TITLES[group] ?? group}</CardTitle>
              <div className="space-y-3">
                {items.map(([key, spec]) => (
                  <Field key={key} label={spec.label} hint={HINTS[key] ? `${key} — ${HINTS[key]}` : key}>
                    {spec.type === 'bool' ? (
                      <Switch
                        checked={values[key] === 'true'}
                        onChange={(v) => setValues((s) => ({ ...s, [key]: v ? 'true' : 'false' }))}
                        label={values[key] === 'true' ? 'включено' : 'выключено'}
                      />
                    ) : (
                      <Input
                        value={values[key] ?? ''}
                        onChange={(e) => setValues((s) => ({ ...s, [key]: e.target.value }))}
                        className={cn(spec.type === 'str' && 'font-mono text-xs')}
                      />
                    )}
                  </Field>
                ))}
              </div>
            </Card>
          ))}

          {snap.unknown_env.length ? (
            <Card>
              <CardTitle right={<Badge tone="muted">только чтение</Badge>}>Прочие переменные</CardTitle>
              <div className="space-y-1.5">
                {snap.unknown_env.map((k) => (
                  <div key={k} className="flex items-center justify-between gap-3 rounded-lg border border-line/60 bg-ink/5 px-3 py-1.5">
                    <span className="font-mono text-[11px] text-muted">{k}</span>
                    <span className="max-w-[55%] truncate font-mono text-[11px] text-ink/80">{snap.environment[k]}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 text-[11px] text-muted">Панель не изменяет эти параметры и сохраняет их как есть.</div>
            </Card>
          ) : null}
        </div>
      ) : null}

      {tab === 'dc' ? (
        <Card>
          <CardTitle right={<Button onClick={() => setTargets((t) => [...t, { dc: '2', ip: '' }])}><Plus className="h-4 w-4" /> Добавить</Button>}>
            Целевые IP дата-центров (флаги --dc-ip)
          </CardTitle>
          <div className="space-y-2">
            {targets.map((t, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <Select value={t.dc} onChange={(e) => setTargets((arr) => arr.map((x, j) => (j === i ? { ...x, dc: e.target.value } : x)))} className="w-28">
                  {[1, 2, 3, 4, 5].map((d) => (
                    <option key={d} value={String(d)}>DC{d}</option>
                  ))}
                </Select>
                <Input
                  value={t.ip}
                  onChange={(e) => setTargets((arr) => arr.map((x, j) => (j === i ? { ...x, ip: e.target.value } : x)))}
                  placeholder="149.154.167.220"
                  className="min-w-[180px] flex-1 font-mono text-xs"
                />
                <Button variant="danger" className="!px-2 !py-1.5" onClick={() => setTargets((arr) => arr.filter((_, j) => j !== i))}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
          <div className="mt-3 text-[11px] text-muted">
            Пустой список означает, что прокси использует встроенные адреса DC. Остальные флаги команды сохраняются без изменений.
          </div>
        </Card>
      ) : null}

      {tab === 'compose' ? (
        <Card>
          <CardTitle right={<CopyBtn value={snap.compose_raw} label="Копировать" />}>docker-compose.yml (только чтение)</CardTitle>
          <Textarea value={snap.compose_raw} readOnly rows={24} />
          <div className="mt-2 text-[11px] text-muted">Файл: /opt/tg-ws-proxy/docker-compose.yml · секрет подставляется из .env</div>
        </Card>
      ) : null}

      {tab === 'backups' ? (
        <Card>
          <CardTitle>Резервные копии конфигурации</CardTitle>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse">
              <thead>
                <tr className="border-b border-line/70">
                  <th className="th">Создана</th>
                  <th className="th">Причина</th>
                  <th className="th">Каталог</th>
                  <th className="th text-right">Действия</th>
                </tr>
              </thead>
              <tbody>
                {snap.backups.map((b) => (
                  <tr key={b.name} className="border-b border-line/40">
                    <td className="td text-muted">{fmtDate(b.created_at)}</td>
                    <td className="td">{b.tag ?? '—'}</td>
                    <td className="td font-mono text-[11px] text-muted">{b.name}</td>
                    <td className="td">
                      <div className="flex justify-end gap-2">
                        <a className="btn-ghost !px-2.5 !py-1.5 text-xs" href={api.downloadBackup(b.name)}>
                          <Download className="h-3.5 w-3.5" /> Скачать
                        </a>
                        <Button variant="warn" className="!px-2.5 !py-1.5 text-xs" onClick={() => setRestoreName(b.name)}>
                          <Undo2 className="h-3.5 w-3.5" /> Восстановить
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!snap.backups.length ? <Empty title="Копий пока нет" hint="Копия создаётся автоматически перед каждым применением изменений." /> : null}
          </div>
        </Card>
      ) : null}

      {result ? (
        <Card>
          <CardTitle right={<Badge tone={result.ok ? 'ok' : 'bad'}>{result.ok ? 'применено' : 'ошибка'}</Badge>}>
            Результат применения
          </CardTitle>
          {result.backup ? <div className="mb-2 text-[11px] text-muted">Резервная копия: <span className="font-mono">{result.backup}</span></div> : null}
          {result.error ? <div className="mb-2 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 font-mono text-[11px] text-bad">{result.error}</div> : null}
          {result.rollback ? <div className="mb-2 rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-[11px] text-warn">{result.rollback}</div> : null}
          {result.warnings?.length ? <div className="mb-2 rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-[11px] text-warn">{result.warnings.join('; ')}</div> : null}
          {result.output ? <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-ink/[0.08] p-3 font-mono text-[11px] text-ink/80">{result.output}</pre> : null}
        </Card>
      ) : null}

      <ConfirmDialog
        open={confirm}
        title="Применить конфигурацию?"
        text={
          <div className="space-y-2">
            <div>Будет создана резервная копия, затем контейнер пересоздан (несколько секунд недоступности).</div>
            {Object.keys(changed).length ? (
              <div className="rounded-lg border border-line bg-ink/5 p-2 font-mono text-[11px]">
                {Object.entries(changed).map(([k, v]) => (
                  <div key={k}><span className="text-muted">{k}</span>: {snap.editable_env[k] || '—'} → {v || '—'}</div>
                ))}
              </div>
            ) : null}
            {targetsChanged ? <div className="text-[11px] text-warn">Изменены DC targets: {targets.map((t) => `DC${t.dc}:${t.ip}`).join(', ') || 'пусто'}</div> : null}
          </div>
        }
        confirmLabel="Применить"
        loading={busy}
        onClose={() => setConfirm(false)}
        onConfirm={() => void apply()}
      />

      <ConfirmDialog
        open={!!restoreName}
        title="Восстановить резервную копию?"
        text={<>Файлы compose и .env будут заменены копией <span className="font-mono">{restoreName}</span>, затем контейнер пересоздан. Текущее состояние также будет сохранено в новую копию.</>}
        confirmLabel="Восстановить"
        danger
        loading={busy}
        onClose={() => setRestoreName(null)}
        onConfirm={() => void restore()}
      />
    </div>
  )
}
