#!/usr/bin/env python3
"""
Silver Trading Strategy Module

Specialized strategy for trading silver (SLV) incorporating:
- Macro factors (Fed policy, dollar strength, real yields)
- Gold/silver ratio mean reversion
- Post-crash capitulation detection
- Retail sentiment extremes
"""

import os
import requests
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class MacroContext:
    """Macro environment for precious metals."""
    dxy_trend: str  # "strengthening", "weakening", "neutral"
    fed_stance: str  # "hawkish", "dovish", "neutral"
    real_yields_trend: str  # "rising", "falling", "stable"
    geopolitical_risk: str  # "elevated", "normal", "low"
    risk_appetite: str  # "risk_on", "risk_off"

    def precious_metals_bias(self) -> str:
        """Determine overall PM bias from macro."""
        bullish_factors = 0
        bearish_factors = 0

        if self.dxy_trend == "weakening":
            bullish_factors += 2
        elif self.dxy_trend == "strengthening":
            bearish_factors += 2

        if self.fed_stance == "dovish":
            bullish_factors += 2
        elif self.fed_stance == "hawkish":
            bearish_factors += 2

        if self.real_yields_trend == "falling":
            bullish_factors += 1
        elif self.real_yields_trend == "rising":
            bearish_factors += 1

        if self.geopolitical_risk == "elevated":
            bullish_factors += 1

        if self.risk_appetite == "risk_off":
            bullish_factors += 1
        elif self.risk_appetite == "risk_on":
            bearish_factors += 1

        if bullish_factors >= bearish_factors + 2:
            return "BULLISH"
        elif bearish_factors >= bullish_factors + 2:
            return "BEARISH"
        return "NEUTRAL"


@dataclass
class SilverSignal:
    """Silver-specific trading signal."""
    signal_type: str  # BUY_CRASH, BUY_PULLBACK, SELL, WAIT
    confidence: str  # HIGH, MEDIUM, LOW

    # Price levels
    current_price: float
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward: float

    # Context
    macro_bias: str
    gold_silver_ratio: float
    ratio_signal: str  # "silver_cheap", "silver_expensive", "fair_value"
    crash_detected: bool
    capitulation_score: int  # 0-100

    # Reasoning
    reasons: list
    warnings: list


@dataclass
class CrashAnalysis:
    """Analysis of a potential crash/capitulation event."""
    is_crash: bool
    severity: str  # "minor", "moderate", "severe", "extreme"
    drop_percent: float
    capitulation_score: int  # 0-100, higher = more likely capitulation
    reasons: list


