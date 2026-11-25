import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, BarChart3, Eye, KeyRound, Plus, Power, RefreshCw, Trash2 } from 'lucide-react'
import type { KeyItem, KeysResponse } from '../lib/types'
import { api } from '../lib/api'
import { fmtDate } from '../lib/format'
import { Badge, Button, Card, ConfirmDialog, CopyBtn, Dialog, Empty, Field, Input, useToast } from '../components/ui'

type Pending = { type: 'disable' | 'enable' | 'delete'; key: KeyItem } | null
type Revealed = { key: string; masked: string; link_lan: string | null; link_external: string | null }

export default function Keys() {
  const [data, setData] = useState<KeysResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [addOpen, setAddOpen] = useState(false)
  const [newComment, setNewComment] = useState('')
  const [newLink, setNewLink] = useState<string | null>(null)
  const [newLinkLan, setNewLinkLan] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<Pending>(null)
  const [confirmAdd, setConfirmAdd] = useState(false)
  const [commentEdit, setCommentEdit] = useState<KeyItem | null>(null)
  const [commentText, setCommentText] = useState('')
  const [statsKey, setStatsKey] = useState<KeyItem | null>(null)
  const [statsText, setStatsText] = useState<string>('')
  const [revealKey, setRevealKey] = useState<KeyItem | null>(null)
  const [revealPassword, setRevealPassword] = useState('')
  const [revealed, setRevealed] = useState<Revealed | null>(null)
  const [revealBusy, setRevealBusy] = useState(false)
  const { push } = useToast()

  const load = useCallback(async () => {
    try {
      const d = await api.keys()
      setData(d)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const t = setInterval(() => void load(), 20000)
    return () => clearInterval(t)
  }, [load])

  const doDisable = async (k: KeyItem) => {
    setBusy(true)
    try {
      const r = await api.disableKey(k.id)
      if (!r.ok) throw new Error(r.error || 'Ошибка')
      push('ok', 'Ключ отключён — контейнер перезапущен')
      await load()
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const doDelete = async (k: KeyItem) => {
    setBusy(true)
    try {
      const r = await api.deleteKey(k.id)
      if (!r.ok) throw new Error(r.error || 'Ошибка')
      push('ok', 'Ключ удалён — контейнер перезапущен')
      await load()
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const doEnable = async (k: KeyItem) => {
    setBusy(true)
    try {
      const r = await api.enableKey(k.id)
      if (!r.ok) throw new Error(r.error || 'Ошибка')
      push('ok', 'Ключ включён — контейнер перезапущен')
      await load()
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const doAdd = async () => {
    setBusy(true)
    setNewLink(null)
    setNewLinkLan(null)
    try {
      const r = await api.addKey(newComment)
      if (!r.ok) throw new Error(r.error || 'Ошибка')
      setNewLink(r.link_external || r.link || null)
      setNewLinkLan(r.link_lan || null)
      setNewComment('')
      push('ok', 'Ключ создан — контейнер перезапущен')
      await load()
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const saveComment = async () => {
    if (!commentEdit) return
    setBusy(true)
    try {
      await api.setComment(commentEdit.id, commentText)
      push('ok', 'Комментарий сохранён')
      setCommentEdit(null)
      await load()
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const showStats = async (k: KeyItem) => {
    setStatsKey(k)
    try {
      const s = await api.keyStats(k.id)
      setStatsText(s.reason ?? 'Статистика недоступна')
    } catch {
      setStatsText('Не удалось получить статистику')
    }
  }

  const openReveal = (k: KeyItem) => {
    setRevealKey(k)
    setRevealPassword('')
    setRevealed(null)
  }

  const doReveal = async () => {
    if (!revealKey) return
    setRevealBusy(true)
    try {
      const r = await api.revealKey(revealKey.id, revealPassword)
      setRevealed(r)
      setRevealPassword('')
    } catch (e) {
      push('bad', e instanceof Error ? e.message : 'Не удалось показать секрет')
    } finally {
      setRevealBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Ключи доступа MTProto</h2>
          <p className="text-[11px] text-muted">
            Источник: TG_SECRET прокси ({data?.secret_source === 'env_file' ? '.env' : 'docker-compose'}). Один ключ — один tg://.
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => void load()} loading={loading}>
            <RefreshCw className="h-4 w-4" /> Обновить
          </Button>
          <Button variant="primary" onClick={() => { setAddOpen(true); setNewLink(null); setNewLinkLan(null) }}>
            <Plus className="h-4 w-4" /> Создать ключ
          </Button>
        </div>
      </div>

      {error ? <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}

      {data?.lan_host && data?.external_host && data.lan_host !== data.external_host ? (
        <div className="flex items-start gap-3 rounded-xl border border-warn/25 bg-warn/[0.06] px-4 py-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <div className="text-xs leading-relaxed text-ink/80">
            <div className="mb-1 font-medium text-warn">Клиенты в LAN должны использовать LAN-ссылку</div>
            Если телефон/компьютер в локальной сети подключается по публичному адресу{' '}
            <span className="font-mono">{data.external_host}</span> через роутер, hairpin NAT может
            подменить источник на IP шлюза (например, <span className="font-mono">192.168.50.1</span>).
            Панель тогда покажет неверный IP и устройство. Для устройств в LAN копируйте ссылку с
            адресом <span className="font-mono">{data.lan_host}</span>.
          </div>
        </div>
      ) : null}

      {data?.stats_supported === false ? (
        <div className="flex items-start gap-3 rounded-xl border border-warn/25 bg-warn/[0.06] px-4 py-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <div className="text-xs leading-relaxed text-ink/80">
            <div className="mb-1 font-medium text-warn">Раздельная статистика по ключам недоступна</div>
            {data.stats_note}
            <div className="mt-1 text-muted">
              Альтернатива: отдельный экземпляр/порт на ключ (изменение архитектуры) либо анализ по IP клиента, который к ключу не привязан.
            </div>
          </div>
        </div>
      ) : null}

      <Card>
        <div className="mb-3 flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-semibold">Активные ключи</h3>
          <Badge tone="ok">{data?.keys.length ?? 0}</Badge>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[1040px] border-collapse">
            <thead>
              <tr className="border-b border-line/70">
                <th className="th">Ключ</th>
                <th className="th">Комментарий</th>
                <th className="th">Создан</th>
                <th className="th">Статус</th>
                <th className="th">Ссылка tg://</th>
                <th className="th text-right">Действия</th>
              </tr>
            </thead>
            <tbody>
              {(data?.keys ?? []).map((k) => (
                <tr key={k.id} className="border-b border-line/40 hover:bg-ink/[0.03]">
                  <td className="td">
                    <div className="flex items-center gap-2">
                      <code className="rounded-md border border-line bg-ink/[0.07] px-2 py-1 text-[11px]">{k.masked}</code>
                      <button className="text-muted hover:text-ink" onClick={() => openReveal(k)} title="Показать ключ и ссылки (нужен пароль)">
                        <Eye className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                  <td className="td text-muted">
                    <button className="text-left hover:text-ink" onClick={() => { setCommentEdit(k); setCommentText(k.comment) }}>
                      {k.comment || <span className="text-muted/50">добавить комментарий</span>}
                    </button>
                  </td>
                  <td className="td text-muted">{k.created_at ? fmtDate(k.created_at) : '—'}</td>
                  <td className="td"><Badge tone="ok">активен</Badge></td>
                  <td className="td">
                    <div className="space-y-1.5">
                      {k.link_lan ? (
                        <div className="flex items-center gap-2">
                          <Badge tone="info">LAN</Badge>
                          <span className="max-w-[210px] truncate font-mono text-[10px] text-muted">{k.link_lan}</span>
                        </div>
                      ) : null}
                      <div className="flex items-center gap-2">
                        <Badge tone="muted">Интернет</Badge>
                        <span className="max-w-[210px] truncate font-mono text-[10px] text-muted">{k.link_external}</span>
                      </div>
                      <Button className="!px-2 !py-1 text-[11px]" onClick={() => openReveal(k)}>
                        <Eye className="h-3 w-3" /> Показать с паролем
                      </Button>
                    </div>
                  </td>
                  <td className="td">
                    <div className="flex flex-wrap justify-end gap-1.5">
                      <Button className="!px-2 !py-1.5 text-xs" onClick={() => void showStats(k)} title="Статистика">
                        <BarChart3 className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="warn" className="!px-2 !py-1.5 text-xs" onClick={() => setPending({ type: 'disable', key: k })}>
                        <Power className="h-3.5 w-3.5" /> Отключить
                      </Button>
                      <Button variant="danger" className="!px-2 !py-1.5 text-xs" onClick={() => setPending({ type: 'delete', key: k })}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data?.keys.length && !loading ? <Empty title="Ключей нет" hint="Прокси не сможет принимать подключения без ключа." /> : null}
        </div>
      </Card>

      {data?.disabled.length ? (
        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Power className="h-4 w-4 text-warn" />
            <h3 className="text-sm font-semibold">Отключённые ключи</h3>
            <Badge tone="warn">{data.disabled.length}</Badge>
          </div>
          <div className="space-y-2">
            {data.disabled.map((k) => (
              <div key={k.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-line/60 bg-ink/5 px-3 py-2">
                <code className="text-[11px] text-muted">{k.masked}</code>
                <span className="text-xs text-muted">{k.comment || 'без комментария'}</span>
                <Badge tone="warn">отключён</Badge>
                <div className="ml-auto flex gap-2">
                  <Button className="!px-2.5 !py-1.5 text-xs" onClick={() => setPending({ type: 'enable', key: k })} loading={busy}>
                    <Power className="h-3.5 w-3.5" /> Включить
                  </Button>
                  <Button variant="danger" className="!px-2 !py-1.5 text-xs" onClick={() => setPending({ type: 'delete', key: k })}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      <Dialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Создать ключ"
        footer={
          <>
            <Button onClick={() => setAddOpen(false)}>Закрыть</Button>
            <Button variant="primary" onClick={() => setConfirmAdd(true)} loading={busy} disabled={!!newLink}>
              Создать
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="Комментарий" hint="Хранится только в панели; в конфигурации прокси — лишь сам секрет.">
            <Input value={newComment} onChange={(e) => setNewComment(e.target.value)} placeholder="например: телефон Михаила" />
          </Field>
          <div className="rounded-lg border border-warn/25 bg-warn/[0.06] px-3 py-2 text-[11px] text-warn">
            Применение ключа пересоздаёт контейнер прокси: короткий разрыв активных сессий (несколько секунд).
          </div>
          {newLink ? (
            <div className="space-y-3 rounded-xl border border-ok/25 bg-ok/[0.06] p-3">
              <div className="text-xs text-ok">Ключ создан. Ссылки для Telegram:</div>
              {newLinkLan ? (
                <div className="space-y-1">
                  <div className="text-[10px] uppercase tracking-wider text-muted">Для устройств в LAN</div>
                  <div className="break-all font-mono text-[11px] text-ink/90">{newLinkLan}</div>
                  <CopyBtn value={newLinkLan} label="Копировать LAN-ссылку" />
                </div>
              ) : null}
              <div className="space-y-1">
                <div className="text-[10px] uppercase tracking-wider text-muted">Для внешних устройств</div>
                <div className="break-all font-mono text-[11px] text-ink/90">{newLink}</div>
                <CopyBtn value={newLink} label="Копировать внешнюю ссылку" />
              </div>
              <div className="text-[11px] text-muted">
                Если устройство в той же LAN, используйте LAN-ссылку — иначе роутер может скрыть
                реальный IP клиента (hairpin NAT), и панель покажет IP шлюза.
              </div>
            </div>
          ) : null}
        </div>
      </Dialog>

      <Dialog
        open={!!commentEdit}
        onClose={() => setCommentEdit(null)}
        title="Комментарий к ключу"
        footer={
          <>
            <Button onClick={() => setCommentEdit(null)}>Отмена</Button>
            <Button variant="primary" onClick={() => void saveComment()} loading={busy}>Сохранить</Button>
          </>
        }
      >
        <Field label="Комментарий">
          <Input value={commentText} onChange={(e) => setCommentText(e.target.value)} autoFocus />
        </Field>
        <div className="mt-2 text-[11px] text-muted">Комментарий не меняет конфигурацию прокси и не требует перезапуска.</div>
      </Dialog>

      <Dialog open={!!statsKey} onClose={() => setStatsKey(null)} title="Статистика ключа" footer={<Button onClick={() => setStatsKey(null)}>Закрыть</Button>}>
        <div className="space-y-3 text-sm">
          <div className="rounded-lg border border-line bg-ink/5 px-3 py-2 font-mono text-[11px] text-muted">{statsKey?.masked}</div>
          <div className="flex items-start gap-2 text-xs text-warn">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            {statsText}
          </div>
          <div className="text-xs text-muted">
            Прокси не записывает, каким секретом клиент прошёл авторизацию, поэтому связать подключения/трафик с ключом невозможно.
          </div>
        </div>
      </Dialog>

      <Dialog
        open={!!revealKey}
        onClose={() => { setRevealKey(null); setRevealed(null); setRevealPassword('') }}
        title="Показать секрет ключа"
        footer={<Button onClick={() => { setRevealKey(null); setRevealed(null); setRevealPassword('') }}>Закрыть</Button>}
      >
        {!revealed ? (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              void doReveal()
            }}
          >
            <div className="rounded-lg border border-line bg-ink/5 px-3 py-2 font-mono text-[11px] text-muted">{revealKey?.masked}</div>
            <Field label="Подтвердите паролем" hint="Просмотр полного ключа и ссылок фиксируется в журнале безопасности.">
              <Input
                type="password"
                value={revealPassword}
                onChange={(e) => setRevealPassword(e.target.value)}
                autoFocus
                autoComplete="current-password"
                required
              />
            </Field>
            <Button type="submit" variant="primary" loading={revealBusy} disabled={!revealPassword}>
              Показать
            </Button>
          </form>
        ) : (
          <div className="space-y-3">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted">Ключ</div>
              <div className="mt-1 flex items-center gap-2">
                <code className="break-all rounded-lg border border-line bg-ink/5 px-2 py-1 text-[11px]">{revealed.key}</code>
                <CopyBtn value={revealed.key} label="Копировать" />
              </div>
            </div>
            {revealed.link_lan ? (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted">LAN-ссылка</div>
                <div className="mt-1 break-all font-mono text-[11px]">{revealed.link_lan}</div>
                <CopyBtn value={revealed.link_lan} label="Копировать LAN" />
              </div>
            ) : null}
            {revealed.link_external ? (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted">Внешняя ссылка</div>
                <div className="mt-1 break-all font-mono text-[11px]">{revealed.link_external}</div>
                <CopyBtn value={revealed.link_external} label="Копировать внешнюю" />
              </div>
            ) : null}
            <div className="text-[11px] text-muted">Не передавайте ссылку посторонним: она содержит секрет прокси.</div>
          </div>
        )}
      </Dialog>

      <ConfirmDialog
        open={!!pending}
        title={
          pending?.type === 'disable'
            ? 'Отключить ключ?'
            : pending?.type === 'enable'
              ? 'Включить ключ?'
              : 'Удалить ключ?'
        }
        text={
          pending?.type === 'disable' ? (
            <>Ключ <span className="font-mono">{pending?.key.masked}</span> будет удалён из TG_SECRET, контейнер перезапустится.
              Клиенты с этим ключом потеряют доступ. Ключ останется в списке отключённых и его можно вернуть.</>
          ) : pending?.type === 'enable' ? (
            <>Ключ <span className="font-mono">{pending?.key.masked}</span> будет добавлен в TG_SECRET, контейнер перезапустится.
              Активные сессии кратковременно прервутся.</>
          ) : (
            <>Ключ <span className="font-mono">{pending?.key.masked}</span> будет удалён из конфигурации без возможности восстановления
              через панель (останется в резервной копии). Контейнер перезапустится.</>
          )
        }
        danger={pending?.type === 'delete'}
        confirmLabel={
          pending?.type === 'delete' ? 'Удалить' : pending?.type === 'enable' ? 'Включить' : 'Отключить'
        }
        loading={busy}
        onClose={() => setPending(null)}
        onConfirm={() => {
          if (!pending) return
          if (pending.type === 'disable') void doDisable(pending.key)
          else if (pending.type === 'enable') void doEnable(pending.key)
          else void doDelete(pending.key)
        }}
      />

      <ConfirmDialog
        open={confirmAdd}
        title="Создать ключ и пересоздать контейнер?"
        text={
          <>
            Новый ключ будет добавлен в <span className="font-mono">TG_SECRET</span>, после чего панель выполнит
            <span className="font-mono"> docker compose up -d</span>. Контейнер прокси будет пересоздан, активные
            сессии кратковременно прервутся (несколько секунд).
          </>
        }
        confirmLabel="Создать ключ"
        danger
        loading={busy}
        onClose={() => setConfirmAdd(false)}
        onConfirm={() => {
          setConfirmAdd(false)
          void doAdd()
        }}
      />
    </div>
  )
}
