# -*- coding: utf-8 -*-
"""股東帳務產生器：讀員工系統的資料庫（唯讀）＋ data/ledger.toml，產生股東網站 ledger/www/index.html。

資料來源
- 營收：fin_day（店長記了就入帳；老闆退回的不算）
- 支出：fin_exp（老闆核銷過、沒刪的；「薪資」類別是從抽屜拿的預支，已經算在薪資裡，不重複算）
- 其他收入：petty 裡 kind＝收入 的（例如廢油回收）
- 薪資：payroll.month_rows（和老闆頁、簽收單同一套算法）；薪資成本＝應發＋老闆調整（獎金、抽成）
- 股東、期初、系統外手記、對帳點、單位成本：data/ledger.toml（沒有就用 config/ledger.example.toml 示範）

用法
  python build_ledger.py                 # 用預設路徑
  python build_ledger.py --db 路徑 --config 路徑 --out 資料夾 --today 2026-10-20

員工系統的記帳有變動時，app 會自動在背景跑這支（ops.sync_ledger）。
"""
import argparse
import datetime
import html
import json
import os
import shutil
import sqlite3
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(LEDGER_DIR)
APP = os.path.join(ROOT, "app")
sys.path.insert(0, APP)
import cfg as SHOP  # noqa: E402
import payroll as P  # noqa: E402

PAYROLL_CAT = "薪資"


def default_db():
    return os.environ.get("CRM_DB") or os.path.join(APP, "data", "crm.db")


def load_config(path=None):
    for p in ([path] if path else [os.path.join(ROOT, "data", "ledger.toml"), os.path.join(ROOT, "config", "ledger.example.toml")]):
        if p and os.path.exists(p):
            with open(p, "rb") as f:
                return tomllib.load(f), p
    raise FileNotFoundError("找不到股東帳務設定（data/ledger.toml 或 config/ledger.example.toml）")


