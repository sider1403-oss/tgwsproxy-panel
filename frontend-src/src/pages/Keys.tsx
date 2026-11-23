import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, BarChart3, Eye, EyeOff, KeyRound, Plus, Power, RefreshCw, Trash2 } from 'lucide-react'
import type { KeyItem, KeysResponse } from '../lib/types'
import { api } from '../lib/api'
import { fmtDate } from '../lib/format'
import { Badge, Button, Card, ConfirmDialog, CopyBtn, Dialog, Empty, Field, Input, useToast } from '../components/ui'

type Pending = { type: 'disable' | 'delete'; key: KeyItem } | null

export default function Keys() {
  const [data, setData] = useState<KeysResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [revealed, setRevealed] = useState<Record<string, boolean>>({})
  const [addOpen, setAddOpen] = useState(false)
  const [newComment, setNewComment] = useState('')
  const [newLink, setNewLink] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<Pending>(null)
  const [commentEdit, setCommentEdit] = useState<KeyItem | null>(null)
  const [commentText, setCommentText] = useState('')
  const [statsKey, setStatsKey] = useState<KeyItem | null>(null)
  const [statsText, setStatsText] = useState<string>('')
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
      const r = await api.disableKey(k.key)
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
      const r = await api.deleteKey(k.key)
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
      const r = await api.enableKey(k.key)
      if (!r.ok) throw new Error(r.error || 'Ошибка')
      push('ok', 'Ключ включён — контейнер перезапущен')
      await load()
    } catch (e) {
      push('bad', e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const doAdd = async () => {
    setBusy(true)
    setNewLink(null)
    try {
      const r = await api.addKey(newComment)
      if (!r.ok) throw new Error(r.error || 'Ошибка')
      setNewLink(r.link || null)
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
      await api.setComment(commentEdit.key, commentText)
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
      const s = await fetch(`/api/keys/${k.key}/stats`).then((r) => r.json())
      setStatsText(s.reason ?? 'Статистика недоступна')
    } catch {
      setStatsText('Не удалось получить статистику')
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
          <Button variant="primary" onClick={() => { setAddOpen(true); setNewLink(null) }}>
            <Plus className="h-4 w-4" /> Создать ключ
          </Button>
        </div>
      </div>

      {error ? <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div> : null}

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
          <table className="w-full min-w-[900px] border-collapse">
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
                <tr key={k.key} className="border-b border-line/40 hover:bg-ink/[0.03]">
                  <td className="td">
                    <div className="flex items-center gap-2">
                      <code className="rounded-md border border-line bg-ink/[0.07] px-2 py-1 text-[11px]">
                        {revealed[k.key] ? k.key : k.masked}
                      </code>
                      <button className="text-muted hover:text-ink" onClick={() => setRevealed((s) => ({ ...s, [k.key]: !s[k.key] }))} title="Показать/скрыть">
                        {revealed[k.key] ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
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
                    <div className="flex items-center gap-2">
                      <CopyBtn value={k.link} label="Ссылка" />
                      <span className="max-w-[220px] truncate font-mono text-[10px] text-muted">{k.link}</span>
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
              <div key={k.key} className="flex flex-wrap items-center gap-3 rounded-xl border border-line/60 bg-ink/5 px-3 py-2">
                <code className="text-[11px] text-muted">{k.masked}</code>
                <span className="text-xs text-muted">{k.comment || 'без комментария'}</span>
                <Badge tone="warn">отключён</Badge>
                <div className="ml-auto flex gap-2">
                  <Button className="!px-2.5 !py-1.5 text-xs" onClick={() => void doEnable(k)} loading={busy}>
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
            <Button variant="primary" onClick={() => void doAdd()} loading={busy} disabled={!!newLink}>
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
            <div className="space-y-2 rounded-xl border border-ok/25 bg-ok/[0.06] p-3">
              <div className="text-xs text-ok">Ключ создан. Ссылка для Telegram:</div>
              <div className="break-all font-mono text-[11px] text-ink/90">{newLink}</div>
              <CopyBtn value={newLink} label="Копировать ссылку" />
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

      <ConfirmDialog
        open={!!pending}
        title={pending?.type === 'disable' ? 'Отключить ключ?' : 'Удалить ключ?'}
        text={
          pending?.type === 'disable' ? (
            <>Ключ <span className="font-mono">{pending?.key.masked}</span> будет удалён из TG_SECRET, контейнер перезапустится.
              Клиенты с этим ключом потеряют доступ. Ключ останется в списке отключённых и его можно вернуть.</>
          ) : (
            <>Ключ <span className="font-mono">{pending?.key.masked}</span> будет удалён из конфигурации без возможности восстановления
              через панель (останется в резервной копии). Контейнер перезапустится.</>
          )
        }
        danger={pending?.type === 'delete'}
        confirmLabel={pending?.type === 'delete' ? 'Удалить' : 'Отключить'}
        loading={busy}
        onClose={() => setPending(null)}
        onConfirm={() => {
          if (!pending) return
          if (pending.type === 'disable') void doDisable(pending.key)
          else void doDelete(pending.key)
        }}
      />
    </div>
  )
}
