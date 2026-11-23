export function fmtBytes(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const units = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']
  let v = Math.abs(value)
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  const sign = value < 0 ? '-' : ''
  return `${sign}${v.toFixed(i === 0 ? 0 : digits)} ${units[i]}`
}

export function fmtSpeed(value: number | null | undefined): string {
  return `${fmtBytes(value ?? 0)}/с`
}

export function fmtNum(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('ru-RU').format(value)
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || seconds < 0) return '—'
  const s = Math.floor(seconds)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (d > 0) return `${d} д ${h} ч`
  if (h > 0) return `${h} ч ${m} мин`
  if (m > 0) return `${m} мин ${sec} с`
  return `${sec} с`
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

export function fmtDateShort(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso).getTime()
  if (Number.isNaN(d)) return '—'
  const diff = Math.floor((Date.now() - d) / 1000)
  if (diff < 5) return 'только что'
  if (diff < 60) return `${diff} с назад`
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`
  return `${Math.floor(diff / 86400)} дн назад`
}

export function levelTone(level: string): 'ok' | 'warn' | 'bad' | 'info' | 'muted' {
  switch (level) {
    case 'ERROR':
      return 'bad'
    case 'WARN':
      return 'warn'
    case 'INFO':
      return 'info'
    case 'DEBUG':
      return 'muted'
    default:
      return 'muted'
  }
}

export function categoryLabel(category: string): string {
  const map: Record<string, string> = {
    session: 'Сессия',
    error: 'Сбой/предупр.',
    upstream: 'Upstream',
    system: 'Система',
    info: 'Инфо',
  }
  return map[category] ?? category
}

export function pct(part: number, total: number): number {
  if (!total) return 0
  return Math.round((part / total) * 1000) / 10
}
