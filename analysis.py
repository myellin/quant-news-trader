#!/usr/bin/env python3
"""
Sophisticated Technical Analysis Engine

Combines multiple factors:
- Trend (moving averages, ADX)
- Momentum (RSI, MACD)
- Volatility (ATR, Bollinger Bands)
- Volume (relative volume, accumulation/distribution)
- Support/Resistance (dynamic, not arbitrary)
- Market regime awareness
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class TechnicalLevels:
    """Key price levels calculated from data."""
    current_price: float
    sma_20: float
    sma_50: float
    sma_200: float
    atr: float  # Average True Range (volatility)
    support_1: float  # Nearest support
    support_2: float  # Stronger support
    resistance_1: float  # Nearest resistance
    resistance_2: float  # Stronger resistance
    volume_support: float  # High volume node below price
    volume_resistance: float  # High volume node above price


@dataclass
class SignalScore:
    """Composite signal with reasoning."""
    ticker: str
    score: float  # -100 (strong sell) to +100 (strong buy)
    trend_score: float
    momentum_score: float
    volume_score: float
    volatility_score: float

    signal: str  # BUY_NOW, BUY_PULLBACK, SELL, WAIT
    entry_type: str  # breakout, pullback, momentum
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward: float

    reasons: list
    warnings: list


def get_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Fetch OHLCV data."""
    stock = yf.Ticker(ticker)
    df = stock.history(period=period)
    return df


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all technical indicators."""
    # Moving averages
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['SMA_200'] = df['Close'].rolling(window=200).mean()
    df['EMA_12'] = df['Close'].ewm(span=12).mean()
    df['EMA_26'] = df['Close'].ewm(span=26).mean()

    # MACD
    df['MACD'] = df['EMA_12'] - df['EMA_26']
    df['MACD_Signal'] = df['MACD'].ewm(span=9).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # ATR (Average True Range)
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()

    # Bollinger Bands
    df['BB_Middle'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Middle'] + (df['BB_Std'] * 2)
    df['BB_Lower'] = df['BB_Middle'] - (df['BB_Std'] * 2)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']
    df['BB_Position'] = (df['Close'] - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower'])

    # Volume analysis
    df['Volume_SMA'] = df['Volume'].rolling(window=20).mean()
    df['Relative_Volume'] = df['Volume'] / df['Volume_SMA']

    # ADX (trend strength)
    df['ADX'] = calculate_adx(df)

    # Rate of Change
    df['ROC_5'] = df['Close'].pct_change(periods=5) * 100
    df['ROC_20'] = df['Close'].pct_change(periods=20) * 100

    return df


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average Directional Index."""
    high = df['High']
    low = df['Low']
    close = df['Close']

    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0

    tr = pd.concat([
        high - low,
        np.abs(high - close.shift()),
        np.abs(low - close.shift())
    ], axis=1).max(axis=1)

    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.abs().rolling(window=period).mean() / atr)

    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()

    return adx


def find_support_resistance(df: pd.DataFrame, current_price: float) -> dict:
    """Find dynamic support/resistance using pivot points and volume."""
    recent = df.tail(60)  # Last 3 months

    # Find swing highs and lows
    highs = []
    lows = []

    for i in range(2, len(recent) - 2):
        # Swing high: higher than 2 bars on each side
        if (recent['High'].iloc[i] > recent['High'].iloc[i-1] and
            recent['High'].iloc[i] > recent['High'].iloc[i-2] and
            recent['High'].iloc[i] > recent['High'].iloc[i+1] and
            recent['High'].iloc[i] > recent['High'].iloc[i+2]):
            highs.append(recent['High'].iloc[i])

        # Swing low
        if (recent['Low'].iloc[i] < recent['Low'].iloc[i-1] and
            recent['Low'].iloc[i] < recent['Low'].iloc[i-2] and
            recent['Low'].iloc[i] < recent['Low'].iloc[i+1] and
            recent['Low'].iloc[i] < recent['Low'].iloc[i+2]):
            lows.append(recent['Low'].iloc[i])

    # Find supports below current price
    supports = sorted([l for l in lows if l < current_price], reverse=True)
    support_1 = supports[0] if supports else current_price * 0.95
    support_2 = supports[1] if len(supports) > 1 else support_1 * 0.97

    # Find resistances above current price
    resistances = sorted([h for h in highs if h > current_price])
    resistance_1 = resistances[0] if resistances else current_price * 1.05
    resistance_2 = resistances[1] if len(resistances) > 1 else resistance_1 * 1.03

    # Volume-weighted price levels (simplified VWAP zones)
    df_temp = recent.copy()
    df_temp['VWAP'] = (df_temp['Close'] * df_temp['Volume']).cumsum() / df_temp['Volume'].cumsum()

    return {
        'support_1': support_1,
        'support_2': support_2,
        'resistance_1': resistance_1,
        'resistance_2': resistance_2,
    }


