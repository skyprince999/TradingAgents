#!/usr/bin/env python3
"""CLI wrapper around tradingagents/dataflows/reddit.py

Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to be set (either in
your shell or in a .env file in the project root). Without credentials,
Reddit blocks unauthenticated requests.

How to get credentials (free, 2 minutes):
  1. Go to https://www.reddit.com/prefs/apps
  2. Click "create another app" → choose "script"
  3. Name: anything  |  Redirect URI: http://localhost
  4. Copy the client ID (below the app name) and client secret

Then add to your .env:
  REDDIT_CLIENT_ID=your_client_id
  REDDIT_CLIENT_SECRET=your_client_secret

Usage examples:
  python reddit_query.py NVDA
  python reddit_query.py AAPL --subreddits wallstreetbets stocks
  python reddit_query.py BTC-USD --subreddits cryptocurrency bitcoin --limit 10
"""

import argparse
import os
import sys
from pathlib import Path

# Allow running from the repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from tradingagents.dataflows.reddit import fetch_reddit_posts, DEFAULT_SUBREDDITS


def _check_credentials() -> None:
    missing = [v for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET") if not os.environ.get(v)]
    if missing:
        print(
            f"Warning: {', '.join(missing)} not set.\n"
            "Reddit will likely block unauthenticated requests.\n"
            "See the docstring at the top of this file for setup instructions.\n",
            file=sys.stderr,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch recent Reddit posts mentioning a ticker.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "query",
        help="Ticker or search term (e.g. NVDA, BTC-USD, 'Siemens')",
    )
    parser.add_argument(
        "--subreddits", "-s",
        nargs="+",
        default=list(DEFAULT_SUBREDDITS),
        metavar="SUB",
        help=f"Subreddits to search (default: {' '.join(DEFAULT_SUBREDDITS)})",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=5,
        metavar="N",
        help="Posts to fetch per subreddit (default: 5)",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=float,
        default=10.0,
        metavar="SECS",
        help="Request timeout in seconds for fallback URL path (default: 10)",
    )
    args = parser.parse_args()

    _check_credentials()

    print(f"Searching Reddit for : {args.query!r}")
    print(f"Subreddits           : {', '.join(f'r/{s}' for s in args.subreddits)}")
    print(f"Limit                : {args.limit} posts per subreddit")
    print("-" * 60)

    result = fetch_reddit_posts(
        ticker=args.query,
        subreddits=args.subreddits,
        limit_per_sub=args.limit,
        timeout=args.timeout,
    )

    print(result)


if __name__ == "__main__":
    main()
