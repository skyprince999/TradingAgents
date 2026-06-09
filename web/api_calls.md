# TradingAgents API — Call Flow Reference

## Base URL

```
http://localhost:8000
```

Interactive docs: `http://localhost:8000/docs`

---

## Full Pipeline Flow

### Step 1 — Load provider config *(on page load)*

```http
GET /api/config
```

**Response**
```json
{
  "available_providers": ["openai", "anthropic", "google", "ollama"],
  "defaults": {
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    "output_language": "English",
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1
  },
  "analysts": ["market", "news", "sentiment", "fundamentals"]
}
```

Use this to populate provider dropdowns and set UI defaults.

---

### Step 2 — Ticker search *(as user types)*

```http
GET /api/search?q=NVDA
```

**Response**
```json
[
  { "symbol": "NVDA", "name": "NVIDIA Corporation", "exchange": "NMS", "type": "EQUITY" }
]
```

Call on each keystroke. Proxies Yahoo Finance — covers the full symbol universe.

---

### Step 3 — Get models for selected provider *(when user picks a provider)*

```http
GET /api/models?provider=openai
```

**Response**
```json
{
  "openai": {
    "quick": [
      ["GPT-5.4 Mini - Fast, strong coding and tool use", "gpt-5.4-mini"],
      ["GPT-5.4 Nano - Cheapest, high-volume tasks", "gpt-5.4-nano"]
    ],
    "deep": [
      ["GPT-5.5 - Latest frontier, 1M context", "gpt-5.5"],
      ["GPT-5.4 - Previous-gen frontier, 1M context", "gpt-5.4"]
    ]
  }
}
```

`quick` models → `quick_think_llm` (analysts, researchers, trader, risk debaters)  
`deep` models → `deep_think_llm` (research manager, portfolio manager)

Omit `?provider=` to get the full catalog for all providers.

---

### Step 4 — Start the pipeline *(on submit)*

```http
POST /api/analyze
Content-Type: application/json
```

