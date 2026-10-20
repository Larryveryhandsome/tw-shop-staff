# -*- coding: utf-8 -*-
"""讀設定檔：config/store.toml（沒有就用 store.example.toml）、config/labor_rules.toml。

只用 Python 標準庫（tomllib，Python 3.11 以上）。
可用環境變數 SHOP_CONFIG_DIR 指定設定檔資料夾（測試用）。"""
import os
import tomllib

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