def months_between(start, end):
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while "%d-%02d" % (y, m) <= end[:7]:
        out.append("%d-%02d" % (y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


# ---------------- 讀資料庫（唯讀） ----------------
def read_db(db_path, start, today, detail=False):
    """回傳 dict：revenue（每天）、expenses（每筆）、other_income（每筆）、payroll（每月）、pending（還沒核銷的筆數）"""
    empty = dict(revenue=[], expenses=[], other_income=[], payroll={}, pending={"rev": 0, "exp": 0}, photo_dir=None)
    if not os.path.exists(db_path):
        return empty
    c = sqlite3.connect("file:%s?mode=ro" % db_path.replace("\\", "/"), uri=True, timeout=15)
    c.row_factory = sqlite3.Row
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    out = dict(empty, photo_dir=os.path.join(os.path.dirname(db_path), "finance"))
    if "fin_day" in tables:
        out["revenue"] = [dict(day=r["day"], total=r["total"] or 0, orders=r["orders"] or 0, units=r["boxes"] or 0)
                          for r in c.execute("SELECT * FROM fin_day WHERE status IN ('已核銷','已入帳') AND day>=? AND day<=? ORDER BY day", (start, today))]
        out["pending"]["rev"] = c.execute("SELECT COUNT(*) FROM fin_day WHERE status NOT IN ('已核銷','已入帳') AND day>=?", (start,)).fetchone()[0]
    if "fin_exp" in tables:
        out["expenses"] = [dict(id=r["id"], day=r["day"], category=r["category"], item=r["item"], vendor=r["vendor"] or "",
                                amount=r["amount"], pay=r["pay"], photo=r["photo"])
                           for r in c.execute("""SELECT * FROM fin_exp WHERE status='已核銷' AND removed=0 AND category<>? AND day>=? AND day<=?
                                                 ORDER BY day, id""", (PAYROLL_CAT, start, today))]
        out["pending"]["exp"] = c.execute("SELECT COUNT(*) FROM fin_exp WHERE status='待核銷' AND removed=0 AND day>=?", (start,)).fetchone()[0]
    if "petty" in tables and "kind" in {r[1] for r in c.execute("PRAGMA table_info(petty)")}:
        out["other_income"] = [dict(day=r["day"], amount=r["amount"], item=r["note"] or "其他收入")
                               for r in c.execute("SELECT * FROM petty WHERE removed=0 AND kind='收入' AND day>=? AND day<=? ORDER BY day", (start, today))]
    if "pay_profile" in tables:
        for m in months_between(start, today):
            rows = [r for r in P.month_rows(c, m, today=today) if r["base"] or r["net"] or r["mins"] or r.get("adj")]   # 這個月沒出勤、沒錢的人不列
            if not rows:
                continue
            locked = P.is_locked(c, m)
            # 薪資成本＝應發＋老闆調整（獎金、抽成是加、賠償扣款是減）：調整算在實發裡，股東頁不能漏掉
            out["payroll"][m] = dict(
                gross=sum(r["base"] + r.get("adj", 0) for r in rows), base=sum(r["base"] for r in rows), adj=sum(r.get("adj", 0) for r in rows),
                net=sum(r["net"] for r in rows), ins=sum(r.get("ins_ded", 0) for r in rows),
                pension=sum(r.get("pension_employer", 0) for r in rows), people=len(rows), locked=locked,
                rows=[dict(name=r["name"], kind=r["kind"], gross=r["base"] + r.get("adj", 0), net=r["net"]) for r in rows] if detail else [])
    c.close()
    return out


# ---------------- 算帳（純函式，方便測試） ----------------
def build(conf, db, today):
    L = conf.get("ledger", {})
    start = L.get("period_start") or conf.get("opening", {}).get("date") or today[:7] + "-01"
    months = months_between(start, today)
    entries = [e for e in conf.get("entries", []) if start <= str(e.get("date", "")) <= today]
    mrow = {m: dict(month=m, revenue=0, other_income=0, manual_income=0, expense=0, manual_expense=0, payroll=0, pension=0,
                    by_cat={}, orders=0, units=0, days=0) for m in months}

    def at(day):
        return mrow.get(str(day)[:7])

    for r in db["revenue"]:
        x = at(r["day"])
        if x:
            x["revenue"] += r["total"]; x["orders"] += r["orders"]; x["units"] += r["units"]; x["days"] += 1
    for r in db["other_income"]:
        x = at(r["day"])
        if x:
            x["other_income"] += r["amount"]
    for e in db["expenses"]:
        x = at(e["day"])
        if x:
            x["expense"] += e["amount"]
            x["by_cat"][e["category"]] = x["by_cat"].get(e["category"], 0) + e["amount"]
    for e in entries:
        x = at(e["date"])
        if not x:
            continue
        amt = int(e.get("amount", 0))
        if e.get("kind") == "支出":
            x["manual_expense"] += amt
            cat = e.get("category") or "其他"
            x["by_cat"][cat] = x["by_cat"].get(cat, 0) + amt
        elif e.get("kind") == "收入":
            x["manual_income"] += amt
    for m, p in db["payroll"].items():
        if m in mrow:
            mrow[m]["payroll"] = p["gross"]; mrow[m]["pension"] = p["pension"]
    for x in mrow.values():
        x["income"] = x["revenue"] + x["other_income"] + x["manual_income"]
        x["cost"] = x["expense"] + x["manual_expense"] + x["payroll"] + x["pension"]
        x["profit"] = x["income"] - x["cost"]
    rows = [mrow[m] for m in months]
    tot = {k: sum(r[k] for r in rows) for k in ("revenue", "other_income", "manual_income", "expense", "manual_expense", "payroll",
                                                 "pension", "income", "cost", "profit", "orders", "units", "days")}
    cats = {}
    for r in rows:
        for k, v in r["by_cat"].items():
            cats[k] = cats.get(k, 0) + v

    # 股東出資與盈餘試算
    sh = conf.get("shareholders", [])
    paid_total = sum(int(s.get("paid", 0)) for s in sh)
    holders = [dict(name=s.get("name", ""), committed=int(s.get("committed", 0)), paid=int(s.get("paid", 0)),
                    ratio=(int(s.get("paid", 0)) / paid_total) if paid_total else 0,
                    owed=int(s.get("committed", 0)) - int(s.get("paid", 0))) for s in sh]
    for h in holders:
        h["profit_share"] = int(round(tot["profit"] * h["ratio"]))

    # 資金估計：期初＋出資＋收入−支出−薪資成本−押金＋借入
    op = conf.get("opening", {})
    deposits = sum(int(e.get("amount", 0)) for e in entries if e.get("kind") == "押金")
    borrowed = sum(int(e.get("amount", 0)) for e in entries if e.get("kind") == "借入")
    opening = int(op.get("bank", 0)) + int(op.get("cash", 0))
    funds = opening + paid_total + tot["income"] - tot["cost"] - deposits + borrowed
    checks = []
    for b in conf.get("balance_checks", []):
        d = str(b.get("date", ""))
        if not (start <= d <= today):
            continue
        part = [r for r in rows if r["month"] <= d[:7]]
        # 對帳點只算到那個月底為止（月中對帳會有落差，頁面上會說明）
        est = opening + paid_total + sum(r["income"] - r["cost"] for r in part) - \
            sum(int(e.get("amount", 0)) for e in entries if e.get("kind") == "押金" and str(e.get("date")) <= d) + \
            sum(int(e.get("amount", 0)) for e in entries if e.get("kind") == "借入" and str(e.get("date")) <= d)
        actual = int(b.get("bank", 0)) + int(b.get("cash", 0))
        checks.append(dict(date=d, bank=int(b.get("bank", 0)), cash=int(b.get("cash", 0)), actual=actual, estimate=est, diff=actual - est))

    # 單位成本
    products = []
    for p in conf.get("products", []):
        cost = sum(float(x.get("cost", 0)) for x in p.get("parts", []))
        price = float(p.get("price", 0))
        fees = {k: float(v) for k, v in (p.get("fees") or {}).items()}
        products.append(dict(name=p.get("name", ""), price=price, cost=round(cost, 2), parts=p.get("parts", []),
                             margin=round(price - cost, 2), margin_pct=round((price - cost) / price * 100, 1) if price else 0,
                             channels=[dict(name=k, rate=v, margin=round(price * (1 - v) - cost, 2)) for k, v in fees.items()]))

    exp_rows = [dict(e, photo=("R_%d" % e["id"]) if e.get("photo") else None, photo_src=e.get("photo")) for e in db["expenses"]]
    exp_rows += [dict(id=None, day=e.get("date"), category=e.get("category") or "其他", item=e.get("item", ""), vendor="",
                      amount=int(e.get("amount", 0)), pay="系統外手記", photo=None, note=e.get("note", ""))
                 for e in entries if e.get("kind") == "支出"]
    exp_rows.sort(key=lambda e: (str(e["day"]), e["id"] or 0))
    return dict(
        title=L.get("title", "股東帳務"), store=SHOP.STORE.get("name", ""), unit=SHOP.FINANCE.get("unit_name", "份"),
        start=start, asof=today, generated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        months=rows, total=tot, categories=sorted(cats.items(), key=lambda x: -x[1]),
        payroll={m: db["payroll"][m] for m in months if m in db["payroll"]}, show_payroll_detail=bool(L.get("show_payroll_detail")),
        shareholders=holders, paid_total=paid_total, opening=opening, deposits=deposits, borrowed=borrowed, funds=funds, checks=checks,
        products=products, expenses=exp_rows if L.get("show_receipts", True) else [dict(e, photo=None) for e in exp_rows],
        revenue_days=db["revenue"], other_income=db["other_income"],
        entries=[dict(date=e.get("date"), kind=e.get("kind"), category=e.get("category", ""), item=e.get("item", ""),
                      amount=int(e.get("amount", 0)), note=e.get("note", "")) for e in entries],
        pending=db["pending"], demo=SHOP.DEMO_MODE)


# ---------------- 輸出 ----------------
def render(data, out_dir, photo_dir=None):
    """先複製單據圖（找不到的就不附），再寫 index.html（先寫暫存檔再換名，股東不會看到寫一半的頁面）"""
    os.makedirs(out_dir, exist_ok=True)
    copied = 0
    img = os.path.join(out_dir, "img")
    for e in data["expenses"]:
        src = e.pop("photo_src", None)
        if not e.get("photo"):
            continue
        fp = os.path.join(photo_dir, src) if (photo_dir and src) else ""
        if fp and src.lower().endswith(".jpg") and os.path.isfile(fp):
            os.makedirs(img, exist_ok=True)
            shutil.copyfile(fp, os.path.join(img, e["photo"] + ".jpg"))
            copied += 1
        else:
            e["photo"] = None
    with open(os.path.join(HERE, "page.html"), encoding="utf-8") as f:
        tpl = f.read()
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    page = tpl.replace("{{TITLE}}", html.escape(data["title"])).replace("/*DATA*/null", blob)
    tmp = os.path.join(out_dir, "index.html.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(tmp, os.path.join(out_dir, "index.html"))
    return copied


def main(argv=None):
    ap = argparse.ArgumentParser(description="產生股東帳務網站")
    ap.add_argument("--db", default=default_db())
    ap.add_argument("--config")
    ap.add_argument("--out", default=os.path.join(LEDGER_DIR, "www"))
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    conf, cpath = load_config(a.config)
    L = conf.get("ledger", {})
    start = L.get("period_start") or conf.get("opening", {}).get("date") or a.today[:7] + "-01"
    db = read_db(a.db, start, a.today, detail=bool(L.get("show_payroll_detail")))
    data = build(conf, db, a.today)
    n = render(data, a.out, db.get("photo_dir"))
    print("股東帳務已更新：%s（設定 %s，%d 個月，單據圖 %d 張）" % (os.path.join(a.out, "index.html"), os.path.basename(cpath), len(data["months"]), n))
    return data


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
