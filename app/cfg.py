# -*- coding: utf-8 -*-
"""讀設定檔：config/store.toml（沒有就用 store.example.toml）、config/labor_rules.toml。

只用 Python 標準庫（tomllib，Python 3.11 以上）。
可用環境變數 SHOP_CONFIG_DIR 指定設定檔資料夾（測試用）。"""
import os
import sys
import time
import tomllib
from datetime import datetime, timezone

# 時區：打卡、算薪、記帳一律用台灣時間（UTC+8，沒有日光節約）。
# 伺服器設成 UTC（雲端主機、Docker 很常見）時，早上 7:30 的打卡會記成前一天 23:30，日期、遲到、國定假日全部算錯。
# 這裡在任何時間函式被呼叫前把 TZ 設好：Python 的 datetime.now()／date.today()、SQLite 的 'localtime'、
# 以及背景跑的股東帳務產生器（子程序繼承環境變數）都跟著用台灣時間。要改時區可設環境變數 SHOP_TZ（POSIX 格式，例："TST-8"）。
TZ = os.environ.get("SHOP_TZ") or "TST-8"
os.environ["TZ"] = TZ
if hasattr(time, "tzset"):
    time.tzset()


def tz_offset_hours():
    """目前程序實際用的時區（相對 UTC 幾小時）"""
    return round((datetime.now() - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds() / 3600, 1)


TZ_OK = os.environ.get("SHOP_TZ") is not None or tz_offset_hours() == 8
if not TZ_OK:
    try:
        print("警告：時區不是台灣時間（UTC%+g），打卡日期與算薪可能差 8 小時；請把這台電腦的時區設成台北，或設環境變數 SHOP_TZ。" % tz_offset_hours(),
              file=sys.stderr)
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG_DIR = os.environ.get("SHOP_CONFIG_DIR") or os.path.join(ROOT, "config")


def _load(*names):
    for n in names:
        p = os.path.join(CONFIG_DIR, n)
        if os.path.exists(p):
            with open(p, "rb") as f:
                return tomllib.load(f), p
    raise FileNotFoundError("找不到設定檔：%s（在 %s）" % (" 或 ".join(names), CONFIG_DIR))


STORE_ALL, STORE_PATH = _load("store.toml", "store.example.toml")
LABOR, LABOR_PATH = _load("labor_rules.toml")
DEMO_MODE = STORE_PATH.endswith("store.example.toml")

STORE = STORE_ALL.get("store", {})
FINANCE = STORE_ALL.get("finance", {})
SALES = STORE_ALL.get("sales", {})
AI = STORE_ALL.get("ai", {})
PATHS = STORE_ALL.get("paths", {})
# 功能開關：沒寫的一律開。safety＝食安紀錄、crm＝團體訂單開發、delivery＝外送、marketing＝行銷審核、news＝每週新聞、journal＝日誌
MODULES = dict({"safety": True, "crm": True, "delivery": True, "marketing": True, "news": True, "journal": True}, **STORE_ALL.get("modules", {}))


def path(p):
    """設定檔裡的相對路徑一律相對於專案根目錄"""
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def public_brand():
    """給前端用的店家資料（不含任何秘密）"""
    return {"name": STORE.get("name", ""), "short_name": STORE.get("short_name", ""), "address": STORE.get("address", ""),
            "phone": STORE.get("phone", ""), "logo": STORE.get("logo", ""), "industry": STORE.get("industry", ""),
            "unit": FINANCE.get("unit_name", "份"), "demo": DEMO_MODE, "modules": MODULES}