**Request body**
```json
{
  "ticker": "NVDA",
  "trade_date": "2026-05-28",
  "asset_type": "stock",
  "llm_provider": "openai",
  "quick_think_llm": "gpt-5.4-mini",
  "deep_think_llm": "gpt-5.4",
  "analysts": ["market", "news", "sentiment", "fundamentals"],
  "max_debate_rounds": 1,
  "max_risk_discuss_rounds": 1,
  "output_language": "English",
  "checkpoint_enabled": false
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `ticker` | string | required | Ticker symbol, e.g. `NVDA`, `BTC-USD`, `0700.HK` |
| `trade_date` | string | required | Date in `YYYY-MM-DD` format |
| `asset_type` | string | `"stock"` | `"stock"` or `"crypto"` |
| `llm_provider` | string | `"openai"` | Provider name from `/api/config` |
| `quick_think_llm` | string | `"gpt-5.4-mini"` | Model for analysts, researchers, trader, risk debaters |
| `deep_think_llm` | string | `"gpt-5.4"` | Model for research manager and portfolio manager |
| `analysts` | array | all four | Subset of `["market", "news", "sentiment", "fundamentals"]` |
| `max_debate_rounds` | int | `1` | Bull/Bear research debate rounds |
| `max_risk_discuss_rounds` | int | `1` | Risk team debate rounds |
| `output_language` | string | `"English"` | Language for all reports |
| `checkpoint_enabled` | bool | `false` | Resume from last checkpoint on crash |
| `backend_url` | string | `null` | Custom LLM endpoint (Ollama, OpenRouter, etc.) |
| `google_thinking_level` | string | `null` | `"high"`, `"minimal"` (Google only) |
| `openai_reasoning_effort` | string | `null` | `"low"`, `"medium"`, `"high"` (OpenAI only) |
| `anthropic_effort` | string | `null` | `"low"`, `"medium"`, `"high"` (Anthropic only) |

**Response** — `202 Accepted`
```json
{
  "job_id": "a1b2c3d4-...",
  "status": "queued",
  "job_type": "full_pipeline"
}
```

Returns immediately. Use `job_id` to poll.

---

### Step 5 — Poll for results *(every 3–5 seconds)*

```http
GET /api/jobs/{job_id}
```

**Response — while running**
```json
{
  "job_id": "a1b2c3d4-...",
  "status": "running",
  "started_at": "2026-05-28T10:00:00Z",
  "reports": null,
  "signal": null,
  "error": null
}
```

**Response — on completion**
```json
{
  "job_id": "a1b2c3d4-...",
  "status": "complete",
  "started_at": "2026-05-28T10:00:00Z",
  "signal": "BUY",
  "reports": {
    "market_report": "...",
    "sentiment_report": "...",
    "news_report": "...",
    "fundamentals_report": "...",
    "investment_plan": "...",
    "trader_investment_plan": "...",
    "final_trade_decision": "...",
    "bull_history": "...",
    "bear_history": "...",
    "research_manager": "...",
    "aggressive_history": "...",
    "conservative_history": "...",
    "neutral_history": "...",
    "portfolio_manager": "..."
  }
}
```

| `status` | Meaning |
|---|---|
| `queued` | Job accepted, not yet started |
| `running` | Pipeline executing |
| `complete` | All stages done — `signal` and `reports` populated |
| `failed` | Error — check `error` field for message |

`signal` is one of `BUY`, `HOLD`, or `SELL`.

Stop polling when `status` is `complete` or `failed`.

---

## Individual Agent Flow

Use this when the user selects only one analyst rather than the full pipeline.
Same polling pattern as the full pipeline — returns a single `report` field instead of all reports.

### Start a single analyst

```http
POST /api/agents/{analyst}
Content-Type: application/json
```

`analyst` is one of: `market` · `news` · `sentiment` · `fundamentals`

**Request body**
```json
{
  "ticker": "NVDA",
  "trade_date": "2026-05-28",
  "asset_type": "stock",
  "llm_provider": "openai",
  "quick_think_llm": "gpt-5.4-mini",
  "output_language": "English"
}
```

**Response** — `202 Accepted`
```json
{
  "job_id": "e5f6g7h8-...",
  "analyst": "market",
  "status": "queued"
}
```

### Poll the agent job

```http
GET /api/agents/jobs/{job_id}
```

**Response — on completion**
```json
{
  "job_id": "e5f6g7h8-...",
  "analyst": "market",
  "status": "complete",
  "started_at": "2026-05-28T10:00:00Z",
  "report": "## Market Analysis\n..."
}
```

---

## Raw Data Endpoints

Call these directly to fetch data without running any LLM agents.

| Endpoint | Required params | Optional params |
|---|---|---|
| `GET /api/data/stock` | `ticker`, `start_date`, `end_date` | — |
| `GET /api/data/indicators` | `ticker`, `indicator`, `date` | `lookback_days` (default 30) |
| `GET /api/data/news` | `ticker`, `start_date`, `end_date` | — |
| `GET /api/data/global-news` | `date` | `lookback_days`, `limit` |
| `GET /api/data/fundamentals` | `ticker`, `date` | — |
| `GET /api/data/balance-sheet` | `ticker`, `date` | `freq` (`annual`/`quarterly`) |
| `GET /api/data/cashflow` | `ticker`, `date` | `freq` |
| `GET /api/data/income-statement` | `ticker`, `date` | `freq` |
| `GET /api/data/insider-transactions` | `ticker` | — |

Valid `indicator` values: `close_50_sma`, `close_200_sma`, `close_10_ema`, `macd`, `macds`, `macdh`, `rsi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`

---

## Call Flow Summary

```
Page load    →  GET /api/config
User types   →  GET /api/search?q=...
Pick LLM     →  GET /api/models?provider=...
Submit       →  POST /api/analyze            →  job_id
Poll loop    →  GET /api/jobs/{job_id}       (repeat every 3–5s)
Done         →  render signal + reports

Single agent →  POST /api/agents/{analyst}   →  job_id
Poll loop    →  GET /api/agents/jobs/{job_id}
Done         →  render report
```

---

## Other Utility Endpoints

```http
GET    /api/jobs                        # List all pipeline jobs
DELETE /api/jobs/{job_id}               # Remove a job record

GET    /api/agents/jobs                 # List all agent jobs

GET    /api/checkpoints                 # List checkpoint files
DELETE /api/checkpoints                 # Clear all checkpoints
DELETE /api/checkpoints/{ticker}        # Clear one ticker (add ?date=YYYY-MM-DD for a specific run)

GET    /api/memory                      # All memory log entries
GET    /api/memory/{ticker}             # Past context + entries for a ticker
```
