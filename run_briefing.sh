#!/bin/bash
cd ~/quant-news-trader
/usr/bin/python3 daily_briefing.py >> ~/quant-news-trader/logs/briefing.log 2>&1
