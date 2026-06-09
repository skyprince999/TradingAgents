import { useState, useEffect } from 'react'
import type { TickerResult, AnalyzeRequest, AppConfig } from '../types'
import { fetchConfig, startAnalysis } from '../api'
import TickerSearch from './TickerSearch'

// ── Provider → default model map ───────────────────────────────────────────
const PROVIDER_DEFAULTS: Record<string, { deep: string; quick: string }> = {
  openai:     { deep: 'gpt-5.4',                quick: 'gpt-5.4-mini' },
  anthropic:  { deep: 'claude-opus-4-7',         quick: 'claude-sonnet-4-6' },
  google:     { deep: 'gemini-3.1-pro-preview',  quick: 'gemini-3-flash-preview' },
  xai:        { deep: 'grok-4.20-reasoning',     quick: 'grok-4.20-non-reasoning' },
  deepseek:   { deep: 'deepseek-v4-pro',         quick: 'deepseek-v4-flash' },
  qwen:       { deep: 'qwen3.6-plus',            quick: 'qwen3.6-flash' },
  glm:        { deep: 'glm-5.1',                 quick: 'glm-5-turbo' },
  minimax:    { deep: 'MiniMax-M2.7',            quick: 'MiniMax-M2.7-highspeed' },
  openrouter: { deep: '',                         quick: '' },
  ollama:     { deep: 'qwen3:latest',            quick: 'qwen3:latest' },
}

const PROVIDER_LABELS: Record<string, string> = {
  openai:     'OpenAI',
  anthropic:  'Anthropic (Claude)',
  google:     'Google (Gemini)',
  xai:        'xAI (Grok)',
  deepseek:   'DeepSeek',
  qwen:       'Qwen (DashScope)',
  glm:        'GLM (Z.AI)',
  minimax:    'MiniMax',
  openrouter: 'OpenRouter',
  ollama:     'Ollama (Local)',
}

const ANALYSTS = [
  { key: 'market',       label: 'Market',       description: 'OHLCV + technical indicators' },
  { key: 'social',       label: 'Sentiment',    description: 'News · StockTwits · Reddit' },
  { key: 'news',         label: 'News',         description: 'Headlines + macro + insider' },
  { key: 'fundamentals', label: 'Fundamentals', description: 'Financials + balance sheet' },
]

function today(): string {
  return new Date().toISOString().split('T')[0]
}

interface Props {
  onJobStart: (jobId: string, ticker: TickerResult, tradeDate: string) => void
}

