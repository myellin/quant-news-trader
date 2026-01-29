# Quant News Trader

Automated options trading system with real-time analysis and paper trading.

## Features

- **Technical Analysis**: Multi-factor scoring (trend, momentum, volume, volatility)
- **Options Trade Generator**: Specific calls/puts with entry, target, stop
- **Paper Trading**: Track all trades with P&L
- **Live Dashboard**: Web UI showing portfolio performance
- **Daily Reports**: Email summary at market close

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Run dashboard
python dashboard.py
# Open http://localhost:8080

# Generate trade ideas
python options_trades.py

# View portfolio
python portfolio.py status
```

## Environment Variables

```
PERPLEXITY_API_KEY=your_key
ALERT_EMAIL_TO=your_email@gmail.com
ALERT_EMAIL_FROM=sender@gmail.com
ALERT_EMAIL_PASSWORD=app_password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
```

## Deploy

### Railway (Recommended)
1. Push to GitHub
2. Connect repo to Railway
3. Add environment variables
4. Deploy

### Render
1. Push to GitHub
2. New Web Service → Connect repo
3. Add environment variables
4. Deploy

## Files

| File | Purpose |
|------|---------|
| `dashboard.py` | Web UI |
| `portfolio.py` | Track trades |
| `options_trades.py` | Generate trade ideas |
| `analysis.py` | Technical analysis |
| `daily_report.py` | End of day email |
| `scanner.py` | Find opportunities |

## Disclaimer

This is for educational purposes only. Paper trading only. Not financial advice.
