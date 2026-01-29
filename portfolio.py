#!/usr/bin/env python3
"""
Paper Trading Portfolio - Track all trades and performance.

Features:
1. Log every trade recommendation
2. Track open positions with live P&L
3. Monitor for exit signals (target/stop hit)
4. Calculate performance metrics
5. Send alerts when to sell
"""

import os
import json
import smtplib
import yfinance as yf
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).parent
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
TRADE_HISTORY_FILE = DATA_DIR / "trade_history.json"


@dataclass
class Position:
    """An open position."""
    id: str
    ticker: str
    contract: str           # e.g., "NVDA 02/21 $180 Call"
    option_type: str        # call or put
    strike: float
    expiration: str

    # Entry
    entry_date: str
    entry_price: float      # Option price paid
    contracts: int
    cost_basis: float       # Total cost

    # Targets
    target_price: float     # Option exit target
    stop_price: float       # Option stop loss
    stock_target: float     # Stock price target

    # Current
    current_price: float = 0
    current_value: float = 0
    pnl_dollars: float = 0
    pnl_percent: float = 0

    # Status
    status: str = "OPEN"    # OPEN, CLOSED_WIN, CLOSED_LOSS, CLOSED_EXPIRED


@dataclass
class ClosedTrade:
    """A closed trade for history."""
    id: str
    ticker: str
    contract: str
    option_type: str

    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    contracts: int

    pnl_dollars: float
    pnl_percent: float
    result: str             # WIN, LOSS, BREAKEVEN
    exit_reason: str        # TARGET, STOP, MANUAL, EXPIRED


def load_portfolio() -> List[Position]:
    """Load open positions."""
    if not PORTFOLIO_FILE.exists():
        return []
    with open(PORTFOLIO_FILE) as f:
        data = json.load(f)
    return [Position(**p) for p in data.get("positions", [])]


def save_portfolio(positions: List[Position]):
    """Save open positions."""
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump({"positions": [asdict(p) for p in positions]}, f, indent=2)


def load_trade_history() -> List[ClosedTrade]:
    """Load closed trades."""
    if not TRADE_HISTORY_FILE.exists():
        return []
    with open(TRADE_HISTORY_FILE) as f:
        data = json.load(f)
    return [ClosedTrade(**t) for t in data.get("trades", [])]


def save_trade_history(trades: List[ClosedTrade]):
    """Save closed trades."""
    with open(TRADE_HISTORY_FILE, "w") as f:
        json.dump({"trades": [asdict(t) for t in trades]}, f, indent=2)


def generate_trade_id() -> str:
    """Generate unique trade ID."""
    return datetime.now().strftime("%Y%m%d%H%M%S")


