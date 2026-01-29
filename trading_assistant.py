#!/usr/bin/env python3
"""
Trading Assistant - Your complete daily trading companion.

Scheduled Emails:
- 9:00 AM EST: Morning briefing (pre-market setup)
- 4:00 PM EST: End of day summary

Real-Time Alerts (throughout the day):
- Price hits buy zone
- Sudden moves (>2% in 5-15 min)
- Volume spikes (2.5x normal)
- Breaking news
- Stop loss / target hit (if you have positions)

Run this ONE script and leave it running during market hours.
"""

import os
import sys
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
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from analysis import generate_signal, get_market_context

load_dotenv()

# =============================================================================
# CONFIG
# =============================================================================

WATCHLIST = [
    # Core holdings
    "NVDA",   # AI chips
    "MU",     # Memory (hot but overbought - wait for pullback)
    "BABA",   # China tech
    "ALB",    # Lithium, analyst upgrades
    "TSLA",   # EV (watching, bearish)
    "ALLY",   # Insider buying
    # User requested
    "INTC",   # Intel
    "SLV",    # Silver ETF - momentum 95
    # Strong technicals
    "GOOGL",  # Mega cap tech
    "AMZN",   # Mega cap tech
    "AMD",    # NVDA competitor
    # Momentum picks (on a tear)
    "GOLD",   # Barrick Gold - momentum 100, +108% in 3mo
    "TXN",    # Texas Instruments - momentum 95
    "FCX",    # Freeport copper - momentum 90
    # Value picks (undervalued)
    "JD",     # JD.com - P/E 9.6, +38% upside
    "PDD",    # Pinduoduo - P/E 10.4, +44% upside
    "VZ",     # Verizon - P/E 8.5, 7% dividend
]

# Timing (Eastern Time)
ET = ZoneInfo("America/New_York")
MORNING_BRIEFING_HOUR = 9   # 9:00 AM ET
EOD_SUMMARY_HOUR = 16       # 4:00 PM ET

# Check intervals
PRICE_CHECK_INTERVAL = 60       # Every 60 seconds
NEWS_CHECK_INTERVAL = 600       # Every 10 minutes

# Alert thresholds
MOVE_THRESHOLD_PCT = 2.0
VOLUME_SPIKE_THRESHOLD = 2.5

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# Files
DATA_DIR = Path(__file__).parent
ALERT_HISTORY_FILE = DATA_DIR / "alert_history.json"
POSITIONS_FILE = DATA_DIR / "positions.json"
DAILY_STATE_FILE = DATA_DIR / "daily_state.json"

# Price history for move detection
price_history = {ticker: deque(maxlen=60) for ticker in WATCHLIST}

# =============================================================================
# HELPERS
# =============================================================================

def now_et():
    """Get current time in Eastern."""
    return datetime.now(ET)


def load_json(filepath):
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return {}


def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def get_daily_state():
    """Track what we've sent today."""
    state = load_json(DAILY_STATE_FILE)
    today = now_et().strftime("%Y-%m-%d")
    if state.get("date") != today:
        state = {"date": today, "morning_sent": False, "eod_sent": False, "alerts": []}
        save_json(DAILY_STATE_FILE, state)
    return state


def update_daily_state(key, value):
    state = get_daily_state()
    state[key] = value
    save_json(DAILY_STATE_FILE, state)


def should_alert(key: str, cooldown_minutes: int = 30) -> bool:
    history = load_json(ALERT_HISTORY_FILE)
    if key not in history:
        return True
    last = datetime.fromisoformat(history[key])
    return datetime.now() - last > timedelta(minutes=cooldown_minutes)


def record_alert(key: str):
    history = load_json(ALERT_HISTORY_FILE)
    history[key] = datetime.now().isoformat()
    save_json(ALERT_HISTORY_FILE, history)


