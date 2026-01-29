"""Fetch and analyze news using Perplexity API."""

import os
import requests
from config import PERPLEXITY_API_URL, PERPLEXITY_MODEL


def get_api_key():
    """Get API key from environment."""
    key = os.getenv("PERPLEXITY_API_KEY")
    if not key:
        raise ValueError("PERPLEXITY_API_KEY not set in environment")
    return key


def fetch_news_analysis(ticker: str, company_name: str) -> dict:
    """
    Fetch recent news and analysis for a ticker using Perplexity.

    Returns structured analysis including sentiment, catalysts, and key events.
    """
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json"
    }

    prompt = f"""Analyze the latest news and market sentiment for {company_name} ({ticker}) for swing trading purposes.

Provide a structured analysis:

1. **Recent News (last 48-72 hours)**: List the most significant news items with dates
2. **Sentiment**: Overall market sentiment (bullish/bearish/neutral) and why
3. **Catalysts**: Upcoming events that could move the stock (earnings, product launches, regulatory decisions, etc.)
4. **Options Flow**: Any notable unusual options activity if available
5. **Technical Context**: Current price action context (at highs, pulling back, breaking out, etc.)
6. **Related Tickers**: Other stocks that might be affected by this news
7. **Risk Factors**: Key risks to watch

Be specific with dates, numbers, and sources where possible."""

    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a financial analyst assistant focused on swing trading. Provide factual, actionable analysis based on current news and market data. Be specific and cite sources when possible."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.1,
        "max_tokens": 2000
    }

    response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    result = response.json()
    return {
        "ticker": ticker,
        "company": company_name,
        "analysis": result["choices"][0]["message"]["content"],
        "model": result.get("model", PERPLEXITY_MODEL)
    }


def fetch_market_overview() -> dict:
    """Fetch overall market conditions and macro context."""
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json"
    }

    prompt = """Provide a current market overview for swing trading:

1. **Market Regime**: Are we in a risk-on or risk-off environment?
2. **Key Macro Factors**: Fed policy, economic data, geopolitical events affecting markets today
3. **Sector Rotation**: Which sectors are showing strength/weakness?
4. **VIX/Volatility**: Current volatility environment and what it means for options
5. **Key Levels**: S&P 500 and QQQ key support/resistance levels

Focus on actionable context for the next 1-2 weeks."""

    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a market analyst providing actionable macro context for swing traders. Be specific with numbers and levels."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.1,
        "max_tokens": 1500
    }

    response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    result = response.json()
    return {
        "overview": result["choices"][0]["message"]["content"],
        "model": result.get("model", PERPLEXITY_MODEL)
    }
