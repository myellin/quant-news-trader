#!/usr/bin/env python3
"""
News Watcher - Monitors for breaking news that could move stocks.

Runs every 30 minutes during market hours.
Alerts immediately if material news is detected.
"""

import os
import json
import requests
import smtplib
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
WATCHLIST = ["NVDA", "MU", "BABA", "ALB", "ALLY", "TSLA"]
SEEN_NEWS_FILE = Path(__file__).parent / "seen_news.json"


def get_api_key():
    return os.getenv("PERPLEXITY_API_KEY")


def load_seen_news():
    if SEEN_NEWS_FILE.exists():
        with open(SEEN_NEWS_FILE) as f:
            return json.load(f)
    return {}


def save_seen_news(seen):
    with open(SEEN_NEWS_FILE, "w") as f:
        json.dump(seen, f)


def query_perplexity(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "sonar",
        "messages": [
            {"role": "system", "content": "You are a breaking news monitor. Only report significant market-moving news. Be specific and concise."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 1000
    }
    response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def send_alert(subject: str, body: str):
    email_to = os.getenv("ALERT_EMAIL_TO")
    email_from = os.getenv("ALERT_EMAIL_FROM")
    email_password = os.getenv("ALERT_EMAIL_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.hostinger.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))

    if not all([email_to, email_from, email_password]):
        print(f"[NO EMAIL] {subject}")
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

        print(f"[ALERT SENT] {subject}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")


def check_breaking_news():
    """Check for breaking news on watchlist stocks."""
    tickers_str = ", ".join(WATCHLIST)

    prompt = f"""Check for BREAKING NEWS in the last 2 hours for: {tickers_str}

Only report if there is MATERIAL NEWS that could move the stock >2%:
- Earnings releases or pre-announcements
- Guidance changes
- Major analyst upgrades/downgrades
- Regulatory decisions
- Product announcements
- Executive changes
- M&A news
- Significant price target changes

For each item found, report:
TICKER: [symbol]
HEADLINE: [one line]
IMPACT: [BULLISH/BEARISH]
DETAILS: [2-3 sentences]

If NO material news in last 2 hours, respond with exactly: "NO_BREAKING_NEWS"

Current time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""

    return query_perplexity(prompt)


def check_new_opportunities():
    """Check for new trading opportunities."""
    prompt = """In the last 4 hours, find any NEW significant:

1. INSIDER BUYING - CEO/CFO/Director purchases >$100k (not option exercises)
2. ANALYST UPGRADES - Major firms with >10% price target increase
3. POLITICIAN TRADES - Congress members buying >$50k

For each, report:
TYPE: [INSIDER/ANALYST/POLITICIAN]
TICKER: [symbol]
DETAILS: [what happened, specific numbers]

If nothing significant, respond with exactly: "NO_NEW_OPPORTUNITIES"
"""
    return query_perplexity(prompt)


def hash_news(text: str) -> str:
    """Create hash of news to detect duplicates."""
    return hashlib.md5(text.encode()).hexdigest()[:16]


def run_check():
    """Run news check."""
    now = datetime.now()
    print(f"\n[{now.strftime('%H:%M')}] Checking for breaking news...")

    seen = load_seen_news()

    # Check breaking news
    try:
        news = check_breaking_news()

        if "NO_BREAKING_NEWS" not in news:
            news_hash = hash_news(news)

            if news_hash not in seen:
                print("  ⚡ Breaking news detected!")

                subject = f"⚡ BREAKING: News Alert for Watchlist"
                body = f"""
BREAKING NEWS ALERT
{now.strftime('%Y-%m-%d %H:%M')}
{'='*50}

{news}

{'='*50}
Review and consider adjusting positions if needed.
"""
                send_alert(subject, body)

                seen[news_hash] = now.isoformat()
                save_seen_news(seen)
            else:
                print("  (News already reported)")
        else:
            print("  No breaking news")

    except Exception as e:
        print(f"  Error checking news: {e}")

    # Check new opportunities (less frequently, include in the check)
    try:
        opps = check_new_opportunities()

        if "NO_NEW_OPPORTUNITIES" not in opps:
            opp_hash = hash_news(opps)

            if opp_hash not in seen:
                print("  🎯 New opportunity detected!")

                subject = f"🎯 NEW OPPORTUNITY: Scanner Alert"
                body = f"""
NEW TRADING OPPORTUNITY
{now.strftime('%Y-%m-%d %H:%M')}
{'='*50}

{opps}

{'='*50}
Run 'python3 analysis.py' for technical analysis.
"""
                send_alert(subject, body)

                seen[opp_hash] = now.isoformat()
                save_seen_news(seen)
            else:
                print("  (Opportunity already reported)")
        else:
            print("  No new opportunities")

    except Exception as e:
        print(f"  Error checking opportunities: {e}")

    print(f"  Done. Next check in 30 minutes.")


if __name__ == "__main__":
    run_check()
