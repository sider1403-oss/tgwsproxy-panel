import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { cn } from '../lib/utils'
import { Card } from './ui'

export function StatCard({
  label,
  value,
  sub,
  icon,
  tone = 'default',
  className,
  to,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  icon?: ReactNode
  tone?: 'default' | 'ok' | 'bad' | 'warn' | 'accent'
  className?: string
  to?: string
}) {
  const card = (
    <Card
      className={cn(
        'relative h-full overflow-hidden p-4 sm:p-5',
        to && 'cursor-pointer transition duration-150 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-lg active:translate-y-0',
        className,
      )}
    >
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
        <div className="flex shrink-0 items-start gap-2">
          {icon ? <div className="rounded-lg border border-line bg-ink/5 p-2 text-muted">{icon}</div> : null}
          {to ? (
            <ChevronRight className="mt-2 h-4 w-4 text-muted transition group-hover:translate-x-0.5 group-hover:text-accent" />
          ) : null}
        </div>
      </div>
    </Card>
  )

  if (!to) return card
  return (
    <Link
      to={to}
      aria-label={`Открыть подробности: ${label}`}
      className="group block h-full rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
    >
      {card}
    </Link>
  )
}
