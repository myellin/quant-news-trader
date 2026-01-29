#!/usr/bin/env python3
"""
Real-Time Monitor - Aggressive monitoring for active trading.

Features:
1. Price checks every 60 seconds (not 5 min)
2. News checks every 10 minutes via Perplexity
3. Sudden move detection (>2% in short period)
4. Volume spike detection
5. Immediate alerts

This is for when you're actively watching the market.
Run during market hours only.
"""

import os
import time
import json
import requests
import smtplib
import yfinance as yf
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path
from collections import deque
from dotenv import load_dotenv

from analysis import generate_signal

load_dotenv()

# =============================================================================
# CONFIG
# =============================================================================

WATCHLIST = ["NVDA", "MU", "BABA", "ALB", "TSLA", "ALLY"]

PRICE_CHECK_INTERVAL = 60      # Check prices every 60 seconds
NEWS_CHECK_INTERVAL = 600      # Check news every 10 minutes
MOVE_THRESHOLD_PCT = 2.0       # Alert on >2% moves
VOLUME_SPIKE_THRESHOLD = 2.5   # Alert on 2.5x average volume

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
ALERT_HISTORY_FILE = Path(__file__).parent / "realtime_alert_history.json"

# Store recent prices for move detection
price_history = {ticker: deque(maxlen=30) for ticker in WATCHLIST}  # Last 30 minutes

# =============================================================================
# HELPERS
# =============================================================================

def load_alert_history():
    if ALERT_HISTORY_FILE.exists():
        with open(ALERT_HISTORY_FILE) as f:
            return json.load(f)
    return {}


def save_alert_history(history):
    with open(ALERT_HISTORY_FILE, "w") as f:
        json.dump(history, f)


def should_alert(key: str, cooldown_minutes: int = 30) -> bool:
    history = load_alert_history()
    if key not in history:
        return True
    last = datetime.fromisoformat(history[key])
    return datetime.now() - last > timedelta(minutes=cooldown_minutes)


def record_alert(key: str):
    history = load_alert_history()
    history[key] = datetime.now().isoformat()
    save_alert_history(history)


