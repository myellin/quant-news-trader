#!/usr/bin/env python3
"""
Daily Briefing - Runs once per day (schedule via cron)

Sends email with:
1. Watchlist status & scores
2. NEW opportunities (analyst upgrades, insider buying, politician trades)
3. Upcoming earnings & catalysts
4. Material news that could move prices
"""

import os
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

from analysis import generate_signal, get_market_context

load_dotenv()

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

WATCHLIST = ["NVDA", "MU", "BABA", "ALB", "ALLY", "TSLA"]


def get_api_key():
    return os.getenv("PERPLEXITY_API_KEY")


def query_perplexity(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
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


def get_watchlist_status() -> str:
    """Generate status for all watchlist stocks."""
    lines = []
    lines.append("WATCHLIST STATUS")
    lines.append("-" * 50)

    for ticker in WATCHLIST:
        try:
            signal = generate_signal(ticker)
            emoji = {"BUY_NOW": "🟢", "BUY_PULLBACK": "🟡", "WAIT": "⚪", "SELL": "🔴"}.get(signal.signal, "⚪")
            lines.append(f"{emoji} {ticker}: Score {signal.score:+.0f} | {signal.signal} | Entry ${signal.entry_price:.2f}")
        except Exception as e:
            lines.append(f"⚠️ {ticker}: Error - {e}")

    return "\n".join(lines)


def get_new_opportunities() -> str:
    """Scan for new opportunities."""
    prompt = """Find the TOP 5 stock opportunities from the last 24 hours based on:

1. ANALYST UPGRADES - Major firms upgrading stocks or raising price targets significantly (>15% upside)
2. INSIDER BUYING - CEO/CFO/Director purchases over $200,000
3. POLITICIAN TRADES - Congress members buying over $100,000

For each opportunity found:
- Ticker and company
- What happened (upgrade/insider buy/politician trade)
- Specific numbers (price target, $ amount bought)
- Why it matters

Focus on mid-large cap stocks ($5B+). Be specific with names, dates, and numbers.
If nothing significant, say "No major opportunities in last 24 hours."
"""
    return query_perplexity(prompt)


def get_earnings_calendar() -> str:
    """Get upcoming earnings for watchlist."""
    tickers_str = ", ".join(WATCHLIST)
    prompt = f"""For these stocks: {tickers_str}

List their NEXT earnings dates and what to expect:
- Exact earnings date and time (before/after market)
- Consensus EPS estimate
- Consensus revenue estimate
- Key things to watch in the report

Also list any OTHER major earnings this week that could affect these stocks (e.g., if NVDA watches AMD earnings, or BABA watches JD earnings).

Be specific with dates. Today is {datetime.now().strftime('%B %d, %Y')}."""

    return query_perplexity(prompt)


def get_material_news() -> str:
    """Get material news for watchlist."""
    tickers_str = ", ".join(WATCHLIST)
    prompt = f"""What MATERIAL NEWS happened in the last 24 hours that could significantly move these stocks: {tickers_str}

Only include news that could move the stock >3%:
- Earnings surprises
- Guidance changes
- Major contract wins/losses
- Regulatory decisions
- Product launches
- Executive changes
- Analyst actions

For each item:
- Ticker affected
- What happened
- Expected impact (bullish/bearish)
- Price move so far if any

If no material news, say "No material news in last 24 hours."
"""
    return query_perplexity(prompt)


def get_macro_context() -> str:
    """Get macro context."""
    prompt = """Provide today's macro context for swing trading:

1. S&P 500 and NASDAQ - current level, trend, key support/resistance
2. VIX - level and what it means for options
3. Fed - any upcoming meetings or recent commentary
4. Key economic data this week
5. Geopolitical risks to watch

Be concise - 2-3 sentences per item."""

    return query_perplexity(prompt)


def send_briefing():
    """Compile and send the daily briefing."""
    now = datetime.now()

    print(f"Generating daily briefing for {now.strftime('%Y-%m-%d')}...")

    # Gather all sections
    sections = []

    # Market context
    print("  Getting market context...")
    market = get_market_context()
    sections.append(f"""MARKET SNAPSHOT
SPY: {market['spy_change']:+.2f}%
VIX: {market['vix']:.1f}
Regime: {'Risk-On ✅' if market['risk_on'] else 'Risk-Off ⚠️'}
""")

    # Watchlist
    print("  Analyzing watchlist...")
    sections.append(get_watchlist_status())

    # Material news
    print("  Checking material news...")
    try:
        sections.append("\nMATERIAL NEWS (Last 24h)\n" + "-"*50 + "\n" + get_material_news())
    except Exception as e:
        sections.append(f"\nMATERIAL NEWS: Error fetching - {e}")

    # New opportunities
    print("  Scanning for opportunities...")
    try:
        sections.append("\nNEW OPPORTUNITIES\n" + "-"*50 + "\n" + get_new_opportunities())
    except Exception as e:
        sections.append(f"\nNEW OPPORTUNITIES: Error fetching - {e}")

    # Earnings
    print("  Checking earnings calendar...")
    try:
        sections.append("\nEARNINGS CALENDAR\n" + "-"*50 + "\n" + get_earnings_calendar())
    except Exception as e:
        sections.append(f"\nEARNINGS CALENDAR: Error fetching - {e}")

    # Macro
    print("  Getting macro context...")
    try:
        sections.append("\nMACRO CONTEXT\n" + "-"*50 + "\n" + get_macro_context())
    except Exception as e:
        sections.append(f"\nMACRO CONTEXT: Error fetching - {e}")

    # Compile email
    body = f"""
DAILY TRADING BRIEFING
{now.strftime('%A, %B %d, %Y')}
{'='*60}

{chr(10).join(sections)}

{'='*60}
This briefing was auto-generated by your Quant News Trader.
Run 'python3 scanner.py' for deeper analysis on any ticker.
"""

    subject = f"📊 Daily Briefing {now.strftime('%m/%d')} | VIX {market['vix']:.0f} | {'Risk-On' if market['risk_on'] else 'Risk-Off'}"

    # Send email
    email_to = os.getenv("ALERT_EMAIL_TO")
    email_from = os.getenv("ALERT_EMAIL_FROM")
    email_password = os.getenv("ALERT_EMAIL_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.hostinger.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))

    if not all([email_to, email_from, email_password]):
        print("\n[Email not configured - printing to console]\n")
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

        print(f"\n✅ Briefing sent to {email_to}")
    except Exception as e:
        print(f"\n❌ Email error: {e}")
        print("\nBriefing content:")
        print(body)


if __name__ == "__main__":
    send_briefing()
