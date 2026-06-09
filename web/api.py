"""FastAPI backend for TradingAgents.

Routes
------
GET  /api/search?q=NVDA                   Yahoo Finance autocomplete proxy
GET  /api/config                          Providers with API keys + defaults
GET  /api/models?provider=openai          Model catalog for a provider

POST /api/analyze                         Start full pipeline job → job_id
GET  /api/jobs                            List all jobs
GET  /api/jobs/{job_id}                   Poll status + reports
DELETE /api/jobs/{job_id}                 Remove a job record

POST /api/agents/{analyst}               Run one analyst in isolation → job_id
    analyst ∈ {market, news, sentiment, fundamentals}
GET  /api/agents/jobs/{job_id}            Poll single-analyst job

GET  /api/data/stock                      Raw OHLCV data
GET  /api/data/indicators                 Technical indicator values
GET  /api/data/news                       Ticker news articles
GET  /api/data/global-news                Macro / global news headlines
GET  /api/data/fundamentals               Fundamentals summary
GET  /api/data/balance-sheet              Balance sheet
GET  /api/data/cashflow                   Cash flow statement
GET  /api/data/income-statement           Income statement
GET  /api/data/insider-transactions       Insider transactions

GET  /api/checkpoints                     List checkpoint files
DELETE /api/checkpoints                   Clear all checkpoints
DELETE /api/checkpoints/{ticker}          Clear one ticker's checkpoints

GET  /api/memory                          All memory log entries
GET  /api/memory/{ticker}                 Past context injected for a ticker
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Path setup — load .env then make the project root importable
# ---------------------------------------------------------------------------
_WEB_DIR = Path(__file__).parent.resolve()
_ROOT = _WEB_DIR.parent.resolve()

try:
    from dotenv import load_dotenv
    if (_ROOT / ".env").exists():
        load_dotenv(_ROOT / ".env")
except ImportError:
    pass

sys.path.insert(0, str(_ROOT))

from tradingagents.default_config import DEFAULT_CONFIG          # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="TradingAgents API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory job store (dev / single-user)
# ---------------------------------------------------------------------------
_jobs: Dict[str, Dict[str, Any]] = {}
_agent_jobs: Dict[str, Dict[str, Any]] = {}

# Valid analyst keys
_ANALYST_KEYS = {"market", "news", "sentiment", "fundamentals"}

# Map analyst key → AgentState report field
_ANALYST_REPORT_FIELD = {
    "market": "market_report",
    "news": "news_report",
    "sentiment": "sentiment_report",
    "fundamentals": "fundamentals_report",
}

# ---------------------------------------------------------------------------
# Provider → API key env var
# ---------------------------------------------------------------------------
_KEY_MAP: Dict[str, str] = {
    "openai":     "OPENAI_API_KEY",
    "anthropic":  "ANTHROPIC_API_KEY",
    "google":     "GOOGLE_API_KEY",
    "xai":        "XAI_API_KEY",
    "deepseek":   "DEEPSEEK_API_KEY",
    "qwen":       "DASHSCOPE_API_KEY",
    "glm":        "ZHIPU_API_KEY",
    "minimax":    "MINIMAX_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    ticker:                   str
    trade_date:               str            # "YYYY-MM-DD"
    asset_type:               str = "stock"
    llm_provider:             str = "openai"
    deep_think_llm:           str = "gpt-5.4"
    quick_think_llm:          str = "gpt-5.4-mini"
    analysts:                 List[str] = ["market", "social", "news", "fundamentals"]
    max_debate_rounds:        int = 1
    max_risk_discuss_rounds:  int = 1
    output_language:          str = "English"
    checkpoint_enabled:       bool = False
    backend_url:              Optional[str] = None
    google_thinking_level:    Optional[str] = None
    openai_reasoning_effort:  Optional[str] = None
    anthropic_effort:         Optional[str] = None


class AgentRequest(BaseModel):
    """Request to run a single analyst agent."""
    ticker:          str
    trade_date:      str            # "YYYY-MM-DD"
    asset_type:      str = "stock"
    llm_provider:    str = "openai"
    quick_think_llm: str = "gpt-5.4-mini"
    backend_url:     Optional[str] = None
    google_thinking_level:   Optional[str] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort:        Optional[str] = None
    output_language: str = "English"


class JobOut(BaseModel):
    job_id:     str
    status:     Literal["queued", "running", "complete", "failed"]
    job_type:   str = "full_pipeline"
    started_at: Optional[str] = None
    reports:    Optional[Dict[str, str]] = None
    signal:     Optional[str] = None
    error:      Optional[str] = None


class AgentJobOut(BaseModel):
    job_id:     str
    analyst:    str
    status:     Literal["queued", "running", "complete", "failed"]
    started_at: Optional[str] = None
    report:     Optional[str] = None
    error:      Optional[str] = None


class CheckpointInfo(BaseModel):
    ticker: str
    path:   str
    size_bytes: int


class MemoryEntry(BaseModel):
    ticker:     str
    date:       str
    rating:     str
    status:     str
    decision:   str
    reflection: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_config(
    llm_provider: str,
    quick_think_llm: str,
    deep_think_llm: Optional[str] = None,
    max_debate_rounds: int = 1,
    max_risk_discuss_rounds: int = 1,
    output_language: str = "English",
    checkpoint_enabled: bool = False,
    backend_url: Optional[str] = None,
    google_thinking_level: Optional[str] = None,
    openai_reasoning_effort: Optional[str] = None,
    anthropic_effort: Optional[str] = None,
) -> dict:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"]            = llm_provider
    config["quick_think_llm"]         = quick_think_llm
    if deep_think_llm:
        config["deep_think_llm"]      = deep_think_llm
    config["max_debate_rounds"]       = max_debate_rounds
    config["max_risk_discuss_rounds"] = max_risk_discuss_rounds
    config["output_language"]         = output_language
    config["checkpoint_enabled"]      = checkpoint_enabled
    if backend_url:
        config["backend_url"]         = backend_url
    if google_thinking_level:
        config["google_thinking_level"] = google_thinking_level
    if openai_reasoning_effort:
        config["openai_reasoning_effort"] = openai_reasoning_effort
    if anthropic_effort:
        config["anthropic_effort"]    = anthropic_effort
    return config


def _build_analyst_mini_graph(analyst_key: str, llm):
    """Build a single-analyst LangGraph mini-graph (analyst + tool loop)."""
    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, StateGraph
    from langgraph.prebuilt import ToolNode

    from tradingagents.agents import (
        create_fundamentals_analyst,
        create_market_analyst,
        create_news_analyst,
        create_sentiment_analyst,
    )
    from tradingagents.agents.utils.agent_states import AgentState
    from tradingagents.agents.utils.agent_utils import (
        get_balance_sheet,
        get_cashflow,
        get_fundamentals,
        get_income_statement,
        get_indicators,
        get_insider_transactions,
        get_news,
        get_stock_data,
    )

    _ANALYST_CONFIG = {
        "market": (
            create_market_analyst,
            [get_stock_data, get_indicators],
        ),
        "news": (
            create_news_analyst,
            [get_news, get_insider_transactions],
        ),
        "sentiment": (
            create_sentiment_analyst,
            [],  # sentiment pre-fetches data in the prompt; no tool loop
        ),
        "fundamentals": (
            create_fundamentals_analyst,
            [get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement],
        ),
    }

    if analyst_key not in _ANALYST_CONFIG:
        raise ValueError(f"Unknown analyst key: {analyst_key!r}")

    factory, tools = _ANALYST_CONFIG[analyst_key]
    analyst_node = factory(llm)

    graph = StateGraph(AgentState)
    graph.add_node("analyst", analyst_node)

    if tools:
        tool_node = ToolNode(tools)
        graph.add_node("tools", tool_node)

        def route_analyst(state):
            last = state["messages"][-1]
            if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
                return "tools"
            return END

        graph.add_edge(START, "analyst")
        graph.add_conditional_edges(
            "analyst", route_analyst, {"tools": "tools", END: END}
        )
        graph.add_edge("tools", "analyst")
    else:
        # Sentiment: single LLM call, no tool loop
        graph.add_edge(START, "analyst")
        graph.add_edge("analyst", END)

    return graph.compile()


def _make_initial_state(ticker: str, trade_date: str, asset_type: str) -> dict:
    """Minimal AgentState for single-analyst runs."""
    from tradingagents.agents.utils.agent_states import InvestDebateState, RiskDebateState

    return {
        "messages": [("human", ticker)],
        "company_of_interest": ticker,
        "asset_type": asset_type,
        "trade_date": str(trade_date),
        "past_context": "",
        "sender": "",
        "investment_debate_state": InvestDebateState(
            bull_history="", bear_history="", history="",
            current_response="", judge_decision="", count=0,
        ),
        "risk_debate_state": RiskDebateState(
            aggressive_history="", conservative_history="",
            neutral_history="", history="", latest_speaker="",
            current_aggressive_response="", current_conservative_response="",
            current_neutral_response="", judge_decision="", count=0,
        ),
        "market_report": "",
        "fundamentals_report": "",
        "sentiment_report": "",
        "news_report": "",
        "investment_plan": "",
        "trader_investment_plan": "",
        "final_trade_decision": "",
    }


# ---------------------------------------------------------------------------
# Routes — search & config
# ---------------------------------------------------------------------------

@app.get("/api/search")
async def search_tickers(q: str) -> List[Dict[str, str]]:
    """Proxy Yahoo Finance search — covers the full Yahoo symbol universe."""
    if not q or len(q.strip()) < 1:
        return []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://query1.finance.yahoo.com/v1/finance/search",
                params={
                    "q":                q,
                    "quotesCount":      15,
                    "newsCount":        0,
                    "enableFuzzyQuery": "false",
                    "lang":             "en-US",
                },
                headers={"User-Agent": "Mozilla/5.0"},
            )
        r.raise_for_status()
        quotes = r.json().get("quotes", [])
        return [
            {
                "symbol":   item["symbol"],
                "name":     item.get("shortname") or item.get("longname") or "",
                "exchange": item.get("exchange") or "",
                "type":     item.get("quoteType") or "",
            }
            for item in quotes
            if "symbol" in item
        ]
    except Exception as exc:
        logger.warning("Yahoo Finance search failed for %r: %s", q, exc)
        return []


@app.get("/api/config")
async def get_config() -> Dict[str, Any]:
    """Return which providers have API keys set, current defaults, and analyst list."""
    available = [p for p, env in _KEY_MAP.items() if os.environ.get(env)]
    available.append("ollama")
    return {
        "available_providers": available,
        "defaults": {
            "llm_provider":    DEFAULT_CONFIG.get("llm_provider", "openai"),
            "deep_think_llm":  DEFAULT_CONFIG.get("deep_think_llm", "gpt-5.4"),
            "quick_think_llm": DEFAULT_CONFIG.get("quick_think_llm", "gpt-5.4-mini"),
            "output_language": DEFAULT_CONFIG.get("output_language", "English"),
            "max_debate_rounds":       DEFAULT_CONFIG.get("max_debate_rounds", 1),
            "max_risk_discuss_rounds": DEFAULT_CONFIG.get("max_risk_discuss_rounds", 1),
        },
        "analysts": list(_ANALYST_KEYS),
    }


@app.get("/api/models")
async def get_models(provider: Optional[str] = None) -> Dict[str, Any]:
    """Return the model catalog.  Pass ?provider=openai to filter to one provider."""
    if provider:
        key = provider.lower()
        if key not in MODEL_OPTIONS:
            raise HTTPException(status_code=404, detail=f"Unknown provider: {provider!r}")
        return {key: MODEL_OPTIONS[key]}
    return MODEL_OPTIONS


# ---------------------------------------------------------------------------
# Routes — full pipeline
# ---------------------------------------------------------------------------

@app.post("/api/analyze", response_model=JobOut, status_code=202)
async def analyze(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Start a full TradingAgents pipeline run.  Returns a job_id to poll."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status":     "queued",
        "job_type":   "full_pipeline",
        "started_at": None,
        "reports":    None,
        "signal":     None,
        "error":      None,
    }
    background_tasks.add_task(_run_full_pipeline, job_id, req)
    return JobOut(job_id=job_id, status="queued", job_type="full_pipeline")


@app.get("/api/jobs", response_model=List[JobOut])
async def list_jobs():
    """Return all job records (newest-first approximation via insertion order)."""
    return [
        JobOut(job_id=jid, **data)
        for jid, data in reversed(list(_jobs.items()))
    ]


@app.get("/api/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut(job_id=job_id, **job)


@app.delete("/api/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str):
    """Remove a job record (does not cancel a running job)."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    del _jobs[job_id]


