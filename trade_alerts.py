#!/usr/bin/env python3
"""
Trade Alerts - Simple, actionable options trades.

ONE email at 9 AM with exact trades.
Intraday alerts ONLY if entry conditions are hit.
"""

import os
import time
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import yfinance as yf
from dotenv import load_dotenv

from options_trades import generate_trades, OptionTrade
from analysis import generate_signal

load_dotenv()

ET = ZoneInfo("America/New_York")

WATCHLIST = [
    "NVDA", "MU", "BABA", "ALB", "INTC", "SLV",
    "GOOGL", "AMZN", "AMD", "GOLD", "TXN", "FCX",
    "JD", "PDD", "VZ", "TSLA", "ALLY"
]

DATA_DIR = Path(__file__).parent
STATE_FILE = DATA_DIR / "trade_state.json"


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"date": "", "morning_sent": False, "active_trades": [], "alerts_sent": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def now_et():
    return datetime.now(ET)


def send_email(subject: str, body: str):
    email_to = os.getenv("ALERT_EMAIL_TO")
    email_from = os.getenv("ALERT_EMAIL_FROM")
    email_password = os.getenv("ALERT_EMAIL_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.hostinger.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))

    print(f"📧 {subject}")

    if not all([email_to, email_from, email_password]):
        print(body[:500])
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


def format_trade_for_email(trade: OptionTrade) -> str:
    """Format a single trade for email."""
    conf_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "⚪"}.get(trade.confidence, "⚪")

    return f"""
{conf_emoji} {trade.contract}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ACTION: {trade.direction} - {trade.strategy}

ENTRY:  ${trade.entry_price:.2f} (limit order)
TARGET: ${trade.option_target:.2f} (+{((trade.option_target/trade.entry_price)-1)*100:.0f}%)
STOP:   ${trade.option_stop:.2f} (-50%)

Stock now: ${trade.current_stock_price:.2f} → Target ${trade.stock_target:.2f}

Risk/Reward: {trade.risk_reward}:1
Risk per contract: ${trade.risk_dollars:.0f}

SIZE:
• $500 risk = {trade.contracts_for_500} contracts
• $1000 risk = {trade.contracts_for_1000} contracts

TRIGGER: {trade.entry_trigger}
EXIT: {trade.exit_trigger}
HOLD MAX: {trade.max_hold_days} days
"""


def send_morning_trades():
    """Send morning email with today's trades."""
    now = now_et()

    trades = generate_trades(WATCHLIST)

    # Filter to only good trades
    good_trades = [t for t in trades if t.risk_reward >= 1.8]
    good_trades.sort(key=lambda x: x.risk_reward, reverse=True)

    if not good_trades:
        subject = f"📊 {now.strftime('%m/%d')} - No Trades Today"
        body = f"""
No high-quality setups today.

Scanned {len(WATCHLIST)} stocks, found no options with:
• R:R >= 1.8
• Reasonable entry points

WHAT TO DO: Nothing. Cash is a position. Wait for better setups.

The system will alert you if conditions change during the day.
"""
    else:
        subject = f"🎯 {now.strftime('%m/%d')} - {len(good_trades)} Trade(s) Ready"

        # Quick summary at top
        body = f"""
{'='*50}
TODAY'S TRADES - {now.strftime('%A %B %d, %Y')}
{'='*50}

QUICK SUMMARY:
"""
        for t in good_trades:
            body += f"• {t.contract} | Entry ${t.entry_price:.2f} | R:R {t.risk_reward}:1\n"

        body += f"""
{'='*50}
DETAILED TRADE INSTRUCTIONS
{'='*50}
"""
        for trade in good_trades[:5]:  # Max 5 trades
            body += format_trade_for_email(trade)

        body += f"""
{'='*50}
RULES
{'='*50}
1. Use LIMIT orders at entry price
2. Don't chase - if it gaps past entry, skip it
3. Set stop loss immediately after fill
4. Take profits at target - don't get greedy
5. Exit before expiration week
"""

    send_email(subject, body)

    # Save trades for monitoring
    state = load_state()
    state["date"] = now.strftime("%Y-%m-%d")
    state["morning_sent"] = True
    state["active_trades"] = [
        {
            "ticker": t.ticker,
            "contract": t.contract,
            "entry": t.entry_price,
            "target": t.option_target,
            "stop": t.option_stop,
            "stock_entry_trigger": t.current_stock_price if "now" in t.entry_trigger.lower() else None
        }
        for t in good_trades
    ]
    save_state(state)


