#!/usr/bin/env python3
"""
Sync local portfolio to Vercel KV.
Run this after trades to update the cloud dashboard.
"""

import json
import requests
import os

VERCEL_URL = os.environ.get("VERCEL_URL", "https://quant-news-trader.vercel.app")
PORTFOLIO_FILE = "portfolio.json"


def sync():
    """Sync local portfolio to Vercel."""
    if not os.path.exists(PORTFOLIO_FILE):
        print("No portfolio.json found")
        return

    with open(PORTFOLIO_FILE) as f:
        data = json.load(f)

    # Convert to format expected by Vercel
    positions = []
    for p in data.get("positions", []):
        positions.append({
            "contract": p.get("contract", ""),
            "entry": p.get("entry_price", 0),
            "current": p.get("current_price", p.get("entry_price", 0)),
            "pnl": p.get("pnl", 0),
            "entry_date": p.get("entry_date", ""),
            "quantity": p.get("quantity", 1)
        })

    history = []
    for t in data.get("closed_trades", []):
        history.append({
            "contract": t.get("contract", ""),
            "entry": t.get("entry_price", 0),
            "exit": t.get("exit_price", 0),
            "pnl": t.get("pnl", 0),
            "result": "WIN" if t.get("pnl", 0) > 0 else "LOSS",
            "entry_date": t.get("entry_date", ""),
            "exit_date": t.get("exit_date", "")
        })

    payload = {
        "positions": positions,
        "trade_history": history
    }

    try:
        resp = requests.post(f"{VERCEL_URL}/api/sync", json=payload)
        if resp.status_code == 200:
            print(f"Synced to Vercel: {len(positions)} positions, {len(history)} closed trades")
        else:
            print(f"Sync failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Sync error: {e}")


if __name__ == "__main__":
    sync()
