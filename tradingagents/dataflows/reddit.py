"""Reddit historical data fetcher for ticker-specific discussion posts.

Uses public APIs backed by the Pushshift Reddit historical data dumps —
no API key or credentials required:

  1. Pullpush.io   — community-maintained Pushshift mirror (primary)
                     https://api.pullpush.io/reddit/search/submission/
  2. Arctic Shift  — photon-reddit.com dump-backed search (fallback)
                     https://arctic-shift.photon-reddit.com/api/posts/search

Both services return historical post metadata from the Pushshift NDJSON
archives. Note that ``score`` in dump data is typically captured at
ingest time (often 1), so ``num_comments`` is the more reliable
engagement signal.

Degrades gracefully — returns a placeholder string rather than raising.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")

_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

# Pullpush.io — Pushshift-compatible, no auth, free
_PULLPUSH = "https://api.pullpush.io/reddit/search/submission/"

# Arctic Shift — photon-reddit.com, no auth, free
_ARCTIC   = "https://arctic-shift.photon-reddit.com/api/posts/search"


def _epoch_days_ago(days: int) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())


def _get(url: str, params: dict, timeout: float) -> dict | None:
    req = Request(
        f"{url}?{urlencode(params)}",
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Request failed [%s]: %s", url, exc)
        return None


def _normalise(raw: dict) -> dict:
    return {
        "title":        (raw.get("title") or "").replace("\n", " ").strip(),
        "score":        raw.get("score", 1),
        "num_comments": raw.get("num_comments", 0),
        "created_utc":  raw.get("created_utc"),
        "selftext":     (raw.get("selftext") or "").replace("\n", " ").strip(),
    }


def _pullpush(ticker: str, sub: str, limit: int, days_back: int, timeout: float) -> list[dict] | None:
    payload = _get(_PULLPUSH, {
        "q":         ticker,
        "subreddit": sub,
        "size":      min(limit, 100),
        "after":     _epoch_days_ago(days_back),
        "sort_type": "created_utc",
        "sort":      "desc",
    }, timeout)
    if payload is None or payload.get("error"):
        return None
    posts = payload.get("data") or []
    return [_normalise(p) for p in posts] if isinstance(posts, list) else None


def _arctic_shift(ticker: str, sub: str, limit: int, timeout: float) -> list[dict] | None:
    payload = _get(_ARCTIC, {
        "query":     ticker,
        "subreddit": sub,
        "limit":     min(limit, 100),
        "sort":      "new",
    }, timeout)
    if payload is None or payload.get("error"):
        return None
    posts = payload.get("data") or []
    return [_normalise(p) for p in posts] if isinstance(posts, list) else None


def _fetch_subreddit(ticker: str, sub: str, limit: int, days_back: int, timeout: float) -> list[dict]:
    result = _pullpush(ticker, sub, limit, days_back, timeout)
    if result is not None:
        return result
    logger.info("Pullpush.io unavailable for r/%s — trying Arctic Shift", sub)
    result = _arctic_shift(ticker, sub, limit, timeout)
    return result if result is not None else []


def fetch_reddit_posts(
    ticker: str,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit_per_sub: int = 5,
    timeout: float = 10.0,
    days_back: int = 7,
    inter_request_delay: float = 0.3,
) -> str:
    """Fetch recent Reddit posts mentioning ``ticker`` from Pushshift dump APIs.

    Queries Pullpush.io first (primary); falls back to Arctic Shift.
    No credentials required — both services are backed by the public
    Pushshift Reddit historical data archives.
    """
    subs = list(subreddits)
    blocks:     list[str] = []
    total_posts = 0

    for i, sub in enumerate(subs):
        if i > 0:
            time.sleep(inter_request_delay)

        posts = _fetch_subreddit(ticker, sub, limit_per_sub, days_back, timeout)
        total_posts += len(posts)

        if not posts:
            blocks.append(
                f"r/{sub}: <no posts found mentioning {ticker.upper()} "
                f"in the past {days_back} days>"
            )
            continue

        lines = [f"r/{sub} — {len(posts)} posts mentioning {ticker.upper()} "
                 f"(past {days_back} days, comments shown — scores reflect archive ingest time):"]
        for p in posts:
            created_str = (
                time.strftime("%Y-%m-%d", time.gmtime(p["created_utc"]))
                if p["created_utc"] else "?"
            )
            selftext = p["selftext"]
            if len(selftext) > 240:
                selftext = selftext[:240] + "…"
            lines.append(
                f"  [{created_str} · {p['num_comments']:>3}c] {p['title']}"
                + (f"\n    excerpt: {selftext}" if selftext else "")
            )
        blocks.append("\n".join(lines))

    if total_posts == 0:
        return (
            f"<no Reddit posts found mentioning {ticker.upper()} across "
            f"{', '.join(f'r/{s}' for s in subs)} in the past {days_back} days>"
        )
    return "\n\n".join(blocks)