export default function AnalyzeForm({ onJobStart }: Props) {
  const [ticker,       setTicker]       = useState<TickerResult | null>(null)
  const [tradeDate,    setTradeDate]    = useState(today())
  const [assetType,    setAssetType]    = useState<'stock' | 'crypto'>('stock')
  const [provider,     setProvider]     = useState('openai')
  const [deepModel,    setDeepModel]    = useState('gpt-5.4')
  const [quickModel,   setQuickModel]   = useState('gpt-5.4-mini')
  const [analysts,     setAnalysts]     = useState(['market', 'social', 'news', 'fundamentals'])
  const [debateRounds, setDebateRounds] = useState(1)
  const [riskRounds,   setRiskRounds]   = useState(1)
  const [showAdv,      setShowAdv]      = useState(false)
  const [submitting,   setSubmitting]   = useState(false)
  const [error,        setError]        = useState<string | null>(null)
  const [config,       setConfig]       = useState<AppConfig | null>(null)

  // fetch available providers on mount
  useEffect(() => {
    fetchConfig()
      .then(cfg => {
        setConfig(cfg)
        const first = cfg.available_providers[0]
        if (first) {
          setProvider(first)
          setDeepModel(PROVIDER_DEFAULTS[first]?.deep  ?? cfg.defaults.deep_think_llm)
          setQuickModel(PROVIDER_DEFAULTS[first]?.quick ?? cfg.defaults.quick_think_llm)
        }
      })
      .catch(() => { /* use defaults */ })
  }, [])

  // auto-fill models when provider changes
  function handleProviderChange(p: string) {
    setProvider(p)
    const def = PROVIDER_DEFAULTS[p]
    if (def) { setDeepModel(def.deep); setQuickModel(def.quick) }
  }

  // auto-detect asset type from ticker
  function handleTickerSelect(t: TickerResult) {
    setTicker(t)
    setError(null)
    if (t.type === 'CRYPTOCURRENCY') setAssetType('crypto')
    else setAssetType('stock')
  }

  function toggleAnalyst(key: string) {
    setAnalysts(prev =>
      prev.includes(key) ? prev.filter(a => a !== key) : [...prev, key]
    )
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!ticker) { setError('Please select a ticker first.'); return }
    if (analysts.length === 0) { setError('Select at least one analyst.'); return }
    setError(null)
    setSubmitting(true)
    try {
      const req: AnalyzeRequest = {
        ticker:                  ticker.symbol,
        trade_date:              tradeDate,
        asset_type:              assetType,
        llm_provider:            provider,
        deep_think_llm:          deepModel,
        quick_think_llm:         quickModel,
        analysts,
        max_debate_rounds:       debateRounds,
        max_risk_discuss_rounds: riskRounds,
      }
      const { job_id } = await startAnalysis(req)
      onJobStart(job_id, ticker, tradeDate)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start analysis')
      setSubmitting(false)
    }
  }

  const availableProviders = config?.available_providers ?? Object.keys(PROVIDER_DEFAULTS)

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* ── Ticker search ──────────────────────────────────────────────── */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-slate-400 uppercase tracking-wider">
          Symbol
        </label>
        <TickerSearch onSelect={handleTickerSelect} />
        {ticker && (
          <div className="flex items-center gap-2 pt-1">
            <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/30 text-sm">
              <span className="font-mono font-bold text-blue-400">{ticker.symbol}</span>
              <span className="text-slate-400">{ticker.name}</span>
              <button
                type="button"
                onClick={() => setTicker(null)}
                className="text-slate-500 hover:text-slate-300 ml-1"
              >
                ✕
              </button>
            </span>
          </div>
        )}
      </div>

      {/* ── Date + asset type ──────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-400 uppercase tracking-wider">
            Trade Date
          </label>
          <input
            type="date"
            value={tradeDate}
            onChange={e => setTradeDate(e.target.value)}
            className="
              w-full px-4 py-3 rounded-xl bg-slate-800/60 border border-slate-700
              text-slate-100 outline-none focus:border-blue-500 focus:ring-2
              focus:ring-blue-500/20 transition-all
            "
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-400 uppercase tracking-wider">
            Asset Type
          </label>
          <div className="flex rounded-xl overflow-hidden border border-slate-700">
            {(['stock', 'crypto'] as const).map(t => (
              <button
                key={t}
                type="button"
                onClick={() => setAssetType(t)}
                className={`
                  flex-1 py-3 text-sm font-medium capitalize transition-colors
                  ${assetType === t
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'}
                `}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── LLM provider ──────────────────────────────────────────────── */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-slate-400 uppercase tracking-wider">
          LLM Provider
        </label>
        <select
          value={provider}
          onChange={e => handleProviderChange(e.target.value)}
          className="
            w-full px-4 py-3 rounded-xl bg-slate-800/60 border border-slate-700
            text-slate-100 outline-none focus:border-blue-500 focus:ring-2
            focus:ring-blue-500/20 transition-all
          "
        >
          {availableProviders.map(p => (
            <option key={p} value={p}>{PROVIDER_LABELS[p] ?? p}</option>
          ))}
        </select>
      </div>

      {/* ── Models ────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4">
        {[
          { label: 'Deep (Research, Portfolio)', val: deepModel,  set: setDeepModel },
          { label: 'Quick (Analysts, Trader)',   val: quickModel, set: setQuickModel },
        ].map(({ label, val, set }) => (
          <div key={label} className="space-y-2">
            <label className="text-sm font-medium text-slate-400 uppercase tracking-wider">
              {label}
            </label>
            <input
              type="text"
              value={val}
              onChange={e => set(e.target.value)}
              placeholder="model name"
              className="
                w-full px-4 py-3 rounded-xl bg-slate-800/60 border border-slate-700
                text-slate-100 font-mono text-sm placeholder-slate-600
                outline-none focus:border-blue-500 focus:ring-2
                focus:ring-blue-500/20 transition-all
              "
            />
          </div>
        ))}
      </div>

      {/* ── Analysts ──────────────────────────────────────────────────── */}
      <div className="space-y-3">
        <label className="text-sm font-medium text-slate-400 uppercase tracking-wider">
          Analysts
        </label>
        <div className="grid grid-cols-2 gap-2">
          {ANALYSTS.map(({ key, label, description }) => (
            <button
              key={key}
              type="button"
              onClick={() => toggleAnalyst(key)}
              className={`
                flex items-start gap-3 px-4 py-3 rounded-xl border text-left
                transition-all duration-150
                ${analysts.includes(key)
                  ? 'bg-blue-600/15 border-blue-500/50 text-blue-300'
                  : 'bg-slate-800/40 border-slate-700 text-slate-400 hover:border-slate-600'}
              `}
            >
              <span className={`mt-0.5 w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center
                ${analysts.includes(key) ? 'bg-blue-500 border-blue-500' : 'border-slate-600'}`}>
                {analysts.includes(key) && (
                  <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7"/>
                  </svg>
                )}
              </span>
              <div>
                <div className="text-sm font-medium">{label}</div>
                <div className="text-xs text-slate-500 mt-0.5">{description}</div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* ── Advanced (collapsible) ────────────────────────────────────── */}
      <div>
        <button
          type="button"
          onClick={() => setShowAdv(v => !v)}
          className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-300 transition-colors"
        >
          <svg className={`w-4 h-4 transition-transform ${showAdv ? 'rotate-90' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7"/>
          </svg>
          Advanced settings
        </button>
        {showAdv && (
          <div className="mt-4 grid grid-cols-2 gap-4">
            {[
              { label: 'Research Debate Rounds', val: debateRounds, set: setDebateRounds },
              { label: 'Risk Debate Rounds',     val: riskRounds,   set: setRiskRounds },
            ].map(({ label, val, set }) => (
              <div key={label} className="space-y-2">
                <label className="text-sm font-medium text-slate-400">{label}</label>
                <input
                  type="number" min={1} max={5} value={val}
                  onChange={e => set(Number(e.target.value))}
                  className="
                    w-full px-4 py-3 rounded-xl bg-slate-800/60 border border-slate-700
                    text-slate-100 outline-none focus:border-blue-500 focus:ring-2
                    focus:ring-blue-500/20 transition-all
                  "
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Error ─────────────────────────────────────────────────────── */}
      {error && (
        <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* ── Submit ────────────────────────────────────────────────────── */}
      <button
        type="submit"
        disabled={submitting || !ticker}
        className="
          w-full py-4 rounded-xl font-semibold text-base
          bg-blue-600 hover:bg-blue-500 disabled:opacity-40
          disabled:cursor-not-allowed text-white
          transition-all duration-150
          focus:outline-none focus:ring-2 focus:ring-blue-500/50
        "
      >
        {submitting ? 'Starting…' : 'Run Analysis'}
      </button>
    </form>
  )
}
