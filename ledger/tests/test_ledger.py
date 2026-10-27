# -*- coding: utf-8 -*-
"""股東帳務產生器測試：python -m unittest discover -s ledger/tests（在專案根目錄執行）"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import tomllib
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ledger", "builder"))
sys.path.insert(0, os.path.join(ROOT, "app"))
TMP = tempfile.mkdtemp(prefix="ledgertest_")
DB = os.path.join(TMP, "crm.db")
os.environ["CRM_DB"] = DB
os.environ["CRM_BAK"] = os.path.join(TMP, "bak")
import app  # noqa: E402
import build_ledger as B  # noqa: E402

CONF = {
    "ledger": {"title": "測試帳務", "period_start": "2026-03-01", "show_payroll_detail": False, "show_receipts": True},
    "shareholders": [{"name": "甲", "committed": 600000, "paid": 600000}, {"name": "乙", "committed": 400000, "paid": 200000}],
    "opening": {"date": "2026-03-01", "bank": 10000, "cash": 5000},
    "entries": [{"date": "2026-03-01", "kind": "支出", "category": "開辦費", "item": "裝潢", "amount": 100000},
                {"date": "2026-03-01", "kind": "押金", "category": "押金", "item": "房屋押金", "amount": 50000},
                {"date": "2026-03-05", "kind": "借入", "category": "借款", "item": "週轉", "amount": 30000},
                {"date": "2025-12-01", "kind": "支出", "category": "開辦費", "item": "期間外，不算", "amount": 999}],
    "balance_checks": [{"date": "2026-03-31", "bank": 700000, "cash": 3000}],
    "products": [{"name": "便當", "price": 100, "parts": [{"name": "主菜", "cost": 40}, {"name": "盒", "cost": 5}], "fees": {"外送": 0.3}}],
}


def seed():
    app.init_db()
    c = sqlite3.connect(DB)
    c.execute("INSERT INTO fin_day(day,total,cash,orders,boxes,status) VALUES('2026-03-02',10000,10000,50,80,'已入帳')")
    c.execute("INSERT INTO fin_day(day,total,cash,orders,boxes,status) VALUES('2026-03-03',12000,12000,60,90,'已核銷')")
    c.execute("INSERT INTO fin_day(day,total,cash,orders,boxes,status) VALUES('2026-03-04',9999,9999,1,1,'退回')")      # 老闆退回：不算
    c.execute("INSERT INTO fin_exp(day,category,item,amount,status) VALUES('2026-03-02','自購食材雜貨','雞蛋',3000,'已核銷')")
    c.execute("INSERT INTO fin_exp(day,category,item,amount,status,photo) VALUES('2026-03-03','清潔文具雜支','垃圾袋',500,'已核銷','exp_2.jpg')")
    c.execute("INSERT INTO fin_exp(day,category,item,amount,status) VALUES('2026-03-03','薪資','預支',2000,'已核銷')")       # 薪資類：不重複算
    c.execute("INSERT INTO fin_exp(day,category,item,amount,status) VALUES('2026-03-03','其他','還沒核銷',777,'待核銷')")
    c.execute("INSERT INTO fin_exp(day,category,item,amount,status,removed) VALUES('2026-03-03','其他','刪掉的',888,'已核銷',1)")
    c.execute("INSERT INTO petty(day,amount,note,kind) VALUES('2026-03-04',600,'廢油回收','收入')")
    c.execute("INSERT INTO users(username,name,pw,role,created) VALUES('pt','時薪夥伴','x','staff','2026-03-01')")
    uid = c.execute("SELECT id FROM users WHERE username='pt'").fetchone()[0]
    c.execute("INSERT INTO pay_profile(user_id,kind,amount,off_days,punch) VALUES(?,?,?,?,1)", (uid, "hourly", 200, 0))
    for d in ("2026-03-02", "2026-03-03"):
        c.execute("INSERT INTO punches(user_id,at,kind) VALUES(?,?,'in')", (uid, d + " 09:00:00"))
        c.execute("INSERT INTO punches(user_id,at,kind) VALUES(?,?,'out')", (uid, d + " 17:00:00"))
    c.commit(); c.close()
    os.makedirs(os.path.join(TMP, "finance"), exist_ok=True)
    with open(os.path.join(TMP, "finance", "exp_2.jpg"), "wb") as f:
        f.write(b"\xff\xd8\xff\xe0fakejpg")


class LedgerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed()
        cls.db = B.read_db(DB, "2026-03-01", "2026-03-31")
        cls.d = B.build(CONF, cls.db, "2026-03-31")

    def test_revenue_only_verified(self):
        self.assertEqual(self.d["total"]["revenue"], 22000)
        self.assertEqual(self.d["pending"]["rev"], 1)

    def test_expense_excludes_payroll_pending_removed(self):
        self.assertEqual(self.d["total"]["expense"], 3500)
        self.assertEqual(self.d["total"]["manual_expense"], 100000)   # 期間外那筆不算
        self.assertEqual(self.d["pending"]["exp"], 1)

    def test_other_income(self):
        self.assertEqual(self.d["total"]["other_income"], 600)

    def test_payroll_from_payroll_module(self):
        self.assertEqual(self.d["total"]["payroll"], 2 * 8 * 200)

    def test_profit(self):
        T = self.d["total"]
        self.assertEqual(T["profit"], 22000 + 600 - 3500 - 100000 - 3200 - T["pension"])

    def test_shareholders(self):
        s = {x["name"]: x for x in self.d["shareholders"]}
        self.assertEqual(self.d["paid_total"], 800000)
        self.assertAlmostEqual(s["甲"]["ratio"], 0.75)
        self.assertEqual(s["乙"]["owed"], 200000)

    def test_funds(self):
        T = self.d["total"]
        self.assertEqual(self.d["funds"], 15000 + 800000 + T["income"] - T["cost"] - 50000 + 30000)
        self.assertEqual(self.d["checks"][0]["actual"], 703000)
        self.assertEqual(self.d["checks"][0]["diff"], 703000 - self.d["funds"])

    def test_products(self):
        p = self.d["products"][0]
        self.assertEqual((p["cost"], p["margin"], p["margin_pct"]), (45, 55, 55.0))
        self.assertEqual(p["channels"][0]["margin"], 100 * 0.7 - 45)

    def test_render_page(self):
        out = os.path.join(TMP, "www")
        n = B.render(json.loads(json.dumps(self.d)), out, self.db["photo_dir"])
        self.assertEqual(n, 1)
        self.assertTrue(os.path.exists(os.path.join(out, "img", "R_2.jpg")))
        with open(os.path.join(out, "index.html"), encoding="utf-8") as f:
            page = f.read()
        self.assertIn("測試帳務", page)
        self.assertIn("https://line.me/R/ti/p/@812ibtir", page)   # 股東頁尾的作者客製化資訊
        blob = page.split("const D = ")[1].split(";\nconst fmt")[0]
        data = json.loads(blob)
        self.assertEqual(data["total"]["revenue"], 22000)
        self.assertNotIn("photo_src", json.dumps(data["expenses"]))

    def test_empty_payroll_month_skipped(self):
        d = B.read_db(DB, "2026-02-01", "2026-03-31")
        self.assertNotIn("2026-02", d["payroll"])
        self.assertIn("2026-03", d["payroll"])

    def test_payroll_detail_hidden(self):
        self.assertEqual(self.d["payroll"]["2026-03"]["rows"], [])

    def test_example_config_parses(self):
        with open(os.path.join(ROOT, "config", "ledger.example.toml"), "rb") as f:
            conf = tomllib.load(f)
        d = B.build(conf, dict(revenue=[], expenses=[], other_income=[], payroll={}, pending={"rev": 0, "exp": 0}), "2026-03-31")
        self.assertEqual(len(d["shareholders"]), 2)
        self.assertTrue(d["products"])


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
