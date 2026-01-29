"""Extract trading signals from news analysis."""

import os
import requests
from config import PERPLEXITY_API_URL, PERPLEXITY_MODEL


def get_api_key():
    """Get API key from environment."""
    key = os.getenv("PERPLEXITY_API_KEY")
    if not key:
        raise ValueError("PERPLEXITY_API_KEY not set in environment")
    return key


def extract_signal(ticker: str, news_analysis: str, market_overview: str) -> dict:
    """
    Extract a structured trading signal from news analysis.

    Returns a signal with direction, confidence, strategy suggestion, and reasoning.
    """
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json"
    }

    prompt = f"""Based on the following news analysis and market context, generate a trading signal for {ticker}.

## News Analysis for {ticker}:
{news_analysis}

## Market Overview:
{market_overview}

---

Generate a structured trading signal in this exact format:

DIRECTION: [BULLISH / BEARISH / NEUTRAL]
CONFIDENCE: [0.0 to 1.0]
TIMEFRAME: [1-3 days / 3-7 days / 1-2 weeks]
IV_ENVIRONMENT: [HIGH / NORMAL / LOW] (based on recent vol and upcoming catalysts)

STRATEGY_SUGGESTION:
- If BULLISH + HIGH IV: Sell put spreads or buy call debit spreads
- If BULLISH + LOW IV: Buy calls or call debit spreads
- If BEARISH + HIGH IV: Sell call spreads or buy put debit spreads
- If BEARISH + LOW IV: Buy puts or put debit spreads
- If NEUTRAL + HIGH IV: Iron condors, sell straddles/strangles
- If NEUTRAL + LOW IV: Wait or avoid

ENTRY_TRIGGER: [What specific event/price action should trigger entry]
STOP_LOGIC: [What would invalidate the thesis]
TARGET_LOGIC: [What's the profit target based on]

KEY_CATALYSTS:
- [List upcoming dates/events that matter]

REASONING: [2-3 sentences on why this signal makes sense]

Be specific and actionable. If there's no clear edge, say NEUTRAL with low confidence."""

    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a quantitative trading signal generator. Analyze news and market context to produce actionable trading signals. Be conservative - only suggest trades with clear edge. Output in the exact format requested."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2,
        "max_tokens": 1000
    }

    response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    result = response.json()
    signal_text = result["choices"][0]["message"]["content"]

    # Parse the signal
    signal = parse_signal(signal_text)
    signal["ticker"] = ticker
    signal["raw"] = signal_text

    return signal


def parse_signal(signal_text: str) -> dict:
    """Parse the structured signal text into a dictionary."""
    import re

    signal = {
        "direction": "NEUTRAL",
        "confidence": 0.0,
        "timeframe": "unknown",
        "iv_environment": "NORMAL",
        "strategy": "",
        "entry_trigger": "",
        "stop_logic": "",
        "target_logic": "",
        "catalysts": [],
        "reasoning": ""
    }

    lines = signal_text.split("\n")
    current_section = None

    def clean_line(s):
        """Strip markdown formatting like ** and #."""
        s = re.sub(r'\*\*', '', s)  # Remove bold
        s = re.sub(r'^#+\s*', '', s)  # Remove heading markers
        return s.strip()

    for line in lines:
        line = clean_line(line)
        if not line:
            continue

        if line.startswith("DIRECTION:"):
            val = line.replace("DIRECTION:", "").strip()
            if "BULLISH" in val.upper():
                signal["direction"] = "BULLISH"
            elif "BEARISH" in val.upper():
                signal["direction"] = "BEARISH"
            else:
                signal["direction"] = "NEUTRAL"

        elif line.startswith("CONFIDENCE:"):
            try:
                val = line.replace("CONFIDENCE:", "").strip()
                # Handle ranges like "0.6-0.7" by taking the first number
                val = val.split("-")[0].split()[0]
                signal["confidence"] = float(val)
            except (ValueError, IndexError):
                signal["confidence"] = 0.5

        elif line.startswith("TIMEFRAME:"):
            signal["timeframe"] = line.replace("TIMEFRAME:", "").strip()

        elif line.startswith("IV_ENVIRONMENT:"):
            val = line.replace("IV_ENVIRONMENT:", "").strip().upper()
            if "HIGH" in val:
                signal["iv_environment"] = "HIGH"
            elif "LOW" in val:
                signal["iv_environment"] = "LOW"
            else:
                signal["iv_environment"] = "NORMAL"

        elif line.startswith("STRATEGY_SUGGESTION:"):
            current_section = "strategy"

        elif line.startswith("ENTRY_TRIGGER:"):
            signal["entry_trigger"] = line.replace("ENTRY_TRIGGER:", "").strip()
            current_section = None

        elif line.startswith("STOP_LOGIC:"):
            signal["stop_logic"] = line.replace("STOP_LOGIC:", "").strip()

        elif line.startswith("TARGET_LOGIC:"):
            signal["target_logic"] = line.replace("TARGET_LOGIC:", "").strip()

        elif line.startswith("KEY_CATALYSTS:"):
            current_section = "catalysts"

        elif line.startswith("REASONING:"):
            signal["reasoning"] = line.replace("REASONING:", "").strip()
            current_section = "reasoning"

        elif current_section == "strategy" and line.startswith("-"):
            signal["strategy"] += line + " "

        elif current_section == "catalysts" and line.startswith("-"):
            signal["catalysts"].append(line.lstrip("- "))

        elif current_section == "reasoning":
            signal["reasoning"] += " " + line

    signal["strategy"] = signal["strategy"].strip()
    signal["reasoning"] = signal["reasoning"].strip()

    return signal
