#!/bin/bash
cd ~/quant-news-trader
/usr/bin/python3 news_watcher.py >> ~/quant-news-trader/logs/news.log 2>&1