def analyze_trend(df: pd.DataFrame) -> tuple[float, list]:
    """
    Score trend from -50 to +50.
    Positive = bullish trend, Negative = bearish trend.
    """
    latest = df.iloc[-1]
    score = 0
    reasons = []

    price = latest['Close']
    sma_20 = latest['SMA_20']
    sma_50 = latest['SMA_50']
    sma_200 = latest['SMA_200']
    adx = latest['ADX']

    # Price vs MAs
    if price > sma_20:
        score += 10
        reasons.append("Price above 20-day MA")
    else:
        score -= 10
        reasons.append("Price below 20-day MA")

    if price > sma_50:
        score += 10
        reasons.append("Price above 50-day MA")
    else:
        score -= 10
        reasons.append("Price below 50-day MA")

    if price > sma_200:
        score += 10
        reasons.append("Price above 200-day MA (long-term uptrend)")
    else:
        score -= 10
        reasons.append("Price below 200-day MA (long-term downtrend)")

    # MA alignment (golden/death cross potential)
    if sma_20 > sma_50 > sma_200:
        score += 15
        reasons.append("MAs aligned bullish (20 > 50 > 200)")
    elif sma_20 < sma_50 < sma_200:
        score -= 15
        reasons.append("MAs aligned bearish (20 < 50 < 200)")

    # Trend strength (ADX)
    if adx > 25:
        reasons.append(f"Strong trend (ADX={adx:.1f})")
        # Amplify the trend score if trend is strong
        score = score * 1.2
    elif adx < 20:
        reasons.append(f"Weak/choppy trend (ADX={adx:.1f})")
        score = score * 0.7

    return min(max(score, -50), 50), reasons


def analyze_momentum(df: pd.DataFrame) -> tuple[float, list]:
    """
    Score momentum from -30 to +30.
    """
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    score = 0
    reasons = []

    rsi = latest['RSI']
    macd = latest['MACD']
    macd_signal = latest['MACD_Signal']
    macd_hist = latest['MACD_Hist']
    prev_macd_hist = prev['MACD_Hist']

    # RSI analysis
    if rsi < 30:
        score += 15
        reasons.append(f"RSI oversold ({rsi:.1f}) - potential bounce")
    elif rsi > 70:
        score -= 15
        reasons.append(f"RSI overbought ({rsi:.1f}) - potential pullback")
    elif 40 <= rsi <= 60:
        reasons.append(f"RSI neutral ({rsi:.1f})")
    elif rsi > 50:
        score += 5
        reasons.append(f"RSI bullish ({rsi:.1f})")
    else:
        score -= 5
        reasons.append(f"RSI bearish ({rsi:.1f})")

    # MACD analysis
    if macd > macd_signal:
        score += 10
        reasons.append("MACD above signal (bullish)")
    else:
        score -= 10
        reasons.append("MACD below signal (bearish)")

    # MACD histogram momentum
    if macd_hist > prev_macd_hist:
        score += 5
        reasons.append("MACD histogram increasing")
    else:
        score -= 5
        reasons.append("MACD histogram decreasing")

    return min(max(score, -30), 30), reasons


def analyze_volume(df: pd.DataFrame) -> tuple[float, list]:
    """
    Score volume from -10 to +10.
    """
    latest = df.iloc[-1]
    score = 0
    reasons = []

    rel_vol = latest['Relative_Volume']
    price_change = (latest['Close'] - df.iloc[-2]['Close']) / df.iloc[-2]['Close']

    # High volume on up days is bullish, high volume on down days is bearish
    if rel_vol > 1.5:
        if price_change > 0:
            score += 10
            reasons.append(f"High volume ({rel_vol:.1f}x avg) on up day - accumulation")
        else:
            score -= 10
            reasons.append(f"High volume ({rel_vol:.1f}x avg) on down day - distribution")
    elif rel_vol < 0.7:
        reasons.append(f"Low volume ({rel_vol:.1f}x avg) - lack of conviction")
    else:
        reasons.append(f"Normal volume ({rel_vol:.1f}x avg)")

    return min(max(score, -10), 10), reasons


