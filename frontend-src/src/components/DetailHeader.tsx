import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, RefreshCw } from 'lucide-react'
import { Button } from './ui'
import { fmtRelative } from '../lib/format'

export function DetailHeader({
  title,
  subtitle,
  backTo = '/',
  backLabel = 'На дашборд',
  updatedAt,
  onRefresh,
  loading,
  children,
}: {
  title: string
  subtitle?: ReactNode
  backTo?: string
  backLabel?: string
  updatedAt?: string | null
  onRefresh?: () => void
  loading?: boolean
  children?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-start gap-3">
      <Link
        to={backTo}
        className="mt-0.5 inline-flex items-center gap-1.5 rounded-lg border border-line bg-card/60 px-2.5 py-1.5 text-xs text-muted transition hover:bg-ink/5 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        {backLabel}
      </Link>
      <div className="min-w-0 flex-1">
        <h2 className="text-lg font-semibold tracking-tight sm:text-xl">{title}</h2>
        {subtitle ? <div className="mt-1 text-xs leading-relaxed text-muted">{subtitle}</div> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {updatedAt ? <span className="text-[11px] text-muted">обновлено {fmtRelative(updatedAt)}</span> : null}
        {onRefresh ? (
          <Button onClick={onRefresh} loading={loading} className="!py-1.5 text-xs">
            <RefreshCw className="h-3.5 w-3.5" /> Обновить
          </Button>
        ) : null}
      </div>
      {children ? <div className="w-full">{children}</div> : null}
    </div>
  )
}
