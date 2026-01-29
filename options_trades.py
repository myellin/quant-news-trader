#!/usr/bin/env python3
"""
Options Trade Generator - Specific, actionable trades.

Output: Exact options to buy/sell with entry, exit, stop.
No fluff. Just trades.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
from analysis import generate_signal


@dataclass
class OptionTrade:
    """A specific options trade recommendation."""
    ticker: str
    direction: str          # BULLISH or BEARISH
    strategy: str           # BUY_CALL, BUY_PUT, SELL_PUT_SPREAD, etc.

    # The specific contract
    contract: str           # e.g., "NVDA 2/21 $180 Call"
    strike: float
    expiration: str
    option_type: str        # call or put

    # Prices
    current_stock_price: float
    option_bid: float
    option_ask: float
    entry_price: float      # Mid price or limit

    # Targets
    stock_target: float     # Where stock needs to go
    option_target: float    # Exit option at this price
    option_stop: float      # Stop loss on option

    # Risk/Reward
    risk_dollars: float     # Max loss per contract
    reward_dollars: float   # Target profit per contract
    risk_reward: float

    # Sizing
    contracts_for_500: int  # How many contracts for ~$500 risk
    contracts_for_1000: int # How many contracts for ~$1000 risk

    # Timing
    entry_trigger: str      # When to enter
    exit_trigger: str       # When to exit
    max_hold_days: int      # Don't hold longer than this

    # Confidence
    confidence: str         # HIGH, MEDIUM, LOW
    reason: str


def get_options_chain(ticker: str, weeks_out: int = 3) -> tuple:
    """Get options chain for a ticker."""
    stock = yf.Ticker(ticker)

    # Get available expiration dates
    expirations = stock.options
    if not expirations:
        return None, None, None

    # Find expiration ~2-4 weeks out (sweet spot for swing trades)
    target_date = datetime.now() + timedelta(weeks=weeks_out)

    best_exp = None
    min_diff = float('inf')
    for exp in expirations:
        exp_date = datetime.strptime(exp, '%Y-%m-%d')
        diff = abs((exp_date - target_date).days)
        if diff < min_diff:
            min_diff = diff
            best_exp = exp

    if not best_exp:
        return None, None, None

    # Get the chain
    chain = stock.option_chain(best_exp)
    return chain.calls, chain.puts, best_exp


def find_best_call(ticker: str, signal, stock_price: float, target_price: float) -> Optional[OptionTrade]:
    """Find the best call option for a bullish trade."""
    calls, puts, expiration = get_options_chain(ticker, weeks_out=3)
    if calls is None or calls.empty:
        return None

    # Calculate days to expiration
    exp_date = datetime.strptime(expiration, '%Y-%m-%d')
    dte = (exp_date - datetime.now()).days

    # Look for strikes slightly OTM (2-5% above current price)
    # This gives leverage while not being too risky
    target_strike_low = stock_price * 0.98   # Slightly ITM
    target_strike_high = stock_price * 1.05  # Slightly OTM

    # Filter to reasonable strikes
    candidates = calls[
        (calls['strike'] >= target_strike_low) &
        (calls['strike'] <= target_strike_high) &
        (calls['bid'] > 0.10) &  # Has liquidity
        (calls['ask'] - calls['bid']) / calls['ask'] < 0.15  # Tight spread
    ].copy()

    if candidates.empty:
        # Broaden search
        candidates = calls[
            (calls['strike'] >= stock_price * 0.95) &
            (calls['strike'] <= stock_price * 1.10) &
            (calls['bid'] > 0.05)
        ].copy()

    if candidates.empty:
        return None

    # Score each option
    def score_option(row):
        strike = row['strike']
        bid = row['bid']
        ask = row['ask']
        mid = (bid + ask) / 2

        # Calculate intrinsic and extrinsic value
        intrinsic = max(0, stock_price - strike)
        extrinsic = mid - intrinsic

        # Calculate potential profit if stock hits target
        value_at_target = max(0, target_price - strike)
        potential_profit = value_at_target - mid

        # Risk/reward
        rr = potential_profit / mid if mid > 0 else 0

        # Prefer options with good R:R and reasonable premium
        score = rr * 10

        # Penalty for wide spreads
        spread_pct = (ask - bid) / ask if ask > 0 else 1
        score -= spread_pct * 20

        # Slight preference for ATM (higher delta)
        distance_from_atm = abs(strike - stock_price) / stock_price
        score -= distance_from_atm * 10

        return score

    candidates['score'] = candidates.apply(score_option, axis=1)
    best = candidates.loc[candidates['score'].idxmax()]

    # Calculate trade parameters
    strike = best['strike']
    bid = best['bid']
    ask = best['ask']
    entry = round((bid + ask) / 2, 2)  # Mid price

    # Option price if stock hits target (simplified)
    # Assume ~70% of move captured in option price
    intrinsic_at_target = max(0, target_price - strike)
    option_target = round(intrinsic_at_target * 0.85, 2)  # Conservative

    # Stop loss: 50% of premium
    option_stop = round(entry * 0.5, 2)

    risk = entry
    reward = option_target - entry
    rr = round(reward / risk, 1) if risk > 0 else 0

    # Position sizing
    contracts_500 = max(1, int(500 / (entry * 100)))
    contracts_1000 = max(1, int(1000 / (entry * 100)))

    # Entry trigger
    if signal.signal == "BUY_NOW":
        entry_trigger = "Enter now at limit price"
    else:
        entry_trigger = f"Enter when stock pulls back to ${signal.entry_price:.2f}"

    # Confidence based on R:R and signal strength
    if rr >= 2 and signal.score >= 40:
        confidence = "HIGH"
    elif rr >= 1.5 and signal.score >= 20:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    contract_name = f"{ticker} {exp_date.strftime('%m/%d')} ${strike:.0f} Call"

    return OptionTrade(
        ticker=ticker,
        direction="BULLISH",
        strategy="BUY_CALL",
        contract=contract_name,
        strike=strike,
        expiration=expiration,
        option_type="call",
        current_stock_price=stock_price,
        option_bid=bid,
        option_ask=ask,
        entry_price=entry,
        stock_target=target_price,
        option_target=option_target,
        option_stop=option_stop,
        risk_dollars=round(entry * 100, 2),
        reward_dollars=round(reward * 100, 2),
        risk_reward=rr,
        contracts_for_500=contracts_500,
        contracts_for_1000=contracts_1000,
        entry_trigger=entry_trigger,
        exit_trigger=f"Exit when option hits ${option_target:.2f} OR stock hits ${target_price:.2f}",
        max_hold_days=min(dte - 5, 14),  # Exit 5 days before expiry
        confidence=confidence,
        reason=f"Score {signal.score:+.0f}, R:R {rr}:1, {dte} DTE"
    )


def find_best_put(ticker: str, signal, stock_price: float, target_price: float) -> Optional[OptionTrade]:
    """Find the best put option for a bearish trade."""
    calls, puts, expiration = get_options_chain(ticker, weeks_out=3)
    if puts is None or puts.empty:
        return None

    exp_date = datetime.strptime(expiration, '%Y-%m-%d')
    dte = (exp_date - datetime.now()).days

    # Look for strikes slightly OTM puts
    target_strike_low = stock_price * 0.95
    target_strike_high = stock_price * 1.02

    candidates = puts[
        (puts['strike'] >= target_strike_low) &
        (puts['strike'] <= target_strike_high) &
        (puts['bid'] > 0.10)
    ].copy()

    if candidates.empty:
        candidates = puts[
            (puts['strike'] >= stock_price * 0.90) &
            (puts['strike'] <= stock_price * 1.05) &
            (puts['bid'] > 0.05)
        ].copy()

    if candidates.empty:
        return None

    # Score options
    def score_put(row):
        strike = row['strike']
        bid = row['bid']
        ask = row['ask']
        mid = (bid + ask) / 2

        value_at_target = max(0, strike - target_price)
        potential_profit = value_at_target - mid
        rr = potential_profit / mid if mid > 0 else 0

        score = rr * 10
        spread_pct = (ask - bid) / ask if ask > 0 else 1
        score -= spread_pct * 20

        return score

    candidates['score'] = candidates.apply(score_put, axis=1)
    best = candidates.loc[candidates['score'].idxmax()]

    strike = best['strike']
    bid = best['bid']
    ask = best['ask']
    entry = round((bid + ask) / 2, 2)

    intrinsic_at_target = max(0, strike - target_price)
    option_target = round(intrinsic_at_target * 0.85, 2)
    option_stop = round(entry * 0.5, 2)

    risk = entry
    reward = option_target - entry
    rr = round(reward / risk, 1) if risk > 0 else 0

    contracts_500 = max(1, int(500 / (entry * 100)))
    contracts_1000 = max(1, int(1000 / (entry * 100)))

    confidence = "HIGH" if rr >= 2 else "MEDIUM" if rr >= 1.5 else "LOW"
    contract_name = f"{ticker} {exp_date.strftime('%m/%d')} ${strike:.0f} Put"

    return OptionTrade(
        ticker=ticker,
        direction="BEARISH",
        strategy="BUY_PUT",
        contract=contract_name,
        strike=strike,
        expiration=expiration,
        option_type="put",
        current_stock_price=stock_price,
        option_bid=bid,
        option_ask=ask,
        entry_price=entry,
        stock_target=target_price,
        option_target=option_target,
        option_stop=option_stop,
        risk_dollars=round(entry * 100, 2),
        reward_dollars=round(reward * 100, 2),
        risk_reward=rr,
        contracts_for_500=contracts_500,
        contracts_for_1000=contracts_1000,
        entry_trigger="Enter on bounce to resistance",
        exit_trigger=f"Exit when option hits ${option_target:.2f}",
        max_hold_days=min(dte - 5, 14),
        confidence=confidence,
        reason=f"Bearish signal, R:R {rr}:1"
    )


def generate_trades(watchlist: list) -> list:
    """Generate option trades for watchlist."""
    trades = []

    for ticker in watchlist:
        try:
            signal = generate_signal(ticker)
            stock = yf.Ticker(ticker)
            stock_price = stock.fast_info.get('lastPrice', 0)

            if stock_price == 0:
                continue

            # Bullish setups
            if signal.score >= 20 and signal.signal in ["BUY_NOW", "BUY_PULLBACK"]:
                trade = find_best_call(ticker, signal, stock_price, signal.target_1)
                if trade and trade.risk_reward >= 1.5:
                    trades.append(trade)

            # Bearish setups
            elif signal.score <= -20:
                target_down = stock_price * 0.92  # 8% downside target
                trade = find_best_put(ticker, signal, stock_price, target_down)
                if trade and trade.risk_reward >= 1.5:
                    trades.append(trade)

        except Exception as e:
            print(f"  {ticker}: Error - {e}")

    return trades


def print_trade(trade: OptionTrade):
    """Print a single trade recommendation."""
    conf_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "⚪"}.get(trade.confidence, "⚪")

    print(f"""
{'='*60}
{conf_emoji} {trade.contract}
{'='*60}
Direction: {trade.direction}
Confidence: {trade.confidence}

