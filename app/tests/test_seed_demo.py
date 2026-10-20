# -*- coding: utf-8 -*-
"""五個產業範本都能建示範店、算薪、產生股東頁：python tests/test_seed_demo.py（在 app/ 底下執行）"""
import datetime
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tomllib

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # app/
ROOT = os.path.dirname(HERE)
PRESETS = sorted(k for k in os.listdir(os.path.join(ROOT, "presets")) if os.path.isfile(os.path.join(ROOT, "presets", k, "demo.toml")))
TODAY = datetime.date(2026, 3, 20)
bad = 0


def check(name, ok, info=""):
    global bad
    print(("OK  " if ok else "BAD ") + name + ("" if ok else "　" + str(info)))
    bad += 0 if ok else 1


# 每個範本開一個獨立程序跑（app 模組在 import 時就讀 CRM_DB，同一個程序只能用一個資料庫）
CHILD = r'''
import json, os, sys, datetime, random, sqlite3
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, os.path.join(os.path.dirname(sys.argv[1]), "ledger", "builder"))
import seed_demo as S
r = S.seed(sys.argv[2], sys.argv[3], days=40, today=datetime.date(2026, 3, 20), rnd=random.Random(1))
P = r["P"]
c = sqlite3.connect(sys.argv[2]); c.row_factory = sqlite3.Row
rows = P.compute(c, "2026-03", today="2026-03-20")
import build_ledger as B
conf = os.path.join(os.path.dirname(sys.argv[1]), "presets", sys.argv[3], "ledger.toml")
cf, _ = B.load_config(conf)
db = B.read_db(sys.argv[2], cf["ledger"]["period_start"], "2026-03-20")
d = B.build(cf, db, "2026-03-20")
print(json.dumps(dict(accounts=len(r["accounts"]), days=r["days"], people=len(rows), gross=sum(x["base"] for x in rows),
                      flags=[f for x in rows for f in x["law_flags"]], revenue=d["total"]["revenue"], expense=d["total"]["expense"],
                      payroll=d["total"]["payroll"], pending=d["pending"], products=len(d["products"]),
                      leads=c.execute("SELECT COUNT(*) FROM leads").fetchone()[0])))
'''

tmp = tempfile.mkdtemp(prefix="seedtest_")
try:
    check("至少五個產業範本", len(PRESETS) >= 5, PRESETS)
    for key in PRESETS:
        for fn in ("store.toml", "ledger.toml", "demo.toml"):
            with open(os.path.join(ROOT, "presets", key, fn), "rb") as f:
                tomllib.load(f)
        db = os.path.join(tmp, key, "crm.db"); os.makedirs(os.path.dirname(db))
        env = dict(os.environ, CRM_DB=db, CRM_BAK=os.path.join(tmp, key, "bak"), PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, "-X", "utf8", "-c", CHILD, HERE, db, key], capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
        if p.returncode:
            check(key + " 建示範店", False, p.stderr[-800:]); continue
        r = json.loads(p.stdout.strip().splitlines()[-1])
        check("%s 有員工帳號（%d 個）" % (key, r["accounts"]), r["accounts"] >= 3, r)
        check("%s 有營業日、營收（%s）" % (key, format(r["revenue"], ",")), r["days"] > 20 and r["revenue"] > 0, r)
        check("%s 薪資算得出來（%s）" % (key, format(r["gross"], ",")), r["people"] >= 2 and r["gross"] > 0 and r["payroll"] > 0, r)
        check("%s 示範班表沒有違反勞基法的提醒" % key, not r["flags"], r["flags"])
        check("%s 最近兩天留著待核銷" % key, r["pending"]["rev"] >= 1, r["pending"])
        check("%s 股東頁有單位成本" % key, r["products"] >= 2, r)
    # 已經有資料庫時不會蓋掉
    db = os.path.join(tmp, "exists.db"); open(db, "w").close()
    p = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "seed_demo.py"), "--db", db, "--no-ledger"], capture_output=True, text=True,
                       encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=60)
    check("資料庫已存在：停下來不蓋", p.returncode != 0 and os.path.getsize(db) == 0, p.stdout + p.stderr)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("全部通過" if not bad else "有 %d 項沒過" % bad)
sys.exit(1 if bad else 0)
