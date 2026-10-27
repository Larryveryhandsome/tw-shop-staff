# -*- coding: utf-8 -*-
"""匯入一期「每週新聞」：python tools/import_news.py 新聞.json

JSON 格式：
  {"week": "2026-W44", "title": "本週餐飲新聞", "intro": "一句話導讀",
   "items": [{"title": "標題", "url": "https://...", "cat": "餐飲業", "source": "來源", "date": "2026-10-28",
              "summary": "摘要", "tip": "對我們店的提醒"}]}
week 不填＝本週；同一週再匯入會覆蓋內容。新聞可以自己整理，也可以叫任何 AI 工具照這個格式產生。
"""
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    import extras as X
    db = os.environ.get("CRM_DB") or os.path.join(ROOT, "app", "data", "crm.db")
    if not os.path.exists(db):
        sys.exit("找不到資料庫：%s（先跑 python setup.py）" % db)
    with open(sys.argv[1], encoding="utf-8-sig") as f:
        data = json.load(f)
    c = sqlite3.connect(db, timeout=15)
    try:
        print("匯入 %d 則新聞" % X.import_news(c, data))
    finally:
        c.close()
