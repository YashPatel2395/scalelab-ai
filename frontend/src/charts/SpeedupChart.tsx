import {
  LineChart,
  Line,
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
  maxWorkers?: number
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
          <span className="font-mono text-slate-200">{p.value?.toFixed(3)}×</span>
        </div>
      ))}
    </div>
  )
}

export default function SpeedupChart({ data, maxWorkers = 8 }: Props) {
  // Pivot: group by worker_count, collect speedup per workload
  const workloads = [...new Set(data.map((d) => d.workload_type))]
  const workerCounts = [...new Set(data.map((d) => d.worker_count))].sort((a, b) => a - b)

  const chartData = workerCounts.map((wc) => {
    const entry: Record<string, number | null> = { workers: wc }
    for (const w of workloads) {
      const point = data.find((d) => d.worker_count === wc && d.workload_type === w)
      entry[w] = point?.speedup ?? null
    }
    return entry
  })

  // Ideal (linear) speedup reference line data
  const idealData = workerCounts.map((wc) => ({ workers: wc, ideal: wc }))

  if (data.length === 0) {
    return (
      <EmptyChart title="Speedup vs Worker Count" subtitle="Run benchmarks to populate this chart." />
    )
  }

  return (
    <div className="card p-5">
      <div className="mb-4">
        <h3 className="text-slate-100 text-sm font-semibold">Speedup vs Worker Count</h3>
        <p className="text-xs text-slate-500 mt-0.5">Dashed line = ideal linear speedup</p>
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis
            dataKey="workers"
            stroke="#334155"
            tickFormatter={(v) => `${v}P`}
          />
          <YAxis stroke="#334155" tickFormatter={(v) => `${v}×`} />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            formatter={(v) => WORKLOAD_LABELS[v] ?? v}
            wrapperStyle={{ fontSize: 11, color: '#94a3b8' }}
          />
          {/* Ideal speedup */}
          {workerCounts.map((wc, i) =>
            i === 0 ? null : null  // rendered via separate data
          )}
          <Line
            data={idealData}
            dataKey="ideal"
            stroke="#334155"
            strokeDasharray="4 3"
            strokeWidth={1}
            dot={false}
            name="ideal"
            legendType="none"
          />
          {workloads.map((w) => (
            <Line
              key={w}
              dataKey={w}
              stroke={WORKLOAD_COLORS[w] ?? '#94a3b8'}
              strokeWidth={2}
              dot={{ r: 3, fill: WORKLOAD_COLORS[w] ?? '#94a3b8' }}
              activeDot={{ r: 5 }}
              connectNulls={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function EmptyChart({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="card p-5 flex flex-col gap-2">
      <h3 className="text-slate-100 text-sm font-semibold">{title}</h3>
      <div className="h-[240px] flex items-center justify-center text-slate-600 text-xs">
        {subtitle}
      </div>
    </div>
  )
}
