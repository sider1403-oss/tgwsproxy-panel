import type { ReactNode } from 'react'
import { cn } from '../lib/utils'
import { Card } from './ui'

export function StatCard({
  label,
  value,
  sub,
  icon,
  tone = 'default',
  className,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  icon?: ReactNode
  tone?: 'default' | 'ok' | 'bad' | 'warn' | 'accent'
  className?: string
}) {
  return (
    <Card className={cn('relative overflow-hidden p-4 sm:p-5', className)}>
      <div
        className={cn(
          'pointer-events-none absolute -right-8 -top-10 h-24 w-24 rounded-full blur-2xl',
          tone === 'ok' && 'bg-ok/10',
          tone === 'bad' && 'bg-bad/10',
          tone === 'warn' && 'bg-warn/10',
          tone === 'accent' && 'bg-accent/10',
          tone === 'default' && 'bg-accent2/10',
        )}
      />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-medium uppercase tracking-wider text-muted">{label}</div>
          <div className="mt-1.5 break-words text-lg font-semibold leading-tight tracking-tight sm:text-2xl">{value}</div>
          {sub ? <div className="mt-1 text-[11px] leading-snug text-muted">{sub}</div> : null}
        </div>
        {icon ? <div className="shrink-0 rounded-lg border border-line bg-ink/5 p-2 text-muted">{icon}</div> : null}
      </div>
    </Card>
  )
}
