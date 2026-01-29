#!/usr/bin/env python3
"""
Value Scanner - Find undervalued stocks.

Criteria:
- Low P/E ratio vs sector/market
- Low P/B ratio
- Low P/S ratio
- Analyst price targets significantly above current price
- Beaten down but fundamentally strong
"""

import os
import yfinance as yf
import requests
from datetime import datetime
from dotenv import load_dotenv
from analysis import generate_signal

load_dotenv()

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# Value scan universe - established companies with earnings
VALUE_UNIVERSE = [
    # Tech (profitable)
    "INTC", "CSCO", "IBM", "HPQ", "DELL", "ORCL", "QCOM", "TXN", "ADI",
    "AAPL", "MSFT", "GOOGL", "META",
    # Financials
    "JPM", "BAC", "WFC", "C", "GS", "MS", "SCHW", "BLK", "AXP", "ALLY",
    "USB", "PNC", "TFC", "COF", "DFS",
    # Energy
    "XOM", "CVX", "COP", "SLB", "OXY", "DVN", "EOG", "HAL", "BKR",
    # Healthcare
    "PFE", "BMY", "MRK", "ABBV", "GILD", "JNJ", "CVS", "CI", "HUM",
    # Consumer
    "WMT", "TGT", "COST", "KR", "DG", "DLTR", "F", "GM",
    # Industrials
    "CAT", "DE", "MMM", "GE", "HON", "RTX", "LMT", "BA",
    # Telecom/Media
    "T", "VZ", "TMUS", "CMCSA", "DIS", "WBD", "PARA",
    # REITs (value traps or opportunities)
    "O", "SPG", "PLD", "AMT", "EQIX",
    # Materials
    "ALB", "NEM", "FCX", "NUE", "CLF",
    # China (often undervalued)
    "BABA", "JD", "PDD", "BIDU",
]


