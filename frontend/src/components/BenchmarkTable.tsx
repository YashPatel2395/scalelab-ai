import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Trash2, ExternalLink, ChevronDown, ChevronUp, FileCode, Activity } from 'lucide-react'
import type { BenchmarkRunSummary } from '../types'
import StatusBadge from './StatusBadge'
import { deleteBenchmark } from '../services/api'

interface Props {
  runs: BenchmarkRunSummary[]
  onDeleted: (id: string) => void
  onViewAnalysis?: (run: BenchmarkRunSummary) => void
  loading?: boolean
}

const WORKLOAD_LABELS: Record<string, string> = {
  matrix_multiplication: 'Matrix Mult',
  parallel_sort: 'Parallel Sort',
  image_processing: 'Image Proc',
  graph_bfs: 'Graph BFS',
  custom_python: 'Custom',
}

function WorkloadBadge({ workloadType, label: labelProp }: { workloadType: string; label?: string | null }) {
  const label = labelProp || WORKLOAD_LABELS[workloadType] || workloadType
  if (workloadType === 'custom_python') {
    return (
      <span className="inline-flex items-center gap-1 font-mono text-xs px-2 py-0.5 rounded bg-violet-500/10 border border-violet-500/30 text-violet-400">
        <FileCode className="w-3 h-3" />
        {label}
      </span>
    )
  }
  return (
    <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
      {label}
    </span>
  )
}

type SortField = 'created_at' | 'execution_time' | 'speedup' | 'efficiency'
type SortDir = 'asc' | 'desc'

export default function BenchmarkTable({ runs, onDeleted, onViewAnalysis, loading = false }: Props) {
  const navigate = useNavigate()
  const [sortField, setSortField] = useState<SortField>('created_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const handleSort = (field: SortField) => {
    if (field === sortField) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  const sorted = [...runs].sort((a, b) => {
    const aVal = a[sortField] ?? 0
    const bVal = b[sortField] ?? 0
    const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0
    return sortDir === 'asc' ? cmp : -cmp
  })

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    setDeletingId(id)
    try {
      await deleteBenchmark(id)
      onDeleted(id)
    } catch {
      // ignore
    } finally {
      setDeletingId(null)
    }
  }

  const SortIcon = ({ field }: { field: SortField }) =>
    sortField === field ? (
      sortDir === 'asc' ? (
        <ChevronUp className="w-3 h-3 inline ml-1 text-cyan-400" />
      ) : (
        <ChevronDown className="w-3 h-3 inline ml-1 text-cyan-400" />
      )
    ) : (
      <ChevronDown className="w-3 h-3 inline ml-1 text-slate-600" />
    )

  if (loading) {
    return (
      <div className="card overflow-hidden">
        <div className="p-5 border-b border-slate-800">
          <h2 className="text-slate-100 font-semibold">Benchmark History</h2>
        </div>
        {[...Array(5)].map((_, i) => (
          <div key={i} className="px-5 py-3 border-b border-slate-800 flex gap-4">
            {[...Array(7)].map((_, j) => (
              <div key={j} className="h-4 bg-slate-800 rounded animate-pulse flex-1" />
            ))}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h2 className="text-slate-100 font-semibold text-sm">Benchmark History</h2>
          <p className="text-slate-500 text-xs mt-0.5">{runs.length} runs total</p>
        </div>
      </div>

      {runs.length === 0 ? (
        <div className="py-16 text-center text-slate-600">
          <p className="text-sm">No benchmark runs yet.</p>
          <p className="text-xs mt-1">Submit a benchmark using the form above.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800">
                {[
                  { label: 'Workload', field: null },
                  { label: 'Input Size', field: null },
                  { label: 'Workers', field: null },
                  { label: 'Time (s)', field: 'execution_time' as SortField },
                  { label: 'Speedup', field: 'speedup' as SortField },
                  { label: 'Efficiency', field: 'efficiency' as SortField },
                  { label: 'Status', field: null },
                  { label: 'Submitted', field: 'created_at' as SortField },
                  { label: '', field: null },
                ].map(({ label, field }) => (
                  <th
                    key={label}
                    onClick={field ? () => handleSort(field) : undefined}
                    className={`px-4 py-3 text-left label-text whitespace-nowrap ${
                      field ? 'cursor-pointer hover:text-slate-400 select-none' : ''
                    }`}
                  >
                    {label}
                    {field && <SortIcon field={field} />}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((run) => (
                <tr
                  key={run.id}
                  onClick={() => navigate(`/benchmark/${run.id}`)}
                  className="border-b border-slate-800/50 hover:bg-slate-800/40 cursor-pointer transition-colors group"
                >
                  <td className="px-4 py-3">
                    <WorkloadBadge workloadType={run.workload_type} label={run.workload_name} />
                  </td>
                  <td className="px-4 py-3 font-mono text-slate-300 text-xs">
                    {run.input_size.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-slate-300 font-mono text-xs">
                    {run.worker_count}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-300">
                    {run.execution_time != null ? run.execution_time.toFixed(4) : '—'}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {run.speedup != null ? (
                      <span className="text-cyan-400">{run.speedup.toFixed(2)}×</span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {run.efficiency != null ? (
                      <span
                        className={
                          run.efficiency >= 80
                            ? 'text-emerald-400'
                            : run.efficiency >= 50
                            ? 'text-amber-400'
                            : 'text-red-400'
                        }
                      >
                        {run.efficiency.toFixed(1)}%
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={run.status} />
                  </td>
                  <td className="px-4 py-3 text-slate-600 text-xs font-mono whitespace-nowrap">
                    {new Date(run.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      {run.status === 'completed' && onViewAnalysis && (
                        <button
                          onClick={(e) => { e.stopPropagation(); onViewAnalysis(run) }}
                          className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 hover:border-cyan-500/50 transition-colors whitespace-nowrap"
                          title="Open analysis"
                        >
                          <Activity className="w-3 h-3" />
                          View Analysis
                        </button>
                      )}
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={(e) => { e.stopPropagation(); navigate(`/benchmark/${run.id}`) }}
                          className="p-1 rounded hover:bg-slate-700 text-slate-500 hover:text-slate-300 transition-colors"
                          title="View details page"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={(e) => handleDelete(e, run.id)}
                          disabled={deletingId === run.id}
                          className="p-1 rounded hover:bg-red-950 text-slate-500 hover:text-red-400 transition-colors"
                          title="Delete run"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
