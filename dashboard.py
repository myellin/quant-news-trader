#!/usr/bin/env python3
"""
Trading Dashboard - Web UI for portfolio tracking.

Run: python3 dashboard.py
Open: http://localhost:5000
"""

from flask import Flask, render_template_string, jsonify
from datetime import datetime
import json
from pathlib import Path

from portfolio import (
    load_portfolio, load_trade_history, get_portfolio_summary,
    update_positions, close_position
)
from options_trades import generate_trades

app = Flask(__name__)

WATCHLIST = [
    "NVDA", "MU", "BABA", "ALB", "INTC", "SLV",
    "GOOGL", "AMZN", "AMD", "GOLD", "TXN", "FCX",
    "JD", "PDD", "VZ", "TSLA", "ALLY"
]

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Trading Dashboard</title>
    <meta http-equiv="refresh" content="60">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #58a6ff; margin-bottom: 10px; }
        .subtitle { color: #8b949e; margin-bottom: 30px; }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 20px;
        }
        .card h2 {
            color: #58a6ff;
            font-size: 14px;
            text-transform: uppercase;
            margin-bottom: 15px;
        }

        .stat {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #21262d;
        }
        .stat:last-child { border-bottom: none; }
        .stat-label { color: #8b949e; }
        .stat-value { font-weight: 600; font-size: 18px; }

        .positive { color: #3fb950; }
        .negative { color: #f85149; }
        .neutral { color: #8b949e; }

        .big-number {
            font-size: 36px;
            font-weight: 700;
            margin: 10px 0;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #21262d;
        }
        th {
            color: #8b949e;
            font-weight: 500;
            font-size: 12px;
            text-transform: uppercase;
        }
        tr:hover { background: #21262d; }

        .badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }
        .badge-win { background: #238636; color: white; }
        .badge-loss { background: #da3633; color: white; }
        .badge-open { background: #1f6feb; color: white; }

        .progress-bar {
            height: 8px;
            background: #21262d;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 10px;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #3fb950, #58a6ff);
            border-radius: 4px;
        }

        .trade-idea {
            background: #21262d;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 10px;
        }
        .trade-idea h3 {
            color: #58a6ff;
            font-size: 14px;
            margin-bottom: 8px;
        }
        .trade-idea .details {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            font-size: 13px;
        }
        .trade-idea .label { color: #8b949e; }

        .refresh-note {
            text-align: center;
            color: #8b949e;
            font-size: 12px;
            margin-top: 20px;
        }

        .actions { margin-top: 15px; }
        .btn {
            padding: 8px 16px;
            border-radius: 6px;
            border: none;
            cursor: pointer;
            font-size: 13px;
            margin-right: 8px;
        }
        .btn-primary { background: #238636; color: white; }
        .btn-danger { background: #da3633; color: white; }
        .btn:hover { opacity: 0.8; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 Trading Dashboard</h1>
        <p class="subtitle">Last updated: {{ updated }} | Auto-refreshes every 60s</p>

        <!-- Summary Cards -->
        <div class="grid">
            <div class="card">
                <h2>Total P&L</h2>
                <div class="big-number {{ 'positive' if summary.total_pnl >= 0 else 'negative' }}">
                    ${{ "%.2f"|format(summary.total_pnl) }}
                </div>
                <div class="stat">
                    <span class="stat-label">Unrealized</span>
                    <span class="{{ 'positive' if summary.unrealized_pnl >= 0 else 'negative' }}">${{ "%.2f"|format(summary.unrealized_pnl) }}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Realized</span>
                    <span class="{{ 'positive' if summary.realized_pnl >= 0 else 'negative' }}">${{ "%.2f"|format(summary.realized_pnl) }}</span>
                </div>
            </div>

            <div class="card">
                <h2>Win Rate</h2>
                <div class="big-number">{{ "%.1f"|format(summary.win_rate) }}%</div>
                <div class="stat">
                    <span class="stat-label">Wins</span>
                    <span class="positive">{{ summary.wins }}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Losses</span>
                    <span class="negative">{{ summary.losses }}</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {{ summary.win_rate }}%"></div>
                </div>
            </div>

            <div class="card">
                <h2>Portfolio Value</h2>
                <div class="big-number">${{ "%.2f"|format(summary.total_value) }}</div>
                <div class="stat">
                    <span class="stat-label">Cost Basis</span>
                    <span>${{ "%.2f"|format(summary.total_cost) }}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Open Positions</span>
                    <span>{{ summary.open_positions }}</span>
                </div>
            </div>
        </div>

        <!-- Open Positions -->
        <div class="card" style="margin-bottom: 20px;">
            <h2>Open Positions (Trades We're Currently In)</h2>
            {% if positions %}
            <table>
                <thead>
                    <tr>
                        <th>Contract</th>
                        <th>Opened</th>
                        <th>Entry</th>
                        <th>Current</th>
                        <th>P&L</th>
                        <th>Target</th>
                        <th>Stop</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                {% for p in positions %}
                    <tr>
                        <td><strong>{{ p.contract }}</strong><br><small style="color: #8b949e;">x{{ p.contracts }} contracts</small></td>
                        <td><small>{{ p.entry_date }}</small></td>
                        <td>${{ "%.2f"|format(p.entry_price) }}</td>
                        <td>${{ "%.2f"|format(p.current_price) }}</td>
                        <td class="{{ 'positive' if p.pnl_dollars >= 0 else 'negative' }}">
                            ${{ "%.2f"|format(p.pnl_dollars) }}<br>
                            <small>({{ "%.1f"|format(p.pnl_percent) }}%)</small>
                        </td>
                        <td class="positive">${{ "%.2f"|format(p.target_price) }}</td>
                        <td class="negative">${{ "%.2f"|format(p.stop_price) }}</td>
                        <td>
                            {% if p.current_price >= p.target_price %}
                                <span class="badge badge-win">🎯 SELL</span>
                            {% elif p.current_price <= p.stop_price %}
                                <span class="badge badge-loss">🛑 SELL</span>
                            {% else %}
                                <span class="badge badge-open">HOLDING</span>
                            {% endif %}
                        </td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p style="color: #8b949e; padding: 20px 0;">No open positions. Check trade ideas below.</p>
            {% endif %}
        </div>

        <!-- Closed Trades -->
        <div class="card" style="margin-bottom: 20px;">
            <h2>Closed Trades (Completed - Win/Loss Recorded)</h2>
            {% if history %}
            <table>
                <thead>
                    <tr>
                        <th>Opened</th>
                        <th>Closed</th>
                        <th>Contract</th>
                        <th>Entry</th>
                        <th>Exit</th>
                        <th>P&L</th>
                        <th>Result</th>
                        <th>Reason</th>
                    </tr>
                </thead>
                <tbody>
                {% for t in history %}
                    <tr>
                        <td><small>{{ t.entry_date }}</small></td>
                        <td><small>{{ t.exit_date }}</small></td>
                        <td>{{ t.contract }}</td>
                        <td>${{ "%.2f"|format(t.entry_price) }}</td>
                        <td>${{ "%.2f"|format(t.exit_price) }}</td>
                        <td class="{{ 'positive' if t.pnl_dollars >= 0 else 'negative' }}">
                            ${{ "%.2f"|format(t.pnl_dollars) }}<br><small>({{ "%.1f"|format(t.pnl_percent) }}%)</small>
                        </td>
                        <td>
                            <span class="badge {{ 'badge-win' if t.result == 'WIN' else 'badge-loss' }}">
                                {{ t.result }}
                            </span>
                        </td>
                        <td><small>{{ t.exit_reason }}</small></td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p style="color: #8b949e; padding: 20px 0;">No closed trades yet. Once you sell a position (hit target, stop, or manual close), it will appear here with the final P&L.</p>
            {% endif %}
        </div>

        <!-- Trade Ideas -->
        <div class="card">
            <h2>Today's Trade Ideas</h2>
            {% if trades %}
            {% for t in trades[:5] %}
            <div class="trade-idea">
                <h3>{{ '🟢' if t.confidence == 'HIGH' else '🟡' if t.confidence == 'MEDIUM' else '⚪' }} {{ t.contract }}</h3>
                <div class="details">
                    <div><span class="label">Entry:</span> ${{ "%.2f"|format(t.entry_price) }}</div>
                    <div><span class="label">Target:</span> <span class="positive">${{ "%.2f"|format(t.option_target) }}</span></div>
                    <div><span class="label">Stop:</span> <span class="negative">${{ "%.2f"|format(t.option_stop) }}</span></div>
                    <div><span class="label">R:R:</span> {{ t.risk_reward }}:1</div>
                    <div><span class="label">Confidence:</span> {{ t.confidence }}</div>
                    <div><span class="label">Direction:</span> {{ t.direction }}</div>
                </div>
            </div>
            {% endfor %}
            {% else %}
            <p style="color: #8b949e; padding: 20px 0;">No high-quality setups right now.</p>
            {% endif %}
        </div>

        <p class="refresh-note">Dashboard auto-refreshes every 60 seconds. Data updates every 2 minutes during market hours.</p>
    </div>
</body>
</html>
"""


@app.route('/')
def dashboard():
    """Main dashboard view."""
    # Update positions first
    update_positions()

    positions = load_portfolio()
    history = load_trade_history()
    summary = get_portfolio_summary()

    # Get trade ideas
    try:
        trades = generate_trades(WATCHLIST)
        trades = [t for t in trades if t.risk_reward >= 1.8]
        trades.sort(key=lambda x: x.risk_reward, reverse=True)
    except:
        trades = []

    return render_template_string(
        DASHBOARD_HTML,
        positions=positions,
        history=history,
        summary=summary,
        trades=trades,
        updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


@app.route('/api/portfolio')
def api_portfolio():
    """API endpoint for portfolio data."""
    update_positions()
    positions = load_portfolio()
    summary = get_portfolio_summary()

    return jsonify({
        "positions": [
            {
                "contract": p.contract,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "pnl_dollars": p.pnl_dollars,
                "pnl_percent": p.pnl_percent,
                "target": p.target_price,
                "stop": p.stop_price
            }
            for p in positions
        ],
        "summary": summary,
        "updated": datetime.now().isoformat()
    })


@app.route('/api/history')
def api_history():
    """API endpoint for trade history."""
    history = load_trade_history()
    return jsonify({
        "trades": [
            {
                "contract": t.contract,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl_dollars": t.pnl_dollars,
                "pnl_percent": t.pnl_percent,
                "result": t.result,
                "exit_date": t.exit_date
            }
            for t in history
        ]
    })


if __name__ == '__main__':
    print("=" * 50)
    print("TRADING DASHBOARD")
    print("=" * 50)
    print("Starting web server...")
    print("Open http://localhost:8080 in your browser")
    print("Press Ctrl+C to stop")
    print("=" * 50)

    app.run(host='0.0.0.0', port=8080, debug=False)
