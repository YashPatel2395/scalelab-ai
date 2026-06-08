/**
 * Custom Workloads page
 *
 * Allows users to upload their own Python workload files, view validation
 * results, run benchmarks, and see timing + speedup output.
 *
 * Security notice shown prominently in the UI:
 * - Code runs as the server process user
 * - Not a full sandbox — AST validation only
 * - Local development use only
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Upload, Play, Trash2, CheckCircle, XCircle, AlertTriangle,
  ChevronDown, ChevronUp, Loader2, FileCode, BarChart3, Terminal,
  Shield, RefreshCw, ExternalLink,
} from 'lucide-react'
import Header from '../components/Header'
import {
  uploadCustomWorkload,
  fetchCustomWorkloads,
  runCustomWorkload,
  deleteCustomWorkload,
  fetchBenchmark,
} from '../services/api'
import type { CustomWorkload, BenchmarkRun } from '../types'

// ── Example workload snippet shown in the upload panel ───────────────────────

const EXAMPLE_CODE = `# example_workload.py
# ScaleLab custom workload — run() is called by the benchmarking harness.
# Must be a regular (non-async) function returning a dict.

import multiprocessing
import time

def _worker(chunk):
    """Simulate CPU work on a chunk of data."""
    return sum(x * x for x in chunk)

def run(input_size: int, worker_count: int) -> dict:
    """
    Parallel sum-of-squares using multiprocessing.

    ScaleLab calls this function directly and times it.
    For speedup measurement it also calls run(input_size, 1) as baseline.
    """
    data = list(range(input_size))
    chunk_size = max(1, len(data) // worker_count)
    chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

    with multiprocessing.Pool(processes=worker_count) as pool:
        results = pool.map(_worker, chunks)

    return {
        "total": sum(results),
        "chunks_processed": len(results),
    }
`

// ── Helpers ──────────────────────────────────────────────────────────────────

function ValidationBadge({ status }: { status: string }) {
  if (status === 'passed') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
        <CheckCircle className="w-3 h-3" /> Passed
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-red-500/10 border border-red-500/30 text-red-400">
        <XCircle className="w-3 h-3" /> Failed
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-400">
      Pending
    </span>
  )
}

function SpeedupBadge({ speedup }: { speedup: number | null }) {
  if (speedup === null) return null
  const color =
    speedup >= 3 ? 'text-emerald-400' :
    speedup >= 1.5 ? 'text-cyan-400' :
    speedup >= 1 ? 'text-amber-400' :
    'text-red-400'
  return <span className={`font-mono font-semibold ${color}`}>{speedup.toFixed(2)}×</span>
}

// ── Upload panel ─────────────────────────────────────────────────────────────

function UploadPanel({ onUploaded }: { onUploaded: (w: CustomWorkload) => void }) {
  const [name, setName] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showExample, setShowExample] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file || !name.trim()) return
    setError(null)
    setUploading(true)
    try {
      const result = await uploadCustomWorkload(name.trim(), file)
      onUploaded(result)
      setName('')
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="card p-6 space-y-5">
      {/* Security notice */}
      <div className="flex items-start gap-3 px-4 py-3 rounded-lg bg-amber-950/40 border border-amber-700/40">
        <Shield className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
        <div>
          <p className="text-amber-300 text-xs font-medium">Local development only</p>
          <p className="text-amber-500/80 text-xs mt-0.5">
            Custom workloads run as the server process user. AST validation blocks common
            dangerous patterns but is <strong>not a full sandbox</strong>. Only upload code
            you wrote or trust. Do not use in production or multi-user environments.
          </p>
        </div>
      </div>

      <div>
        <h2 className="text-slate-100 font-semibold text-base">Upload Workload</h2>
        <p className="text-slate-500 text-xs mt-0.5">
          Python file must expose{' '}
          <code className="text-cyan-400 font-mono text-xs">def run(input_size, worker_count)</code>
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="label-text block mb-1.5">Workload Name</label>
          <input
            className="input-field"
            placeholder="e.g. fraud_detection_pipeline"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>

        <div>
          <label className="label-text block mb-1.5">Python File</label>
          <div
            className="border-2 border-dashed border-slate-700 rounded-lg px-4 py-6 text-center cursor-pointer hover:border-cyan-600 transition-colors"
            onClick={() => fileRef.current?.click()}
          >
            {file ? (
              <div className="flex items-center justify-center gap-2 text-slate-300">
                <FileCode className="w-4 h-4 text-cyan-400" />
                <span className="text-sm">{file.name}</span>
                <span className="text-xs text-slate-500">({(file.size / 1024).toFixed(1)} KB)</span>
              </div>
            ) : (
              <div className="text-slate-500 text-sm">
                <Upload className="w-5 h-5 mx-auto mb-1 text-slate-600" />
                Click to select a .py file
              </div>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".py"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {error && (
          <div className="px-3 py-2 rounded-lg bg-red-950 border border-red-800 text-red-400 text-xs whitespace-pre-wrap">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={uploading || !file || !name.trim()}
          className="btn-primary w-full justify-center"
        >
          {uploading ? (
            <><Loader2 className="w-4 h-4 animate-spin" /> Validating &amp; uploading…</>
          ) : (
            <><Upload className="w-4 h-4" /> Upload &amp; Validate</>
          )}
        </button>
      </form>

      {/* Example */}
      <div>
        <button
          onClick={() => setShowExample((p) => !p)}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          {showExample ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          Show example workload file
        </button>
        {showExample && (
          <pre className="mt-2 p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-400 overflow-auto max-h-80 font-mono leading-relaxed">
            {EXAMPLE_CODE}
          </pre>
        )}
      </div>
    </div>
  )
}

// ── Run panel ────────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 1500

function RunPanel({
  workload,
  onClose,
}: {
  workload: CustomWorkload
  onClose: () => void
}) {
  const navigate = useNavigate()
  const [inputSize, setInputSize] = useState(10000)
  const [workerCount, setWorkerCount] = useState(4)
  const [iterations, setIterations] = useState(1)
  const [timeout, setTimeout_] = useState(60)
  const [enableProfiling, setEnableProfiling] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [polling, setPolling] = useState(false)
  const [run, setRun] = useState<BenchmarkRun | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showStdout, setShowStdout] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    setPolling(false)
  }, [])

  useEffect(() => () => stopPolling(), [stopPolling])

  const handleRun = async () => {
    setError(null)
    setRun(null)
    setShowStdout(false)
    setSubmitting(true)
    stopPolling()
    try {
      const runPayload = {
        input_size: inputSize,
        worker_count: workerCount,
        iterations,
        timeout_seconds: timeout,
        enable_profiling: enableProfiling,
      }
      console.log('[PROFILING_DEBUG] RunPanel payload:', JSON.stringify(runPayload))
      const pendingRun = await runCustomWorkload(workload.id, runPayload)
      console.log('[PROFILING_DEBUG] RunPanel response run_id=%s status=%s', pendingRun.id, pendingRun.status)
      setRun(pendingRun)
      setPolling(true)

      pollRef.current = setInterval(async () => {
        try {
          const updated = await fetchBenchmark(pendingRun.id)
          setRun(updated)
          if (updated.status === 'completed' || updated.status === 'failed') {
            console.log('[PROFILING_DEBUG] RunPanel poll final: run_id=%s status=%s profiling_data=%s',
              updated.id, updated.status, updated.profiling_data != null ? 'present' : 'null')
            stopPolling()
          }
        } catch (pollErr) {
          stopPolling()
          setError(pollErr instanceof Error ? `Poll failed: ${pollErr.message}` : 'Lost contact with benchmark run')
        }
      }, POLL_INTERVAL_MS)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Run failed')
    } finally {
      setSubmitting(false)
    }
  }

  const isRunning = submitting || polling
  const completed = run?.status === 'completed'
  const failed = run?.status === 'failed'

  // Custom workload stores stdout/return_value in observability_data
  const obs = run?.observability_data as Record<string, unknown> | null | undefined
  const stdout = obs?.stdout as string | null | undefined
  const returnValue = obs?.return_value

  return (
    <div className="card p-6 space-y-5">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-slate-100 font-semibold">{workload.name}</h3>
          <p className="text-slate-500 text-xs font-mono mt-0.5">{workload.filename}</p>
        </div>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-xs">
          ✕ close
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label-text block mb-1">Input Size</label>
          <input
            type="number"
            className="input-field"
            value={inputSize}
            min={1}
            onChange={(e) => setInputSize(Number(e.target.value))}
          />
        </div>
        <div>
          <label className="label-text block mb-1">Workers</label>
          <input
            type="number"
            className="input-field"
            value={workerCount}
            min={1}
            max={32}
            onChange={(e) => setWorkerCount(Number(e.target.value))}
          />
          <div className="flex gap-1 mt-1">
            {[1, 2, 4, 8].map((w) => (
              <button
                key={w}
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
        <div>
          <label className="label-text block mb-1">Iterations</label>
          <input
            type="number"
            className="input-field"
            value={iterations}
            min={1}
            max={10}
            onChange={(e) => setIterations(Number(e.target.value))}
          />
        </div>
        <div>
          <label className="label-text block mb-1">Timeout (s)</label>
          <input
            type="number"
            className="input-field"
            value={timeout}
            min={5}
            max={300}
            onChange={(e) => setTimeout_(Number(e.target.value))}
          />
        </div>
      </div>

      {/* Enable Profiling */}
      <label className="flex items-center gap-2.5 cursor-pointer select-none group">
        <input
          type="checkbox"
          checked={enableProfiling}
          onChange={(e) => setEnableProfiling(e.target.checked)}
          className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-cyan-500 accent-cyan-500 cursor-pointer"
        />
        <div>
          <span className="text-sm text-slate-300 group-hover:text-slate-100 transition-colors">
            Enable Profiling
          </span>
          <p className="text-xs text-slate-600 mt-0.5">
            Captures cProfile hotspots during the parallel run. View in the Profiling tab after the run.
          </p>
        </div>
      </label>

      <button
        onClick={handleRun}
        disabled={isRunning}
        className="btn-primary w-full justify-center"
      >
        {isRunning ? (
          <><Loader2 className="w-4 h-4 animate-spin" /> {submitting ? 'Submitting…' : 'Running…'}</>
        ) : (
          <><Play className="w-4 h-4" /> Run Benchmark</>
        )}
      </button>

      {polling && run && (
        <p className="text-xs text-slate-500 text-center">
          Executing in subprocess… status: <span className="text-cyan-400">{run.status}</span>
        </p>
      )}

      {error && (
        <div className="px-3 py-2 rounded-lg bg-red-950 border border-red-800 text-red-400 text-xs">
          {error}
        </div>
      )}

      {run && (completed || failed) && (
        <div className="space-y-3">
          {/* Result header + link */}
          <div className={`flex items-center justify-between px-3 py-2 rounded-lg border ${
            completed
              ? 'bg-emerald-950/30 border-emerald-700/30'
              : 'bg-red-950/30 border-red-700/30'
          }`}>
            <div className="flex items-center gap-2">
              {completed
                ? <CheckCircle className="w-4 h-4 text-emerald-400" />
                : <XCircle className="w-4 h-4 text-red-400" />
              }
              <span className={`text-sm font-medium ${completed ? 'text-emerald-300' : 'text-red-300'}`}>
                {completed ? 'Completed successfully' : 'Run failed'}
              </span>
            </div>
            <button
              onClick={() => navigate(`/benchmark/${run.id}`)}
              className="flex items-center gap-1 text-xs text-slate-400 hover:text-cyan-400 transition-colors"
              title="View full benchmark details"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              View details
            </button>
          </div>

          {/* Metrics */}
          {completed && (
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-slate-800/60 rounded-lg p-3">
                <p className="text-slate-500 text-xs mb-1">Sequential time</p>
                <p className="text-slate-100 font-mono text-sm">
                  {run.sequential_time?.toFixed(4)}s
                </p>
              </div>
              <div className="bg-slate-800/60 rounded-lg p-3">
                <p className="text-slate-500 text-xs mb-1">Parallel time ({run.worker_count}w)</p>
                <p className="text-slate-100 font-mono text-sm">
                  {run.execution_time?.toFixed(4)}s
                </p>
              </div>
              <div className="bg-slate-800/60 rounded-lg p-3">
                <p className="text-slate-500 text-xs mb-1">Speedup</p>
                <p className="text-lg font-bold">
                  <SpeedupBadge speedup={run.speedup} />
                </p>
              </div>
              <div className="bg-slate-800/60 rounded-lg p-3">
                <p className="text-slate-500 text-xs mb-1">Efficiency</p>
                <p className={`font-mono text-sm font-semibold ${
                  (run.efficiency ?? 0) >= 80 ? 'text-emerald-400' :
                  (run.efficiency ?? 0) >= 50 ? 'text-amber-400' :
                  'text-red-400'
                }`}>
                  {run.efficiency?.toFixed(1)}%
                </p>
              </div>
            </div>
          )}

          {/* Error detail */}
          {failed && run.error_message && (
            <div className="px-3 py-2 rounded-lg bg-red-950 border border-red-800">
              <p className="text-red-400 text-xs font-mono whitespace-pre-wrap">{run.error_message}</p>
            </div>
          )}

          {/* Return value */}
          {completed && returnValue !== null && returnValue !== undefined && (
            <div>
              <p className="label-text mb-1">Return value</p>
              <pre className="p-2 rounded bg-slate-950 border border-slate-800 text-xs text-slate-400 font-mono overflow-auto max-h-32">
                {JSON.stringify(returnValue, null, 2)}
              </pre>
            </div>
          )}

          {/* Stdout */}
          {stdout && (
            <div>
              <button
                onClick={() => setShowStdout((p) => !p)}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                <Terminal className="w-3.5 h-3.5" />
                {showStdout ? 'Hide' : 'Show'} captured stdout
                {showStdout ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
              {showStdout && (
                <pre className="mt-1 p-2 rounded bg-slate-950 border border-slate-800 text-xs text-slate-400 font-mono overflow-auto max-h-40">
                  {stdout || '(empty)'}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Workload list item ────────────────────────────────────────────────────────

function WorkloadRow({
  workload,
  onSelect,
  onDelete,
  selected,
}: {
  workload: CustomWorkload
  onSelect: () => void
  onDelete: () => void
  selected: boolean
}) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [showErrors, setShowErrors] = useState(false)

  return (
    <div
      className={`rounded-lg border transition-colors ${
        selected
          ? 'bg-cyan-950/30 border-cyan-700/40'
          : 'bg-slate-900 border-slate-800 hover:border-slate-700'
      }`}
    >
      <div className="flex items-center gap-3 p-4">
        <FileCode className="w-4 h-4 text-slate-500 shrink-0" />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-slate-200 text-sm font-medium truncate">{workload.name}</span>
            <ValidationBadge status={workload.validation_status} />
          </div>
          <p className="text-slate-600 text-xs font-mono mt-0.5 truncate">{workload.filename}</p>

          {workload.validation_warnings && workload.validation_warnings.length > 0 && (
            <div className="flex items-center gap-1 mt-1 text-amber-500 text-xs">
              <AlertTriangle className="w-3 h-3" />
              {workload.validation_warnings.length} warning(s)
            </div>
          )}

          {workload.validation_errors && workload.validation_errors.length > 0 && (
            <div>
              <button
                onClick={() => setShowErrors((p) => !p)}
                className="flex items-center gap-1 mt-1 text-red-400 text-xs hover:text-red-300"
              >
                <XCircle className="w-3 h-3" />
                {workload.validation_errors.length} error(s) — click to show
              </button>
              {showErrors && (
                <ul className="mt-1 space-y-1">
                  {workload.validation_errors.map((e, i) => (
                    <li key={i} className="text-red-400 text-xs font-mono bg-red-950/40 px-2 py-1 rounded">
                      {e}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {workload.validation_status === 'passed' && (
            <button
              onClick={onSelect}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                selected
                  ? 'bg-cyan-600 text-white'
                  : 'bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/20'
              }`}
            >
              <BarChart3 className="w-3.5 h-3.5" />
              {selected ? 'Selected' : 'Run'}
            </button>
          )}
          {confirmDelete ? (
            <div className="flex items-center gap-1.5">
              <button
                onClick={onDelete}
                className="px-2 py-1 rounded text-xs bg-red-900 border border-red-700 text-red-300 hover:bg-red-800 transition-colors"
              >
                Confirm
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="px-2 py-1 rounded text-xs text-slate-500 hover:text-slate-300"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="p-1.5 rounded text-slate-600 hover:text-red-400 hover:bg-red-950/30 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CustomWorkloads() {
  const [workloads, setWorkloads] = useState<CustomWorkload[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    setLoading(true)
    fetchCustomWorkloads()
      .then(setWorkloads)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [refreshKey])

  const handleUploaded = (w: CustomWorkload) => {
    setWorkloads((prev) => [w, ...prev])
    if (w.validation_status === 'passed') {
      setSelectedId(w.id)
    }
  }

  const handleDelete = async (id: string) => {
    await deleteCustomWorkload(id)
    setWorkloads((prev) => prev.filter((w) => w.id !== id))
    if (selectedId === id) setSelectedId(null)
  }

  const selectedWorkload = workloads.find((w) => w.id === selectedId) ?? null

  return (
    <div className="min-h-screen bg-slate-950">
      <Header />
      <div className="max-w-screen-2xl mx-auto px-6 py-8">
        {/* Page header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-1">
            <FileCode className="w-5 h-5 text-cyan-400" />
            <h1 className="text-slate-100 font-bold text-xl">Custom Workloads</h1>
          </div>
          <p className="text-slate-400 text-sm max-w-2xl">
            Benchmark your own Python code. Upload a file that exposes{' '}
            <code className="text-cyan-400 font-mono text-xs">run(input_size, worker_count)</code>,
            and ScaleLab will time it, compute speedup, and show efficiency — exactly like built-in workloads.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left column: upload + workload list */}
          <div className="space-y-6">
            <UploadPanel onUploaded={handleUploaded} />

            {/* Workload list */}
            <div className="card p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-slate-100 font-semibold text-base">
                  Uploaded Workloads
                  {workloads.length > 0 && (
                    <span className="ml-2 px-1.5 py-0.5 rounded bg-slate-700 text-slate-400 text-xs font-normal">
                      {workloads.length}
                    </span>
                  )}
                </h2>
                <button
                  onClick={() => setRefreshKey((k) => k + 1)}
                  className="p-1.5 rounded text-slate-600 hover:text-slate-300 transition-colors"
                  title="Refresh"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-5 h-5 animate-spin text-slate-600" />
                </div>
              ) : workloads.length === 0 ? (
                <div className="text-center py-10">
                  <FileCode className="w-10 h-10 mx-auto text-slate-700 mb-3" />
                  <p className="text-slate-500 text-sm">No workloads uploaded yet.</p>
                  <p className="text-slate-600 text-xs mt-1">
                    Upload a Python file above to get started.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {workloads.map((w) => (
                    <WorkloadRow
                      key={w.id}
                      workload={w}
                      selected={w.id === selectedId}
                      onSelect={() => setSelectedId(w.id === selectedId ? null : w.id)}
                      onDelete={() => handleDelete(w.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right column: run panel */}
          <div>
            {selectedWorkload ? (
              <RunPanel workload={selectedWorkload} onClose={() => setSelectedId(null)} />
            ) : (
              <div className="card p-8 flex flex-col items-center justify-center text-center h-full min-h-64">
                <BarChart3 className="w-10 h-10 text-slate-700 mb-3" />
                <p className="text-slate-400 text-sm font-medium">No workload selected</p>
                <p className="text-slate-600 text-xs mt-1 max-w-xs">
                  Upload a workload and click <strong className="text-slate-500">Run</strong> to benchmark it.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* What this can and cannot do */}
        <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card p-5">
            <h3 className="text-emerald-400 font-semibold text-sm mb-3 flex items-center gap-2">
              <CheckCircle className="w-4 h-4" /> What ScaleLab can benchmark
            </h3>
            <ul className="space-y-1.5 text-slate-400 text-xs">
              <li>• Python functions following <code className="text-cyan-400 font-mono">run(input_size, worker_count)</code></li>
              <li>• Any pure Python parallelism: multiprocessing, concurrent.futures, numpy, etc.</li>
              <li>• Execution time, speedup, efficiency, and return value</li>
              <li>• Code that completes within the configured timeout</li>
            </ul>
          </div>
          <div className="card p-5">
            <h3 className="text-red-400 font-semibold text-sm mb-3 flex items-center gap-2">
              <XCircle className="w-4 h-4" /> What it cannot fully benchmark
            </h3>
            <ul className="space-y-1.5 text-slate-400 text-xs">
              <li>• Arbitrary production services or closed-source systems</li>
              <li>• Code that requires private infrastructure or databases</li>
              <li>• Distributed microservices or network-dependent workloads</li>
              <li>• Untrusted code — no full Docker/gVisor sandbox yet</li>
              <li>• GPU workloads (CPU benchmarking only)</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
