#!/usr/bin/env python3
"""
Price Alert System - Monitors stocks and sends email alerts.

Setup:
1. Copy .env.example to .env and fill in:
   - ALERT_EMAIL_TO=your_email@gmail.com
   - ALERT_EMAIL_FROM=sender@gmail.com
   - ALERT_EMAIL_PASSWORD=your_app_password (Gmail App Password, not regular password)

2. Run: python3 alerts.py

To run in background: nohup python3 alerts.py > alerts.log 2>&1 &
"""

import os
import time
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# ALERT CONFIGURATION - Edit these levels based on your strategy
# =============================================================================

WATCHLIST = {
    "MU": {
        "name": "Micron",
        "buy_zone": (395, 405),      # Buy on pullback to this range
        "stop_loss": 385,             # Exit if drops below
        "profit_target": 450,         # Take profit here
        "current_position": False,    # Set True if you own it
    },
    "BABA": {
        "name": "Alibaba",
        "buy_zone": (165, 172),       # Buy on pullback to support
        "stop_loss": 160,
        "profit_target": 190,
        "current_position": False,
    },
    "NVDA": {
        "name": "NVIDIA",
        "buy_zone": (175, 182),       # Buy on pullback, not breakout
        "stop_loss": 170,
        "profit_target": 210,
        "current_position": False,
    },
    "TSLA": {
        "name": "Tesla",
        "buy_zone": (380, 400),       # Deep pullback only
        "stop_loss": 365,
        "profit_target": 480,
        "current_position": False,
    },
}

CHECK_INTERVAL_SECONDS = 300  # Check every 5 minutes
ALERT_COOLDOWN_HOURS = 4      # Don't repeat same alert within this window

# =============================================================================
# Alert tracking (persisted to file)
# =============================================================================

ALERT_HISTORY_FILE = Path(__file__).parent / "alert_history.json"


def load_alert_history():
    if ALERT_HISTORY_FILE.exists():
        with open(ALERT_HISTORY_FILE) as f:
            return json.load(f)
    return {}


