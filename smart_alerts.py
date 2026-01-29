#!/usr/bin/env python3
"""
Smart Alert System - Uses technical analysis to determine dynamic levels.

Combines:
- Real support/resistance (not arbitrary numbers)
- ATR-based stops (adapts to volatility)
- Composite scoring (trend + momentum + volume)
- Multiple entry types (pullback, breakout, mean reversion)
"""

import os
import time
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from analysis import generate_signal, get_market_context, get_data, calculate_indicators

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

WATCHLIST = [
    "NVDA",   # Core: AI chips
    "MU",     # Core: Memory
    "TSLA",   # Core: EV (watching, not buying)
    "BABA",   # Core: China tech
    "ALB",    # Scanner: 3 analyst upgrades, lithium play, score +60
    "ALLY",   # Scanner: CFO bought $500k, watching for bounce
]

CHECK_INTERVAL_SECONDS = 300  # 5 minutes
ALERT_COOLDOWN_HOURS = 2

# Score thresholds
STRONG_BUY_THRESHOLD = 40
MODERATE_BUY_THRESHOLD = 20

ALERT_HISTORY_FILE = Path(__file__).parent / "smart_alert_history.json"
POSITIONS_FILE = Path(__file__).parent / "positions.json"


# =============================================================================
# State management
# =============================================================================

def load_json(filepath):
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return {}


def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def load_positions():
    """Load current positions. Format: {ticker: {entry_price, stop, target}}"""
    return load_json(POSITIONS_FILE)


def save_position(ticker, entry_price, stop, target):
    positions = load_positions()
    positions[ticker] = {
        "entry_price": entry_price,
        "stop": stop,
        "target": target,
        "entry_date": datetime.now().isoformat()
    }
    save_json(POSITIONS_FILE, positions)


def remove_position(ticker):
    positions = load_positions()
    if ticker in positions:
        del positions[ticker]
        save_json(POSITIONS_FILE, positions)


def should_alert(ticker: str, alert_type: str) -> bool:
    history = load_json(ALERT_HISTORY_FILE)
    key = f"{ticker}_{alert_type}"
    if key not in history:
        return True
    last_sent = datetime.fromisoformat(history[key])
    return datetime.now() - last_sent > timedelta(hours=ALERT_COOLDOWN_HOURS)


def record_alert(ticker: str, alert_type: str):
    history = load_json(ALERT_HISTORY_FILE)
    history[f"{ticker}_{alert_type}"] = datetime.now().isoformat()
    save_json(ALERT_HISTORY_FILE, history)


# =============================================================================
# Email
# =============================================================================

