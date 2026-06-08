import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Activity, Cpu, FlaskConical, FileCode, BarChart3 } from 'lucide-react'
import { fetchHealth } from '../services/api'

export default function Header() {
  const [health, setHealth] = useState<{ status: string; ai_provider: string } | null>(null)
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null)
  const location = useLocation()

  useEffect(() => {
    fetchHealth()
      .then((h) => {
        setHealth(h)
        setBackendOnline(h.status === 'ok')
      })
      .catch(() => setBackendOnline(false))
  }, [])

  return (
    <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-screen-2xl mx-auto px-6 h-14 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-3">
          {/* ScaleLab logo: two stacked rectangles + scale-up arrow */}
          <svg viewBox="0 0 512 512" className="w-8 h-8 drop-shadow-md" aria-hidden="true">
            {/* Small rect — bottom-left — cyan */}
            <path fill="#22d3ee" d="M225 512H15c-8.285 0-15-6.715-15-15V287c0-8.285 6.715-15 15-15h210c8.285 0 15 6.715 15 15v210c0 8.285-6.715 15-15 15z"/>
            <path fill="#0891b2" d="M4.395 507.605A14.953 14.953 0 0 0 15 512h210c8.285 0 15-6.715 15-15V287c0-4.133-1.672-7.875-4.375-10.586z"/>
            {/* Large rect — top-right — blue */}
            <path fill="#3b82f6" d="M497 420H107c-8.285 0-15-6.715-15-15V15c0-8.285 6.715-15 15-15h390c8.285 0 15 6.715 15 15v390c0 8.285-6.715 15-15 15z"/>
            <path fill="#1d4ed8" d="M96.402 415.613A14.951 14.951 0 0 0 107 420h390c8.285 0 15-6.715 15-15V15c0-4.121-1.664-7.852-4.355-10.563z"/>
            {/* Scale-up arrow — white */}
            <path fill="#ffffff" d="M422.773 73.02h-65.847c-8.285 0-15 6.714-15 15 0 8.285 6.715 15 15 15h30.34L261.145 229.145c-5.86 5.855-5.86 15.355 0 21.21 2.93 2.93 6.765 4.395 10.605 4.395s7.68-1.465 10.605-4.395l125.418-125.414v28.84c0 8.285 6.715 15 15 15 8.286 0 15-6.715 15-15V88.02c0-8.286-6.714-15-15-15z"/>
            <path fill="#bfdbfe" d="M261.43 250.613a14.937 14.937 0 0 0 10.32 4.137c3.84 0 7.68-1.465 10.605-4.395l125.418-125.417v28.843c0 8.281 6.715 15 15 15 8.286 0 15-6.719 15-15V88.02c0-3.817-1.437-7.29-3.785-9.938z"/>
          </svg>
          <div>
            <span className="text-slate-100 font-semibold tracking-tight">ScaleLab</span>
            <span className="text-cyan-400 font-semibold tracking-tight"> AI</span>
          </div>
          <span className="hidden sm:block text-slate-600 text-xs ml-2 border-l border-slate-700 pl-3 uppercase tracking-widest">
            Performance Intelligence
          </span>
        </div>

        {/* Nav links */}
        <nav className="hidden md:flex items-center gap-1 ml-6">
          <Link
            to="/"
            className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              location.pathname === '/'
                ? 'text-cyan-400 bg-cyan-500/10'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Dashboard
          </Link>
          <Link
            to="/research"
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              location.pathname === '/research'
                ? 'text-purple-400 bg-purple-500/10'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <FlaskConical className="w-3.5 h-3.5" />
            Research Mode
          </Link>
          <Link
            to="/custom-workloads"
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              location.pathname === '/custom-workloads'
                ? 'text-cyan-400 bg-cyan-500/10'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <FileCode className="w-3.5 h-3.5" />
            Custom Workloads
          </Link>
          <Link
            to="/benchmark-packs"
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              location.pathname === '/benchmark-packs'
                ? 'text-cyan-400 bg-cyan-500/10'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" />
            Benchmark Packs
          </Link>
        </nav>

        {/* Status indicators */}
        <div className="flex items-center gap-4">
          {/* Backend status */}
          <div className="flex items-center gap-2 text-xs">
            <div
              className={`w-1.5 h-1.5 rounded-full ${
                backendOnline === null
                  ? 'bg-slate-500'
                  : backendOnline
                  ? 'bg-emerald-400 animate-pulse'
                  : 'bg-red-400'
              }`}
            />
            <span className="text-slate-500 hidden sm:block">
              {backendOnline === null ? 'Connecting…' : backendOnline ? 'Backend online' : 'Backend offline'}
            </span>
          </div>

          {/* AI Provider pill */}
          {health && (
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-800 border border-slate-700">
              <Cpu className="w-3 h-3 text-purple-400" />
              <span className="text-xs text-slate-400 font-mono">
                AI: {health.ai_provider}
              </span>
            </div>
          )}

          {/* Live indicator */}
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <Activity className="w-3.5 h-3.5 text-cyan-500" />
            <span className="hidden sm:block">Live</span>
          </div>
        </div>
      </div>
    </header>
  )
}
