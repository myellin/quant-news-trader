#!/usr/bin/env python3
"""
Stock Scanner - Find opportunities using:
1. Technical analysis (our scoring system)
2. Analyst upgrades / price target hikes
3. Insider buying (Form 4 filings)
4. Politician trades (Congress disclosures)

Uses Perplexity for real-time data on upgrades, insiders, politicians.
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

from analysis import generate_signal, get_data, calculate_indicators

load_dotenv()

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar"


def get_api_key():
    key = os.getenv("PERPLEXITY_API_KEY")
    if not key:
        raise ValueError("PERPLEXITY_API_KEY not set")
    return key


def query_perplexity(prompt: str) -> str:
    """Query Perplexity API."""
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {"role": "system", "content": "You are a financial research assistant. Provide specific, factual information with dates and numbers. Be concise."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 1500
    }
    response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def scan_analyst_upgrades() -> str:
    """Find recent analyst upgrades and price target increases."""
    prompt = """List the most significant stock analyst UPGRADES and PRICE TARGET INCREASES from the last 3 days.

Focus on:
- Upgrades from major firms (Goldman, Morgan Stanley, JPMorgan, BofA, etc.)
- Significant price target raises (>10% above current price)
- Mid to large cap stocks ($10B+ market cap)

For each, provide:
- Ticker and company name
- Analyst firm
- Old rating → New rating (or old PT → new PT)
- Brief reason for upgrade
- Current stock price vs new target

Format as a list. Be specific with numbers."""

    return query_perplexity(prompt)


def scan_insider_buying() -> str:
    """Find significant insider purchases."""
    prompt = """List the most significant INSIDER BUYING (Form 4 filings) from the last 7 days.

Focus on:
- CEO, CFO, or Director purchases (not options exercises)
- Purchases over $100,000
- Cluster buying (multiple insiders buying)
- Mid to large cap stocks

For each, provide:
- Ticker and company name
- Insider name and title
- Number of shares and dollar amount
- Purchase price vs current price
- Is this their first purchase or adding to position?

Insider BUYING is bullish. Ignore insider selling. Be specific."""

    return query_perplexity(prompt)


def scan_politician_trades() -> str:
    """Find recent Congressional trading activity."""
    prompt = """List the most notable POLITICIAN STOCK TRADES disclosed in the last 14 days.

Focus on:
- US Congress members (House and Senate)
- Purchases over $50,000 (larger = more significant)
- Members on relevant committees (Finance, Tech, Defense, etc.)
- Any unusual timing relative to legislation or news

For each, provide:
- Politician name and party/state
- Ticker and company name
- Buy or Sell
- Approximate amount (they report ranges)
- Any relevant committee membership
- Any notable timing (before announcements, etc.)

Sources: Capitol Trades, Quiver Quantitative, House/Senate disclosures.