def send_email(subject: str, body: str):
    email_to = os.getenv("ALERT_EMAIL_TO")
    email_from = os.getenv("ALERT_EMAIL_FROM")
    email_password = os.getenv("ALERT_EMAIL_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.hostinger.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))

    if not all([email_to, email_from, email_password]):
        print(f"[NO EMAIL CONFIG] {subject}")
        print(body)
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
# Alert Logic
# =============================================================================

def check_ticker(ticker: str, positions: dict):
    """Run full analysis and check for alert conditions."""
    try:
        signal = generate_signal(ticker)
        df = get_data(ticker, period="5d")
        current_price = df['Close'].iloc[-1]

        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # =====================================================================
        # ENTRY ALERTS (no position)
        # =====================================================================
        if ticker not in positions:

            # === BUY NOW (strong setup at good price) ===
            if signal.signal == "BUY_NOW" and signal.score >= STRONG_BUY_THRESHOLD:
                if should_alert(ticker, "buy_now"):
                    subject = f"🟢 BUY NOW: {ticker} at ${current_price:.2f} (Score: {signal.score:+.0f})"
                    body = f"""
STRONG BUY SIGNAL for {ticker}

Current Price: ${current_price:.2f}
Composite Score: {signal.score:+.0f}/100

ENTRY: ${signal.entry_price:.2f}
STOP LOSS: ${signal.stop_loss:.2f}
TARGET 1: ${signal.target_1:.2f} (1:1 R:R)
TARGET 2: ${signal.target_2:.2f} (2:1 R:R)
Risk/Reward: {signal.risk_reward:.1f}:1

WHY:
{chr(10).join(['• ' + r for r in signal.reasons[:8]])}

SCORES:
• Trend: {signal.trend_score:+.0f}
• Momentum: {signal.momentum_score:+.0f}
• Volume: {signal.volume_score:+.0f}
• Volatility: {signal.volatility_score:+.0f}

Time: {now}
"""
                    send_email(subject, body)
                    record_alert(ticker, "buy_now")

            # === PULLBACK ENTRY (price hits our calculated support) ===
            elif signal.signal == "BUY_PULLBACK":
                distance_to_entry = (current_price - signal.entry_price) / signal.entry_price * 100

                # At entry level
                if distance_to_entry <= 1:  # Within 1% of entry
                    if should_alert(ticker, "pullback_entry"):
                        subject = f"🟢 PULLBACK ENTRY: {ticker} at ${current_price:.2f}"
                        body = f"""
{ticker} has pulled back to your entry level!

Current Price: ${current_price:.2f}
Target Entry: ${signal.entry_price:.2f}
Score: {signal.score:+.0f}

TRADE SETUP:
• Entry: ${signal.entry_price:.2f}
• Stop: ${signal.stop_loss:.2f}
• Target 1: ${signal.target_1:.2f}
• Target 2: ${signal.target_2:.2f}
• R:R: {signal.risk_reward:.1f}:1

WHY:
{chr(10).join(['• ' + r for r in signal.reasons[:6]])}

Time: {now}
"""
                        send_email(subject, body)
                        record_alert(ticker, "pullback_entry")

                # Approaching entry (within 3%)
                elif distance_to_entry <= 3:
                    if should_alert(ticker, "approaching_entry"):
                        subject = f"🟡 APPROACHING: {ticker} at ${current_price:.2f} ({distance_to_entry:.1f}% to entry)"
                        body = f"""
{ticker} is approaching your entry level.

Current: ${current_price:.2f}
Entry: ${signal.entry_price:.2f}
Distance: {distance_to_entry:.1f}%

Get ready - if it drops a bit more, it's time to buy.

Score: {signal.score:+.0f}
Stop would be: ${signal.stop_loss:.2f}
Target would be: ${signal.target_1:.2f}

Time: {now}
"""
                        send_email(subject, body)
                        record_alert(ticker, "approaching_entry")

            # === BREAKOUT ALERT (price breaking above resistance with strength) ===
            if signal.score >= 30:
                df_ind = calculate_indicators(get_data(ticker, period="3mo"))
                latest = df_ind.iloc[-1]

                # Breaking above 20 SMA with volume
                if (current_price > latest['SMA_20'] and
                    df_ind.iloc[-2]['Close'] < df_ind.iloc[-2]['SMA_20'] and
                    latest['Relative_Volume'] > 1.3):

                    if should_alert(ticker, "breakout"):
                        subject = f"🚀 BREAKOUT: {ticker} above 20-MA at ${current_price:.2f}"
                        body = f"""
{ticker} is breaking out above its 20-day moving average on volume!

Current Price: ${current_price:.2f}
20-day MA: ${latest['SMA_20']:.2f}
Relative Volume: {latest['Relative_Volume']:.1f}x average

This is a MOMENTUM entry, not a pullback.

Score: {signal.score:+.0f}
Stop: Below today's low or ${current_price * 0.97:.2f}
Target: ${current_price * 1.08:.2f} (8% move)

Time: {now}
"""
                        send_email(subject, body)
                        record_alert(ticker, "breakout")

        # =====================================================================
        # EXIT ALERTS (have position)
        # =====================================================================
        else:
            pos = positions[ticker]
            entry = pos['entry_price']
            stop = pos['stop']
            target = pos['target']

            pnl_pct = (current_price - entry) / entry * 100

            # === STOP LOSS HIT ===
            if current_price <= stop:
                if should_alert(ticker, "stop_hit"):
                    subject = f"🔴 STOP HIT: {ticker} at ${current_price:.2f} - EXIT"
                    body = f"""
{ticker} has hit your stop loss!

Current: ${current_price:.2f}
Your Stop: ${stop:.2f}
Your Entry: ${entry:.2f}
P&L: {pnl_pct:+.1f}%

ACTION: Exit position to limit losses.

Time: {now}
"""
                    send_email(subject, body)
                    record_alert(ticker, "stop_hit")

            # === TARGET HIT ===
            elif current_price >= target:
                if should_alert(ticker, "target_hit"):
                    subject = f"🎯 TARGET HIT: {ticker} at ${current_price:.2f} - TAKE PROFITS"
                    body = f"""
{ticker} has reached your profit target!

Current: ${current_price:.2f}
Your Target: ${target:.2f}
Your Entry: ${entry:.2f}
P&L: {pnl_pct:+.1f}%

SUGGESTION:
• Take at least partial profits
• Trail stop to ${entry:.2f} (breakeven) on remainder

Time: {now}
"""
                    send_email(subject, body)
                    record_alert(ticker, "target_hit")

            # === TREND REVERSAL WARNING ===
            elif signal.score < 0 and pnl_pct > 0:
                if should_alert(ticker, "trend_warning"):
                    subject = f"⚠️ TREND WARNING: {ticker} score turned negative"
                    body = f"""
{ticker} technical score has turned negative while you're in profit.

Current: ${current_price:.2f}
Your Entry: ${entry:.2f}
P&L: {pnl_pct:+.1f}%
New Score: {signal.score:+.0f}

Consider:
• Tightening stop to ${current_price * 0.97:.2f}
• Taking partial profits
• Watching for further weakness

Reasons for concern:
{chr(10).join(['• ' + w for w in signal.warnings[:4]])}

Time: {now}
"""
                    send_email(subject, body)
                    record_alert(ticker, "trend_warning")

        return signal

    except Exception as e:
        print(f"Error checking {ticker}: {e}")
        return None


def run_monitor():
    """Main monitoring loop."""
    print("=" * 60)
    print("SMART ALERT MONITOR")
    print("=" * 60)
    print(f"Watching: {', '.join(WATCHLIST)}")
    print(f"Check interval: {CHECK_INTERVAL_SECONDS}s")
    print(f"Using dynamic technical levels (not arbitrary)")
    print("\nPress Ctrl+C to stop\n")

    while True:
        try:
            positions = load_positions()
            now = datetime.now().strftime("%H:%M")
            print(f"\n[{now}] Checking...")

            market = get_market_context()
            print(f"  Market: SPY {market['spy_change']:+.2f}%, VIX {market['vix']:.1f}")

            for ticker in WATCHLIST:
                signal = check_ticker(ticker, positions)
                if signal:
                    status = "POSITION" if ticker in positions else "WATCHING"
                    print(f"  {ticker}: ${signal.entry_price:.2f} | Score {signal.score:+.0f} | {signal.signal} | {status}")

            time.sleep(CHECK_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\nStopping...")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run_monitor()
