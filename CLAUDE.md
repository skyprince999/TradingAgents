# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install
pip install .               # standard install
uv sync                     # if using uv (uv.lock is present)

# Run CLI
tradingagents               # interactive CLI (after install)
python -m cli.main          # run directly from source

# Docker
cp .env.example .env        # fill in API keys first
docker compose run --rm tradingagents

# Tests
pytest                                        # all tests
pytest -m unit                               # only unit tests
pytest tests/test_signal_processing.py       # single file
pytest tests/test_signal_processing.py::test_buy_signal  # single test

# Smoke test
python scripts/smoke_structured_output.py
```

All tests run without real API keys — `conftest.py` auto-patches every known key with `"placeholder"`.

## Architecture

TradingAgents is a **LangGraph multi-agent pipeline** that produces BUY/HOLD/SELL decisions. A single `ta.propagate("NVDA", "2026-01-15")` call runs the full pipeline.

### Pipeline stages (in order)

1. **Analyst Team** — four independent analysts run sequentially (or concurrently when `analyst_concurrency_limit > 1`), each writing a report to `AgentState`:
   - `Market Analyst` → `market_report` — OHLCV and technical indicators via tool calls
   - `Sentiment Analyst` → `sentiment_report` — pre-fetches news + StockTwits + Reddit in the system prompt; no tool calls
   - `News Analyst` → `news_report` — ticker news, macro headlines, insider transactions via tool calls
   - `Fundamentals Analyst` → `fundamentals_report` — balance sheet, income statement, cash flows via tool calls

2. **Researcher Debate** — `Bull Researcher` and `Bear Researcher` debate `max_debate_rounds` times; `Research Manager` (deep LLM) adjudicates → `investment_plan`

3. **Trader** — synthesises all reports into `trader_investment_plan`

4. **Risk Debate** — `Aggressive Analyst`, `Conservative Analyst`, `Neutral Analyst` debate `max_risk_discuss_rounds` times; `Portfolio Manager` (deep LLM) makes the final call → `final_trade_decision`

### Key modules

| Path | Purpose |
|---|---|
| `tradingagents/graph/trading_graph.py` | `TradingAgentsGraph` — main entry point, holds `propagate()` |
| `tradingagents/graph/setup.py` | `GraphSetup.setup_graph()` — builds the `StateGraph` |
| `tradingagents/graph/propagation.py` | `Propagator` — creates initial `AgentState` |
| `tradingagents/graph/conditional_logic.py` | routing conditions (when debate continues vs. escalates) |
| `tradingagents/graph/analyst_execution.py` | `AnalystNodeSpec`, `build_analyst_execution_plan()`, wall-time tracker |
| `tradingagents/graph/checkpointer.py` | SQLite-backed LangGraph checkpoint resume |
| `tradingagents/graph/reflection.py` | `Reflector` — generates post-run lesson from realised return |
| `tradingagents/graph/signal_processing.py` | `SignalProcessor` — extracts BUY/HOLD/SELL from free-text |
| `tradingagents/agents/utils/agent_states.py` | `AgentState`, `InvestDebateState`, `RiskDebateState` (LangGraph TypedDicts) |
| `tradingagents/agents/utils/structured.py` | `bind_structured` / `invoke_structured_or_freetext` — shared structured-output pattern with free-text fallback |
| `tradingagents/agents/utils/memory.py` | `TradingMemoryLog` — persists decisions; resolves pending entries on next same-ticker run |
| `tradingagents/dataflows/interface.py` | Vendor router — dispatches data tool calls to yfinance or alpha_vantage; falls back on rate limits |
| `tradingagents/llm_clients/factory.py` | `create_llm_client(provider, model, ...)` — lazy-imports provider clients |
| `tradingagents/llm_clients/capabilities.py` | Per-model capability table (`supports_tool_choice`, `requires_reasoning_split`, etc.) |
| `tradingagents/llm_clients/model_catalog.py` | Shared model lists for CLI dropdowns and validation |
| `tradingagents/default_config.py` | `DEFAULT_CONFIG` — single source of truth; all `TRADINGAGENTS_*` env overrides live here |
| `cli/main.py` | Typer app registered as the `tradingagents` command |

### Two LLMs

`deep_think_llm` handles Research Manager and Portfolio Manager (complex adjudication). `quick_think_llm` handles all four analysts, both researchers, the trader, and the three risk debaters. Both are set in config and can be different models.

### Data vendor abstraction

`tradingagents/dataflows/interface.py` owns the routing table. Every agent tool (`get_stock_data`, `get_news`, etc.) dispatches through `route_to_vendor()`. Category-level defaults come from `config["data_vendors"]`; tool-level overrides from `config["tool_vendors"]`. Alpha Vantage rate-limit errors trigger automatic fallback to the next vendor — no other errors do.

The Sentiment analyst is special: it does **not** use tool calls. It calls `fetch_stocktwits_messages()` and `fetch_reddit_posts()` directly and injects all three data sources into the system prompt before invoking the LLM.

### LLM provider system

`llm_clients/factory.py` maps provider names to client classes. OpenAI, xAI, DeepSeek, Qwen (CN + intl), GLM (CN + intl), MiniMax (CN + global), Ollama, and OpenRouter all share `OpenAIClient` (OpenAI-compatible endpoint). `capabilities.py` is the single table for per-model quirks — add rows there, not conditionals in client code.

### Configuration

`DEFAULT_CONFIG` in `tradingagents/default_config.py` is the canonical config dict. `TRADINGAGENTS_*` env vars override it at import time (see `_ENV_OVERRIDES`). Copy `.env.example` to `.env` to set keys and overrides without modifying code.

Runtime directories (`results_dir`, `data_cache_dir`, `memory_log_path`) all default under `~/.tradingagents/` and can be overridden with env vars (`TRADINGAGENTS_RESULTS_DIR`, `TRADINGAGENTS_CACHE_DIR`, `TRADINGAGENTS_MEMORY_LOG_PATH`).

### Memory and checkpointing

- **Memory log** (`TradingMemoryLog`): always on. Appends each completed decision to `~/.tradingagents/memory/trading_memory.md`. On the next run for the same ticker, resolves pending entries (fetches realised returns, generates reflections), then injects recent same-ticker decisions and cross-ticker lessons into the Portfolio Manager prompt via `past_context`.
- **Checkpoint resume** (`--checkpoint` / `checkpoint_enabled=True`): opt-in. Per-ticker SQLite databases at `~/.tradingagents/cache/checkpoints/<TICKER>.db`. Cleared on successful completion. Use `--clear-checkpoints` to reset.

### Structured output pattern

`Research Manager`, `Trader`, and `Portfolio Manager` use `with_structured_output(Schema)` via helpers in `agents/utils/structured.py`. If the provider doesn't support structured output, `bind_structured` returns `None` and `invoke_structured_or_freetext` falls back to plain `llm.invoke`. When adding a new structured-output agent, follow this same pattern to keep the pipeline resilient.

### Adding a new analyst

1. Create a factory function in `tradingagents/agents/analysts/`.
2. Add an `AnalystNodeSpec` entry to `ANALYST_NODE_SPECS` in `graph/analyst_execution.py`.
3. Register a matching `ToolNode` in `TradingAgentsGraph._create_tool_nodes()` and a factory lambda in `GraphSetup.setup_graph()`.
4. Export the factory from `tradingagents/agents/__init__.py`.

### Adding a new LLM provider

1. Create a client class inheriting `BaseLLMClient` in `tradingagents/llm_clients/`.
2. Add its provider name(s) to `factory.py` (`create_llm_client`).
3. Add model options to `model_catalog.py` (`MODEL_OPTIONS`).
4. If it has API-parameter quirks, add entries to `capabilities.py`.
5. Add the env-var key name to `conftest.py`'s `_API_KEY_ENV_VARS` so tests don't require it.
