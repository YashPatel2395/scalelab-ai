import { type ReactNode } from 'react'
import { clsx } from 'clsx'

interface Props {
  label: string
  value: string | number | null
  unit?: string
  subtext?: string
  icon: ReactNode
  accentColor?: 'cyan' | 'blue' | 'purple' | 'green' | 'amber' | 'red'
  loading?: boolean
}

const ACCENT_MAP = {
  cyan:   { bg: 'bg-cyan-500/10',   border: 'border-cyan-500/20',   icon: 'text-cyan-400',   value: 'text-cyan-300' },
  blue:   { bg: 'bg-blue-500/10',   border: 'border-blue-500/20',   icon: 'text-blue-400',   value: 'text-blue-300' },
  purple: { bg: 'bg-purple-500/10', border: 'border-purple-500/20', icon: 'text-purple-400', value: 'text-purple-300' },
  green:  { bg: 'bg-emerald-500/10',border: 'border-emerald-500/20',icon: 'text-emerald-400',value: 'text-emerald-300' },
  amber:  { bg: 'bg-amber-500/10',  border: 'border-amber-500/20',  icon: 'text-amber-400',  value: 'text-amber-300' },
  red:    { bg: 'bg-red-500/10',    border: 'border-red-500/20',    icon: 'text-red-400',    value: 'text-red-300' },
}

export default function MetricCard({
  label,
  value,
  unit,
  subtext,
  icon,
  accentColor = 'cyan',
  loading = false,
}: Props) {
  const accent = ACCENT_MAP[accentColor]

  return (
    <div className="card p-5 flex flex-col gap-3 hover:border-slate-700 transition-colors">
      {/* Icon + label */}
      <div className="flex items-center justify-between">
        <span className="label-text">{label}</span>
        <div
          className={clsx(
            'w-8 h-8 rounded-lg border flex items-center justify-center',
            accent.bg,
            accent.border
          )}
        >
          <span className={clsx('w-4 h-4', accent.icon)}>{icon}</span>
        </div>
      </div>

      {/* Value */}
      {loading ? (
        <div className="h-9 w-24 bg-slate-800 rounded animate-pulse" />
      ) : (
        <div className="flex items-baseline gap-1.5">
          <span className={clsx('metric-value', accent.value)}>
            {value ?? '—'}
          </span>
          {unit && (
            <span className="text-sm text-slate-500 font-medium">{unit}</span>
          )}
        </div>
      )}

      {/* Subtext */}
      {subtext && (
        <p className="text-xs text-slate-500 leading-relaxed">{subtext}</p>
      )}
    </div>
  )
}