def save_alert_history(history):
    with open(ALERT_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def should_send_alert(ticker: str, alert_type: str, history: dict) -> bool:
    """Check if we should send this alert (cooldown logic)."""
    key = f"{ticker}_{alert_type}"
    if key not in history:
        return True

    last_sent = datetime.fromisoformat(history[key])
    cooldown = timedelta(hours=ALERT_COOLDOWN_HOURS)
    return datetime.now() - last_sent > cooldown


def record_alert(ticker: str, alert_type: str, history: dict):
    """Record that we sent an alert."""
    key = f"{ticker}_{alert_type}"
    history[key] = datetime.now().isoformat()
    save_alert_history(history)


# =============================================================================
# Email functions
# =============================================================================

def send_email(subject: str, body: str):
    """Send an email alert."""
    email_to = os.getenv("ALERT_EMAIL_TO")
    email_from = os.getenv("ALERT_EMAIL_FROM")
    email_password = os.getenv("ALERT_EMAIL_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.hostinger.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))

    if not all([email_to, email_from, email_password]):
        print(f"[EMAIL NOT CONFIGURED] {subject}")
        print(body)
        print("-" * 50)
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = email_from
        msg["To"] = email_to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(email_from, email_password)
            server.send_message(msg)

        print(f"[EMAIL SENT] {subject}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False


# =============================================================================
# Price monitoring
# =============================================================================

def get_current_price(ticker: str):
    """Get current price using yfinance."""
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period="1d")
        if not data.empty:
            return float(data["Close"].iloc[-1])
        # Try fast_info for real-time
        return stock.fast_info.get("lastPrice")
    except Exception as e:
        print(f"Error getting price for {ticker}: {e}")
        return None


def check_alerts():
    """Check all watchlist stocks and send alerts as needed."""
    history = load_alert_history()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n[{now}] Checking prices...")

    for ticker, config in WATCHLIST.items():
        price = get_current_price(ticker)
        if price is None:
            continue

        name = config["name"]
        buy_low, buy_high = config["buy_zone"]
        stop = config["stop_loss"]
        target = config["profit_target"]
        has_position = config["current_position"]

        print(f"  {ticker}: ${price:.2f}")

        # === BUY ZONE ALERT ===
        if buy_low <= price <= buy_high:
            if should_send_alert(ticker, "buy_zone", history):
                subject = f"🟢 BUY ALERT: {ticker} in buy zone at ${price:.2f}"
                body = f"""
{name} ({ticker}) has pulled back to your buy zone!

Current Price: ${price:.2f}
Buy Zone: ${buy_low} - ${buy_high}
Stop Loss: ${stop}
Profit Target: ${target}

SUGGESTED ACTION:
- Consider entering a position if you don't have one
- Use a stop loss below ${stop}
- This is a PULLBACK entry, not chasing

Time: {now}
"""
                send_email(subject, body)
                record_alert(ticker, "buy_zone", history)

        # === APPROACHING BUY ZONE ===
        elif buy_high < price <= buy_high * 1.03:  # Within 3% of buy zone
            if should_send_alert(ticker, "approaching_buy", history):
                subject = f"🟡 WATCH: {ticker} approaching buy zone at ${price:.2f}"
                body = f"""
{name} ({ticker}) is getting close to your buy zone.

Current Price: ${price:.2f}
Buy Zone: ${buy_low} - ${buy_high}
Distance to buy zone: {((price - buy_high) / buy_high * 100):.1f}%

Get ready - if it pulls back a bit more, it may be time to buy.

Time: {now}
"""
                send_email(subject, body)
                record_alert(ticker, "approaching_buy", history)

        # === STOP LOSS ALERT (if you have a position) ===
        if has_position and price <= stop:
            if should_send_alert(ticker, "stop_loss", history):
                subject = f"🔴 STOP LOSS: {ticker} hit ${price:.2f} - EXIT NOW"
                body = f"""
{name} ({ticker}) has hit your stop loss level!

Current Price: ${price:.2f}
Stop Loss Level: ${stop}

ACTION REQUIRED: Consider exiting your position to limit losses.

Time: {now}
"""
                send_email(subject, body)
                record_alert(ticker, "stop_loss", history)

        # === PROFIT TARGET (if you have a position) ===
        if has_position and price >= target:
            if should_send_alert(ticker, "profit_target", history):
                subject = f"🎯 PROFIT TARGET: {ticker} hit ${price:.2f} - TAKE PROFITS"
                body = f"""
{name} ({ticker}) has reached your profit target!

Current Price: ${price:.2f}
Profit Target: ${target}

SUGGESTED ACTION:
- Consider taking profits (at least partial)
- Or trail your stop up to lock in gains

Time: {now}
"""
                send_email(subject, body)
                record_alert(ticker, "profit_target", history)

        # === BREAKDOWN ALERT (below stop, no position - opportunity) ===
        if not has_position and price < stop * 0.95:  # 5% below stop
            if should_send_alert(ticker, "breakdown", history):
                subject = f"⚠️ BREAKDOWN: {ticker} at ${price:.2f} - Stay away"
                body = f"""
{name} ({ticker}) has broken down significantly.

Current Price: ${price:.2f}
Original Buy Zone: ${buy_low} - ${buy_high}

This is NOT a buy. Wait for stabilization and new support to form.
Catching falling knives = losing money.

Time: {now}
"""
                send_email(subject, body)
                record_alert(ticker, "breakdown", history)


def run_monitor():
    """Run the continuous monitoring loop."""
    print("=" * 60)
    print("PRICE ALERT MONITOR")
    print("=" * 60)
    print(f"Checking every {CHECK_INTERVAL_SECONDS} seconds")
    print(f"Alert cooldown: {ALERT_COOLDOWN_HOURS} hours")
    print("\nWatchlist:")
    for ticker, config in WATCHLIST.items():
        print(f"  {ticker}: Buy ${config['buy_zone'][0]}-${config['buy_zone'][1]}, "
              f"Stop ${config['stop_loss']}, Target ${config['profit_target']}")
    print("\nPress Ctrl+C to stop\n")

    while True:
        try:
            check_alerts()
            time.sleep(CHECK_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\nStopping monitor...")
            break
        except Exception as e:
            print(f"Error in monitor loop: {e}")
            time.sleep(60)  # Wait a minute on error


if __name__ == "__main__":
    run_monitor()