def check_entry_triggers():
    """Check if any stocks hit entry triggers."""
    state = load_state()

    for trade_info in state.get("active_trades", []):
        ticker = trade_info["ticker"]
        contract = trade_info["contract"]

        try:
            stock = yf.Ticker(ticker)
            price = stock.fast_info.get('lastPrice', 0)

            if price == 0:
                continue

            signal = generate_signal(ticker)

            # Check if stock hit our entry level
            entry_level = signal.entry_price

            # If price is within 1% of entry level and we haven't alerted
            alert_key = f"{contract}_entry"
            if alert_key not in state.get("alerts_sent", []):
                distance_pct = ((price - entry_level) / entry_level) * 100

                if abs(distance_pct) <= 1.5:
                    subject = f"🚨 ENTRY NOW: {contract}"
                    body = f"""
{contract} - ENTRY TRIGGERED

Stock price: ${price:.2f}
Entry level: ${entry_level:.2f}

ACTION: Place limit order for the option now.

Option entry: ${trade_info['entry']:.2f}
Option target: ${trade_info['target']:.2f}
Option stop: ${trade_info['stop']:.2f}

Don't chase if option has already moved significantly.
"""
                    send_email(subject, body)

                    state.setdefault("alerts_sent", []).append(alert_key)
                    save_state(state)

        except Exception as e:
            pass


def check_portfolio_exits():
    """Check if any positions hit target or stop."""
    from portfolio import monitor_positions
    monitor_positions()


def check_price_alerts():
    """Check for significant price moves."""
    for ticker in WATCHLIST:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if len(hist) < 2:
                continue

            current = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2]
            change_pct = ((current - prev_close) / prev_close) * 100

            # Alert on big moves (>4%)
            if abs(change_pct) >= 4:
                state = load_state()
                alert_key = f"{ticker}_bigmove_{now_et().strftime('%Y%m%d')}"

                if alert_key not in state.get("alerts_sent", []):
                    direction = "UP" if change_pct > 0 else "DOWN"
                    emoji = "🚀" if change_pct > 0 else "📉"

                    subject = f"{emoji} {ticker} {direction} {abs(change_pct):.1f}%"
                    body = f"""
{ticker} moved {change_pct:+.1f}% today.

Current: ${current:.2f}
Previous close: ${prev_close:.2f}

Check if this affects any of your positions or creates a new opportunity.
"""
                    send_email(subject, body)

                    state.setdefault("alerts_sent", []).append(alert_key)
                    save_state(state)

        except:
            pass


def run():
    """Main loop."""
    print("=" * 50)
    print("TRADE ALERTS")
    print("=" * 50)
    print(f"Watching: {len(WATCHLIST)} stocks")
    print("Morning trades: 9:00 AM ET")
    print("Entry alerts: Real-time")
    print("=" * 50)

    while True:
        try:
            now = now_et()
            state = load_state()

            # Reset state if new day
            if state.get("date") != now.strftime("%Y-%m-%d"):
                state = {"date": now.strftime("%Y-%m-%d"), "morning_sent": False, "active_trades": [], "alerts_sent": []}
                save_state(state)

            # Morning trades at 9:00-9:05 AM
            if now.hour == 9 and now.minute < 5 and not state.get("morning_sent"):
                print(f"\n[{now.strftime('%H:%M')}] Sending morning trades...")
                send_morning_trades()

            # During market hours (9:30 AM - 4 PM), check triggers every 2 minutes
            is_market_hours = (now.hour == 9 and now.minute >= 30) or (10 <= now.hour < 16)

            if is_market_hours:
                print(f"[{now.strftime('%H:%M')}] Checking triggers...", end="\r")
                check_entry_triggers()
                check_portfolio_exits()
                check_price_alerts()
                time.sleep(120)  # 2 minutes
            else:
                print(f"[{now.strftime('%H:%M')}] Outside market hours", end="\r")
                time.sleep(300)  # 5 minutes

        except KeyboardInterrupt:
            print("\nStopping...")
            break
        except Exception as e:
            print(f"\nError: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run()
