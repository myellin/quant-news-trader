#!/usr/bin/env python3
"""
Quant News Trader - News-based swing trading signal generator.

Usage:
    export PERPLEXITY_API_KEY=your_key_here
    python main.py [--ticker NVDA] [--all]
"""

import argparse
import sys
from dotenv import load_dotenv

from config import WATCHLIST, MIN_SIGNAL_SCORE
from news_fetcher import fetch_news_analysis, fetch_market_overview
from signal_extractor import extract_signal


# Ticker to company name mapping
TICKER_NAMES = {
    "NVDA": "NVIDIA Corporation",
    "MU": "Micron Technology",
    "TSLA": "Tesla Inc",
    "BABA": "Alibaba Group",
}


def print_separator():
    print("\n" + "=" * 70 + "\n")


def analyze_ticker(ticker: str, market_overview: str) -> dict:
    """Run full analysis pipeline for a single ticker."""
    company = TICKER_NAMES.get(ticker, ticker)

    print(f"Fetching news for {ticker} ({company})...")
    news = fetch_news_analysis(ticker, company)

    print(f"Extracting trading signal...")
    signal = extract_signal(ticker, news["analysis"], market_overview)

    return {
        "news": news,
        "signal": signal
    }


def print_signal_summary(signal: dict):
    """Print a formatted signal summary."""
    direction_emoji = {
        "BULLISH": "[+]",
        "BEARISH": "[-]",
        "NEUTRAL": "[=]"
    }

    d = signal["direction"]
    conf = signal["confidence"]

    print(f"\n{signal['ticker']}: {direction_emoji.get(d, '[?]')} {d} (confidence: {conf:.1%})")
    print(f"  Timeframe: {signal['timeframe']}")
    print(f"  IV Environment: {signal['iv_environment']}")

    if signal["strategy"]:
        print(f"  Strategy: {signal['strategy'][:100]}...")

    if signal["entry_trigger"]:
        print(f"  Entry: {signal['entry_trigger'][:80]}")

    if signal["catalysts"]:
        print(f"  Catalysts: {', '.join(signal['catalysts'][:3])}")

    if conf >= MIN_SIGNAL_SCORE:
        print(f"  >>> ACTIONABLE SIGNAL (above {MIN_SIGNAL_SCORE:.0%} threshold)")
    else:
        print(f"  (below threshold, watch only)")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="News-based swing trading signal generator")
    parser.add_argument("--ticker", "-t", help="Analyze a specific ticker")
    parser.add_argument("--all", "-a", action="store_true", help="Analyze all watchlist tickers")
    parser.add_argument("--no-market", action="store_true", help="Skip market overview")
    args = parser.parse_args()

    # Determine which tickers to analyze
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.all:
        tickers = WATCHLIST
    else:
        # Default: analyze all
        tickers = WATCHLIST

    print("=" * 70)
    print("QUANT NEWS TRADER - Swing Trading Signal Generator")
    print("=" * 70)

    # Get market overview first
    market_overview = ""
    if not args.no_market:
        print("\nFetching market overview...")
        try:
            market_data = fetch_market_overview()
            market_overview = market_data["overview"]
            print("\n--- MARKET OVERVIEW ---")
            print(market_overview)
            print_separator()
        except Exception as e:
            print(f"Warning: Could not fetch market overview: {e}")
            print("Continuing with ticker analysis...")

    # Analyze each ticker
    results = []
    for ticker in tickers:
        try:
            print(f"\n--- ANALYZING {ticker} ---")
            result = analyze_ticker(ticker, market_overview)
            results.append(result)

            print("\n[News Analysis]")
            print(result["news"]["analysis"][:2000])
            if len(result["news"]["analysis"]) > 2000:
                print("... (truncated)")

            print("\n[Trading Signal]")
            print(result["signal"]["raw"])

        except Exception as e:
            print(f"Error analyzing {ticker}: {e}")
            continue

    # Summary
    print_separator()
    print("SIGNAL SUMMARY")
    print("-" * 40)

    actionable = []
    for result in results:
        signal = result["signal"]
        print_signal_summary(signal)
        if signal["confidence"] >= MIN_SIGNAL_SCORE and signal["direction"] != "NEUTRAL":
            actionable.append(signal)

    if actionable:
        print("\n" + "=" * 40)
        print(f"ACTIONABLE SIGNALS: {len(actionable)}")
        for s in actionable:
            print(f"  - {s['ticker']}: {s['direction']} ({s['confidence']:.0%})")
    else:
        print("\nNo actionable signals above threshold.")

    print("\n[Done]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