def analyze_crash(
    current_price: float,
    high_price: float,
    daily_change_pct: float,
    volume_ratio: float,  # vs 20-day average
    rsi: float
) -> CrashAnalysis:
    """
    Detect if we're in a crash/capitulation scenario.

    Capitulation signs:
    - Large single-day drop (>5% for silver is significant, >15% is extreme)
    - High volume (panic selling)
    - RSI deeply oversold
    - Price far from recent highs
    """
    drop_from_high = ((high_price - current_price) / high_price) * 100

    reasons = []
    capitulation_score = 0

    # Daily drop analysis
    if daily_change_pct <= -25:
        capitulation_score += 40
        reasons.append(f"Extreme daily drop: {daily_change_pct:.1f}%")
        severity = "extreme"
    elif daily_change_pct <= -15:
        capitulation_score += 30
        reasons.append(f"Severe daily drop: {daily_change_pct:.1f}%")
        severity = "severe"
    elif daily_change_pct <= -8:
        capitulation_score += 20
        reasons.append(f"Moderate daily drop: {daily_change_pct:.1f}%")
        severity = "moderate"
    elif daily_change_pct <= -5:
        capitulation_score += 10
        reasons.append(f"Minor daily drop: {daily_change_pct:.1f}%")
        severity = "minor"
    else:
        severity = "none"

    # Drop from highs
    if drop_from_high >= 30:
        capitulation_score += 25
        reasons.append(f"Down {drop_from_high:.1f}% from highs - major correction")
    elif drop_from_high >= 20:
        capitulation_score += 15
        reasons.append(f"Down {drop_from_high:.1f}% from highs - correction territory")
    elif drop_from_high >= 10:
        capitulation_score += 5
        reasons.append(f"Down {drop_from_high:.1f}% from highs - pullback")

    # Volume spike (panic selling)
    if volume_ratio >= 5:
        capitulation_score += 20
        reasons.append(f"Extreme volume: {volume_ratio:.1f}x average - panic selling")
    elif volume_ratio >= 3:
        capitulation_score += 15
        reasons.append(f"High volume: {volume_ratio:.1f}x average - heavy selling")
    elif volume_ratio >= 2:
        capitulation_score += 10
        reasons.append(f"Elevated volume: {volume_ratio:.1f}x average")

    # RSI oversold
    if rsi <= 15:
        capitulation_score += 15
        reasons.append(f"RSI extremely oversold: {rsi:.1f}")
    elif rsi <= 25:
        capitulation_score += 10
        reasons.append(f"RSI deeply oversold: {rsi:.1f}")
    elif rsi <= 30:
        capitulation_score += 5
        reasons.append(f"RSI oversold: {rsi:.1f}")

    is_crash = capitulation_score >= 30 or daily_change_pct <= -10

    return CrashAnalysis(
        is_crash=is_crash,
        severity=severity,
        drop_percent=daily_change_pct,
        capitulation_score=min(capitulation_score, 100),
        reasons=reasons
    )


def analyze_gold_silver_ratio(gold_price: float, silver_price: float) -> tuple[float, str, str]:
    """
    Analyze gold/silver ratio for relative value.

    Historical context:
    - Long-term average: ~60-65
    - Silver cheap: >80 (buy silver)
    - Silver expensive: <50 (sell silver / buy gold)
    - Extreme cheap: >90 (strong buy silver)
    - Extreme expensive: <45 (strong sell silver)
    """
    ratio = gold_price / silver_price

    if ratio >= 90:
        signal = "silver_very_cheap"
        reason = f"Gold/Silver ratio {ratio:.1f} - historically extreme, silver deeply undervalued vs gold"
    elif ratio >= 80:
        signal = "silver_cheap"
        reason = f"Gold/Silver ratio {ratio:.1f} - silver undervalued vs gold"
    elif ratio >= 65:
        signal = "fair_value"
        reason = f"Gold/Silver ratio {ratio:.1f} - near historical average"
    elif ratio >= 50:
        signal = "silver_rich"
        reason = f"Gold/Silver ratio {ratio:.1f} - silver relatively expensive"
    else:
        signal = "silver_very_rich"
        reason = f"Gold/Silver ratio {ratio:.1f} - silver extremely expensive vs gold"

    return ratio, signal, reason


