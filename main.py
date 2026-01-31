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
from silver_strategy import generate_silver_signal, print_silver_signal, MacroContext


# Ticker to company name mapping
TICKER_NAMES = {
    "NVDA": "NVIDIA Corporation",
    "MU": "Micron Technology",
    "TSLA": "Tesla Inc",
    "BABA": "Alibaba Group",
    "SLV": "iShares Silver Trust",
    "GOLD": "Barrick Gold Corporation",
    "GLD": "SPDR Gold Trust",
}

# Precious metals tickers that use specialized strategy
PRECIOUS_METALS = ["SLV", "GOLD", "GLD"]


def print_separator():
    print("\n" + "=" * 70 + "\n")


def analyze_silver(market_overview: str) -> dict:
    """
    Run specialized silver analysis using silver_strategy module.
    Uses current market data and macro context.
    """
    print("Running specialized silver strategy analysis...")

    # Parse macro context from market overview if available
    macro = None
    if market_overview:
        overview_lower = market_overview.lower()
        dxy = "strengthening" if "dollar strength" in overview_lower or "dxy up" in overview_lower else (
            "weakening" if "dollar weak" in overview_lower or "dxy down" in overview_lower else "neutral"
        )
        fed = "hawkish" if "hawkish" in overview_lower else (
            "dovish" if "dovish" in overview_lower else "neutral"
        )
        yields_trend = "rising" if "yields rising" in overview_lower or "yields up" in overview_lower else (
            "falling" if "yields falling" in overview_lower or "yields down" in overview_lower else "stable"
        )
        geo = "elevated" if "geopolitical" in overview_lower or "tension" in overview_lower else "normal"
        risk = "risk_off" if "risk-off" in overview_lower or "risk off" in overview_lower else "risk_on"

        macro = MacroContext(
            dxy_trend=dxy,
            fed_stance=fed,
            real_yields_trend=yields_trend,
            geopolitical_risk=geo,
            risk_appetite=risk
        )

    # For now, use placeholder values - in production these come from yfinance
    # These represent the Jan 2026 crash scenario
    signal = generate_silver_signal(
        silver_price=80.0,        # Would fetch from yfinance
        gold_price=2800.0,        # Would fetch from yfinance
        silver_high_52w=121.0,    # Would fetch from yfinance
        daily_change_pct=-28.0,   # Would calculate from yfinance
        volume_ratio=5.0,         # Would calculate from yfinance
        rsi=18.0,                 # Would calculate
        atr=3.5,                  # Would calculate
        macro=macro
    )

    return {
        "ticker": "SLV",
        "signal": signal,
        "is_silver_strategy": True
    }


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

            # Use specialized silver strategy for precious metals
            if ticker == "SLV":
                result = analyze_silver(market_overview)
                results.append(result)
                print_silver_signal(result["signal"])
                continue

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
        # Handle silver strategy results separately
        if result.get("is_silver_strategy"):
            sig = result["signal"]
            conf_map = {"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.4}
            conf = conf_map.get(sig.confidence, 0.5)
            direction = "BULLISH" if sig.signal_type in ["BUY_CRASH", "BUY_PULLBACK"] else (
                "BEARISH" if sig.signal_type == "SELL" else "NEUTRAL"
            )
            print(f"\nSLV: [{'+' if direction == 'BULLISH' else '-' if direction == 'BEARISH' else '='}] {direction} ({conf:.0%})")
            print(f"  Signal: {sig.signal_type} | Entry: ${sig.entry_price} | Stop: ${sig.stop_loss}")
            print(f"  Macro: {sig.macro_bias} | G/S Ratio: {sig.gold_silver_ratio}")
            if sig.signal_type in ["BUY_CRASH", "BUY_PULLBACK"] and conf >= MIN_SIGNAL_SCORE:
                actionable.append({"ticker": "SLV", "direction": direction, "confidence": conf})
            continue

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
