export interface TickerResult {
  symbol:   string
  name:     string
  exchange: string
  type:     string
}

export interface AnalyzeRequest {
  ticker:                  string
  trade_date:              string
  asset_type:              string
  llm_provider:            string
  deep_think_llm:          string
  quick_think_llm:         string
  analysts:                string[]
  max_debate_rounds:       number
  max_risk_discuss_rounds: number
}

export interface Job {
  job_id:     string
  status:     'queued' | 'running' | 'complete' | 'failed'
  started_at: string | null
  reports:    Record<string, string> | null
  signal:     string | null
  error:      string | null
}

export interface AppConfig {
  available_providers: string[]
  defaults: {
    llm_provider:    string
    deep_think_llm:  string
    quick_think_llm: string
  }
}

export const REPORT_TABS = [
  { key: 'market_report',          label: 'Market',       icon: '📈' },
  { key: 'sentiment_report',       label: 'Sentiment',    icon: '💬' },
  { key: 'news_report',            label: 'News',         icon: '📰' },
  { key: 'fundamentals_report',    label: 'Fundamentals', icon: '💰' },
  { key: 'investment_plan',        label: 'Research',     icon: '🤝' },
  { key: 'trader_investment_plan', label: 'Trader',       icon: '🎯' },
  { key: 'final_trade_decision',   label: 'Decision',     icon: '✅' },
] as const

export type ReportKey = typeof REPORT_TABS[number]['key']