def fetch_silver_macro_context() -> Optional[MacroContext]:
    """
    Fetch current macro context for precious metals using Perplexity.
    Returns None if API call fails.
    """
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    prompt = """Analyze current macro conditions for precious metals trading. Answer concisely:

1. US Dollar (DXY) trend: strengthening, weakening, or neutral?
2. Fed policy stance: hawkish, dovish, or neutral?
3. Real yields trend: rising, falling, or stable?
4. Geopolitical risk level: elevated, normal, or low?
5. Overall risk appetite: risk_on or risk_off?

Format: Just list the 5 answers, one per line."""

    payload = {
        "model": "sonar",
        "messages": [
            {"role": "system", "content": "You are a macro analyst. Be concise and direct."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 200
    }

    try:
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].lower()

        # Parse response
        dxy = "strengthening" if "strengthen" in content else ("weakening" if "weaken" in content else "neutral")
        fed = "hawkish" if "hawkish" in content else ("dovish" if "dovish" in content else "neutral")
        yields = "rising" if "rising" in content else ("falling" if "falling" in content else "stable")
        geo = "elevated" if "elevated" in content else ("low" if "low" in content else "normal")
        risk = "risk_off" if "risk_off" in content or "risk off" in content else "risk_on"

        return MacroContext(
            dxy_trend=dxy,
            fed_stance=fed,
            real_yields_trend=yields,
            geopolitical_risk=geo,
            risk_appetite=risk
        )
    except Exception:
        return None


def generate_silver_signal(
    silver_price: float,
    gold_price: float,
    silver_high_52w: float,
    daily_change_pct: float,
    volume_ratio: float,
    rsi: float,
    atr: float,
    macro: Optional[MacroContext] = None
) -> SilverSignal:
    """
    Generate a comprehensive silver trading signal.

    Args:
        silver_price: Current SLV or spot silver price
        gold_price: Current gold price for ratio analysis
        silver_high_52w: 52-week high for crash detection
        daily_change_pct: Today's percentage change
        volume_ratio: Volume vs 20-day average
        rsi: Current RSI reading
        atr: Average True Range for stops/targets
        macro: Optional macro context from Perplexity
    """
    reasons = []
    warnings = []

    # Analyze crash/capitulation
    crash = analyze_crash(silver_price, silver_high_52w, daily_change_pct, volume_ratio, rsi)

    # Analyze gold/silver ratio
    gs_ratio, ratio_signal, ratio_reason = analyze_gold_silver_ratio(gold_price, silver_price)
    reasons.append(ratio_reason)

    # Macro context
    if macro:
        macro_bias = macro.precious_metals_bias()
        reasons.append(f"Macro bias: {macro_bias} (DXY {macro.dxy_trend}, Fed {macro.fed_stance})")
    else:
        macro_bias = "UNKNOWN"
        warnings.append("Could not fetch macro context - using technical analysis only")

    # Determine signal
    if crash.is_crash and crash.capitulation_score >= 50:
        # High probability capitulation - aggressive buy
        signal_type = "BUY_CRASH"
        confidence = "HIGH" if crash.capitulation_score >= 70 else "MEDIUM"
        entry_price = silver_price  # Buy now on capitulation
        reasons.append(f"Capitulation detected (score: {crash.capitulation_score}/100)")
        reasons.extend(crash.reasons)

        if macro_bias == "BEARISH":
            warnings.append("Macro headwinds remain - size position smaller")
            confidence = "MEDIUM"

    elif crash.is_crash and crash.capitulation_score >= 30:
        # Possible capitulation - cautious buy
        signal_type = "BUY_CRASH"
        confidence = "MEDIUM"
        entry_price = silver_price
        reasons.append(f"Possible capitulation (score: {crash.capitulation_score}/100)")
        reasons.extend(crash.reasons)
        warnings.append("Wait for stabilization candle before full position")

    elif ratio_signal in ["silver_very_cheap", "silver_cheap"] and rsi < 40:
        # Ratio play + oversold
        signal_type = "BUY_PULLBACK"
        confidence = "MEDIUM"
        entry_price = silver_price - (atr * 0.5)  # Wait for small pullback
        reasons.append("Silver cheap vs gold + oversold RSI")

    elif ratio_signal in ["silver_very_rich", "silver_rich"] and rsi > 70:
        # Overbought + expensive
        signal_type = "SELL"
        confidence = "MEDIUM"
        entry_price = silver_price
        reasons.append("Silver expensive vs gold + overbought RSI")

    else:
        signal_type = "WAIT"
        confidence = "LOW"
        entry_price = silver_price - (atr * 1.5)  # Would need bigger pullback
        warnings.append("No clear edge - wait for better setup")

    # Calculate stops and targets
    if signal_type in ["BUY_CRASH", "BUY_PULLBACK"]:
        # Wider stops for volatile silver, especially post-crash
        stop_multiplier = 2.5 if crash.is_crash else 2.0
        stop_loss = entry_price - (atr * stop_multiplier)
        target_1 = entry_price + (atr * 4)  # 1.6:1 to 2:1 R:R
        target_2 = entry_price + (atr * 6)  # 2.4:1 to 3:1 R:R
    else:
        stop_loss = entry_price + (atr * 2)
        target_1 = entry_price - (atr * 4)
        target_2 = entry_price - (atr * 6)

    risk = abs(entry_price - stop_loss)
    reward = abs(target_1 - entry_price)
    risk_reward = reward / risk if risk > 0 else 0

    return SilverSignal(
        signal_type=signal_type,
        confidence=confidence,
        current_price=silver_price,
        entry_price=round(entry_price, 2),
        stop_loss=round(stop_loss, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        risk_reward=round(risk_reward, 2),
        macro_bias=macro_bias,
        gold_silver_ratio=round(gs_ratio, 1),
        ratio_signal=ratio_signal,
        crash_detected=crash.is_crash,
        capitulation_score=crash.capitulation_score,
        reasons=reasons,
        warnings=warnings
    )


def print_silver_signal(signal: SilverSignal):
    """Pretty print the silver signal."""
    print(f"\n{'='*60}")
    print(f"  SILVER (SLV) STRATEGY SIGNAL")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    # Signal box
    signal_colors = {
        "BUY_CRASH": "BUY THE CRASH",
        "BUY_PULLBACK": "BUY ON PULLBACK",
        "SELL": "SELL / AVOID",
        "WAIT": "WAIT"
    }

    print(f"\n>>> SIGNAL: {signal_colors.get(signal.signal_type, signal.signal_type)}")
    print(f"    Confidence: {signal.confidence}")

    if signal.crash_detected:
        print(f"\n    CRASH DETECTED - Capitulation Score: {signal.capitulation_score}/100")

    print(f"\n  Price Levels:")
    print(f"    Current:    ${signal.current_price:.2f}")
    print(f"    Entry:      ${signal.entry_price:.2f}")
    print(f"    Stop Loss:  ${signal.stop_loss:.2f}")
    print(f"    Target 1:   ${signal.target_1:.2f}")
    print(f"    Target 2:   ${signal.target_2:.2f}")
    print(f"    R:R Ratio:  {signal.risk_reward:.1f}:1")

    print(f"\n  Context:")
    print(f"    Macro Bias:       {signal.macro_bias}")
    print(f"    Gold/Silver:      {signal.gold_silver_ratio} ({signal.ratio_signal})")

    print(f"\n  Reasons:")
    for r in signal.reasons:
        print(f"    + {r}")

    if signal.warnings:
        print(f"\n  Warnings:")
        for w in signal.warnings:
            print(f"    ! {w}")

    print(f"\n{'='*60}")


# Example usage / testing
if __name__ == "__main__":
    # Simulate the Jan 2026 crash scenario
    print("Simulating Jan 2026 Silver Crash Scenario...")
    print("Silver dropped from $121 to ~$80 (-30%)")

    signal = generate_silver_signal(
        silver_price=80.0,        # Crashed to $80
        gold_price=2800.0,        # Gold holding better
        silver_high_52w=121.0,    # Recent high
        daily_change_pct=-28.0,   # Massive single-day drop
        volume_ratio=5.0,         # 5x normal volume (panic)
        rsi=18.0,                 # Extremely oversold
        atr=3.5,                  # High volatility
        macro=MacroContext(
            dxy_trend="strengthening",    # Warsh nomination boosted dollar
            fed_stance="hawkish",         # Warsh = inflation hawk
            real_yields_trend="rising",
            geopolitical_risk="normal",
            risk_appetite="risk_on"       # Equity rally
        )
    )

    print_silver_signal(signal)
