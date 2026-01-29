#!/usr/bin/env python3
"""
Smart Entry Calculator - Don't just buy at market price.

Principles:
1. NEVER chase - if you missed the move, wait for pullback
2. SCALE IN - don't go 100% at once
3. REQUIRE 2:1+ R:R - anything less isn't worth it
4. USE LIMIT ORDERS - at support, not market orders
5. WAIT FOR CONFIRMATION - bouncing off support, not just touching it
"""

import yfinance as yf
from analysis import generate_signal, get_data, calculate_indicators


def calculate_smart_entry(ticker: str) -> dict:
    """
    Calculate optimal entry strategy for a ticker.

    Returns entry plan with:
    - Limit order prices (not market)
    - Scale-in levels (3 tranches)
    - R:R for each level
    - Confirmation signals to watch for
    """
    signal = generate_signal(ticker)
    df = get_data(ticker, period="3mo")
    df = calculate_indicators(df)

    latest = df.iloc[-1]
    current_price = latest['Close']
    atr = latest['ATR']

    # Find key support levels
    recent_low = df['Low'].tail(20).min()
    sma_20 = latest['SMA_20']
    sma_50 = latest['SMA_50']
    bb_lower = latest['BB_Lower']

    # Calculate entry levels (scale in at 3 levels)
    entry_1 = min(sma_20, current_price * 0.98)  # First tranche: 20 MA or 2% below
    entry_2 = min(sma_50, current_price * 0.95)  # Second tranche: 50 MA or 5% below
    entry_3 = max(recent_low, bb_lower)           # Third tranche: recent low or BB lower

    # Stop loss below all entries
    stop_loss = entry_3 - (atr * 1.5)

    # Calculate R:R for each entry
    def calc_rr(entry, stop, target):
        risk = entry - stop
        reward = target - entry
        return reward / risk if risk > 0 else 0

    target = current_price + (atr * 4)  # 4 ATR target

    rr_1 = calc_rr(entry_1, stop_loss, target)
    rr_2 = calc_rr(entry_2, stop_loss, target)
    rr_3 = calc_rr(entry_3, stop_loss, target)

    # Overall assessment
    distance_to_entry_1 = ((current_price - entry_1) / entry_1) * 100

    if distance_to_entry_1 < 1:
        action = "WAIT - Price at entry level, wait for bounce confirmation"
    elif distance_to_entry_1 < 3:
        action = "SET LIMITS - Place limit orders at entry levels"
    else:
        action = "MONITOR - Wait for price to approach entry levels"

    return {
        'ticker': ticker,
        'current_price': current_price,
        'signal': signal.signal,
        'score': signal.score,
        'atr': atr,

        # Entry levels (scale in)
        'entry_1': {
            'price': round(entry_1, 2),
            'allocation': '40%',
            'rr': round(rr_1, 1),
            'distance': round(distance_to_entry_1, 1),
        },
        'entry_2': {
            'price': round(entry_2, 2),
            'allocation': '30%',
            'rr': round(rr_2, 1),
            'distance': round(((current_price - entry_2) / entry_2) * 100, 1),
        },
        'entry_3': {
            'price': round(entry_3, 2),
            'allocation': '30%',
            'rr': round(rr_3, 1),
            'distance': round(((current_price - entry_3) / entry_3) * 100, 1),
        },

        'stop_loss': round(stop_loss, 2),
        'target': round(target, 2),

        'action': action,

        # Confirmation signals
        'confirmations': [
            f"RSI bouncing from oversold (currently {latest['RSI']:.0f})",
            f"Price holding above ${entry_1:.2f} (20 MA)",
            "Green candle with increasing volume",
            "MACD histogram turning positive",
        ]
    }


def print_entry_plan(plan: dict):
    """Print the entry plan."""
    print(f"\n{'='*60}")
    print(f"SMART ENTRY PLAN: {plan['ticker']}")
    print(f"{'='*60}")

    print(f"\nCurrent Price: ${plan['current_price']:.2f}")
    print(f"Signal: {plan['signal']} (Score: {plan['score']:+.0f})")
    print(f"Daily ATR: ${plan['atr']:.2f} ({plan['atr']/plan['current_price']*100:.1f}%)")

    print(f"\n>>> {plan['action']}")

    print(f"\n{'─'*60}")
    print("SCALE-IN LEVELS (Don't go all in at once!)")
    print(f"{'─'*60}")

    for i, key in enumerate(['entry_1', 'entry_2', 'entry_3'], 1):
        e = plan[key]
        status = "✅ AT LEVEL" if e['distance'] < 1 else f"↓ {e['distance']:.1f}% away"
        rr_status = "✅" if e['rr'] >= 2 else "⚠️" if e['rr'] >= 1.5 else "❌"
        print(f"\n  Entry {i}: ${e['price']:.2f} ({e['allocation']} of position)")
        print(f"    Distance: {status}")
        print(f"    R:R at this level: {e['rr']:.1f}:1 {rr_status}")

    print(f"\n{'─'*60}")
    print("RISK MANAGEMENT")
    print(f"{'─'*60}")
    print(f"  Stop Loss: ${plan['stop_loss']:.2f}")
    print(f"  Target: ${plan['target']:.2f}")

    avg_entry = (plan['entry_1']['price'] * 0.4 +
                 plan['entry_2']['price'] * 0.3 +
                 plan['entry_3']['price'] * 0.3)
    avg_rr = (plan['target'] - avg_entry) / (avg_entry - plan['stop_loss'])
    print(f"  Average Entry (if all filled): ${avg_entry:.2f}")
    print(f"  Blended R:R: {avg_rr:.1f}:1")

    print(f"\n{'─'*60}")
    print("CONFIRMATION SIGNALS (Wait for these before entry)")
    print(f"{'─'*60}")
    for c in plan['confirmations']:
        print(f"  • {c}")

    print(f"\n{'─'*60}")
    print("⚠️  RULES")
    print(f"{'─'*60}")
    print("  1. Use LIMIT orders, not market orders")
    print("  2. Don't chase if it rips without you")
    print("  3. Scale in - don't go 100% at first level")
    print("  4. Move stop to breakeven after 1R profit")
    print("  5. Take partial profits at Target 1")


def main():
    """Calculate entry plans for watchlist."""
    watchlist = ["NVDA", "MU", "BABA", "GOOGL", "INTC", "ALB"]

    print("=" * 60)
    print("SMART ENTRY CALCULATOR")
    print("=" * 60)
    print("Calculating optimal entry levels...")

    for ticker in watchlist:
        try:
            plan = calculate_smart_entry(ticker)
            print_entry_plan(plan)
        except Exception as e:
            print(f"\n{ticker}: Error - {e}")


if __name__ == "__main__":
    main()
