import { Apple, HelpCircle, Laptop, Monitor, Smartphone, Terminal, type LucideIcon } from 'lucide-react'
import type { DeviceInfo } from '../lib/types'
import { cn } from '../lib/utils'

const ICONS: Record<string, LucideIcon> = {
  windows: Monitor,
  apple: Apple,
  ios: Apple,
  macos: Laptop,
  android: Smartphone,
  linux: Terminal,
  other: HelpCircle,
  unknown: HelpCircle,
}

const COLORS: Record<string, string> = {
  windows: 'text-accent',
  apple: 'text-ink',
  ios: 'text-accent',
  macos: 'text-accent',
  android: 'text-ok',
  linux: 'text-warn',
  other: 'text-muted',
  unknown: 'text-muted',
}

export function DeviceBadge({
  device,
  onClick,
  className,
}: {
  device?: DeviceInfo | null
  onClick?: () => void
  className?: string
}) {
  const info = device ?? { family: 'unknown', label: 'неизвестно', source: 'none' }
  const Icon = ICONS[info.family] ?? HelpCircle
  const color = COLORS[info.family] ?? 'text-muted'
  const title = info.detail ? `${info.label} — ${info.detail}` : info.label

  const body = (
    <>
      <Icon className={cn('h-4 w-4 shrink-0', color)} />
      <span className="max-w-[150px] truncate text-ink/85">{info.label}</span>
      {info.source === 'syn' ? <span className="text-[10px] text-muted" title="приблизительно">~</span> : null}
      {info.source === 'manual' ? <span className="text-[10px] text-ok" title="указано вручную">✓</span> : null}
    </>
  )

  if (onClick) {
    return (
      <button
        type="button"
        title={`${title}. Нажмите, чтобы указать устройство вручную.`}
        onClick={onClick}
        className={cn('inline-flex items-center gap-1.5 rounded-lg px-1.5 py-1 text-xs transition hover:bg-ink/5', className)}
      >
        {body}
      </button>
    )
  }
  return (
    <span title={title} className={cn('inline-flex items-center gap-1.5 text-xs', className)}>
      {body}
    </span>
  )
}
