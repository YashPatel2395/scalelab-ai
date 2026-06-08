import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { ChartPoint } from '../types'

interface Props {
  data: ChartPoint[]
}

const WORKLOAD_COLORS: Record<string, string> = {
  matrix_multiplication: '#06b6d4',
  parallel_sort:         '#3b82f6',
  image_processing:      '#8b5cf6',
  graph_bfs:             '#10b981',
}

const WORKLOAD_LABELS: Record<string, string> = {
  matrix_multiplication: 'Matrix Mult',
  parallel_sort:         'Parallel Sort',
  image_processing:      'Image Proc',
  graph_bfs:             'Graph BFS',
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 shadow-xl">
      <p className="text-xs text-slate-400 mb-2">{label} workers</p>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-xs">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-slate-400">{WORKLOAD_LABELS[p.dataKey] ?? p.dataKey}:</span>
          <span className="font-mono text-slate-200">{p.value?.toFixed(1)}%</span>
        </div>
      ))}
    </div>
  )
}

export default function EfficiencyChart({ data }: Props) {
  const workloads = [...new Set(data.map((d) => d.workload_type))]
  const workerCounts = [...new Set(data.map((d) => d.worker_count))].sort((a, b) => a - b)

  const chartData = workerCounts.map((wc) => {
    const entry: Record<string, number | null> = { workers: wc }
    for (const w of workloads) {
      const point = data.find((d) => d.worker_count === wc && d.workload_type === w)
      entry[w] = point?.efficiency ?? null
    }
    return entry
  })

  if (data.length === 0) {
    return (
      <div className="card p-5 flex flex-col gap-2">
        <h3 className="text-slate-100 text-sm font-semibold">Parallel Efficiency</h3>
        <div className="h-[240px] flex items-center justify-center text-slate-600 text-xs">
          Run benchmarks to populate this chart.
        </div>
      </div>
    )
  }

  return (
    <div className="card p-5">
      <div className="mb-4">
        <h3 className="text-slate-100 text-sm font-semibold">Parallel Efficiency</h3>
        <p className="text-xs text-slate-500 mt-0.5">Efficiency = Speedup / Workers × 100%</p>
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <AreaChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <defs>
            {workloads.map((w) => (
              <linearGradient key={w} id={`grad-${w}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={WORKLOAD_COLORS[w] ?? '#94a3b8'} stopOpacity={0.3} />
                <stop offset="95%" stopColor={WORKLOAD_COLORS[w] ?? '#94a3b8'} stopOpacity={0.0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="workers" stroke="#334155" tickFormatter={(v) => `${v}P`} />
          <YAxis stroke="#334155" domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            formatter={(v) => WORKLOAD_LABELS[v] ?? v}
            wrapperStyle={{ fontSize: 11, color: '#94a3b8' }}
          />
          <ReferenceLine y={80} stroke="#10b981" strokeDasharray="4 3" strokeOpacity={0.4} label={{ value: '80%', fill: '#10b981', fontSize: 10, position: 'right' }} />
          {workloads.map((w) => (
            <Area
              key={w}
              type="monotone"
              dataKey={w}
              stroke={WORKLOAD_COLORS[w] ?? '#94a3b8'}
              fill={`url(#grad-${w})`}
              strokeWidth={2}
              dot={{ r: 3, fill: WORKLOAD_COLORS[w] ?? '#94a3b8' }}
              connectNulls={false}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
