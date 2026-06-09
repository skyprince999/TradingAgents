import { useState, useEffect } from 'react'
import type { TickerResult, Job } from './types'
import { useJobPoller } from './hooks/useJobPoller'
import AnalyzeForm from './components/AnalyzeForm'
import ReportViewer from './components/ReportViewer'

// ── App state machine ────────────────────────────────────────────────────
type Phase =
  | { tag: 'form' }
  | { tag: 'analyzing'; jobId: string; ticker: TickerResult; tradeDate: string; startedAt: number }
  | { tag: 'complete';  jobId: string; ticker: TickerResult; tradeDate: string; job: Job }
  | { tag: 'error';     message: string }

// ── Elapsed timer (updates every second while analyzing) ──────────────────
function useElapsed(startedAt: number | null): string {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (startedAt === null) return
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000)
    return () => clearInterval(id)
  }, [startedAt])
  const m = Math.floor(elapsed / 60)
  const s = elapsed % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function AnalyzingScreen({ ticker, tradeDate, elapsed }: {
  ticker: TickerResult; tradeDate: string; elapsed: string
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 space-y-6 text-center">
      {/* Spinner */}
      <div className="relative w-20 h-20">
        <div className="absolute inset-0 rounded-full border-4 border-slate-700"/>
        <div className="absolute inset-0 rounded-full border-4 border-t-blue-500 animate-spin"/>
      </div>

      <div>
        <div className="text-xl font-semibold text-slate-100">
          Analysing{' '}
          <span className="font-mono text-blue-400">{ticker.symbol}</span>
        </div>
        <div className="text-sm text-slate-500 mt-1">{tradeDate}</div>
      </div>

      <div className="text-4xl font-mono font-bold text-slate-300 tabular-nums">
        {elapsed}
      </div>

      <div className="max-w-xs text-sm text-slate-600 leading-relaxed">
        Running the full multi-agent pipeline — analysts, researcher debate,
        trader, and risk management. This typically takes 3–10 minutes.
      </div>

      {/* Animated pipeline stages */}
      <div className="flex items-center gap-2 text-xs text-slate-600">
        {['Analysts', 'Researchers', 'Trader', 'Risk Mgmt', 'Portfolio'].map((stage, i) => (
          <span key={stage} className="flex items-center gap-2">
            <span className="px-2 py-1 rounded bg-slate-800 border border-slate-700 animate-pulse"
              style={{ animationDelay: `${i * 300}ms` }}>
              {stage}
            </span>
            {i < 4 && <span className="text-slate-700">→</span>}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function App() {
  const [phase, setPhase] = useState<Phase>({ tag: 'form' })

  const jobId = phase.tag === 'analyzing' || phase.tag === 'complete' ? phase.jobId : null

  const elapsed = useElapsed(
    phase.tag === 'analyzing' ? phase.startedAt : null
  )

  useJobPoller(
    phase.tag === 'analyzing' ? jobId : null,
    job => {
      if (phase.tag === 'analyzing') {
        setPhase({ tag: 'complete', jobId: phase.jobId, ticker: phase.ticker, tradeDate: phase.tradeDate, job })
      }
    },
    message => {
      setPhase({ tag: 'error', message })
    },
  )

  function handleJobStart(jId: string, ticker: TickerResult, tradeDate: string) {
    setPhase({ tag: 'analyzing', jobId: jId, ticker, tradeDate, startedAt: Date.now() })
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col" style={{ fontFamily: 'Inter, sans-serif' }}>
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="border-b border-slate-800/60 px-6 py-4">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-sm">
              TA
            </div>
            <span className="font-semibold text-slate-100">TradingAgents</span>
          </div>
          <span className="text-xs text-slate-600">Multi-Agent AI Market Analysis</span>
        </div>
      </header>

      {/* ── Main ───────────────────────────────────────────────────────── */}
      <main className="flex-1 flex items-start justify-center px-4 py-10">
        <div className="w-full max-w-2xl space-y-6">

          {phase.tag === 'form' && (
            <>
              <div className="text-center space-y-2 mb-8">
                <h1 className="text-3xl font-bold text-slate-100">
                  What would you like to analyse?
                </h1>
                <p className="text-slate-500">
                  Search any equity, ETF, crypto, or index from Yahoo Finance's full universe.
                </p>
              </div>

              <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 shadow-xl">
                <AnalyzeForm onJobStart={handleJobStart} />
              </div>
            </>
          )}

          {phase.tag === 'analyzing' && (
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 shadow-xl">
              <AnalyzingScreen
                ticker={phase.ticker}
                tradeDate={phase.tradeDate}
                elapsed={elapsed}
              />
            </div>
          )}

          {phase.tag === 'error' && (
            <div className="bg-slate-900/60 border border-red-800/50 rounded-2xl p-6 shadow-xl space-y-4">
              <div className="text-red-400 font-semibold">Analysis failed</div>
              <div className="text-sm text-slate-400 font-mono break-all">{phase.message}</div>
              <button
                onClick={() => setPhase({ tag: 'form' })}
                className="px-4 py-2 rounded-xl bg-slate-800 border border-slate-700
                  text-slate-300 hover:text-white text-sm transition-colors"
              >
                ← Try again
              </button>
            </div>
          )}

          {phase.tag === 'complete' && (
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 shadow-xl">
              <ReportViewer
                ticker={phase.ticker.symbol}
                tradeDate={phase.tradeDate}
                job={phase.job}
                onReset={() => setPhase({ tag: 'form' })}
              />
            </div>
          )}

        </div>
      </main>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <footer className="border-t border-slate-800/60 py-4 text-center text-xs text-slate-700">
        For research purposes only — not financial advice.
      </footer>
    </div>
  )
}