# ---------------------------------------------------------------------------
# Routes — individual analyst agents
# ---------------------------------------------------------------------------

@app.post("/api/agents/{analyst}", response_model=AgentJobOut, status_code=202)
async def run_agent(analyst: str, req: AgentRequest, background_tasks: BackgroundTasks):
    """Run a single analyst (market | news | sentiment | fundamentals) in isolation."""
    key = analyst.lower()
    if key not in _ANALYST_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown analyst {analyst!r}. Valid: {sorted(_ANALYST_KEYS)}",
        )
    job_id = str(uuid.uuid4())
    _agent_jobs[job_id] = {
        "analyst":    key,
        "status":     "queued",
        "started_at": None,
        "report":     None,
        "error":      None,
    }
    background_tasks.add_task(_run_single_analyst, job_id, key, req)
    return AgentJobOut(job_id=job_id, analyst=key, status="queued")


@app.get("/api/agents/jobs/{job_id}", response_model=AgentJobOut)
async def get_agent_job(job_id: str):
    job = _agent_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Agent job not found")
    return AgentJobOut(job_id=job_id, **job)


@app.get("/api/agents/jobs", response_model=List[AgentJobOut])
async def list_agent_jobs():
    return [
        AgentJobOut(job_id=jid, **data)
        for jid, data in reversed(list(_agent_jobs.items()))
    ]


