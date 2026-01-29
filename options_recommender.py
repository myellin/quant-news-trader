#!/usr/bin/env python3
"""Generate specific options trade recommendations."""

import os
import requests
from dotenv import load_dotenv
from config import PERPLEXITY_API_URL, PERPLEXITY_MODEL

load_dotenv()


def get_api_key():
    key = os.getenv("PERPLEXITY_API_KEY")
    if not key:
        raise ValueError("PERPLEXITY_API_KEY not set")
    return key


def get_specific_options_trade(ticker: str, direction: str, timeframe: str) -> str:
    """
    Get specific options trade recommendation with current prices.
    """
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json"
    }

    prompt = f"""I need a SPECIFIC options trade recommendation for {ticker}.

Direction bias: {direction}
Timeframe: {timeframe}

Provide the following with CURRENT real data:

1. **CURRENT STOCK PRICE**: What is {ticker} trading at right now?

2. **SPECIFIC TRADE**: Give me ONE specific options trade:
   - Exact contract: Strike price, expiration date (use actual available expiration dates)
   - Entry price range (bid/ask if available, or estimate)
   - For spreads: both legs with strikes

3. **POSITION SIZING**:
   - Max risk per contract/spread
   - Suggested position size for a $10,000 account (risk 2-5% per trade)

4. **ENTRY CRITERIA**:
   - Exact price level or condition to enter
   - Time of day considerations

5. **EXIT PLAN**:
   - Profit target (% gain on the option)
   - Stop loss (stock price or option price)
   - Time stop (when to exit if nothing happens)

6. **KEY LEVELS**:
   - Support levels to watch
   - Resistance levels / targets

7. **RISK/REWARD**: Calculate the R:R ratio

8. **WHY THIS TRADE**: 2-3 sentences on the edge

Be extremely specific with numbers. Use real current market data."""

    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are an options trading specialist. Provide specific, actionable trade recommendations with real current market data. Always include exact strikes, expirations, and price levels. Be precise with numbers."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 1500
    }

    response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def main():
    # Based on our signals: MU and BABA are bullish
    trades = [
        ("MU", "BULLISH", "3-7 days"),
        ("BABA", "BULLISH", "1-2 weeks"),
        ("NVDA", "CAUTIOUSLY BULLISH (wait for breakout)", "1-2 weeks"),
        ("TSLA", "NEUTRAL - volatility play post-earnings", "1 week"),
    ]

    print("=" * 70)
    print("SPECIFIC OPTIONS TRADE RECOMMENDATIONS")
    print("=" * 70)

    for ticker, direction, timeframe in trades:
        print(f"\n{'='*70}")
        print(f"  {ticker} - {direction}")
        print("=" * 70)

        try:
            recommendation = get_specific_options_trade(ticker, direction, timeframe)
            print(recommendation)
        except Exception as e:
            print(f"Error getting recommendation: {e}")

        print()


if __name__ == "__main__":
    main()
