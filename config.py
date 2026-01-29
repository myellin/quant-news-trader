"""Configuration for the quant news trading system."""

# Target tickers for swing trading
WATCHLIST = [
    "NVDA",  # NVIDIA
    "MU",    # Micron
    "TSLA",  # Tesla
    "BABA",  # Alibaba
]

# Perplexity API settings
PERPLEXITY_MODEL = "sonar"  # sonar has real-time web access
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# Signal thresholds
MIN_SIGNAL_SCORE = 0.6  # Minimum score to consider a trade
