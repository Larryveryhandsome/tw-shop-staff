# -*- coding: utf-8 -*-
"""讀設定檔：config/store.toml（沒有就用 store.example.toml）、config/labor_rules.toml、config/labor_calendar/<年份>.toml。

只用 Python 標準庫（tomllib，Python 3.11 以上）。
可用環境變數 SHOP_CONFIG_DIR 指定設定檔資料夾（測試用）；SHOP_LABOR_CALENDAR_DIR 指定勞動曆資料夾（測試用）。"""
import os
import re
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


def _calendar_dir():
    d = os.environ.get("SHOP_LABOR_CALENDAR_DIR")
    if d:
        return d
    d = os.path.join(CONFIG_DIR, "labor_calendar")
    # 測試或自訂設定資料夾沒有勞動曆時，用專案內建的（勞動曆是全國共通的公告資料，不是店家設定）
    return d if os.path.isdir(d) else os.path.join(ROOT, "config", "labor_calendar")


def load_labor_calendar(cal_dir=None, labor=None):
    """每年的基本工資、國定假日 → ({年: {"minimum_wage": {...}, "holidays": [...], "path": ...}}, [讀檔問題])

    來源：config/labor_calendar/<年份>.toml（一年一檔）；相容舊版 labor_rules.toml 的 [minimum_wage] YYYY、[holiday] dates_YYYY。
    同一年兩邊都有時，以 labor_calendar 為準。檔案格式錯誤不讓系統掛掉，而是列進問題清單，啟動時與老闆頁會顯示。"""
    cal_dir = cal_dir or _calendar_dir()
    labor = LABOR if labor is None else labor
    cal, problems = {}, []
    for k, v in (labor.get("minimum_wage") or {}).items():
        if str(k).isdigit():
            cal.setdefault(int(k), {})["minimum_wage"] = dict(v)
    for k, v in (labor.get("holiday") or {}).items():
        m = re.fullmatch(r"dates_(\d{4})", str(k))
        if m:
            cal.setdefault(int(m.group(1)), {})["holidays"] = list(v)
    if os.path.isdir(cal_dir):
        for fn in sorted(os.listdir(cal_dir)):
            m = re.fullmatch(r"(\d{4})\.toml", fn)
            if not m:
                continue
            y, fp = int(m.group(1)), os.path.join(cal_dir, fn)
            try:
                with open(fp, "rb") as f:
                    d = tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError) as e:
                problems.append("勞動曆 %s 讀不到或格式錯誤（%s），%d 年當作沒有設定" % (fn, e, y))
                continue
            if int(d.get("year", y)) != y:
                problems.append("勞動曆 %s 裡的 year = %s 和檔名不一致，%d 年當作沒有設定" % (fn, d.get("year"), y))
                continue
            ent = cal.setdefault(y, {})
            ent["path"] = fp
            mw = d.get("minimum_wage") or {}
            if mw:
                bad = [k for k in ("monthly", "hourly") if not isinstance(mw.get(k), int) or mw.get(k) <= 0]
                if bad:
                    problems.append("勞動曆 %s 的 [minimum_wage] %s 要填正整數" % (fn, "、".join(bad)))
                else:
                    ent["minimum_wage"] = {"monthly": mw["monthly"], "hourly": mw["hourly"]}
            hol = (d.get("holidays") or {}).get("dates")
            if hol is not None:
                good, wrong = [], []
                for x in hol:
                    x = str(x)
                    (good if re.fullmatch(r"%d-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])" % y, x) else wrong).append(x)
                if wrong:
                    problems.append("勞動曆 %s 有不是 %d 年的日期或格式不對：%s（已略過這幾天）" % (fn, y, "、".join(wrong[:5])))
                ent["holidays"] = good
    return cal, problems


LABOR_CALENDAR, LABOR_CALENDAR_PROBLEMS = load_labor_calendar()

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
