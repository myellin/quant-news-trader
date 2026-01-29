#!/usr/bin/env python3
"""
Momentum Scanner - Find stocks on a tear.

Criteria:
- Up >15% in last month
- Near 52-week high (within 10%)
- Above all major moving averages
- High relative strength vs SPY
- Strong volume confirmation
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from analysis import generate_signal

# Universe to scan - liquid mid/large caps
SCAN_UNIVERSE = [
    # Tech
    "NVDA", "AMD", "AVGO", "MRVL", "QCOM", "INTC", "MU", "AMAT", "LRCX", "KLAC",
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NFLX", "CRM", "NOW", "ADBE", "ORCL",
    "PLTR", "SNOW", "DDOG", "NET", "CRWD", "ZS", "PANW", "FTNT",
    # AI / Tech Infrastructure
    "SMCI", "ARM", "DELL", "HPE", "CDNS", "SNPS",
    # Semis
    "TSM", "ASML", "ON", "MCHP", "ADI", "TXN",
    # EV / Auto
    "TSLA", "RIVN", "LCID", "F", "GM", "TM",
    # China
    "BABA", "JD", "PDD", "BIDU", "NIO", "XPEV", "LI",
    # Financials
    "JPM", "BAC", "GS", "MS", "C", "WFC", "SCHW", "BLK", "ALLY",
    # Energy
    "XOM", "CVX", "COP", "SLB", "OXY", "DVN", "EOG",
    # Commodities / Materials
    "ALB", "GOLD", "NEM", "FCX", "AA",
    # Healthcare
    "UNH", "JNJ", "PFE", "MRNA", "LLY", "NVO", "ABBV",
    # Consumer
    "COST", "WMT", "TGT", "HD", "LOW", "NKE", "SBUX",
    # ETFs
    "SPY", "QQQ", "IWM", "XLF", "XLE", "XLK", "GLD", "SLV",
]


def get_momentum_data(ticker: str) -> dict:
    """Get momentum metrics for a ticker."""
    try:
        stock = yf.Ticker(ticker)

        # Get price history
        hist = stock.history(period="1y")
        if len(hist) < 50:
            return None

        current = hist['Close'].iloc[-1]

        # Performance metrics
        price_1w = hist['Close'].iloc[-5] if len(hist) >= 5 else current
        price_1m = hist['Close'].iloc[-21] if len(hist) >= 21 else current
        price_3m = hist['Close'].iloc[-63] if len(hist) >= 63 else current
        price_6m = hist['Close'].iloc[-126] if len(hist) >= 126 else current

        perf_1w = ((current - price_1w) / price_1w) * 100
        perf_1m = ((current - price_1m) / price_1m) * 100
        perf_3m = ((current - price_3m) / price_3m) * 100
        perf_6m = ((current - price_6m) / price_6m) * 100

        # 52-week high/low
        high_52w = hist['High'].max()
        low_52w = hist['Low'].min()
        pct_from_high = ((current - high_52w) / high_52w) * 100
        pct_from_low = ((current - low_52w) / low_52w) * 100

        # Moving averages
        sma_20 = hist['Close'].rolling(20).mean().iloc[-1]
        sma_50 = hist['Close'].rolling(50).mean().iloc[-1]
        sma_200 = hist['Close'].rolling(200).mean().iloc[-1] if len(hist) >= 200 else sma_50

        above_20 = current > sma_20
        above_50 = current > sma_50
        above_200 = current > sma_200

        # Volume
        avg_vol = hist['Volume'].rolling(20).mean().iloc[-1]
        recent_vol = hist['Volume'].iloc[-5:].mean()
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1

        return {
            'ticker': ticker,
            'price': current,
            'perf_1w': perf_1w,
            'perf_1m': perf_1m,
            'perf_3m': perf_3m,
            'perf_6m': perf_6m,
            'pct_from_high': pct_from_high,
            'pct_from_low': pct_from_low,
            'above_20': above_20,
            'above_50': above_50,
            'above_200': above_200,
            'vol_ratio': vol_ratio,
        }
    except Exception as e:
        return None


def calculate_momentum_score(data: dict) -> float:
    """Calculate composite momentum score (0-100)."""
    score = 0

    # Performance (max 40 points)
    if data['perf_1m'] > 20:
        score += 20
    elif data['perf_1m'] > 10:
        score += 15
    elif data['perf_1m'] > 5:
        score += 10
    elif data['perf_1m'] > 0:
        score += 5

    if data['perf_3m'] > 30:
        score += 20
    elif data['perf_3m'] > 15:
        score += 15
    elif data['perf_3m'] > 5:
        score += 10

    # Near 52-week high (max 25 points)
    if data['pct_from_high'] > -5:
        score += 25  # Within 5% of high
    elif data['pct_from_high'] > -10:
        score += 20
    elif data['pct_from_high'] > -20:
        score += 10

    # MA alignment (max 20 points)
    if data['above_20']:
        score += 7
    if data['above_50']:
        score += 7
    if data['above_200']:
        score += 6

    # Volume confirmation (max 15 points)
    if data['vol_ratio'] > 1.5:
        score += 15
    elif data['vol_ratio'] > 1.2:
        score += 10
    elif data['vol_ratio'] > 1.0:
        score += 5

    return score


def scan_momentum():
    """Scan for momentum stocks."""
    print("=" * 70)
    print("MOMENTUM SCANNER - Stocks on a Tear")
    print(f"Scanning {len(SCAN_UNIVERSE)} tickers...")
    print("=" * 70)

    results = []

    for i, ticker in enumerate(SCAN_UNIVERSE):
        print(f"\r  Scanning {i+1}/{len(SCAN_UNIVERSE)}: {ticker}    ", end="", flush=True)

        data = get_momentum_data(ticker)
        if data:
            score = calculate_momentum_score(data)
            data['momentum_score'] = score
            results.append(data)

    print("\n")

    # Filter and sort
    momentum_stocks = [r for r in results if r['momentum_score'] >= 60]
    momentum_stocks.sort(key=lambda x: x['momentum_score'], reverse=True)

    print("TOP MOMENTUM STOCKS (Score >= 60)")
    print("-" * 70)
    print(f"{'Ticker':<8} {'Price':>10} {'1W':>8} {'1M':>8} {'3M':>8} {'From Hi':>10} {'Score':>8}")
    print("-" * 70)

    for r in momentum_stocks[:15]:
        print(f"{r['ticker']:<8} ${r['price']:>9.2f} {r['perf_1w']:>+7.1f}% {r['perf_1m']:>+7.1f}% {r['perf_3m']:>+7.1f}% {r['pct_from_high']:>+9.1f}% {r['momentum_score']:>7.0f}")

    # Get technical signals for top picks
    print("\n" + "=" * 70)
    print("TECHNICAL ANALYSIS - Top 5 Momentum Stocks")
    print("=" * 70)

    for r in momentum_stocks[:5]:
        try:
            signal = generate_signal(r['ticker'])
            print(f"\n{r['ticker']} - Momentum: {r['momentum_score']:.0f} | Technical: {signal.score:+.0f}")
            print(f"  Signal: {signal.signal} | Entry: ${signal.entry_price:.2f} | Stop: ${signal.stop_loss:.2f}")

            if signal.score < 0:
                print(f"  ⚠️ WARNING: Strong momentum but weak technicals - could be overextended")
        except Exception as e:
            print(f"\n{r['ticker']} - Error: {e}")

    return momentum_stocks


if __name__ == "__main__":
    scan_momentum()
