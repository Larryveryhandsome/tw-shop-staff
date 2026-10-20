# -*- coding: utf-8 -*-
"""建一家示範店：員工、班表、打卡、營收、支出、開發名單、公告、教育訓練，打開就看得到完整畫面。

用法：
  python app/seed_demo.py --preset drink               # 建到 app/data/crm.db（檔案已存在就停下來，不會蓋掉）
  python app/seed_demo.py --preset salon --db 路徑      # 建到指定位置
  python app/seed_demo.py --preset bento --force        # 已經有資料庫也重建（舊的先備份成 .bak-日期時間）

全部是假資料：人名用職稱代稱、電話一律 0900-000-xxx、公司名稱一律「示範○○」。
帳號密碼寫在資料庫旁邊的「示範帳號.txt」（data/ 不進 git）。
"""
import argparse
import datetime
import os
import random
import shutil
import sqlite3
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_demo(key):
    p = os.path.join(ROOT, "presets", key, "demo.toml")
    if not os.path.exists(p):
        raise SystemExit("沒有這個範本：%s（presets/ 底下）" % key)
    with open(p, "rb") as f:
        return tomllib.load(f)


def hm_add(t, mins):
    h, m = map(int, t.split(":"))
    x = max(0, min(23 * 60 + 59, h * 60 + m + mins))
    return "%02d:%02d" % (x // 60, x % 60)


def seed(db_path, key, days=45, today=None, rnd=None):
    """回傳 dict(accounts=[(帳號, 密碼, 名字, 角色)], days=幾天)；db_path 必須是還不存在的檔案"""
    rnd = rnd or random.Random(20260101)
    today = today or datetime.date.today()
    demo = load_demo(key)
    os.environ["CRM_DB"] = db_path
    os.environ.setdefault("CRM_BAK", os.path.join(os.path.dirname(db_path), "backups"))
    sys.path.insert(0, HERE)
    import app  # noqa: E402  讀 CRM_DB，所以要在設好環境變數之後才 import
    import payroll as P  # noqa: E402
    app.DB = db_path
    app.init_db()
    with open(os.path.join(os.path.dirname(db_path), "首次管理員密碼.txt"), "w", encoding="utf-8") as f:
        print("這是示範店：帳號密碼請看同一個資料夾的「示範帳號.txt」。", file=f)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    admin = c.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()["id"]
    admin_pw = "demo-" + "".join(rnd.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(8))
    c.execute("UPDATE users SET pw=?, must_change=0 WHERE id=?", (app.hash_pw(admin_pw), admin))
    accounts = [("admin", admin_pw, "老闆", "admin")]
    start = today - datetime.timedelta(days=days)
    closed = {int(x) for x in str(demo.get("weekly_closed", "")).split(",") if x.strip().isdigit()}
    c.execute("INSERT INTO settings(k,v) VALUES('weekly_closed',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (",".join(map(str, sorted(closed))),))

    staff = []
    for i, s in enumerate(demo.get("staff", []), 1):
        un = "staff%d" % i
        pw = "".join(rnd.choice("23456789") for _ in range(6))
        c.execute("""INSERT INTO users(username,name,pw,role,active,target,created,phone,position,must_change)
                     VALUES(?,?,?,?,1,?,?,?,?,0)""", (un, s["name"], app.hash_pw(pw), s["role"], 50 if s["role"] != "admin" else 0, now,
                                                     "0900-000-%03d" % i, s["name"]))
        uid = c.execute("SELECT id FROM users WHERE username=?", (un,)).fetchone()[0]
        off = 9 if s["kind"] == "monthly" else 0
        c.execute("INSERT INTO pay_profile(user_id,kind,amount,off_days,punch,updated) VALUES(?,?,?,?,1,?)", (uid, s["kind"], s["amount"], off, now))
        sh = list(s.get("shift", [])) + ["", "", "", ""]
        c.execute("INSERT INTO shifts(user_id,effective,s1,e1,s2,e2,created,created_by) VALUES(?,?,?,?,?,?,?,?)",
                  (uid, start.isoformat(), sh[0], sh[1], sh[2] or None, sh[3] or None, now, admin))
        # 每週休兩天：店休那天＋輪流一天（沒有店休就輪兩天）；時薪夥伴一週上四天
        rest = set(closed)
        k = i
        while len(rest) < (2 if s["kind"] != "hourly" else 3):
            rest.add(k % 7)
            k += 3
        staff.append(dict(uid=uid, shift=sh, rest=rest, kind=s["kind"]))
        accounts.append((un, pw, s["name"], s["role"]))

    d = start
    n_days = 0
    while d < today:
        ds = d.isoformat()
        if d.weekday() not in closed:
            n_days += 1
            for st in staff:
                if d.weekday() in st["rest"]:
                    continue
                segs = [(x, y) for x, y in ((st["shift"][0], st["shift"][1]), (st["shift"][2], st["shift"][3])) if x and y]
                for j, (a, b) in enumerate(segs):
                    # 第一段可以早到；休息回來只會準時或晚到、休息前準時下班，休息才不會被壓到 30 分鐘以下
                    tin = hm_add(a, rnd.choice([-5, -3, -2, 0, 0, 1, 4]) if j == 0 else rnd.choice([0, 0, 1, 3]))
                    tout = hm_add(b, rnd.choice([0, 2, 3, 5]) if j == len(segs) - 1 else 0)
                    c.execute("INSERT INTO punches(user_id,at,kind,source,created) VALUES(?,?,?,?,?)", (st["uid"], ds + " " + tin + ":00", "in", "demo", now))
                    c.execute("INSERT INTO punches(user_id,at,kind,source,created) VALUES(?,?,?,?,?)", (st["uid"], ds + " " + tout + ":00", "out", "demo", now))
            recent = (today - d).days <= 2                       # 最近兩天的支出留著「待核銷」，示範老闆核銷流程（營收店長記了就入帳）
            total = rnd.randrange(int(demo["revenue_min"]), int(demo["revenue_max"]) + 1, 10)
            units = max(1, round(total / float(demo.get("avg_price", 100))))
            cash = int(total * rnd.uniform(0.55, 0.8)) // 10 * 10
            st_ = "待核銷" if recent else "已核銷"
            c.execute("""INSERT INTO fin_day(day,total,cash,stored,eticket,orders,boxes,voucher,topup,drawer,status,created_by,created,verified_by,verified_at)
                         VALUES(?,?,?,0,?,?,?,0,0,NULL,?,?,?,?,?)""",
                      (ds, total, cash, total - cash, max(1, int(units * 0.7)), units, "已入帳", admin, now, None, None))
            for e in rnd.sample(demo.get("expense", []), k=min(len(demo.get("expense", [])), 1 if recent else rnd.choice([0, 1, 1, 2]))):
                amt = rnd.randrange(int(e["min"]), int(e["max"]) + 1, 10)
                c.execute("""INSERT INTO fin_exp(day,category,item,vendor,amount,pay,status,created_by,created,verified_by,verified_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                          (ds, e["category"], e["item"], "示範廠商", amt, "零用金", st_, admin, now, None if recent else admin, None if recent else now))
        d += datetime.timedelta(days=1)

    c.execute("INSERT INTO petty(day,amount,note,created_by,created,kind) VALUES(?,?,?,?,?,'撥款')", (start.isoformat(), 20000, "零用金（示範）", admin, now))
    for i, name in enumerate(demo.get("leads", []), 1):
        c.execute("""INSERT INTO leads(code,name,category,area,phone,priority,status,updated) VALUES(?,?,?,?,?,?,?,?)""",
                  ("D%03d" % i, name, "示範", "示範區", "0900-000-%03d" % (100 + i), rnd.choice("ABC"),
                   rnd.choice(["未聯絡", "未聯絡", "未接", "有興趣", "已報價"]), now))
    c.execute("INSERT INTO notices(title,body,pinned,need_ack,created,created_by) VALUES(?,?,1,1,?,?)",
              ("歡迎使用示範店", "這是示範資料。到「老闆」頁可以看出勤、薪資試算；到「記帳」可以練習核銷。", now, admin))
    c.execute("INSERT INTO notices(title,body,pinned,need_ack,created,created_by) VALUES(?,?,0,1,?,?)",
              ("排休請提早說", "下個月要排休的，請在 25 號前到「班表」登記。", now, admin))
    for i, m in enumerate(demo.get("manual", []), 1):
        c.execute("INSERT INTO manual(chapter,title,body,sort,updated,updated_by) VALUES(?,?,?,?,?,?)", (m["chapter"], m["title"], m["body"], i, now, admin))
    c.commit()
    c.close()
    return dict(accounts=accounts, days=n_days, P=P)


def main(argv=None):
    ap = argparse.ArgumentParser(description="建一家示範店（全部是假資料）")
    ap.add_argument("--preset", default="bento")
    ap.add_argument("--db", default=os.environ.get("CRM_DB") or os.path.join(HERE, "data", "crm.db"))
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-ledger", action="store_true")
    a = ap.parse_args(argv)
    db = os.path.abspath(a.db)
    if os.path.exists(db):
        if not a.force:
            raise SystemExit("已經有資料庫：%s\n為了不蓋掉你的資料，沒有做任何事。真的要重建示範店請加 --force（會先備份）。" % db)
        bak = db + ".bak-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        shutil.move(db, bak)
        for ext in ("-wal", "-shm"):
            if os.path.exists(db + ext):
                shutil.move(db + ext, bak + ext)
        print("舊資料庫已備份：%s" % bak)
    os.makedirs(os.path.dirname(db), exist_ok=True)
    r = seed(db, a.preset, days=a.days)
    with open(os.path.join(os.path.dirname(db), "示範帳號.txt"), "w", encoding="utf-8") as f:
        f.write("示範店帳號（%s 範本，全部是假資料）\n\n" % a.preset)
        for un, pw, nm, role in r["accounts"]:
            f.write("%-8s 密碼 %-14s %s（%s）\n" % (un, pw, nm, {"admin": "老闆", "manager": "店長", "staff": "夥伴"}.get(role, role)))
    print("示範店建好了：%d 個營業日、%d 個帳號。帳號密碼在 %s" % (r["days"], len(r["accounts"]), os.path.join(os.path.dirname(db), "示範帳號.txt")))
    if not a.no_ledger:
        sys.path.insert(0, os.path.join(ROOT, "ledger", "builder"))
        import build_ledger as B
        conf = os.path.join(ROOT, "data", "ledger.toml")
        if not os.path.exists(conf):
            conf = os.path.join(ROOT, "presets", a.preset, "ledger.toml")
        B.main(["--db", db, "--config", conf])
    import cfg
    if cfg.STORE.get("industry") != a.preset:
        print("提醒：目前的店家設定是「%s」。要讓畫面也換成這個產業，請先跑 python tools/use_preset.py %s" % (cfg.STORE.get("name"), a.preset))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