def analyze_volatility(df: pd.DataFrame) -> tuple[float, list, str]:
    """
    Analyze volatility regime.
    Returns score (-10 to +10), reasons, and regime description.
    """
    latest = df.iloc[-1]
    score = 0
    reasons = []

    bb_position = latest['BB_Position']
    bb_width = latest['BB_Width']
    atr = latest['ATR']
    price = latest['Close']
    atr_pct = (atr / price) * 100

    # Bollinger Band position
    if bb_position < 0.1:
        score += 10
        reasons.append("Near lower Bollinger Band - potential mean reversion")
        regime = "oversold"
    elif bb_position > 0.9:
        score -= 5
        reasons.append("Near upper Bollinger Band - extended")
        regime = "overbought"
    else:
        regime = "normal"
        reasons.append(f"Mid-range in Bollinger Bands ({bb_position:.0%})")

    # Volatility squeeze detection
    if bb_width < df['BB_Width'].rolling(50).mean().iloc[-1] * 0.8:
        reasons.append("Bollinger Band squeeze - big move coming")
        regime = "squeeze"

    # ATR context
    reasons.append(f"Daily ATR: ${atr:.2f} ({atr_pct:.1f}% of price)")

    return score, reasons, regime


def get_market_context() -> dict:
    """Get SPY and VIX for market context."""
    try:
        spy = yf.Ticker("SPY")
        vix = yf.Ticker("^VIX")

        spy_data = spy.history(period="5d")
        vix_data = vix.history(period="5d")

        spy_change = (spy_data['Close'].iloc[-1] - spy_data['Close'].iloc[-2]) / spy_data['Close'].iloc[-2] * 100
        vix_level = vix_data['Close'].iloc[-1]

        return {
            'spy_change': spy_change,
            'vix': vix_level,
            'risk_on': vix_level < 20 and spy_change > -0.5
        }
    except:
        return {'spy_change': 0, 'vix': 20, 'risk_on': True}


