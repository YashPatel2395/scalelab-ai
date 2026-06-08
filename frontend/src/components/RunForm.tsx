import { useState, useEffect } from 'react'
import { Play, Loader2, ChevronDown, AlertTriangle } from 'lucide-react'
import { fetchWorkloads, submitBenchmark } from '../services/api'
import type { WorkloadMeta, BenchmarkRunCreate, WorkloadType } from '../types'

interface Props {
  onRunStarted: (runId: string) => void
}

export default function RunForm({ onRunStarted }: Props) {
  const [workloads, setWorkloads] = useState<WorkloadMeta[]>([])
  const [selectedWorkload, setSelectedWorkload] = useState<WorkloadType>('matrix_multiplication')
  const [inputSize, setInputSize] = useState<number>(512)
  const [workerCount, setWorkerCount] = useState<number>(4)
  const [iterations, setIterations] = useState<number>(1)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchWorkloads().then((wl) => {
      setWorkloads(wl)
      if (wl.length > 0) {
        setInputSize(wl[0].default_size)
      }
    })
  }, [])

  const currentWorkload = workloads.find((w) => w.id === selectedWorkload)

  const handleWorkloadChange = (id: WorkloadType) => {
    setSelectedWorkload(id)
    const meta = workloads.find((w) => w.id === id)
    if (meta) setInputSize(meta.default_size)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const payload: BenchmarkRunCreate = {
        workload_type: selectedWorkload,
        input_size: inputSize,
        worker_count: workerCount,
        iterations,
      }
      const run = await submitBenchmark(payload)
      onRunStarted(run.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  const maxWorkers = navigator.hardwareConcurrency || 8

  return (
    <div className="card p-6">
      <div className="mb-5">
        <h2 className="text-slate-100 font-semibold text-base">Run Benchmark</h2>
        <p className="text-slate-500 text-xs mt-0.5">Configure and dispatch a parallel workload</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Workload selector */}
        <div>
          <label className="label-text block mb-1.5">Workload Type</label>
          <div className="relative">
            <select
              className="select-field pr-8"
              value={selectedWorkload}
              onChange={(e) => handleWorkloadChange(e.target.value as WorkloadType)}
            >
              {workloads.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 pointer-events-none" />
          </div>
          {currentWorkload && (
            <p className="mt-1.5 text-xs text-slate-500">{currentWorkload.description}</p>
          )}
        </div>

        {/* Size + Workers (side by side) */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label-text block mb-1.5">
              {currentWorkload?.input_label ?? 'Input Size'}
            </label>
            <input
              type="number"
              className="input-field"
              value={inputSize}
              min={1}
              onChange={(e) => setInputSize(Number(e.target.value))}
            />
            {currentWorkload && (
              <div className="flex flex-wrap gap-1 mt-1.5">
                {currentWorkload.size_presets.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setInputSize(p)}
                    className={`px-2 py-0.5 rounded text-xs border transition-colors ${
                      inputSize === p
                        ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-400'
                        : 'bg-slate-800 border-slate-700 text-slate-500 hover:border-slate-600'
                    }`}
                  >
                    {p.toLocaleString()}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="label-text block mb-1.5">
              Workers <span className="text-slate-600">(max {maxWorkers})</span>
            </label>
            <input
              type="number"
              className="input-field"
              value={workerCount}
              min={1}
              max={maxWorkers}
              onChange={(e) => setWorkerCount(Number(e.target.value))}
            />
            <div className="flex flex-wrap gap-1 mt-1.5">
              {[1, 2, 4, 8].filter((w) => w <= maxWorkers).map((w) => (
                <button
                  key={w}
                  type="button"
                  onClick={() => setWorkerCount(w)}
                  className={`px-2 py-0.5 rounded text-xs border transition-colors ${
                    workerCount === w
                      ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-400'
                      : 'bg-slate-800 border-slate-700 text-slate-500 hover:border-slate-600'
                  }`}
                >
                  {w}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Iterations */}
        <div>
          <label className="label-text block mb-1.5">Iterations (best-of)</label>
          <input
            type="number"
            className="input-field"
            value={iterations}
            min={1}
            max={10}
            onChange={(e) => setIterations(Number(e.target.value))}
          />
          <p className="text-xs text-slate-600 mt-1">Reports the minimum time across N iterations for stable results.</p>
        </div>

        {/* Input size warning */}
        {currentWorkload?.min_recommended_size !== undefined &&
          inputSize < currentWorkload.min_recommended_size && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-950/40 border border-amber-700/40">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0" />
            <p className="text-amber-400 text-xs">
              {currentWorkload.size_warning ||
                `Input too small for reliable scaling. Recommended minimum: ${currentWorkload.min_recommended_size.toLocaleString()}.`}
            </p>
          </div>
        )}

        {/* Complexity note */}
        {currentWorkload && (
          <div className="px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700">
            <span className="label-text">Complexity: </span>
            <span className="text-xs text-slate-400 font-mono">{currentWorkload.complexity}</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="px-3 py-2 rounded-lg bg-red-950 border border-red-800 text-red-400 text-xs">
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={submitting || workloads.length === 0}
          className="btn-primary w-full justify-center"
        >
          {submitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Submitting…
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              Run Benchmark
            </>
          )}
        </button>
      </form>
    </div>
  )
}
