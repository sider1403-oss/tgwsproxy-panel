import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { Check, Copy, Loader2, X } from 'lucide-react'
import { cn } from '../lib/utils'
import { useCopy } from '../lib/hooks'

// ── Toasts ───────────────────────────────────────────────────────────────────

type Tone = 'ok' | 'bad' | 'warn' | 'info'
type Toast = { id: number; tone: Tone; text: string }
const ToastCtx = createContext<{ push: (tone: Tone, text: string) => void }>({ push: () => undefined })

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((tone: Tone, text: string) => {
    const id = Date.now() + Math.random()
    setItems((prev) => [...prev, { id, tone, text }])
    setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 5000)
  }, [])
  const value = useMemo(() => ({ push }), [push])
  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex w-[min(92vw,380px)] flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            className={cn(
              'animate-fade-up rounded-xl border px-4 py-3 text-sm shadow-2xl backdrop-blur',
              t.tone === 'ok' && 'border-ok/30 bg-ok/10 text-ok',
              t.tone === 'bad' && 'border-bad/30 bg-bad/10 text-bad',
              t.tone === 'warn' && 'border-warn/30 bg-warn/10 text-warn',
              t.tone === 'info' && 'border-accent/30 bg-accent/10 text-accent',
            )}
          >
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export function useToast() {
  return useContext(ToastCtx)
}

// ── primitives ───────────────────────────────────────────────────────────────

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn('h-4 w-4 animate-spin', className)} />
}

export function Button({
  children,
  variant = 'ghost',
  loading,
  className,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'danger' | 'warn'; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={cn(
        variant === 'primary' && 'btn-primary',
        variant === 'ghost' && 'btn-ghost',
        variant === 'danger' && 'btn-danger',
        variant === 'warn' && 'btn-warn',
        className,
      )}
    >
      {loading ? <Spinner /> : null}
      {children}
    </button>
  )
}

export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('surface p-5', className)}>{children}</div>
}

export function CardTitle({ children, right, className }: { children: React.ReactNode; right?: React.ReactNode; className?: string }) {
  return (
    <div className={cn('mb-4 flex flex-wrap items-center justify-between gap-x-3 gap-y-2', className)}>
      <h3 className="text-sm font-semibold tracking-wide text-ink/90">{children}</h3>
      {right}
    </div>
  )
}

export function Badge({ children, tone = 'muted', className }: { children: React.ReactNode; tone?: 'ok' | 'bad' | 'warn' | 'info' | 'muted'; className?: string }) {
  return (
    <span
      className={cn(
        'chip',
        tone === 'ok' && 'border-ok/30 bg-ok/10 text-ok',
        tone === 'bad' && 'border-bad/30 bg-bad/10 text-bad',
        tone === 'warn' && 'border-warn/30 bg-warn/10 text-warn',
        tone === 'info' && 'border-accent/30 bg-accent/10 text-accent',
        tone === 'muted' && 'border-line bg-ink/5 text-muted',
        className,
      )}
    >
      {children}
    </span>
  )
}

export function Dot({ tone = 'ok', live = false }: { tone?: 'ok' | 'bad' | 'warn' | 'muted'; live?: boolean }) {
  return (
    <span
      className={cn(
        'inline-block h-2 w-2 rounded-full',
        tone === 'ok' && 'bg-ok',
        tone === 'bad' && 'bg-bad',
        tone === 'warn' && 'bg-warn',
        tone === 'muted' && 'bg-muted',
        live && 'dot-live',
      )}
    />
  )
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn('input', props.className)} />
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cn('select', props.className)} />
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cn('input font-mono text-xs leading-relaxed', props.className)} />
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-[11px] text-muted/80">{hint}</span> : null}
    </label>
  )
}

export function Switch({ checked, onChange, disabled, label }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'inline-flex items-center gap-2 text-sm text-ink/80 disabled:opacity-50',
      )}
    >
      <span
        className={cn(
          'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition',
          checked ? 'border-accent/40 bg-accent/25' : 'border-line bg-ink/5',
        )}
      >
        <span
          className={cn(
            'absolute h-4 w-4 rounded-full shadow-sm transition-all',
            checked ? 'left-6 bg-white' : 'left-1 bg-ink',
          )}
        />
      </span>
      {label ? <span>{label}</span> : null}
    </button>
  )
}

export function CopyBtn({ value, label = 'Копировать', className }: { value: string; label?: string; className?: string }) {
  const { copied, copy } = useCopy()
  return (
    <button
      type="button"
      onClick={() => void copy(value)}
      className={cn('btn-ghost !px-2.5 !py-1.5 text-xs', className)}
      title={label}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-ok" /> : <Copy className="h-3.5 w-3.5" />}
      <span className="hidden sm:inline">{copied ? 'Скопировано' : label}</span>
    </button>
  )
}

// ── dialog ───────────────────────────────────────────────────────────────────

export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  wide,
}: {
  open: boolean
  onClose: () => void
  title: React.ReactNode
  children: React.ReactNode
  footer?: React.ReactNode
  wide?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', handler)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-0 backdrop-blur-sm sm:items-center sm:p-6" onMouseDown={onClose}>
      <div
        className={cn(
          'animate-fade-up max-h-[92vh] w-full overflow-y-auto rounded-t-2xl border border-line bg-card shadow-2xl sm:rounded-2xl',
          wide ? 'sm:max-w-4xl' : 'sm:max-w-lg',
        )}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4 border-b border-line/70 px-5 py-4">
          <h2 className="text-base font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted transition hover:bg-ink/5 hover:text-ink" aria-label="Закрыть">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer ? <div className="flex flex-wrap justify-end gap-2 border-t border-line/70 px-5 py-4">{footer}</div> : null}
      </div>
    </div>
  )
}

export function ConfirmDialog({
  open,
  title,
  text,
  confirmLabel = 'Подтвердить',
  danger,
  onConfirm,
  onClose,
  loading,
}: {
  open: boolean
  title: string
  text: React.ReactNode
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => void
  onClose: () => void
  loading?: boolean
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button onClick={onClose} disabled={loading}>
            Отмена
          </Button>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-sm leading-relaxed text-ink/80">{text}</div>
    </Dialog>
  )
}

// ── misc ─────────────────────────────────────────────────────────────────────

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 px-4 py-12 text-center">
      <div className="text-sm font-medium text-ink/80">{title}</div>
      {hint ? <div className="max-w-md text-xs text-muted">{hint}</div> : null}
    </div>
  )
}

export function Tabs({ value, onChange, items }: { value: string; onChange: (v: string) => void; items: { value: string; label: string }[] }) {
  return (
    <div className="inline-flex max-w-full overflow-x-auto rounded-xl border border-line bg-field p-1">
      {items.map((it) => (
        <button
          key={it.value}
          onClick={() => onChange(it.value)}
          className={cn(
            'rounded-lg px-3.5 py-1.5 text-sm transition',
            value === it.value ? 'bg-accent/15 text-accent' : 'text-muted hover:text-ink',
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  )
}