# ---------------------------------------------------------------------------
# Routes — raw data endpoints
# ---------------------------------------------------------------------------

@app.get("/api/data/stock")
async def data_stock(
    ticker: str,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """Fetch OHLCV data for a ticker between start_date and end_date (yyyy-mm-dd)."""
    from tradingagents.dataflows.interface import route_to_vendor
    try:
        result = route_to_vendor("get_stock_data", ticker.upper(), start_date, end_date)
        return {"ticker": ticker.upper(), "start_date": start_date, "end_date": end_date, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/data/indicators")
async def data_indicators(
    ticker: str,
    indicator: str,
    date: str,
    lookback_days: int = 30,
) -> Dict[str, Any]:
    """Fetch a technical indicator for a ticker.

    indicator: one of close_50_sma, close_200_sma, close_10_ema, macd, macds,
               macdh, rsi, boll, boll_ub, boll_lb, atr, vwma
    """
    from tradingagents.dataflows.interface import route_to_vendor
    try:
        result = route_to_vendor("get_indicators", ticker.upper(), indicator, date, lookback_days)
        return {"ticker": ticker.upper(), "indicator": indicator, "date": date, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/data/news")
async def data_news(
    ticker: str,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """Fetch news articles for a ticker between start_date and end_date."""
    from tradingagents.dataflows.interface import route_to_vendor
    try:
        result = route_to_vendor("get_news", ticker.upper(), start_date, end_date)
        return {"ticker": ticker.upper(), "start_date": start_date, "end_date": end_date, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/data/global-news")
async def data_global_news(
    date: str,
    lookback_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Fetch macro / global news headlines."""
    from tradingagents.dataflows.interface import route_to_vendor
    try:
        result = route_to_vendor("get_global_news", date, lookback_days, limit)
        return {"date": date, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/data/fundamentals")
async def data_fundamentals(
    ticker: str,
    date: str,
) -> Dict[str, Any]:
    """Fetch comprehensive fundamental data for a ticker."""
    from tradingagents.dataflows.interface import route_to_vendor
    try:
        result = route_to_vendor("get_fundamentals", ticker.upper(), date)
        return {"ticker": ticker.upper(), "date": date, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/data/balance-sheet")
async def data_balance_sheet(
    ticker: str,
    date: str,
    freq: str = "quarterly",
) -> Dict[str, Any]:
    """Fetch balance sheet data.  freq: annual | quarterly"""
    from tradingagents.dataflows.interface import route_to_vendor
    try:
        result = route_to_vendor("get_balance_sheet", ticker.upper(), freq, date)
        return {"ticker": ticker.upper(), "date": date, "freq": freq, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/data/cashflow")
async def data_cashflow(
    ticker: str,
    date: str,
    freq: str = "quarterly",
) -> Dict[str, Any]:
    """Fetch cash flow statement.  freq: annual | quarterly"""
    from tradingagents.dataflows.interface import route_to_vendor
    try:
        result = route_to_vendor("get_cashflow", ticker.upper(), freq, date)
        return {"ticker": ticker.upper(), "date": date, "freq": freq, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/data/income-statement")
async def data_income_statement(
    ticker: str,
    date: str,
    freq: str = "quarterly",
) -> Dict[str, Any]:
    """Fetch income statement.  freq: annual | quarterly"""
    from tradingagents.dataflows.interface import route_to_vendor
    try:
        result = route_to_vendor("get_income_statement", ticker.upper(), freq, date)
        return {"ticker": ticker.upper(), "date": date, "freq": freq, "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/data/insider-transactions")
async def data_insider_transactions(ticker: str) -> Dict[str, Any]:
    """Fetch insider transaction data for a ticker."""
    from tradingagents.dataflows.interface import route_to_vendor
    try:
        result = route_to_vendor("get_insider_transactions", ticker.upper())
        return {"ticker": ticker.upper(), "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Routes — checkpoint management
# ---------------------------------------------------------------------------

@app.get("/api/checkpoints", response_model=List[CheckpointInfo])
async def list_checkpoints():
    """List all checkpoint SQLite files."""
    from tradingagents.dataflows.utils import safe_ticker_component

    cp_dir = Path(DEFAULT_CONFIG["data_cache_dir"]) / "checkpoints"
    if not cp_dir.exists():
        return []
    results = []
    for db in sorted(cp_dir.glob("*.db")):
        results.append(CheckpointInfo(
            ticker=db.stem,
            path=str(db),
            size_bytes=db.stat().st_size,
        ))
    return results


@app.delete("/api/checkpoints", status_code=200)
async def clear_all_checkpoints_endpoint():
    """Delete all checkpoint files."""
    from tradingagents.graph.checkpointer import clear_all_checkpoints
    n = clear_all_checkpoints(DEFAULT_CONFIG["data_cache_dir"])
    return {"deleted": n}


@app.delete("/api/checkpoints/{ticker}", status_code=200)
async def clear_ticker_checkpoint(ticker: str, date: Optional[str] = None):
    """Clear checkpoints for a specific ticker.

    If ?date=YYYY-MM-DD is given, only that thread is removed.
    Otherwise the entire per-ticker DB is deleted.
    """
    from tradingagents.graph.checkpointer import clear_checkpoint
    from tradingagents.dataflows.utils import safe_ticker_component

    safe = safe_ticker_component(ticker).upper()
    cp_dir = Path(DEFAULT_CONFIG["data_cache_dir"]) / "checkpoints"
    db = cp_dir / f"{safe}.db"

    if not db.exists():
        raise HTTPException(status_code=404, detail=f"No checkpoint for ticker {ticker!r}")

    if date:
        clear_checkpoint(DEFAULT_CONFIG["data_cache_dir"], ticker, date)
        return {"deleted": f"thread {ticker}:{date}"}
    else:
        db.unlink()
        return {"deleted": f"all checkpoints for {ticker}"}


# ---------------------------------------------------------------------------
# Routes — memory log
# ---------------------------------------------------------------------------

@app.get("/api/memory", response_model=List[MemoryEntry])
async def get_memory():
    """Return all entries from the trading memory log."""
    from tradingagents.agents.utils.memory import TradingMemoryLog
    log = TradingMemoryLog(DEFAULT_CONFIG)
    entries = log.load_entries()
    result = []
    for e in entries:
        result.append(MemoryEntry(
            ticker=e.get("ticker", ""),
            date=e.get("date", ""),
            rating=e.get("rating", ""),
            status=e.get("status", ""),
            decision=e.get("decision", ""),
            reflection=e.get("reflection"),
        ))
    return result


@app.get("/api/memory/{ticker}")
async def get_ticker_memory(ticker: str) -> Dict[str, Any]:
    """Return the past-context string that would be injected for a ticker."""
    from tradingagents.agents.utils.memory import TradingMemoryLog
    log = TradingMemoryLog(DEFAULT_CONFIG)
    context = log.get_past_context(ticker.upper())
    entries = [e for e in log.load_entries() if e.get("ticker", "").upper() == ticker.upper()]
    return {
        "ticker": ticker.upper(),
        "past_context": context,
        "entries": entries,
    }


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

def _run_full_pipeline(job_id: str, req: AnalyzeRequest) -> None:
    _jobs[job_id]["status"]     = "running"
    _jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        config = _build_config(
            llm_provider=req.llm_provider,
            quick_think_llm=req.quick_think_llm,
            deep_think_llm=req.deep_think_llm,
            max_debate_rounds=req.max_debate_rounds,
            max_risk_discuss_rounds=req.max_risk_discuss_rounds,
            output_language=req.output_language,
            checkpoint_enabled=req.checkpoint_enabled,
            backend_url=req.backend_url,
            google_thinking_level=req.google_thinking_level,
            openai_reasoning_effort=req.openai_reasoning_effort,
            anthropic_effort=req.anthropic_effort,
        )

        ta = TradingAgentsGraph(
            selected_analysts=req.analysts,
            debug=False,
            config=config,
        )
        final_state, signal = ta.propagate(
            req.ticker, req.trade_date, asset_type=req.asset_type
        )

        debate = final_state.get("investment_debate_state", {})
        risk   = final_state.get("risk_debate_state", {})

        _jobs[job_id].update({
            "status": "complete",
            "signal": signal,
            "reports": {
                "market_report":          final_state.get("market_report", ""),
                "sentiment_report":       final_state.get("sentiment_report", ""),
                "news_report":            final_state.get("news_report", ""),
                "fundamentals_report":    final_state.get("fundamentals_report", ""),
                "investment_plan":        final_state.get("investment_plan", ""),
                "trader_investment_plan": final_state.get("trader_investment_plan", ""),
                "final_trade_decision":   final_state.get("final_trade_decision", ""),
                # Debate internals
                "bull_history":           debate.get("bull_history", ""),
                "bear_history":           debate.get("bear_history", ""),
                "research_manager":       debate.get("judge_decision", ""),
                "aggressive_history":     risk.get("aggressive_history", ""),
                "conservative_history":   risk.get("conservative_history", ""),
                "neutral_history":        risk.get("neutral_history", ""),
                "portfolio_manager":      risk.get("judge_decision", ""),
            },
        })
        logger.info("Job %s complete — signal: %s", job_id, signal)
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        _jobs[job_id].update({"status": "failed", "error": str(exc)})


def _run_single_analyst(job_id: str, analyst_key: str, req: AgentRequest) -> None:
    _agent_jobs[job_id]["status"]     = "running"
    _agent_jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        config = _build_config(
            llm_provider=req.llm_provider,
            quick_think_llm=req.quick_think_llm,
            output_language=req.output_language,
            backend_url=req.backend_url,
            google_thinking_level=req.google_thinking_level,
            openai_reasoning_effort=req.openai_reasoning_effort,
            anthropic_effort=req.anthropic_effort,
        )

        # Apply config so vendor routing picks it up
        from tradingagents.dataflows.config import set_config
        set_config(config)

        from tradingagents.llm_clients import create_llm_client

        client = create_llm_client(
            provider=config["llm_provider"],
            model=config["quick_think_llm"],
            base_url=config.get("backend_url"),
        )
        llm = client.get_llm()

        mini_graph = _build_analyst_mini_graph(analyst_key, llm)
        init_state = _make_initial_state(req.ticker, req.trade_date, req.asset_type)

        final_state = mini_graph.invoke(init_state, config={"recursion_limit": 50})

        report_field = _ANALYST_REPORT_FIELD[analyst_key]
        report = final_state.get(report_field, "")

        _agent_jobs[job_id].update({
            "status": "complete",
            "report": report,
        })
        logger.info("Agent job %s (%s) complete", job_id, analyst_key)
    except Exception as exc:
        logger.exception("Agent job %s failed", job_id)
        _agent_jobs[job_id].update({"status": "failed", "error": str(exc)})


# ---------------------------------------------------------------------------
# Serve compiled React app in production (optional)
# ---------------------------------------------------------------------------
_dist = _WEB_DIR / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")