STOCK
  Current: ${trade.current_stock_price:.2f}
  Target:  ${trade.stock_target:.2f} ({((trade.stock_target/trade.current_stock_price)-1)*100:+.1f}%)

OPTION
  Bid/Ask: ${trade.option_bid:.2f} / ${trade.option_ask:.2f}
  >>> ENTRY: ${trade.entry_price:.2f} (use limit order)
  >>> TARGET: ${trade.option_target:.2f} ({((trade.option_target/trade.entry_price)-1)*100:+.0f}% gain)
  >>> STOP: ${trade.option_stop:.2f} ({((trade.option_stop/trade.entry_price)-1)*100:.0f}% loss)

RISK/REWARD
  Risk per contract: ${trade.risk_dollars:.0f}
  Reward per contract: ${trade.reward_dollars:.0f}
  R:R Ratio: {trade.risk_reward}:1

POSITION SIZE
  $500 risk = {trade.contracts_for_500} contract(s)
  $1000 risk = {trade.contracts_for_1000} contract(s)

WHEN TO ENTER
  {trade.entry_trigger}

WHEN TO EXIT
  {trade.exit_trigger}
  Max hold: {trade.max_hold_days} days (exit before expiry)

WHY: {trade.reason}
""")


def print_trades_summary(trades: list):
    """Print summary of all trades."""
    print("\n" + "=" * 60)
    print("TODAY'S OPTIONS TRADES")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    if not trades:
        print("\nNo high-confidence trades today. Be patient.")
        return

    # Sort by confidence and R:R
    trades.sort(key=lambda x: (
        {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(x.confidence, 0),
        x.risk_reward
    ), reverse=True)

    # Summary table
    print(f"\n{'Ticker':<8} {'Contract':<25} {'Entry':>8} {'Target':>8} {'R:R':>6} {'Conf':<8}")
    print("-" * 70)

    for t in trades:
        print(f"{t.ticker:<8} {t.contract:<25} ${t.entry_price:>6.2f} ${t.option_target:>6.2f} {t.risk_reward:>5.1f}:1 {t.confidence:<8}")

    # Print top trades in detail
    print("\n" + "=" * 60)
    print("TOP TRADES (Details)")
    print("=" * 60)

    for trade in trades[:5]:
        print_trade(trade)


def main():
    """Generate today's options trades."""
    watchlist = [
        "NVDA", "MU", "BABA", "ALB", "INTC", "SLV",
        "GOOGL", "AMZN", "AMD", "GOLD", "TXN", "FCX",
        "JD", "PDD", "VZ", "TSLA"
    ]

    print("Scanning for options trades...")
    trades = generate_trades(watchlist)
    print_trades_summary(trades)


if __name__ == "__main__":
    main()
