import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Job, ReportKey } from '../types'
import { REPORT_TABS } from '../types'

// ── Signal badge ──────────────────────────────────────────────────────────
function parseSignal(signal: string | null): { label: string; cls: string } {
  const upper = (signal ?? '').toUpperCase()
  if (upper.includes('BUY'))  return { label: 'BUY',  cls: 'bg-green-500/20 text-green-400 border-green-500/50 ring-green-500/30' }
  if (upper.includes('SELL')) return { label: 'SELL', cls: 'bg-red-500/20   text-red-400   border-red-500/50   ring-red-500/30' }
  if (upper.includes('HOLD')) return { label: 'HOLD', cls: 'bg-amber-500/20 text-amber-400 border-amber-500/50 ring-amber-500/30' }
  return { label: signal ?? '—', cls: 'bg-slate-700 text-slate-300 border-slate-600' }
}

interface Props {
  ticker:    string
  tradeDate: string
  job:       Job
  onReset:   () => void
}

export default function ReportViewer({ ticker, tradeDate, job, onReset }: Props) {
  const [activeTab, setActiveTab] = useState<ReportKey>('final_trade_decision')
  const sig = parseSignal(job.signal)
  const reports = job.reports ?? {}

  return (
    <div className="space-y-6">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div>
            <div className="flex items-center gap-3">
              <span className="font-mono text-2xl font-bold text-slate-100">{ticker}</span>
              <span
                className={`
                  px-3 py-1 rounded-lg border text-sm font-bold tracking-wider
                  ring-2 ${sig.cls}
                `}
              >
                {sig.label}
              </span>
            </div>
            <div className="text-sm text-slate-500 mt-1">{tradeDate}</div>
          </div>
        </div>
        <button
          onClick={onReset}
          className="
            px-4 py-2 rounded-xl text-sm font-medium
            bg-slate-800 border border-slate-700 text-slate-400
            hover:text-slate-200 hover:border-slate-600 transition-all
          "
        >
          ← New Analysis
        </button>
      </div>

      {/* ── Tab bar ────────────────────────────────────────────────────── */}
      <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-none">
        {REPORT_TABS.map(tab => {
          const hasContent = Boolean(reports[tab.key])
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              disabled={!hasContent}
              className={`
                flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium
                whitespace-nowrap transition-all duration-150
                ${activeTab === tab.key
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-500/40'
                  : hasContent
                    ? 'text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-transparent'
                    : 'text-slate-700 cursor-not-allowed border border-transparent'}
              `}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          )
        })}
      </div>

      {/* ── Content ────────────────────────────────────────────────────── */}
      <div className="
        min-h-[400px] p-6 rounded-2xl
        bg-slate-800/40 border border-slate-700
      ">
        {reports[activeTab] ? (
          <div className="prose prose-invert prose-sm max-w-none
            prose-headings:text-slate-100 prose-headings:font-semibold
            prose-p:text-slate-300 prose-p:leading-relaxed
            prose-strong:text-slate-200
            prose-code:text-blue-300 prose-code:bg-slate-700/50 prose-code:rounded prose-code:px-1
            prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-700
            prose-table:text-slate-300 prose-th:text-slate-200 prose-th:bg-slate-700/50
            prose-tr:border-slate-700 prose-td:border-slate-700
            prose-a:text-blue-400 prose-a:no-underline hover:prose-a:underline
            prose-blockquote:border-blue-500/50 prose-blockquote:text-slate-400
            prose-li:text-slate-300 prose-ul:text-slate-300 prose-ol:text-slate-300
          ">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {reports[activeTab]}
            </ReactMarkdown>
          </div>
        ) : (
          <div className="flex items-center justify-center h-40 text-slate-600 text-sm">
            No content for this tab
          </div>
        )}
      </div>
    </div>
  )
}