def generate_signal(ticker: str) -> SignalScore:
    """Generate comprehensive trading signal."""
    # Fetch data
    df = get_data(ticker, period="1y")
    df = calculate_indicators(df)

    latest = df.iloc[-1]
    price = latest['Close']
    atr = latest['ATR']

    # Get all scores
    trend_score, trend_reasons = analyze_trend(df)
    momentum_score, momentum_reasons = analyze_momentum(df)
    volume_score, volume_reasons = analyze_volume(df)
    volatility_score, volatility_reasons, vol_regime = analyze_volatility(df)

    # Find levels
    levels = find_support_resistance(df, price)

    # Market context
    market = get_market_context()

    # Calculate composite score
    total_score = trend_score + momentum_score + volume_score + volatility_score

    # Adjust for market context
    if not market['risk_on']:
        total_score -= 10
        trend_reasons.append(f"Risk-off market (VIX={market['vix']:.1f})")

    # Determine signal type and entry
    reasons = trend_reasons + momentum_reasons + volume_reasons + volatility_reasons
    warnings = []

    if total_score >= 40:
        # Strong bullish
        if price < latest['SMA_20']:
            signal = "BUY_NOW"
            entry_type = "pullback"
            entry_price = price
            reasons.append("Strong bullish setup at pullback - buy now")
        else:
            signal = "BUY_PULLBACK"
            entry_type = "pullback"
            entry_price = levels['support_1']
            reasons.append(f"Wait for pullback to ${entry_price:.2f}")

    elif total_score >= 20:
        # Moderately bullish
        if vol_regime == "oversold":
            signal = "BUY_NOW"
            entry_type = "mean_reversion"
            entry_price = price
            reasons.append("Oversold bounce setup")
        else:
            signal = "BUY_PULLBACK"
            entry_type = "pullback"
            entry_price = levels['support_1']
            reasons.append(f"Moderately bullish - wait for ${entry_price:.2f}")

    elif total_score <= -40:
        signal = "SELL"
        entry_type = "breakdown"
        entry_price = price
        reasons.append("Strong bearish - avoid or short")

    elif total_score <= -20:
        signal = "WAIT"
        entry_type = "none"
        entry_price = levels['support_2']  # Would need major support to buy
        warnings.append("Bearish bias - wait for better setup")

    else:
        signal = "WAIT"
        entry_type = "none"
        entry_price = levels['support_1']
        warnings.append("No clear edge - patience")

    # Calculate stops and targets using ATR
    # MINIMUM 2:1 R:R - anything less isn't worth the risk
    if signal in ["BUY_NOW", "BUY_PULLBACK"]:
        stop_loss = entry_price - (atr * 1.5)  # Tighter stop: 1.5 ATR
        target_1 = entry_price + (atr * 3)     # 2:1 R:R minimum
        target_2 = entry_price + (atr * 4.5)   # 3:1 R:R
    else:
        stop_loss = price + (atr * 1.5)
        target_1 = price - (atr * 3)
        target_2 = price - (atr * 4.5)

    risk = abs(entry_price - stop_loss)
    reward = abs(target_1 - entry_price)
    risk_reward = reward / risk if risk > 0 else 0

    # Downgrade signal if R:R is bad
    if risk_reward < 1.8 and signal == "BUY_NOW":
        signal = "BUY_PULLBACK"  # Wait for better entry
        warnings.append(f"R:R only {risk_reward:.1f}:1 - wait for pullback to improve entry")

    return SignalScore(
        ticker=ticker,
        score=total_score,
        trend_score=trend_score,
        momentum_score=momentum_score,
        volume_score=volume_score,
        volatility_score=volatility_score,
        signal=signal,
        entry_type=entry_type,
        entry_price=round(entry_price, 2),
        stop_loss=round(stop_loss, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        risk_reward=round(risk_reward, 2),
        reasons=reasons,
        warnings=warnings
    )


def print_analysis(signal: SignalScore):
    """Pretty print the analysis."""
    print(f"\n{'='*60}")
    print(f"  {signal.ticker} ANALYSIS")
    print(f"{'='*60}")

    # Score visualization
    score_bar = ""
    normalized = int((signal.score + 100) / 200 * 20)  # 0-20 scale
    score_bar = "▓" * normalized + "░" * (20 - normalized)

    print(f"\nComposite Score: {signal.score:+.0f} [{score_bar}]")
    print(f"  Trend:      {signal.trend_score:+.0f}")
    print(f"  Momentum:   {signal.momentum_score:+.0f}")
    print(f"  Volume:     {signal.volume_score:+.0f}")
    print(f"  Volatility: {signal.volatility_score:+.0f}")

    signal_emoji = {
        "BUY_NOW": "🟢 BUY NOW",
        "BUY_PULLBACK": "🟡 BUY ON PULLBACK",
        "SELL": "🔴 SELL/AVOID",
        "WAIT": "⚪ WAIT"
    }

    print(f"\n>>> SIGNAL: {signal_emoji.get(signal.signal, signal.signal)}")
    print(f"    Entry Type: {signal.entry_type}")
    print(f"    Entry Price: ${signal.entry_price:.2f}")
    print(f"    Stop Loss: ${signal.stop_loss:.2f}")
    print(f"    Target 1: ${signal.target_1:.2f} (1:1 R:R)")
    print(f"    Target 2: ${signal.target_2:.2f} (2:1 R:R)")
    print(f"    Risk/Reward: {signal.risk_reward:.1f}:1")

    print(f"\nReasons:")
    for r in signal.reasons:
        print(f"  + {r}")

    if signal.warnings:
        print(f"\nWarnings:")
        for w in signal.warnings:
            print(f"  ! {w}")


def main():
    """Run analysis on watchlist."""
    tickers = ["NVDA", "MU", "TSLA", "BABA"]

    print("="*60)
    print("SOPHISTICATED TECHNICAL ANALYSIS")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)

    # Market context
    market = get_market_context()
    print(f"\nMarket Context:")
    print(f"  SPY change: {market['spy_change']:+.2f}%")
    print(f"  VIX: {market['vix']:.1f}")
    print(f"  Regime: {'Risk-On' if market['risk_on'] else 'Risk-Off'}")

    signals = []
    for ticker in tickers:
        try:
            signal = generate_signal(ticker)
            signals.append(signal)
            print_analysis(signal)
        except Exception as e:
            print(f"\nError analyzing {ticker}: {e}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY - RANKED BY SCORE")
    print("="*60)

    signals.sort(key=lambda x: x.score, reverse=True)

    for s in signals:
        print(f"{s.ticker:6} | Score: {s.score:+4.0f} | {s.signal:15} | Entry: ${s.entry_price:.2f}")

    actionable = [s for s in signals if s.signal == "BUY_NOW"]
    if actionable:
        print(f"\n🎯 ACTIONABLE NOW: {', '.join([s.ticker for s in actionable])}")
    else:
        print(f"\n⏳ No immediate entries - wait for pullbacks or setups to develop")


if __name__ == "__main__":
    main()
