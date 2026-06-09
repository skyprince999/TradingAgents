#!/usr/bin/env python3
"""Standalone StockTwits CLI.

Fetch recent StockTwits messages for one or more tickers and print them
to stdout.  No API key required.

Usage
-----
    python stocktwits_query.py NVDA
    python stocktwits_query.py AAPL TSLA MSFT
    python stocktwits_query.py NVDA --limit 50
    python stocktwits_query.py NVDA --timeout 15
    python stocktwits_query.py NVDA --json        # raw JSON from the API
    python stocktwits_query.py NVDA --quiet       # suppress the summary header
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_API = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
# Mimic a real browser UA — bare library strings often trigger 403s
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0  # seconds; doubles each retry


def _fetch_raw(ticker: str, timeout: float, retries: int = _MAX_RETRIES) -> dict:
    """Return the raw JSON dict from the StockTwits API.

    Retries up to ``retries`` times with exponential back-off on 429 / 403
    (both indicate rate-limiting on the public endpoint).
    """
    url = _API.format(ticker=ticker.upper())
    req = Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://stocktwits.com/",
        },
    )
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except HTTPError as exc:
            last_exc = exc
            if exc.code in (403, 429) and attempt < retries - 1:
                wait = _BACKOFF_BASE ** (attempt + 1)
                print(
                    f"  [rate-limited {exc.code}] retrying in {wait:.0f}s "
                    f"(attempt {attempt + 1}/{retries}) …",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            raise
        except (URLError, json.JSONDecodeError, TimeoutError):
            raise
    raise last_exc  # type: ignore[misc]


def _format_messages(ticker: str, data: dict, limit: int, quiet: bool) -> str:
    """Format a StockTwits API response into a human-readable block."""
    messages = data.get("messages", []) if isinstance(data, dict) else []
    if not messages:
        return f"<no StockTwits messages found for ${ticker.upper()}>"

    lines: list[str] = []
    bullish = bearish = unlabeled = 0

    for m in messages[:limit]:
        created = m.get("created_at", "")
        user = (m.get("user") or {}).get("username", "?")
        entities = m.get("entities") or {}
        sentiment_obj = entities.get("sentiment") or {}
        sentiment = sentiment_obj.get("basic") if isinstance(sentiment_obj, dict) else None
        body = unescape((m.get("body") or "").replace("\n", " ").strip())
        if len(body) > 280:
            body = body[:280] + "…"

        if sentiment == "Bullish":
            bullish += 1
            tag = "🟢 Bullish"
        elif sentiment == "Bearish":
            bearish += 1
            tag = "🔴 Bearish"
        else:
            unlabeled += 1
            tag = "⬜ no-label"

        lines.append(f"[{created} · @{user} · {tag}]\n  {body}")

    total = bullish + bearish + unlabeled
    bull_pct = round(100 * bullish / total) if total else 0
    bear_pct = round(100 * bearish / total) if total else 0

    parts: list[str] = []
    if not quiet:
        header = (
            f"─── ${ticker.upper()} · StockTwits sentiment "
            f"({total} messages) ───\n"
            f"  🟢 Bullish  : {bullish:>3}  ({bull_pct}%)\n"
            f"  🔴 Bearish  : {bearish:>3}  ({bear_pct}%)\n"
            f"  ⬜ Unlabeled: {unlabeled:>3}"
        )
        parts.append(header)

    parts.append("\n".join(lines))
    return "\n\n".join(parts)


def run(tickers: list[str], limit: int, timeout: float, as_json: bool, quiet: bool) -> int:
    """Fetch and print messages for every ticker. Returns an exit code."""
    exit_code = 0
    for i, ticker in enumerate(tickers):
        if i > 0:
            print("\n" + "═" * 60 + "\n")
        try:
            data = _fetch_raw(ticker, timeout)
        except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
            print(f"ERROR fetching ${ticker.upper()}: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        if as_json:
            print(json.dumps(data, indent=2))
        else:
            print(_format_messages(ticker, data, limit, quiet))

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch recent StockTwits messages for one or more tickers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "tickers",
        nargs="+",
        metavar="TICKER",
        help="One or more stock/crypto tickers (e.g. NVDA AAPL BTC.X)",
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=30,
        metavar="N",
        help="Max messages to show per ticker (default: 30)",
    )
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=10.0,
        metavar="SECS",
        help="HTTP timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON response from the API instead of formatted output",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress the summary header; show only the message list",
    )

    args = parser.parse_args()
    sys.exit(run(args.tickers, args.limit, args.timeout, args.json, args.quiet))


if __name__ == "__main__":
    main()
