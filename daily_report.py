#!/usr/bin/env python3
"""
Daily Report - ONE email at 4 PM ET with trading performance.

No spam. Just results.
"""

import os
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json
from dotenv import load_dotenv

from portfolio import (
    load_portfolio, load_trade_history, get_portfolio_summary,
    update_positions, close_position
)
from options_trades import generate_trades

load_dotenv()

ET = ZoneInfo("America/New_York")
STATE_FILE = Path(__file__).parent / "daily_report_state.json"

WATCHLIST = [
    "NVDA", "MU", "BABA", "ALB", "INTC", "SLV",
    "GOOGL", "AMZN", "AMD", "GOLD", "TXN", "FCX",
    "JD", "PDD", "VZ", "TSLA", "ALLY"
]


def now_et():
    return datetime.now(ET)


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def send_email(subject: str, body: str):
    email_to = os.getenv("ALERT_EMAIL_TO")
    email_from = os.getenv("ALERT_EMAIL_FROM")
    email_password = os.getenv("ALERT_EMAIL_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.hostinger.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))

    print(f"📧 Sending: {subject}")

    if not all([email_to, email_from, email_password]):
        print(body)
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
        print("  ✅ Sent")
    except Exception as e:
        print(f"  ❌ {e}")


def auto_close_positions():
    """Auto-close positions that hit target or stop."""
    positions = load_portfolio()
    closed_today = []

    for p in positions:
        if p.current_price >= p.target_price:
            # Hit target - close for profit
            closed = close_position(p.id, p.current_price, "TARGET")
            closed_today.append(("WIN", p.contract, p.pnl_dollars, p.pnl_percent))

        elif p.current_price <= p.stop_price:
            # Hit stop - close for loss
            closed = close_position(p.id, p.current_price, "STOP")
            closed_today.append(("LOSS", p.contract, p.pnl_dollars, p.pnl_percent))

    return closed_today


def generate_daily_report():
    """Generate the 4 PM daily report."""
    now = now_et()

    # Update all positions first
    update_positions()

    # Auto-close any positions that hit targets/stops
    closed_today = auto_close_positions()

    # Get current state
    positions = load_portfolio()
    history = load_trade_history()
    summary = get_portfolio_summary()

    # Build report
    report = []
    report.append("=" * 50)
    report.append(f"DAILY TRADING REPORT")
    report.append(f"{now.strftime('%A, %B %d, %Y')} - Market Close")
    report.append("=" * 50)

    # Performance summary
    report.append("")
    report.append("PERFORMANCE")
    report.append("-" * 50)

    pnl_emoji = "🟢" if summary['total_pnl'] >= 0 else "🔴"
    report.append(f"{pnl_emoji} Total P&L: ${summary['total_pnl']:+.2f}")
    report.append(f"   Unrealized: ${summary['unrealized_pnl']:+.2f}")
    report.append(f"   Realized: ${summary['realized_pnl']:+.2f}")
    report.append("")
    report.append(f"Win Rate: {summary['win_rate']:.1f}% ({summary['wins']}W / {summary['losses']}L)")
    report.append(f"Total Trades: {summary['total_trades']}")

    # Closed today
    if closed_today:
        report.append("")
        report.append("CLOSED TODAY")
        report.append("-" * 50)
        for result, contract, pnl, pct in closed_today:
            emoji = "✅" if result == "WIN" else "❌"
            report.append(f"{emoji} {contract}: ${pnl:+.2f} ({pct:+.1f}%) - {result}")

    # Open positions
    report.append("")
    report.append("OPEN POSITIONS")
    report.append("-" * 50)

    if positions:
        for p in positions:
            emoji = "🟢" if p.pnl_dollars >= 0 else "🔴"
            report.append(f"{emoji} {p.contract}")
            report.append(f"   Entry: ${p.entry_price:.2f} | Now: ${p.current_price:.2f}")
            report.append(f"   P&L: ${p.pnl_dollars:+.2f} ({p.pnl_percent:+.1f}%)")
            report.append(f"   Target: ${p.target_price:.2f} | Stop: ${p.stop_price:.2f}")
            report.append("")
    else:
        report.append("No open positions.")

    # Trade ideas for tomorrow
    report.append("")
    report.append("TRADE IDEAS FOR TOMORROW")
    report.append("-" * 50)

    try:
        trades = generate_trades(WATCHLIST)
        good_trades = [t for t in trades if t.risk_reward >= 1.8][:3]

        if good_trades:
            for t in good_trades:
                report.append(f"• {t.contract}")
                report.append(f"  Entry: ${t.entry_price:.2f} | Target: ${t.option_target:.2f} | R:R {t.risk_reward}:1")
        else:
            report.append("No high-quality setups. Cash is fine.")
    except:
        report.append("Could not generate ideas.")

    report.append("")
    report.append("=" * 50)
    report.append("Dashboard: http://localhost:8080")
    report.append("=" * 50)

    return "\n".join(report)


def send_daily_report():
    """Send the daily report email."""
    now = now_et()
    summary = get_portfolio_summary()

    pnl = summary['total_pnl']
    emoji = "🟢" if pnl >= 0 else "🔴"

    subject = f"{emoji} Daily Report {now.strftime('%m/%d')} | P&L: ${pnl:+.2f}"
    body = generate_daily_report()

    send_email(subject, body)


def run():
    """Main loop - just waits for 4 PM to send report."""
    print("=" * 50)
    print("DAILY REPORT SERVICE")
    print("=" * 50)
    print("Sends ONE email at 4:00 PM ET with:")
    print("  - Today's P&L")
    print("  - Open positions")
    print("  - Closed trades")
    print("  - Ideas for tomorrow")
    print("")
    print("Dashboard: http://localhost:8080")
    print("=" * 50)

    last_report_date = load_state().get("last_report_date")

    while True:
        try:
            now = now_et()
            today = now.strftime("%Y-%m-%d")

            # Send report at 4:00-4:05 PM if not sent today
            if now.hour == 16 and now.minute < 5 and last_report_date != today:
                print(f"\n[{now.strftime('%H:%M')}] Sending daily report...")
                update_positions()
                send_daily_report()
                last_report_date = today
                save_state({"last_report_date": today})

            # Also update positions periodically during market hours
            is_market_hours = (now.hour == 9 and now.minute >= 30) or (10 <= now.hour < 16)
            if is_market_hours:
                update_positions()
                print(f"[{now.strftime('%H:%M')}] Positions updated", end="\r")

            time.sleep(60)  # Check every minute

        except KeyboardInterrupt:
            print("\nStopping...")
            break
        except Exception as e:
            print(f"\nError: {e}")
            time.sleep(60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "now":
        # Send report immediately (for testing)
        print("Sending report now...")
        update_positions()
        send_daily_report()
    else:
        run()