def send_alert(subject: str, body: str, urgent: bool = False):
    """Send email alert. If urgent, add 🚨 to subject."""
    email_to = os.getenv("ALERT_EMAIL_TO")
    email_from = os.getenv("ALERT_EMAIL_FROM")
    email_password = os.getenv("ALERT_EMAIL_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.hostinger.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))

    if urgent:
        subject = f"🚨 {subject}"

    if not all([email_to, email_from, email_password]):
        print(f"[ALERT] {subject}")
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

        print(f"  📧 Alert sent: {subject}")
    except Exception as e:
        print(f"  ❌ Email error: {e}")


def get_quote(ticker: str) -> dict:
    """Get real-time quote data."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.fast_info

        # Get intraday data for volume comparison
        hist = stock.history(period="5d", interval="1d")
        avg_volume = hist['Volume'].mean() if not hist.empty else 0

        # Get current day's data
        today = stock.history(period="1d", interval="1m")
        current_volume = today['Volume'].sum() if not today.empty else 0

        return {
            'price': info.get('lastPrice', 0),
            'prev_close': info.get('previousClose', 0),
            'volume': current_volume,
            'avg_volume': avg_volume,
            'day_high': info.get('dayHigh', 0),
            'day_low': info.get('dayLow', 0),
        }
    except Exception as e:
        print(f"    Error getting quote for {ticker}: {e}")
        return None


def query_perplexity(prompt: str) -> str:
    """Query Perplexity for news."""
    headers = {
        "Authorization": f"Bearer {os.getenv('PERPLEXITY_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "sonar",
        "messages": [
            {"role": "system", "content": "You are a breaking news monitor. Only report material market-moving news. Be extremely concise."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 800
    }
    response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=45)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


# =============================================================================
# DETECTION LOGIC
# =============================================================================

def check_sudden_move(ticker: str, current_price: float) -> tuple:
    """
    Check if price moved significantly in short period.
    Returns (is_alert, direction, pct_change, minutes)
    """
    history = price_history[ticker]

    if len(history) < 5:  # Need at least 5 minutes of data
        return False, None, 0, 0

    # Check against 5 minutes ago
    price_5min_ago = history[-5]['price'] if len(history) >= 5 else history[0]['price']
    pct_change_5min = ((current_price - price_5min_ago) / price_5min_ago) * 100

    if abs(pct_change_5min) >= MOVE_THRESHOLD_PCT:
        direction = "UP" if pct_change_5min > 0 else "DOWN"
        return True, direction, pct_change_5min, 5

    # Check against 15 minutes ago
    if len(history) >= 15:
        price_15min_ago = history[-15]['price']
        pct_change_15min = ((current_price - price_15min_ago) / price_15min_ago) * 100

        if abs(pct_change_15min) >= MOVE_THRESHOLD_PCT * 1.5:  # Higher threshold for longer period
            direction = "UP" if pct_change_15min > 0 else "DOWN"
            return True, direction, pct_change_15min, 15

    return False, None, 0, 0


def check_volume_spike(ticker: str, current_volume: float, avg_volume: float) -> bool:
    """Check if volume is spiking."""
    if avg_volume == 0:
        return False

    # Adjust for time of day (volume should be compared proportionally)
    now = datetime.now()
    market_open = now.replace(hour=9, minute=30, second=0)
    market_close = now.replace(hour=16, minute=0, second=0)

    if now < market_open or now > market_close:
        return False

    minutes_since_open = (now - market_open).seconds / 60
    trading_minutes = 390  # 6.5 hours
    expected_volume_pct = minutes_since_open / trading_minutes

    expected_volume = avg_volume * expected_volume_pct
    volume_ratio = current_volume / expected_volume if expected_volume > 0 else 0

    return volume_ratio >= VOLUME_SPIKE_THRESHOLD


def check_breaking_news() -> str:
    """Check for breaking news."""
    tickers = ", ".join(WATCHLIST)
    prompt = f"""BREAKING NEWS CHECK for: {tickers}

In the LAST 30 MINUTES, is there any MATERIAL news that could move these stocks >2%?

Types of news to report:
- Earnings surprises
- Guidance changes
- Major analyst calls
- Regulatory news
- Product announcements
- Executive changes

If YES, format:
TICKER: [symbol]
NEWS: [one line summary]
IMPACT: [BULLISH/BEARISH]
SOURCE: [where reported]

If NO material news, respond exactly: NO_BREAKING_NEWS

Time now: {datetime.now().strftime('%H:%M')}"""

    return query_perplexity(prompt)


# =============================================================================
# MAIN LOOP
# =============================================================================

def run_price_check():
    """Run a single price check cycle."""
    now = datetime.now()
    print(f"\n[{now.strftime('%H:%M:%S')}] Price check...")

    for ticker in WATCHLIST:
        quote = get_quote(ticker)
        if not quote or quote['price'] == 0:
            continue

        price = quote['price']
        prev_close = quote['prev_close']
        day_change = ((price - prev_close) / prev_close * 100) if prev_close else 0

        # Store in history
        price_history[ticker].append({
            'price': price,
            'time': now.isoformat(),
            'volume': quote['volume']
        })

        # Print status
        arrow = "↑" if day_change > 0 else "↓" if day_change < 0 else "→"
        print(f"  {ticker}: ${price:.2f} {arrow} {day_change:+.2f}%", end="")

        # Check for sudden moves
        is_move, direction, pct, minutes = check_sudden_move(ticker, price)
        if is_move:
            alert_key = f"{ticker}_move_{direction}"
            if should_alert(alert_key, cooldown_minutes=30):
                print(f" ⚡ SUDDEN MOVE!")

                subject = f"⚡ {ticker} {direction} {abs(pct):.1f}% in {minutes} min"
                body = f"""
SUDDEN PRICE MOVE DETECTED

{ticker} moved {pct:+.1f}% in the last {minutes} minutes!

Current Price: ${price:.2f}
Day Change: {day_change:+.2f}%

This could indicate:
- Breaking news
- Large institutional order
- Technical breakout/breakdown

Check news immediately and consider:
- If you're long and it's DOWN: Review stop loss
- If you're watching and it's UP: Don't chase, wait for pullback
- If you're watching and it's DOWN: Could be buying opportunity

Time: {now.strftime('%H:%M:%S')}
"""
                send_alert(subject, body, urgent=True)
                record_alert(alert_key)
            else:
                print(" (move already alerted)")
        else:
            print()

        # Check for volume spike
        if check_volume_spike(ticker, quote['volume'], quote['avg_volume']):
            alert_key = f"{ticker}_volume"
            if should_alert(alert_key, cooldown_minutes=60):
                vol_ratio = quote['volume'] / (quote['avg_volume'] * 0.5) if quote['avg_volume'] else 0

                subject = f"📊 {ticker} Volume Spike - {vol_ratio:.1f}x normal"
                body = f"""
UNUSUAL VOLUME DETECTED

{ticker} is trading with {vol_ratio:.1f}x normal volume!

Current Price: ${price:.2f}
Day Change: {day_change:+.2f}%
Volume: {quote['volume']:,.0f}
Avg Volume: {quote['avg_volume']:,.0f}

High volume often precedes or accompanies big moves.
Check for news or large institutional activity.

Time: {now.strftime('%H:%M:%S')}
"""
                send_alert(subject, body)
                record_alert(alert_key)


def run_news_check():
    """Check for breaking news."""
    print(f"\n  📰 Checking news...")

    try:
        news = check_breaking_news()

        if "NO_BREAKING_NEWS" not in news:
            alert_key = f"news_{datetime.now().strftime('%Y%m%d%H')}"
            if should_alert(alert_key, cooldown_minutes=15):
                print(f"  ⚡ Breaking news found!")

                subject = "⚡ BREAKING NEWS on Watchlist"
                body = f"""
BREAKING NEWS DETECTED
{datetime.now().strftime('%H:%M:%S')}
{'='*50}

{news}

{'='*50}
React quickly if this affects your positions.
"""
                send_alert(subject, body, urgent=True)
                record_alert(alert_key)
        else:
            print("  No breaking news")

    except Exception as e:
        print(f"  News check error: {e}")


def run_monitor():
    """Main monitoring loop."""
    print("=" * 60)
    print("REAL-TIME MONITOR")
    print("=" * 60)
    print(f"Watching: {', '.join(WATCHLIST)}")
    print(f"Price check: Every {PRICE_CHECK_INTERVAL}s")
    print(f"News check: Every {NEWS_CHECK_INTERVAL}s")
    print(f"Move alert threshold: {MOVE_THRESHOLD_PCT}%")
    print(f"Volume spike threshold: {VOLUME_SPIKE_THRESHOLD}x")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)

    last_news_check = datetime.now() - timedelta(seconds=NEWS_CHECK_INTERVAL)

    while True:
        try:
            # Price check every cycle
            run_price_check()

            # News check every NEWS_CHECK_INTERVAL
            if (datetime.now() - last_news_check).seconds >= NEWS_CHECK_INTERVAL:
                run_news_check()
                last_news_check = datetime.now()

            time.sleep(PRICE_CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n\nStopping monitor...")
            break
        except Exception as e:
            print(f"\nError: {e}")
            time.sleep(30)


if __name__ == "__main__":
    run_monitor()
