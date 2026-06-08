import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ZAxis,
  Legend,
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

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 shadow-xl">
      <p className="text-xs text-slate-300 font-medium mb-1">{WORKLOAD_LABELS[d.workload_type] ?? d.workload_type}</p>
      <p className="text-xs text-slate-400">Workers: <span className="font-mono text-slate-200">{d.worker_count}</span></p>
      <p className="text-xs text-slate-400">CPU: <span className="font-mono text-amber-400">{d.cpu_usage?.toFixed(1)}%</span></p>
      <p className="text-xs text-slate-400">Memory: <span className="font-mono text-purple-400">{d.memory_usage?.toFixed(1)}%</span></p>
    </div>
  )
}

export default function ResourceChart({ data }: Props) {
  const workloads = [...new Set(data.map((d) => d.workload_type))]

  if (data.length === 0) {
    return (
      <div className="card p-5 flex flex-col gap-2">
        <h3 className="text-slate-100 text-sm font-semibold">Resource Utilization</h3>
        <div className="h-[240px] flex items-center justify-center text-slate-600 text-xs">
          Run benchmarks to populate this chart.
        </div>
      </div>
    )
  }

  return (
    <div className="card p-5">
      <div className="mb-4">
        <h3 className="text-slate-100 text-sm font-semibold">Resource Utilization</h3>
        <p className="text-xs text-slate-500 mt-0.5">CPU % vs Memory % – bubble size = worker count</p>
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <ScatterChart margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis
            dataKey="cpu_usage"
            name="CPU"
            stroke="#334155"
            type="number"
            domain={[0, 100]}
            tickFormatter={(v) => `${v}%`}
            label={{ value: 'CPU %', fill: '#64748b', fontSize: 10, position: 'insideBottom', offset: -4 }}
          />
          <YAxis
            dataKey="memory_usage"
            name="Memory"
            stroke="#334155"
            type="number"
            domain={[0, 100]}
            tickFormatter={(v) => `${v}%`}
          />
          <ZAxis dataKey="worker_count" range={[40, 200]} name="Workers" />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            formatter={(v) => WORKLOAD_LABELS[v] ?? v}
            wrapperStyle={{ fontSize: 11, color: '#94a3b8' }}
          />
          {workloads.map((w) => (
            <Scatter
              key={w}
              name={w}
              data={data.filter((d) => d.workload_type === w)}
              fill={WORKLOAD_COLORS[w] ?? '#94a3b8'}
              fillOpacity={0.8}
            />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}