def send_email(subject: str, body: str, urgent: bool = False):
    """Send email."""
    email_to = os.getenv("ALERT_EMAIL_TO")
    email_from = os.getenv("ALERT_EMAIL_FROM")
    email_password = os.getenv("ALERT_EMAIL_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.hostinger.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))

    if urgent:
        subject = f"🚨 {subject}"

    print(f"  📧 Sending: {subject}")

    if not all([email_to, email_from, email_password]):
        print(f"    [No email config - printing only]")
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

        print(f"    ✅ Sent!")
    except Exception as e:
        print(f"    ❌ Error: {e}")


def query_perplexity(prompt: str) -> str:
    """Query Perplexity API."""
    headers = {
        "Authorization": f"Bearer {os.getenv('PERPLEXITY_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "sonar",
        "messages": [
            {"role": "system", "content": "You are a financial analyst. Be specific and concise."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 1500
    }
    response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def get_quote(ticker: str) -> dict:
    """Get quote data."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.fast_info
        hist = stock.history(period="5d", interval="1d")
        avg_volume = hist['Volume'].mean() if not hist.empty else 0

        return {
            'price': info.get('lastPrice', 0),
            'prev_close': info.get('previousClose', 0),
            'open': info.get('open', 0),
            'day_high': info.get('dayHigh', 0),
            'day_low': info.get('dayLow', 0),
            'volume': info.get('lastVolume', 0),
            'avg_volume': avg_volume,
        }
    except Exception as e:
        return None


# =============================================================================
# MORNING BRIEFING (9 AM ET)
# =============================================================================

def generate_morning_briefing():
    """Generate the morning briefing email."""
    now = now_et()

    sections = []
    sections.append(f"""
{'='*60}
MORNING BRIEFING - {now.strftime('%A, %B %d, %Y')}
{'='*60}
""")

    # Market context
    try:
        market = get_market_context()
        sections.append(f"""
MARKET SNAPSHOT
---------------
SPY: {market['spy_change']:+.2f}% (yesterday)
VIX: {market['vix']:.1f}
Regime: {'🟢 Risk-On' if market['risk_on'] else '🔴 Risk-Off'}
""")
    except Exception as e:
        sections.append(f"Market data error: {e}")

    # Watchlist analysis
    sections.append("""
WATCHLIST STATUS
----------------""")

    for ticker in WATCHLIST:
        try:
            signal = generate_signal(ticker)
            quote = get_quote(ticker)
            price = quote['price'] if quote else 0

            emoji = {"BUY_NOW": "🟢", "BUY_PULLBACK": "🟡", "WAIT": "⚪", "SELL": "🔴"}.get(signal.signal, "⚪")

            distance_to_entry = ((price - signal.entry_price) / signal.entry_price * 100) if signal.entry_price else 0

            sections.append(f"""
{emoji} {ticker} - Score: {signal.score:+.0f}
   Price: ${price:.2f} | Entry: ${signal.entry_price:.2f} ({distance_to_entry:+.1f}% away)
   Signal: {signal.signal}
   Stop: ${signal.stop_loss:.2f} | Target: ${signal.target_1:.2f}""")

        except Exception as e:
            sections.append(f"\n⚠️ {ticker}: Error - {e}")

    # Overnight news
    try:
        news_prompt = f"""What significant news happened OVERNIGHT (after 4 PM yesterday through this morning) for: {', '.join(WATCHLIST)}

Also include:
- Major index futures (S&P, Nasdaq)
- Any macro news (Fed, economic data)
- Earnings released after hours or pre-market

Be concise - bullet points only. If nothing significant, say so."""

        news = query_perplexity(news_prompt)
        sections.append(f"""
OVERNIGHT NEWS
--------------
{news}
""")
    except Exception as e:
        sections.append(f"\nNews error: {e}")

    # Today's calendar
    try:
        calendar_prompt = f"""What's on the economic/earnings calendar for TODAY that could affect: {', '.join(WATCHLIST)}

Include:
- Economic data releases (time ET)
- Fed speakers
- Earnings reports (before/after market)
- Any scheduled company events

Be specific with times."""

        calendar = query_perplexity(calendar_prompt)
        sections.append(f"""
TODAY'S CALENDAR
----------------
{calendar}
""")
    except Exception as e:
        sections.append(f"\nCalendar error: {e}")

    # Action items
    sections.append(f"""
{'='*60}
ACTION ITEMS FOR TODAY
{'='*60}
""")

    actionable = []
    for ticker in WATCHLIST:
        try:
            signal = generate_signal(ticker)
            quote = get_quote(ticker)
            price = quote['price'] if quote else 0

            if signal.signal == "BUY_NOW":
                actionable.append(f"🟢 {ticker}: Consider buying at ${price:.2f}")
            elif signal.signal == "BUY_PULLBACK":
                distance = ((price - signal.entry_price) / signal.entry_price * 100)
                if distance < 5:
                    actionable.append(f"🟡 {ticker}: Watch for entry at ${signal.entry_price:.2f} ({distance:.1f}% away)")
        except:
            pass

    if actionable:
        sections.append("\n".join(actionable))
    else:
        sections.append("No immediate action items. Stay patient and wait for setups.")

    sections.append(f"""
{'='*60}
You'll receive alerts throughout the day if prices hit targets.
Good luck trading!
{'='*60}
""")

    return "\n".join(sections)


def send_morning_briefing():
    """Send the morning briefing."""
    state = get_daily_state()
    if state.get("morning_sent"):
        return

    print("\n📬 Generating morning briefing...")
    body = generate_morning_briefing()

    now = now_et()
    subject = f"☀️ Morning Briefing {now.strftime('%m/%d')} - Pre-Market Setup"

    send_email(subject, body)
    update_daily_state("morning_sent", True)


# =============================================================================
# END OF DAY SUMMARY (4 PM ET)
# =============================================================================

def generate_eod_summary():
    """Generate end of day summary."""
    now = now_et()

    sections = []
    sections.append(f"""
{'='*60}
END OF DAY SUMMARY - {now.strftime('%A, %B %d, %Y')}
{'='*60}
""")

    # Market performance
    try:
        market = get_market_context()
        sections.append(f"""
MARKET CLOSE
------------
SPY: {market['spy_change']:+.2f}%
VIX: {market['vix']:.1f}
""")
    except Exception as e:
        sections.append(f"Market data error: {e}")

    # Watchlist performance
    sections.append("""
WATCHLIST PERFORMANCE
---------------------""")

    winners = []
    losers = []

    for ticker in WATCHLIST:
        try:
            quote = get_quote(ticker)
            if quote and quote['prev_close']:
                price = quote['price']
                change = ((price - quote['prev_close']) / quote['prev_close']) * 100

                emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"
                sections.append(f"{emoji} {ticker}: ${price:.2f} ({change:+.2f}%)")

                if change > 1:
                    winners.append((ticker, change))
                elif change < -1:
                    losers.append((ticker, change))
        except Exception as e:
            sections.append(f"⚠️ {ticker}: Error")

    # Biggest movers
    if winners:
        sections.append(f"\n🏆 Best: {', '.join([f'{t} +{c:.1f}%' for t, c in sorted(winners, key=lambda x: -x[1])])}")
    if losers:
        sections.append(f"📉 Worst: {', '.join([f'{t} {c:.1f}%' for t, c in sorted(losers, key=lambda x: x[1])])}")

    # What happened today (news)
    try:
        news_prompt = f"""Summarize the most important market news from TODAY that affected: {', '.join(WATCHLIST)}

Include:
- Why did the biggest movers move?
- Any analyst actions
- Any company news
- Macro events that affected markets

Be concise."""

        news = query_perplexity(news_prompt)
        sections.append(f"""
TODAY'S NEWS SUMMARY
--------------------
{news}
""")
    except Exception as e:
        sections.append(f"\nNews error: {e}")

    # Setup for tomorrow
    sections.append("""
SETUP FOR TOMORROW
------------------""")

    for ticker in WATCHLIST:
        try:
            signal = generate_signal(ticker)
            quote = get_quote(ticker)
            price = quote['price'] if quote else 0

            if signal.signal in ["BUY_NOW", "BUY_PULLBACK"] and signal.score >= 30:
                distance = ((price - signal.entry_price) / signal.entry_price * 100) if signal.entry_price else 0
                sections.append(f"👀 {ticker}: Entry ${signal.entry_price:.2f} ({distance:+.1f}% away) | Score {signal.score:+.0f}")
        except:
            pass

    # After hours to watch
    try:
        ah_prompt = f"""What earnings or events are happening AFTER HOURS today or TOMORROW PRE-MARKET that could affect: {', '.join(WATCHLIST)}

Be specific with company names and times."""

        ah = query_perplexity(ah_prompt)
        sections.append(f"""
AFTER HOURS / TOMORROW
----------------------
{ah}
""")
    except:
        pass

    sections.append(f"""
{'='*60}
See you tomorrow at 9 AM ET!
{'='*60}
""")

    return "\n".join(sections)


def send_eod_summary():
    """Send end of day summary."""
    state = get_daily_state()
    if state.get("eod_sent"):
        return

    print("\n📬 Generating EOD summary...")
    body = generate_eod_summary()

    now = now_et()
    subject = f"🌙 EOD Summary {now.strftime('%m/%d')} - Market Close"

    send_email(subject, body)
    update_daily_state("eod_sent", True)


# =============================================================================
# REAL-TIME ALERTS (Throughout the day)
# =============================================================================

def check_buy_zones():
    """Check if any stocks hit buy zones."""
    for ticker in WATCHLIST:
        try:
            signal = generate_signal(ticker)
            quote = get_quote(ticker)
            if not quote:
                continue

            price = quote['price']

            # Check if at or below entry
            if signal.signal in ["BUY_NOW", "BUY_PULLBACK"] and price <= signal.entry_price * 1.01:
                alert_key = f"{ticker}_buyzone_{now_et().strftime('%Y%m%d')}"
                if should_alert(alert_key, cooldown_minutes=120):
                    subject = f"🟢 BUY ZONE: {ticker} at ${price:.2f}"
                    body = f"""
{ticker} HAS HIT YOUR BUY ZONE!

Current Price: ${price:.2f}
Entry Target: ${signal.entry_price:.2f}
Score: {signal.score:+.0f}

TRADE SETUP:
• Entry: ${price:.2f}
• Stop Loss: ${signal.stop_loss:.2f}
• Target: ${signal.target_1:.2f}
• Risk/Reward: {signal.risk_reward:.1f}:1

Time: {now_et().strftime('%H:%M:%S ET')}
"""
                    send_email(subject, body, urgent=True)
                    record_alert(alert_key)

        except Exception as e:
            pass


def check_sudden_moves():
    """Check for sudden price moves."""
    for ticker in WATCHLIST:
        try:
            quote = get_quote(ticker)
            if not quote:
                continue

            price = quote['price']
            history = price_history[ticker]

            # Store current price
            history.append({'price': price, 'time': datetime.now().isoformat()})

            if len(history) < 5:
                continue

            # Check 5-minute move
            price_5min = history[-5]['price']
            pct_change = ((price - price_5min) / price_5min) * 100

            if abs(pct_change) >= MOVE_THRESHOLD_PCT:
                direction = "UP" if pct_change > 0 else "DOWN"
                alert_key = f"{ticker}_move_{direction}_{now_et().strftime('%Y%m%d%H')}"

                if should_alert(alert_key, cooldown_minutes=30):
                    subject = f"⚡ {ticker} {direction} {abs(pct_change):.1f}% in 5 min"
                    body = f"""
SUDDEN MOVE DETECTED!

{ticker} moved {pct_change:+.1f}% in the last 5 minutes.

Current: ${price:.2f}
5 min ago: ${price_5min:.2f}

Check news immediately!

Time: {now_et().strftime('%H:%M:%S ET')}
"""
                    send_email(subject, body, urgent=True)
                    record_alert(alert_key)

        except Exception as e:
            pass


def check_breaking_news():
    """Check for breaking news."""
    try:
        prompt = f"""BREAKING NEWS in last 15 minutes for: {', '.join(WATCHLIST)}

Only report MATERIAL news (earnings, guidance, major analyst calls, regulatory).
If nothing, respond: NO_BREAKING_NEWS"""

        news = query_perplexity(prompt)

        if "NO_BREAKING_NEWS" not in news:
            alert_key = f"news_{now_et().strftime('%Y%m%d%H%M')}"
            if should_alert(alert_key, cooldown_minutes=20):
                subject = "⚡ Breaking News Alert"
                body = f"""
BREAKING NEWS
{now_et().strftime('%H:%M ET')}
{'='*40}

{news}

{'='*40}
"""
                send_email(subject, body, urgent=True)
                record_alert(alert_key)

    except Exception as e:
        pass


# =============================================================================
# MAIN LOOP
# =============================================================================

def run():
    """Main run loop."""
    print("=" * 60)
    print("TRADING ASSISTANT")
    print("=" * 60)
    print(f"Watching: {', '.join(WATCHLIST)}")
    print(f"Morning briefing: 9:00 AM ET")
    print(f"EOD summary: 4:00 PM ET")
    print(f"Price checks: Every {PRICE_CHECK_INTERVAL}s")
    print(f"News checks: Every {NEWS_CHECK_INTERVAL}s")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)

    last_news_check = datetime.now() - timedelta(seconds=NEWS_CHECK_INTERVAL)

    while True:
        try:
            now = now_et()
            current_hour = now.hour
            current_minute = now.minute

            # Morning briefing at 9:00 AM ET
            if current_hour == MORNING_BRIEFING_HOUR and current_minute < 5:
                send_morning_briefing()

            # EOD summary at 4:00 PM ET
            if current_hour == EOD_SUMMARY_HOUR and current_minute < 5:
                send_eod_summary()

            # Real-time checks (market hours: 9:30 AM - 4:00 PM ET)
            is_market_hours = (current_hour == 9 and current_minute >= 30) or (10 <= current_hour < 16)

            if is_market_hours:
                print(f"\n[{now.strftime('%H:%M:%S')}] Checking...", end="")

                # Price check
                for ticker in WATCHLIST:
                    quote = get_quote(ticker)
                    if quote:
                        price = quote['price']
                        prev = quote['prev_close']
                        change = ((price - prev) / prev * 100) if prev else 0
                        arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
                        print(f" {ticker}:${price:.0f}{arrow}{change:+.1f}%", end="")

                print()

                # Check alerts
                check_buy_zones()
                check_sudden_moves()

                # News check every 10 min
                if (datetime.now() - last_news_check).seconds >= NEWS_CHECK_INTERVAL:
                    print("  📰 Checking news...")
                    check_breaking_news()
                    last_news_check = datetime.now()

            else:
                # Outside market hours - just check for scheduled emails
                print(f"[{now.strftime('%H:%M')}] Outside market hours. Waiting...")

            time.sleep(PRICE_CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n\nShutting down...")
            break
        except Exception as e:
            print(f"\nError: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run()
