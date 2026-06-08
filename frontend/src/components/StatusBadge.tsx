import { clsx } from 'clsx'
import type { BenchmarkStatus } from '../types'

const CONFIG: Record<BenchmarkStatus, { label: string; classes: string; dot: string }> = {
  pending:   { label: 'Pending',   classes: 'bg-slate-800 text-slate-400 border-slate-700',      dot: 'bg-slate-500' },
  running:   { label: 'Running',   classes: 'bg-blue-950 text-blue-400 border-blue-800',          dot: 'bg-blue-400 animate-pulse' },
  completed: { label: 'Completed', classes: 'bg-emerald-950 text-emerald-400 border-emerald-800', dot: 'bg-emerald-400' },
  failed:    { label: 'Failed',    classes: 'bg-red-950 text-red-400 border-red-800',              dot: 'bg-red-400' },
}

interface Props {
  status: BenchmarkStatus
  size?: 'sm' | 'md'
}

export default function StatusBadge({ status, size = 'sm' }: Props) {
  const cfg = CONFIG[status] ?? CONFIG.pending
  return (
    <span
      className={clsx(
        'badge border',
        cfg.classes,
        size === 'md' && 'px-3 py-1 text-sm'
      )}
    >
      <span className={clsx('w-1.5 h-1.5 rounded-full', cfg.dot)} />
      {cfg.label}
    </span>
  )
}