Politicians often trade on information advantage. List the buys."""

    return query_perplexity(prompt)


def scan_technical_setups(tickers: list) -> list:
    """Run technical analysis on a list of tickers."""
    results = []
    for ticker in tickers:
        try:
            signal = generate_signal(ticker)
            results.append({
                'ticker': ticker,
                'score': signal.score,
                'signal': signal.signal,
                'entry': signal.entry_price,
                'stop': signal.stop_loss,
                'target': signal.target_1,
                'rr': signal.risk_reward,
                'reasons': signal.reasons[:3]
            })
        except Exception as e:
            print(f"  Error on {ticker}: {e}")
    return results


def extract_tickers_from_text(text: str) -> list:
    """Extract stock tickers from text using common patterns."""
    import re
    # Match patterns like (AAPL), $AAPL, AAPL:, "AAPL"
    patterns = [
        r'\(([A-Z]{1,5})\)',  # (AAPL)
        r'\$([A-Z]{1,5})\b',  # $AAPL
        r'\b([A-Z]{2,5})(?:\.|\:|\s-\s)',  # AAPL: or AAPL -
        r'ticker[:\s]+([A-Z]{1,5})',  # ticker: AAPL
    ]

    tickers = set()
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            t = m.upper()
            # Filter out common false positives
            if t not in ['CEO', 'CFO', 'COO', 'IPO', 'ETF', 'NYSE', 'SEC', 'FDA', 'EPS', 'USD', 'THE', 'FOR', 'AND', 'NEW', 'BUY', 'NOW']:
                tickers.add(t)

    return list(tickers)


def run_full_scan():
    """Run complete scan and identify best opportunities."""
    print("=" * 70)
    print("OPPORTUNITY SCANNER")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    all_tickers = set()

    # === ANALYST UPGRADES ===
    print("\n" + "=" * 70)
    print("1. ANALYST UPGRADES & PRICE TARGET HIKES")
    print("=" * 70)
    try:
        upgrades = scan_analyst_upgrades()
        print(upgrades)
        tickers = extract_tickers_from_text(upgrades)
        all_tickers.update(tickers)
        print(f"\n[Extracted tickers: {', '.join(tickers)}]")
    except Exception as e:
        print(f"Error: {e}")

    # === INSIDER BUYING ===
    print("\n" + "=" * 70)
    print("2. INSIDER BUYING (Form 4)")
    print("=" * 70)
    try:
        insiders = scan_insider_buying()
        print(insiders)
        tickers = extract_tickers_from_text(insiders)
        all_tickers.update(tickers)
        print(f"\n[Extracted tickers: {', '.join(tickers)}]")
    except Exception as e:
        print(f"Error: {e}")

    # === POLITICIAN TRADES ===
    print("\n" + "=" * 70)
    print("3. POLITICIAN TRADES (Congress)")
    print("=" * 70)
    try:
        politicians = scan_politician_trades()
        print(politicians)
        tickers = extract_tickers_from_text(politicians)
        all_tickers.update(tickers)
        print(f"\n[Extracted tickers: {', '.join(tickers)}]")
    except Exception as e:
        print(f"Error: {e}")

    # === TECHNICAL ANALYSIS ON FOUND TICKERS ===
    print("\n" + "=" * 70)
    print("4. TECHNICAL ANALYSIS ON DISCOVERED TICKERS")
    print("=" * 70)

    # Add our core watchlist
    core_watchlist = ["NVDA", "MU", "TSLA", "BABA"]
    all_tickers.update(core_watchlist)

    print(f"\nAnalyzing {len(all_tickers)} tickers: {', '.join(sorted(all_tickers))}\n")

    results = scan_technical_setups(list(all_tickers))

    # Sort by score
    results.sort(key=lambda x: x['score'], reverse=True)

    print("\nRANKED BY TECHNICAL SCORE:")
    print("-" * 70)
    print(f"{'Ticker':<8} {'Score':>6} {'Signal':<15} {'Entry':>10} {'Stop':>10} {'Target':>10} {'R:R':>6}")
    print("-" * 70)

    for r in results:
        print(f"{r['ticker']:<8} {r['score']:>+6.0f} {r['signal']:<15} ${r['entry']:>9.2f} ${r['stop']:>9.2f} ${r['target']:>9.2f} {r['rr']:>5.1f}:1")

    # === TOP PICKS ===
    print("\n" + "=" * 70)
    print("TOP PICKS (Score >= 30)")
    print("=" * 70)

    top_picks = [r for r in results if r['score'] >= 30]
    if top_picks:
        for r in top_picks:
            print(f"\n{r['ticker']} (Score: {r['score']:+.0f})")
            print(f"  Signal: {r['signal']}")
            print(f"  Entry: ${r['entry']:.2f} | Stop: ${r['stop']:.2f} | Target: ${r['target']:.2f}")
            print(f"  Why: {'; '.join(r['reasons'][:2])}")
    else:
        print("No strong setups found. Be patient.")

    # === ACTIONABLE NOW ===
    buy_now = [r for r in results if r['signal'] == 'BUY_NOW' and r['score'] >= 30]
    if buy_now:
        print("\n" + "=" * 70)
        print("🎯 ACTIONABLE NOW")
        print("=" * 70)
        for r in buy_now:
            print(f"\n{r['ticker']}: BUY at ${r['entry']:.2f}")
            print(f"  Stop: ${r['stop']:.2f} | Target: ${r['target']:.2f}")

    return results


if __name__ == "__main__":
    run_full_scan()
