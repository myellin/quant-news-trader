"""
Vercel Serverless Function - Trading Dashboard
"""

from flask import Flask, render_template_string, jsonify
from datetime import datetime
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yfinance as yf

app = Flask(__name__)

# Since Vercel is serverless, we'll store data in memory for the session
# For persistence, you'd need a database (Vercel KV, Supabase, etc.)

WATCHLIST = [
    "NVDA", "MU", "BABA", "ALB", "INTC", "SLV",
    "GOOGL", "AMZN", "AMD", "GOLD", "TXN", "FCX",
    "JD", "PDD", "VZ", "TSLA", "ALLY"
]

# In-memory storage (resets on cold start)
POSITIONS = []
TRADE_HISTORY = []

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Trading Dashboard</title>
    <meta http-equiv="refresh" content="60">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #58a6ff; margin-bottom: 10px; font-size: 24px; }
        .subtitle { color: #8b949e; margin-bottom: 30px; font-size: 14px; }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }

        .card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 20px;
        }
        .card h2 {
            color: #58a6ff;
            font-size: 12px;
            text-transform: uppercase;
            margin-bottom: 15px;
            letter-spacing: 0.5px;
        }

        .big-number {
            font-size: 32px;
            font-weight: 700;
            margin: 10px 0;
        }

        .positive { color: #3fb950; }
        .negative { color: #f85149; }

        .stat {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #21262d;
            font-size: 14px;
        }
        .stat:last-child { border-bottom: none; }
        .stat-label { color: #8b949e; }

        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th, td { padding: 12px 8px; text-align: left; border-bottom: 1px solid #21262d; }
        th { color: #8b949e; font-weight: 500; font-size: 11px; text-transform: uppercase; }
        tr:hover { background: #21262d; }

        .badge {
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-up { background: #238636; color: white; }
        .badge-down { background: #da3633; color: white; }
        .badge-neutral { background: #30363d; color: #8b949e; }

        .ticker-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #21262d;
        }
        .ticker-row:last-child { border-bottom: none; }
        .ticker-name { font-weight: 600; }
        .ticker-price { color: #8b949e; }

        @media (max-width: 600px) {
            .grid { grid-template-columns: 1fr; }
            table { font-size: 12px; }
            th, td { padding: 8px 4px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 Trading Dashboard</h1>
        <p class="subtitle">Last updated: {{ updated }} ET | Auto-refreshes every 60s</p>

        <div class="grid">
            <div class="card">
                <h2>Portfolio P&L</h2>
                <div class="big-number {{ 'positive' if total_pnl >= 0 else 'negative' }}">
                    ${{ "%.2f"|format(total_pnl) }}
                </div>
                <div class="stat">
                    <span class="stat-label">Open Positions</span>
                    <span>{{ positions|length }}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Closed Trades</span>
                    <span>{{ history|length }}</span>
                </div>
            </div>

            <div class="card">
                <h2>Win Rate</h2>
                <div class="big-number">{{ "%.0f"|format(win_rate) }}%</div>
                <div class="stat">
                    <span class="stat-label">Wins</span>
                    <span class="positive">{{ wins }}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Losses</span>
                    <span class="negative">{{ losses }}</span>
                </div>
            </div>

            <div class="card">
                <h2>Market Status</h2>
                <div class="big-number">{{ market_status }}</div>
                <div class="stat">
                    <span class="stat-label">SPY</span>
                    <span class="{{ 'positive' if spy_change >= 0 else 'negative' }}">{{ "%.2f"|format(spy_change) }}%</span>
                </div>
                <div class="stat">
                    <span class="stat-label">VIX</span>
                    <span>{{ "%.1f"|format(vix) }}</span>
                </div>
            </div>
        </div>

        <div class="card" style="margin-bottom: 20px;">
            <h2>Watchlist</h2>
            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Price</th>
                        <th>Change</th>
                        <th>Signal</th>
                    </tr>
                </thead>
                <tbody>
                {% for stock in stocks %}
                    <tr>
                        <td><strong>{{ stock.ticker }}</strong></td>
                        <td>${{ "%.2f"|format(stock.price) }}</td>
                        <td class="{{ 'positive' if stock.change >= 0 else 'negative' }}">
                            {{ "%.2f"|format(stock.change) }}%
                        </td>
                        <td>
                            <span class="badge {{ 'badge-up' if stock.change > 1 else 'badge-down' if stock.change < -1 else 'badge-neutral' }}">
                                {{ 'BULLISH' if stock.change > 1 else 'BEARISH' if stock.change < -1 else 'NEUTRAL' }}
                            </span>
                        </td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>

        {% if positions %}
        <div class="card" style="margin-bottom: 20px;">
            <h2>Open Positions</h2>
            <table>
                <thead>
                    <tr>
                        <th>Contract</th>
                        <th>Entry</th>
                        <th>Current</th>
                        <th>P&L</th>
                    </tr>
                </thead>
                <tbody>
                {% for p in positions %}
                    <tr>
                        <td>{{ p.contract }}</td>
                        <td>${{ "%.2f"|format(p.entry) }}</td>
                        <td>${{ "%.2f"|format(p.current) }}</td>
                        <td class="{{ 'positive' if p.pnl >= 0 else 'negative' }}">
                            ${{ "%.2f"|format(p.pnl) }}
                        </td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}

        <div class="card">
            <h2>System Status</h2>
            <div class="stat">
                <span class="stat-label">Deployment</span>
                <span>Vercel</span>
            </div>
            <div class="stat">
                <span class="stat-label">Data</span>
                <span>Live (yfinance)</span>
            </div>
            <div class="stat">
                <span class="stat-label">Portfolio</span>
                <span style="color: #f0883e;">In-memory (resets on deploy)</span>
            </div>
        </div>

        <p style="text-align: center; color: #8b949e; font-size: 12px; margin-top: 20px;">
            Built with Python + Flask | Deployed on Vercel
        </p>
    </div>
</body>
</html>
"""


def get_stock_data(ticker):
    """Get current stock data."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2d")
        if len(hist) >= 2:
            current = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2]
            change = ((current - prev) / prev) * 100
            return {"ticker": ticker, "price": current, "change": change}
        return {"ticker": ticker, "price": 0, "change": 0}
    except:
        return {"ticker": ticker, "price": 0, "change": 0}


def get_market_context():
    """Get SPY and VIX."""
    try:
        spy = yf.Ticker("SPY")
        vix = yf.Ticker("^VIX")

        spy_hist = spy.history(period="2d")
        vix_hist = vix.history(period="1d")

        spy_change = 0
        if len(spy_hist) >= 2:
            spy_change = ((spy_hist['Close'].iloc[-1] - spy_hist['Close'].iloc[-2]) / spy_hist['Close'].iloc[-2]) * 100

        vix_level = vix_hist['Close'].iloc[-1] if len(vix_hist) > 0 else 20

        return spy_change, vix_level
    except:
        return 0, 20


@app.route('/')
def dashboard():
    """Main dashboard."""
    # Get stock data
    stocks = []
    for ticker in WATCHLIST[:10]:  # Limit to avoid timeout
        stocks.append(get_stock_data(ticker))

    # Get market context
    spy_change, vix = get_market_context()

    # Market status
    hour = datetime.now().hour
    if 9 <= hour < 16:
        market_status = "OPEN"
    else:
        market_status = "CLOSED"

    # Calculate totals from positions
    total_pnl = sum(p.get('pnl', 0) for p in POSITIONS)
    wins = len([h for h in TRADE_HISTORY if h.get('result') == 'WIN'])
    losses = len([h for h in TRADE_HISTORY if h.get('result') == 'LOSS'])
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

    return render_template_string(
        DASHBOARD_HTML,
        stocks=stocks,
        positions=POSITIONS,
        history=TRADE_HISTORY,
        total_pnl=total_pnl,
        win_rate=win_rate,
        wins=wins,
        losses=losses,
        spy_change=spy_change,
        vix=vix,
        market_status=market_status,
        updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


@app.route('/api/stocks')
def api_stocks():
    """API endpoint for stock data."""
    stocks = []
    for ticker in WATCHLIST:
        stocks.append(get_stock_data(ticker))
    return jsonify(stocks)


@app.route('/api/health')
def health():
    """Health check."""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


# Vercel requires this
app = app