def get_valuation_data(ticker: str) -> dict:
    """Get valuation metrics for a ticker."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Get price data
        hist = stock.history(period="1y")
        if len(hist) < 50:
            return None

        current = hist['Close'].iloc[-1]
        high_52w = hist['High'].max()
        low_52w = hist['Low'].min()

        # Valuation ratios
        pe_ratio = info.get('trailingPE') or info.get('forwardPE')
        pb_ratio = info.get('priceToBook')
        ps_ratio = info.get('priceToSalesTrailing12Months')
        peg_ratio = info.get('pegRatio')

        # Dividend
        div_yield = info.get('dividendYield', 0) or 0
        div_yield_pct = div_yield * 100

        # Analyst targets
        target_mean = info.get('targetMeanPrice')
        target_high = info.get('targetHighPrice')
        upside = ((target_mean - current) / current * 100) if target_mean else 0

        # Profitability
        profit_margin = info.get('profitMargins', 0) or 0
        roe = info.get('returnOnEquity', 0) or 0

        # How beaten down?
        pct_from_high = ((current - high_52w) / high_52w) * 100
        pct_from_low = ((current - low_52w) / low_52w) * 100

        return {
            'ticker': ticker,
            'name': info.get('shortName', ticker),
            'sector': info.get('sector', 'Unknown'),
            'price': current,
            'pe_ratio': pe_ratio,
            'pb_ratio': pb_ratio,
            'ps_ratio': ps_ratio,
            'peg_ratio': peg_ratio,
            'div_yield': div_yield_pct,
            'target_mean': target_mean,
            'target_high': target_high,
            'upside': upside,
            'profit_margin': profit_margin * 100 if profit_margin else 0,
            'roe': roe * 100 if roe else 0,
            'pct_from_high': pct_from_high,
            'pct_from_low': pct_from_low,
            'market_cap': info.get('marketCap', 0),
        }
    except Exception as e:
        return None


def calculate_value_score(data: dict) -> float:
    """Calculate composite value score (0-100)."""
    score = 0

    # P/E ratio (max 25 points) - lower is better
    pe = data.get('pe_ratio')
    if pe and pe > 0:
        if pe < 10:
            score += 25
        elif pe < 15:
            score += 20
        elif pe < 20:
            score += 15
        elif pe < 25:
            score += 10
        elif pe < 30:
            score += 5

    # P/B ratio (max 15 points) - lower is better
    pb = data.get('pb_ratio')
    if pb and pb > 0:
        if pb < 1:
            score += 15  # Trading below book value
        elif pb < 2:
            score += 12
        elif pb < 3:
            score += 8
        elif pb < 5:
            score += 4

    # Analyst upside (max 25 points)
    upside = data.get('upside', 0)
    if upside > 50:
        score += 25
    elif upside > 30:
        score += 20
    elif upside > 20:
        score += 15
    elif upside > 10:
        score += 10
    elif upside > 5:
        score += 5

    # Dividend yield (max 10 points)
    div = data.get('div_yield', 0)
    if div > 5:
        score += 10
    elif div > 3:
        score += 7
    elif div > 2:
        score += 5
    elif div > 1:
        score += 3

    # Beaten down from highs (max 15 points) - but not too much (value trap)
    pct_from_high = data.get('pct_from_high', 0)
    if -30 <= pct_from_high <= -10:
        score += 15  # Sweet spot - down but not destroyed
    elif -40 <= pct_from_high < -30:
        score += 10
    elif -50 <= pct_from_high < -40:
        score += 5  # Getting risky

    # Profitability (max 10 points) - must be profitable for value
    margin = data.get('profit_margin', 0)
    if margin > 20:
        score += 10
    elif margin > 10:
        score += 7
    elif margin > 5:
        score += 5
    elif margin > 0:
        score += 2

    return score


def scan_value():
    """Scan for undervalued stocks."""
    print("=" * 70)
    print("VALUE SCANNER - Undervalued Stocks")
    print(f"Scanning {len(VALUE_UNIVERSE)} tickers...")
    print("=" * 70)

    results = []

    for i, ticker in enumerate(VALUE_UNIVERSE):
        print(f"\r  Scanning {i+1}/{len(VALUE_UNIVERSE)}: {ticker}    ", end="", flush=True)

        data = get_valuation_data(ticker)
        if data:
            score = calculate_value_score(data)
            data['value_score'] = score
            results.append(data)

    print("\n")

    # Filter and sort
    value_stocks = [r for r in results if r['value_score'] >= 50]
    value_stocks.sort(key=lambda x: x['value_score'], reverse=True)

    print("TOP VALUE STOCKS (Score >= 50)")
    print("-" * 80)
    print(f"{'Ticker':<8} {'Price':>10} {'P/E':>8} {'P/B':>8} {'Upside':>10} {'Div%':>8} {'From Hi':>10} {'Score':>8}")
    print("-" * 80)

    for r in value_stocks[:15]:
        pe = f"{r['pe_ratio']:.1f}" if r['pe_ratio'] else "N/A"
        pb = f"{r['pb_ratio']:.1f}" if r['pb_ratio'] else "N/A"

        print(f"{r['ticker']:<8} ${r['price']:>9.2f} {pe:>8} {pb:>8} {r['upside']:>+9.1f}% {r['div_yield']:>7.1f}% {r['pct_from_high']:>+9.1f}% {r['value_score']:>7.0f}")

    # Get technical signals for top picks
    print("\n" + "=" * 70)
    print("TECHNICAL ANALYSIS - Top 5 Value Stocks")
    print("=" * 70)

    for r in value_stocks[:5]:
        try:
            signal = generate_signal(r['ticker'])
            print(f"\n{r['ticker']} ({r['sector']}) - Value: {r['value_score']:.0f} | Technical: {signal.score:+.0f}")
            print(f"  P/E: {r['pe_ratio']:.1f if r['pe_ratio'] else 'N/A'} | Analyst Target: ${r['target_mean']:.2f if r['target_mean'] else 'N/A'} ({r['upside']:+.1f}% upside)")
            print(f"  Signal: {signal.signal} | Entry: ${signal.entry_price:.2f}")

            if signal.score < 0:
                print(f"  ⚠️ Value trap risk - cheap but weak technicals")
            elif signal.score > 30:
                print(f"  ✅ Both value AND momentum aligning")
        except Exception as e:
            print(f"\n{r['ticker']} - Error: {e}")

    return value_stocks


def get_perplexity_value_picks():
    """Use Perplexity to find undervalued stocks from recent analysis."""
    print("\n" + "=" * 70)
    print("AI-POWERED VALUE SCAN (via Perplexity)")
    print("=" * 70)

    prompt = """Find the TOP 5 most undervalued stocks right now based on recent analyst reports and financial analysis.

Criteria:
- Trading significantly below intrinsic value or analyst targets
- Strong fundamentals (profitable, good balance sheet)
- Recent price weakness creating buying opportunity
- Not a value trap (has catalyst for rerating)

For each stock:
1. Ticker and company name
2. Current price vs analyst target (% upside)
3. Key valuation metrics (P/E, P/B) vs sector average
4. Why it's undervalued
5. What catalyst could unlock value

Focus on actionable opportunities, not just "cheap" stocks."""

    try:
        headers = {
            "Authorization": f"Bearer {os.getenv('PERPLEXITY_API_KEY')}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "sonar",
            "messages": [
                {"role": "system", "content": "You are a value investing analyst. Find genuinely undervalued stocks with catalysts."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 1500
        }
        response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()["choices"][0]["message"]["content"]
        print(result)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    # Quantitative scan
    value_stocks = scan_value()

    # AI-powered scan
    get_perplexity_value_picks()