def send_email(subject: str, body: str):
    """Send email alert."""
    email_to = os.getenv("ALERT_EMAIL_TO")
    email_from = os.getenv("ALERT_EMAIL_FROM")
    email_password = os.getenv("ALERT_EMAIL_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.hostinger.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))

    print(f"📧 {subject}")

    if not all([email_to, email_from, email_password]):
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = email_from
        msg["To"] = email_to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(email_from, email_password)
            server.send_message(msg)
    except Exception as e:
        print(f"  Email error: {e}")


# =============================================================================
# PORTFOLIO OPERATIONS
# =============================================================================

def open_position(
    ticker: str,
    contract: str,
    option_type: str,
    strike: float,
    expiration: str,
    entry_price: float,
    contracts: int,
    target_price: float,
    stop_price: float,
    stock_target: float
) -> Position:
    """Open a new paper position."""
    position = Position(
        id=generate_trade_id(),
        ticker=ticker,
        contract=contract,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
        entry_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        entry_price=entry_price,
        contracts=contracts,
        cost_basis=entry_price * contracts * 100,
        target_price=target_price,
        stop_price=stop_price,
        stock_target=stock_target,
        current_price=entry_price,
        current_value=entry_price * contracts * 100,
        pnl_dollars=0,
        pnl_percent=0,
        status="OPEN"
    )

    positions = load_portfolio()
    positions.append(position)
    save_portfolio(positions)

    print(f"✅ Opened: {contract} x{contracts} @ ${entry_price:.2f}")
    print(f"   Cost: ${position.cost_basis:.2f}")
    print(f"   Target: ${target_price:.2f} | Stop: ${stop_price:.2f}")

    return position


def close_position(position_id: str, exit_price: float, exit_reason: str):
    """Close a position."""
    positions = load_portfolio()
    history = load_trade_history()

    position = None
    for i, p in enumerate(positions):
        if p.id == position_id:
            position = positions.pop(i)
            break

    if not position:
        print(f"Position {position_id} not found")
        return

    # Calculate P&L
    exit_value = exit_price * position.contracts * 100
    pnl_dollars = exit_value - position.cost_basis
    pnl_percent = (pnl_dollars / position.cost_basis) * 100

    result = "WIN" if pnl_dollars > 0 else "LOSS" if pnl_dollars < 0 else "BREAKEVEN"

    # Create closed trade record
    closed = ClosedTrade(
        id=position.id,
        ticker=position.ticker,
        contract=position.contract,
        option_type=position.option_type,
        entry_date=position.entry_date,
        entry_price=position.entry_price,
        exit_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        exit_price=exit_price,
        contracts=position.contracts,
        pnl_dollars=round(pnl_dollars, 2),
        pnl_percent=round(pnl_percent, 2),
        result=result,
        exit_reason=exit_reason
    )

    history.append(closed)
    save_portfolio(positions)
    save_trade_history(history)

    emoji = "🟢" if result == "WIN" else "🔴"
    print(f"{emoji} Closed: {position.contract}")
    print(f"   Entry: ${position.entry_price:.2f} → Exit: ${exit_price:.2f}")
    print(f"   P&L: ${pnl_dollars:+.2f} ({pnl_percent:+.1f}%)")
    print(f"   Reason: {exit_reason}")

    return closed


def get_option_price(ticker: str, expiration: str, strike: float, option_type: str) -> Optional[float]:
    """Get current option price."""
    try:
        stock = yf.Ticker(ticker)
        chain = stock.option_chain(expiration)

        if option_type == "call":
            options = chain.calls
        else:
            options = chain.puts

        opt = options[options['strike'] == strike]
        if opt.empty:
            return None

        bid = opt['bid'].iloc[0]
        ask = opt['ask'].iloc[0]
        return (bid + ask) / 2

    except Exception as e:
        return None


def update_positions() -> List[dict]:
    """Update all open positions with current prices."""
    positions = load_portfolio()
    alerts = []

    for pos in positions:
        # Get current option price
        price = get_option_price(pos.ticker, pos.expiration, pos.strike, pos.option_type)

        if price is None:
            # Can't get price, estimate from stock
            try:
                stock = yf.Ticker(pos.ticker)
                stock_price = stock.fast_info.get('lastPrice', 0)

                if pos.option_type == "call":
                    intrinsic = max(0, stock_price - pos.strike)
                else:
                    intrinsic = max(0, pos.strike - stock_price)

                # Rough estimate with some time value
                price = max(intrinsic * 0.9, pos.entry_price * 0.1)
            except:
                price = pos.current_price  # Keep old price

        pos.current_price = round(price, 2)
        pos.current_value = round(price * pos.contracts * 100, 2)
        pos.pnl_dollars = round(pos.current_value - pos.cost_basis, 2)
        pos.pnl_percent = round((pos.pnl_dollars / pos.cost_basis) * 100, 2)

        # Check for exit signals
        if price >= pos.target_price:
            alerts.append({
                "position": pos,
                "alert_type": "TARGET_HIT",
                "message": f"🎯 TARGET HIT: {pos.contract} at ${price:.2f} (target was ${pos.target_price:.2f})"
            })
        elif price <= pos.stop_price:
            alerts.append({
                "position": pos,
                "alert_type": "STOP_HIT",
                "message": f"🛑 STOP HIT: {pos.contract} at ${price:.2f} (stop was ${pos.stop_price:.2f})"
            })

        # Check expiration
        exp_date = datetime.strptime(pos.expiration, "%Y-%m-%d")
        days_to_exp = (exp_date - datetime.now()).days

        if days_to_exp <= 5:
            alerts.append({
                "position": pos,
                "alert_type": "EXPIRING_SOON",
                "message": f"⏰ EXPIRING: {pos.contract} expires in {days_to_exp} days - consider closing"
            })

    save_portfolio(positions)
    return alerts


def get_portfolio_summary() -> dict:
    """Get portfolio summary."""
    positions = load_portfolio()
    history = load_trade_history()

    # Open positions
    total_cost = sum(p.cost_basis for p in positions)
    total_value = sum(p.current_value for p in positions)
    total_pnl = sum(p.pnl_dollars for p in positions)

    # Closed trades
    wins = [t for t in history if t.result == "WIN"]
    losses = [t for t in history if t.result == "LOSS"]

    total_trades = len(history)
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0

    realized_pnl = sum(t.pnl_dollars for t in history)

    return {
        "open_positions": len(positions),
        "total_cost": total_cost,
        "total_value": total_value,
        "unrealized_pnl": total_pnl,
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "realized_pnl": realized_pnl,
        "total_pnl": realized_pnl + total_pnl
    }


def print_portfolio():
    """Print current portfolio."""
    positions = load_portfolio()
    summary = get_portfolio_summary()

    print("\n" + "=" * 70)
    print("PAPER TRADING PORTFOLIO")
    print(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    if not positions:
        print("\nNo open positions.")
    else:
        print(f"\n{'Contract':<30} {'Entry':>8} {'Current':>8} {'P&L':>12} {'%':>8}")
        print("-" * 70)

        for p in positions:
            pnl_emoji = "🟢" if p.pnl_dollars >= 0 else "🔴"
            print(f"{p.contract:<30} ${p.entry_price:>6.2f} ${p.current_price:>6.2f} {pnl_emoji}${p.pnl_dollars:>+8.2f} {p.pnl_percent:>+7.1f}%")

    print("\n" + "-" * 70)
    print("SUMMARY")
    print("-" * 70)
    print(f"Open Positions: {summary['open_positions']}")
    print(f"Cost Basis: ${summary['total_cost']:.2f}")
    print(f"Current Value: ${summary['total_value']:.2f}")
    print(f"Unrealized P&L: ${summary['unrealized_pnl']:+.2f}")
    print(f"\nClosed Trades: {summary['total_trades']}")
    print(f"Win Rate: {summary['win_rate']:.1f}% ({summary['wins']}W / {summary['losses']}L)")
    print(f"Realized P&L: ${summary['realized_pnl']:+.2f}")
    print(f"\nTOTAL P&L: ${summary['total_pnl']:+.2f}")


def print_trade_history():
    """Print trade history."""
    history = load_trade_history()

    print("\n" + "=" * 70)
    print("TRADE HISTORY")
    print("=" * 70)

    if not history:
        print("\nNo closed trades yet.")
        return

    print(f"\n{'Date':<12} {'Contract':<25} {'Entry':>7} {'Exit':>7} {'P&L':>10} {'Result':<8}")
    print("-" * 70)

    for t in history:
        emoji = "🟢" if t.result == "WIN" else "🔴"
        date = t.exit_date.split()[0]
        print(f"{date:<12} {t.contract:<25} ${t.entry_price:>5.2f} ${t.exit_price:>5.2f} {emoji}${t.pnl_dollars:>+7.2f} {t.result:<8}")

    # Summary
    summary = get_portfolio_summary()
    print("-" * 70)
    print(f"Total: {summary['total_trades']} trades | Win Rate: {summary['win_rate']:.1f}% | P&L: ${summary['realized_pnl']:+.2f}")


# =============================================================================
# MAIN
# =============================================================================

def monitor_positions():
    """Check positions and send alerts."""
    print(f"[{datetime.now().strftime('%H:%M')}] Updating positions...")

    alerts = update_positions()

    for alert in alerts:
        pos = alert["position"]

        if alert["alert_type"] == "TARGET_HIT":
            subject = f"🎯 SELL - Target Hit: {pos.contract}"
            body = f"""
TARGET HIT - TIME TO SELL

{pos.contract}

Entry: ${pos.entry_price:.2f}
Current: ${pos.current_price:.2f}
Target: ${pos.target_price:.2f}

P&L: ${pos.pnl_dollars:+.2f} ({pos.pnl_percent:+.1f}%)

ACTION: Close position to lock in profits.

To close in the system, run:
python3 -c "from portfolio import close_position; close_position('{pos.id}', {pos.current_price}, 'TARGET')"
"""
            send_email(subject, body)

        elif alert["alert_type"] == "STOP_HIT":
            subject = f"🛑 SELL - Stop Hit: {pos.contract}"
            body = f"""
STOP LOSS HIT - EXIT NOW

{pos.contract}

Entry: ${pos.entry_price:.2f}
Current: ${pos.current_price:.2f}
Stop: ${pos.stop_price:.2f}

P&L: ${pos.pnl_dollars:+.2f} ({pos.pnl_percent:+.1f}%)

ACTION: Close position to limit losses.

To close in the system, run:
python3 -c "from portfolio import close_position; close_position('{pos.id}', {pos.current_price}, 'STOP')"
"""
            send_email(subject, body)

        elif alert["alert_type"] == "EXPIRING_SOON":
            subject = f"⏰ Expiring Soon: {pos.contract}"
            body = f"""
POSITION EXPIRING SOON

{pos.contract}

Current P&L: ${pos.pnl_dollars:+.2f} ({pos.pnl_percent:+.1f}%)

Consider closing before expiration week to avoid theta decay.
"""
            send_email(subject, body)

    return alerts


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "status":
            print_portfolio()

        elif cmd == "history":
            print_trade_history()

        elif cmd == "update":
            monitor_positions()
            print_portfolio()

    else:
        print_portfolio()
        print("\nCommands:")
        print("  python3 portfolio.py status   - View positions")
        print("  python3 portfolio.py history  - View trade history")
        print("  python3 portfolio.py update   - Update prices & check alerts")
