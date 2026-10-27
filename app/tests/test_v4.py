# -*- coding: utf-8 -*-
"""v4 整合測試（老闆 10/5 晚）：優先名單 A 級最前面、晚上 9 點日誌關心（60 天不重複）、店長不用日誌、老闆回覆某一天、
崗位必讀與輪調、待辦、個人檔案、每週新聞、外送單刪除、預支從抽屜拿 → 帳務支出、月初預支從上個月扣、店休日打卡不計薪、導覽紀錄。
暫存資料庫＋5493 埠。跑法：python test_v4.py"""
import base64, http.cookiejar, json, os, secrets, shutil, subprocess, sys, tempfile, time, urllib.request
from datetime import date, timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # app/
tmp = tempfile.mkdtemp()
DB = os.path.join(tmp, "crm.db")
env = dict(os.environ, CRM_DB=DB, CRM_BAK=os.path.join(tmp, "bak"), CRM_PORT="5493", CRM_EXP_START="2026-01-01")
sys.path.insert(0, HERE)
os.environ.update(CRM_DB=DB, CRM_BAK=os.path.join(tmp, "bak"), CRM_EXP_START="2026-01-01")
import app, ops as O, extras as X, payroll as P  # noqa: E402

app.init_db()
c = app.db()
PW = {}
T = date.today().isoformat()
for un, name, role in (("boss4", "老闆四", "admin"), ("mgr4", "店長四", "manager"), ("amy4", "阿美四", "staff"), ("bob4", "阿寶四", "staff")):
    PW[un] = secrets.token_urlsafe(10)
    c.execute("INSERT INTO users(username,name,pw,role,created) VALUES(?,?,?,?,?)", (un, name, app.hash_pw(PW[un]), role, app.now()))
ids = {r["username"]: r["id"] for r in c.execute("SELECT id, username FROM users")}
for un in ("amy4", "bob4"):
    c.execute("INSERT INTO pay_profile(user_id,kind,amount,off_days,punch) VALUES(?,?,?,?,1)", (ids[un], "monthly", 36000, 6))
    c.execute("INSERT INTO shifts(user_id,effective,s1,e1,s2,e2) VALUES(?,?,?,?,?,?)", (ids[un], "2026-01-01", "09:00", "13:00", "15:30", "19:30"))
c.execute("INSERT INTO settings(k,v) VALUES('weekly_closed','')")
c.execute("INSERT INTO jobs_done(k,at) VALUES(?,?)", ("care:" + T, app.now()))   # 晚上 9 點後跑測試：別讓測試站自己的排程先送關心
for ch, title in (("1 認識我們的店", "店的基本資料"), ("5 食品安全與衛生", "洗手"), ("6 櫃檯與收銀", "收銀"), ("3 備料與烹調", "白飯"), ("10 顧客服務", "客訴")):
    c.execute("INSERT INTO manual(chapter,title,body,sort) VALUES(?,?,?,?)", (ch, title, "內容", int(ch.split()[0]) * 100))
for code, name, pri in (("T1", "B 級單位", "B"), ("T2", "A 級單位", "A"), ("D" + T.replace("-", "") + "001", "今天 AI 單位", "B"), ("T3", "仲介", "D")):
    c.execute("INSERT INTO leads(code,name,phone,priority,status,updated) VALUES(?,?,?,?,?,?)", (code, name, "03-9" + code[-3:].rjust(6, "0"), pri, "未聯絡", app.now()))
c.commit(); c.close()
SITE = os.path.normpath(os.path.join(HERE, "..", "_部署(股東帳務網站)", "www", "index.html"))
SITE_MT = os.path.getmtime(SITE) if os.path.exists(SITE) else None
srv = subprocess.Popen([sys.executable, os.path.join(HERE, "app.py")], env=env, cwd=HERE)
time.sleep(1.8)
BASE = "http://127.0.0.1:5493"
fails = []
JPG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 300).decode()


def client():
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(path, body=None):
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-Req": "1"} if body is not None else {})
        try:
            r = op.open(req); raw = r.read()
            return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try: return e.code, json.loads(raw)
            except Exception: return e.code, raw
    return call


def check(name, cond, extra=""):
    print(("OK  " if cond else "BAD ") + name + (("　" + str(extra)) if extra and not cond else ""))
    if not cond: fails.append(name)


try:
    boss, mgr, amy, bob = client(), client(), client(), client()
    for cl, un in ((boss, "boss4"), (mgr, "mgr4"), (amy, "amy4"), (bob, "bob4")):
        cl("/api/login", {"username": un, "password": PW[un]})
    # ── 優先名單：A 級一律最前面、AI 新名單併進來、D 級不進來
    s, d = amy("/api/dashboard"); names = [x["name"] for x in d["priority"]]
    check("優先名單 A 級最前面", names and names[0] == "A 級單位", names)
    check("今天 AI 新名單併進優先名單", any(x["why"] == "今天 AI 新開發" for x in d["priority"]), [x["why"] for x in d["priority"]])
    check("仲介（D 級）不進優先名單", "仲介" not in names)
    # ── 崗位必讀：沒設崗位 → 共同必讀（第 1、5 章）；輪調到外場 → 加收銀、客訴
    s, me = amy("/api/me"); check("夥伴沒設崗位：共同必讀 2 篇", me["train_left"] == 2, me.get("train_left"))
    s, me = mgr("/api/me"); check("店長沒有必讀擋", me["train_left"] == 0)
    s, _ = boss("/api/user/save", {"id": ids["amy4"], "position": "外場"}); s2, me = amy("/api/me")
    check("輪調到外場：必讀變 4 篇", s == 200 and me["position"] == "外場" and me["train_left"] == 4, me.get("train_left"))
    s, ib = amy("/api/inbox"); check("輪調會通知本人", any("崗位調到「外場」" in x["title"] for x in ib))
    check("崗位亂填擋掉", boss("/api/user/save", {"id": ids["amy4"], "position": "老闆"})[0] == 400)
    s, ms = amy("/api/manual"); req = [m for m in ms if m["required"]]
    check("訓練頁標出必讀", {m["title"] for m in req} == {"店的基本資料", "洗手", "收銀", "客訴"}, [m["title"] for m in req])
    for m in req: amy("/api/manual/ack", {"id": m["id"]})
    s, me = amy("/api/me"); check("必讀看完：解除", me["train_left"] == 0)
    boss("/api/user/save", {"id": ids["amy4"], "position": "內場"}); s, me = amy("/api/me")
    check("輪調到內場：新崗位的必讀（白飯）要再看", me["train_left"] == 1, me.get("train_left"))
    s, pl = boss("/api/position/log"); check("輪調有紀錄", len(pl) == 2)
    # ── 日誌：店長不用；老闆回覆某一天；9 點關心
    s, ts = boss("/api/journal/threads"); check("店長不在日誌名單", all(t["name"] != "店長四" for t in ts) and len(ts) == 2, [t["name"] for t in ts])
    YD = (date.today() - timedelta(days=1)).isoformat()
    s, _ = boss("/api/journal/post", {"uid": ids["amy4"], "body": "昨天辛苦了", "day": YD}); s2, j = amy("/api/journal")
    check("老闆回覆昨天那一天", s == 200 and any(m["day"] == YD and m["body"] == "昨天辛苦了" for m in j["messages"]))
    amy("/api/journal/post", {"body": "今天把冷藏庫整理好"})
    c = app.db()
    c.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,?,?)", (ids["bob4"], T + " 09:00:00", "in", "test"))
    c.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,?,?)", (ids["amy4"], T + " 09:00:00", "in", "test")); c.commit()
    n = X.send_care(c, T); n2 = X.send_care(c, T)
    check("9 點關心：只傳給有上班、還沒寫的（阿寶），同一天不重傳", n == 1 and n2 == 0, (n, n2))
    s, j = bob("/api/journal"); auto = [m for m in j["messages"] if m["auto"]]
    check("關心出現在阿寶的日誌、署名老闆", auto and auto[0]["author_role"] == "admin" and auto[0]["body"] in X.CARE)
    s, ib = bob("/api/inbox"); check("阿寶手機收到通知", any(x["title"] == "老闆：今天辛苦了" for x in ib))
    c.execute("DELETE FROM care_log WHERE user_id=?", (ids["bob4"],)); c.commit()   # 照日期順序重跑 60 天
    for k in range(60):
        dd = (date.today() - timedelta(days=60 - k)).isoformat()
        c.execute("DELETE FROM journal WHERE user_id=? AND day=?", (ids["bob4"], dd))
        c.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,?,?)", (ids["bob4"], dd + " 09:00:00", "in", "test"))
        X.send_care(c, dd)
    idx = [r[0] for r in c.execute("SELECT idx FROM care_log WHERE user_id=? AND day<? ORDER BY day DESC LIMIT 60", (ids["bob4"], T))]   # 今天那則是先傳的，不算在這 60 天裡
    check("60 天內關心不重複（%d 則都不一樣）" % len(set(idx)), len(X.CARE) == 60 and len(set(idx)) == 60, len(set(idx)))
    c.close()
    # ── 待辦
    s, _ = boss("/api/todo/save", {"title": "幫大家拍形象照", "due": T}); s2, _ = boss("/api/todo/save", {"title": "填個人檔案", "assignee": "staff", "due": T})
    s3, td = amy("/api/todos"); mine = [t for t in td["rows"] if t["title"] == "填個人檔案"]
    check("老闆交辦每位夥伴各一份", s == 200 and s2 == 200 and len(mine) == 1)
    check("夥伴不能交辦別人", amy("/api/todo/save", {"title": "x", "assignee": ids["bob4"]})[0] == 403)
    s, _ = amy("/api/todo/done", {"id": mine[0]["id"]}); s2, ib = boss("/api/inbox")
    check("完成待辦通知交辦的人", s == 200 and any("完成了待辦" in x["title"] for x in ib))
    # ── 個人檔案
    s, _ = amy("/api/profile/save", {"nickname": "阿美", "intro": "我在內場", "likes": "炸排骨", "photo": JPG}); s2, ps = bob("/api/profiles")
    a = [p for p in ps if p["id"] == ids["amy4"]][0]
    check("填個人檔案、大家看得到", s == 200 and a["nickname"] == "阿美" and a["has_photo"])
    check("看得到形象照", bob("/api/profile/photo?id=%d" % ids["amy4"])[0] == 200)
    check("不能改別人的個人檔案", bob("/api/profile/save", {"user_id": ids["amy4"], "intro": "x"})[0] == 403)
    s, _ = boss("/api/profile/save", {"user_id": ids["bob4"], "photo": JPG}); check("老闆幫夥伴上傳形象照", s == 200)
    # ── 每週新聞
    c = app.db(); X.import_news(c, {"week": "2026-W41", "title": "測試週", "intro": "導讀", "items": [{"cat": "食安", "title": "標題", "summary": "摘要", "tip": "對我們店：注意", "source": "中央社", "url": "https://www.cna.com.tw/x", "date": T}]}); c.close()
    s, me = amy("/api/me"); check("新一期新聞：有「新」", me["news_unread"] == 1)
    s, ns = amy("/api/news"); amy("/api/news/read", {"id": ns[0]["id"]}); s2, me = amy("/api/me")
    check("看過就不再顯示「新」", ns[0]["items"][0]["title"] == "標題" and me["news_unread"] == 0)
    if "08:00" <= time.strftime("%H:%M") < "20:59":
        time.sleep(31); s, ib = bob("/api/inbox"); check("新聞出刊通知大家（白天）", any(x["title"].startswith("每週新聞") for x in ib))
    # ── 外送單刪除
    s, d = mgr("/api/delivery/save", {"customer": "CC", "address": "test", "boxes": 1, "amount": 100, "pay": "現金收款"}); did = d["id"]
    check("夥伴不能刪外送單", amy("/api/delivery/delete", {"id": did})[0] == 403)
    s, _ = mgr("/api/delivery/delete", {"id": did}); s2, dv = mgr("/api/deliveries")
    check("店長刪掉測試單：看板看不到", s == 200 and all(r["id"] != did for r in dv["rows"]))
    # ── 預支：從抽屜拿 → 帳務支出；月初預支從上個月扣
    s, _ = boss("/api/boss/advance/save", {"user_id": ids["bob4"], "day": T, "amount": 3000})
    c = app.db(); e = c.execute("SELECT * FROM fin_exp WHERE category='薪資' AND removed=0").fetchall()
    a = c.execute("SELECT * FROM advances WHERE user_id=? ORDER BY id DESC", (ids["bob4"],)).fetchone()
    check("預支從抽屜拿 → 自動記一筆帳務支出（已核銷）", s == 200 and len(e) == 1 and e[0]["amount"] == 3000 and e[0]["status"] == "已核銷" and a["exp_id"] == e[0]["id"])
    PM = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    check("預支記在對的月份", a["pay_month"] == (PM if int(T[8:]) <= 5 else T[:7]), a["pay_month"])
    s, _ = boss("/api/boss/advance/save", {"user_id": ids["bob4"], "day": T[:7] + "-03", "amount": 1000, "drawer": False})
    a2 = c.execute("SELECT * FROM advances WHERE user_id=? ORDER BY id DESC", (ids["bob4"],)).fetchone()
    check("3 號預支：從上個月薪資扣；沒勾抽屜就不記帳務", a2["pay_month"] == PM and not a2["exp_id"], dict(a2))
    s, fd = mgr("/api/fin/day?day=" + T); pe = [e for e in fd["exps"] if e["id"] == a["exp_id"]]
    check("薪資是秘密：店長只看到「老闆處理的款項」，看不到是誰", pe and pe[0]["item"] == "老闆處理的款項" and "阿寶" not in json.dumps(fd, ensure_ascii=False), pe)
    s, fl = mgr("/api/fin/list?month=" + T[:7]); check("店長的本月記帳也看不到薪資明細", "阿寶" not in json.dumps(fl, ensure_ascii=False))
    s, fd = boss("/api/fin/day?day=" + T); check("老闆看得到預支是誰", any("阿寶" in (e["item"] or "") for e in fd["exps"]))
    boss("/api/boss/advance/void", {"id": a["id"]})
    check("作廢預支：帳務支出一起拿掉", c.execute("SELECT removed FROM fin_exp WHERE id=?", (a["exp_id"],)).fetchone()[0] == 1)
    # ── 店沒開的日子不給薪
    c.execute("INSERT INTO closed_days(day,reason) VALUES(?,?)", (T, "測試公休"))
    c.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,?,?)", (ids["amy4"], T + " 12:00:00", "out", "test")); c.commit()
    r = [x for x in P.compute(c, T[:7]) if x["id"] == ids["amy4"]][0]; dd = [x for x in r["per_day"] if x["day"] == T][0]
    check("公休日有打卡：照實際工時計薪、標出來給老闆確認", dd["mins"] == 180 and "照實際工時計薪" in dd["flag"] and dd["segs"], dd)
    c.close()
    # ── 食安紀錄
    s, sf = amy("/api/safety?kind=fridge"); f6 = [t for t in sf["targets"] if t["name"] == "6 門冰箱"][0]
    check("冰箱紀錄沒拍照不能存", amy("/api/safety/save", {"kind": "fridge", "slot": "上午", "target_id": f6["id"], "data": {"freeze": -18, "chill": 5}})[0] == 400)
    s, d = amy("/api/safety/save", {"kind": "fridge", "slot": "上午", "target_id": f6["id"], "data": {"freeze": -18, "chill": 5}, "photo": JPG}); check("冰箱溫度正常記錄", s == 200 and not d["alert"], d)
    check("同一台同一時段不能記兩次", amy("/api/safety/save", {"kind": "fridge", "slot": "上午", "target_id": f6["id"], "data": {"freeze": -18, "chill": 5}, "photo": JPG})[0] == 400)
    from datetime import datetime as _now
    early = _now.now().strftime("%H:%M") < "16:00"
    PMD = (date.fromisoformat(T) - timedelta(days=1)).isoformat() if early else T
    if early: check("16:00 以前不能記今天的「下班」", amy("/api/safety/save", {"kind": "fridge", "slot": "下班", "target_id": f6["id"], "data": {"freeze": -18, "chill": 5}, "photo": JPG})[0] == 400)
    s, d = amy("/api/safety/save", {"kind": "fridge", "day": PMD, "slot": "下班", "target_id": f6["id"], "data": {"freeze": -18, "chill": 9}, "photo": JPG})
    s2, ib = mgr("/api/inbox"); check("冷藏 9 度超標：通知店長", s == 200 and "冷藏" in d["alert"] and any(x["title"].startswith("食安警示") for x in ib), d)
    s, d = amy("/api/safety/save", {"kind": "gas", "slot": "上午", "data": {"pressure": 1.2, "pipe": True, "closed_yday": True, "main_on": True, "soup_off": False}})
    check("瓦斯檢查沒做到的會警示", s == 200 and "湯台" in d["alert"], d)
    check("廢油回收沒拍回收單不能存", amy("/api/safety/save", {"kind": "wasteoil", "data": {"qty": 2, "unit": "桶", "vendor": "某某回收"}})[0] == 400)
    s, d = amy("/api/safety/save", {"kind": "oil", "data": {"filter": True, "change": False, "changed": False, "polar": 27}}); check("極性值 27% 沒換油會警示", "換油" in d["alert"], d)
    check("夥伴不能複檢", amy("/api/safety/review", {"ids": [1]})[0] == 403)
    s, sf = mgr("/api/safety?kind=fridge"); s2, _ = mgr("/api/safety/review", {"ids": [r["id"] for r in sf["rows"]]}); s3, sf = mgr("/api/safety?kind=fridge")
    check("店長複檢、月表看得到", s2 == 200 and all(r["reviewed_by"] for r in sf["rows"]) and len(sf["rows"]) == (2 if PMD[:7] == T[:7] else 1))
    check("看得到照片", amy("/api/safety/photo?id=%d" % sf["rows"][0]["id"])[0] == 200)
    s_, sf2 = amy("/api/safety?kind=fridge")
    check("今天還沒記：早上、下班分開算（6 門早上記了就不能再說早上沒記）", "6 門冰箱" not in sf2["today"]["fridge_am"] and "4 門冰箱" in sf2["today"]["fridge_am"]
          and ("6 門冰箱" not in sf2["today"]["fridge_pm"]) == (PMD == T), sf2["today"])
    check("冰箱不能再選「下午」（店長 10/8 改成上午、下班）", amy("/api/safety/save", {"kind": "fridge", "slot": "下午", "target_id": f6["id"], "data": {"freeze": -18, "chill": 5}, "photo": JPG})[0] == 400)
    import safety as SA
    c = app.db(); D2 = T
    while P.is_closed(c, D2): D2 = (date.fromisoformat(D2) + timedelta(days=1)).isoformat()
    check("18:30 以前打下班卡不提醒食安", SA.closing_check(c, {"id": ids["amy4"]}, D2, "13:00") == [])
    miss = SA.closing_check(c, {"id": ids["amy4"]}, D2, "19:35")
    check("18:30 後打下班卡：冰箱、打烊瓦斯沒記會提醒", any("冰箱" in m for m in miss) and "打烊瓦斯檢查" in miss
          and c.execute("SELECT 1 FROM inbox WHERE user_id=? AND title LIKE '下班前%'", (ids["amy4"],)).fetchone(), miss)
    check("店休日打下班卡不提醒", SA.closing_check(c, {"id": ids["amy4"]}, T, "19:35") == [])
    # 班表可以只排一週幾天
    sat = D2
    while date.fromisoformat(sat).weekday() != 5: sat = (date.fromisoformat(sat) + timedelta(days=1)).isoformat()
    fri = (date.fromisoformat(sat) - timedelta(days=1)).isoformat()
    sh = [{"effective": "2000-01-01", "s1": "09:30", "e1": "13:30", "s2": None, "e2": None, "days": "0,1,2,3,4"}]
    check("班表只排週一到週五：週六沒有班、週五有班", P.shift_on(sh, sat) == [] and P.shift_on(sh, fri) == [("09:30", "13:30")])
    check("班表一天都沒勾不能存", boss("/api/boss/shift/save", {"user_id": ids["amy4"], "effective": "2099-01-01", "s1": "09:30", "e1": "13:30", "days": []})[0] == 400)
    s_, _ = boss("/api/boss/shift/save", {"user_id": ids["amy4"], "effective": "2099-01-01", "s1": "09:30", "e1": "13:30", "days": [0, 1, 2, 3, 4]})
    check("班表存週一到週五", s_ == 200 and c.execute("SELECT days FROM shifts WHERE user_id=? AND effective='2099-01-01'", (ids["amy4"],)).fetchone()[0] == "0,1,2,3,4")
    check("開發提醒：名單現況、今天有班的人算得出來", isinstance(O.call_hint(c), str) and isinstance(O.duty_ids(c, D2), list))
    c.close()
    # ── 零用金、營收現金收走（老闆 10/6）
    check("店長不能撥零用金", mgr("/api/fin/petty", {"day": T, "amount": 5000})[0] == 403)
    s, _ = boss("/api/fin/petty", {"day": T, "amount": 5000, "note": "撥給店長"}); check("老闆撥零用金 5,000", s == 200)
    s, _ = mgr("/api/fin/exp", {"day": T, "category": "其他", "item": "垃圾袋", "amount": 120, "photo": JPG, "pay": "零用金"})
    s2, fd = mgr("/api/fin/day?day=" + T); check("從零用金付：零用金剩 4,880", s == 200 and fd["petty"]["left"] == 4880, fd.get("petty"))
    check("收走營收現金要寫去哪裡", mgr("/api/fin/cashout", {"day": T, "amount": 1000})[0] == 400)
    s, _ = mgr("/api/fin/cashout", {"day": T, "amount": 1000, "dest": "存銀行"}); s2, fd = mgr("/api/fin/day?day=" + T); check("記營收現金存銀行", s == 200 and fd["cash_out"][0]["amount"] == 1000)
    # ── 其他收入（廢油回收，10/9）：店長記、現金放零用金；夥伴不能記；店長只能刪自己記的
    check("其他收入要寫是什麼", mgr("/api/fin/petty", {"kind": "收入", "day": T, "amount": 1600})[0] == 400)
    check("夥伴不能記其他收入", amy("/api/fin/petty", {"kind": "收入", "day": T, "amount": 1600, "note": "廢油回收"})[0] == 403)
    s, _ = mgr("/api/fin/petty", {"kind": "收入", "day": T, "amount": 1600, "note": "廢油回收"}); s2, fd = mgr("/api/fin/day?day=" + T); pt = fd["petty"]
    check("店長記廢油回收 1,600：待存 1,600，零用金還是 4,880（不放零用金）", s == 200 and pt["left"] == 4880 and pt["given"] == 5000 and pt["pending"] == 1600 and len(pt["rows"]) == 1, pt)
    s, ib = boss("/api/inbox"); check("店長記其他收入會通知老闆", any("其他收入 1,600" in x["title"] for x in ib))
    check("店長不能刪老闆的撥款", mgr("/api/fin/petty", {"remove": pt["rows"][0]["id"]})[0] == 403)
    check("夥伴不能標已存", amy("/api/fin/petty", {"deposit": pt["inc_rows"][0]["id"], "day": T})[0] == 403)
    s, _ = mgr("/api/fin/petty", {"deposit": pt["inc_rows"][0]["id"], "day": T}); s2, fd = mgr("/api/fin/day?day=" + T)
    check("店長標已存銀行：待存變 0、記下存的日期", s == 200 and fd["petty"]["pending"] == 0 and fd["petty"]["inc_rows"][0]["deposited"] == T, fd["petty"])
    s, ib = boss("/api/inbox"); check("存了會通知老闆", any("存進銀行" in x["title"] for x in ib))
    check("存了就不能被店長刪", mgr("/api/fin/petty", {"remove": pt["inc_rows"][0]["id"]})[0] == 403)
    mgr("/api/fin/petty", {"kind": "收入", "day": T, "amount": 300, "note": "紙箱回收"}); s2, fd = mgr("/api/fin/day?day=" + T)
    s, _ = mgr("/api/fin/petty", {"remove": fd["petty"]["inc_rows"][0]["id"]}); s2, fd = mgr("/api/fin/day?day=" + T)
    check("店長可以刪自己記的、還沒存的其他收入", s == 200 and fd["petty"]["pending"] == 0 and len(fd["petty"]["inc_rows"]) == 1, fd["petty"])
    # ── 兩頭班打卡：上班 → 下班 → 上班 不能被擋；連按同一種才擋；打卡通知店長和老闆
    c = app.db(); from datetime import datetime as _dt
    ago = lambda m: (_dt.now() - timedelta(minutes=m)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("DELETE FROM punches WHERE user_id=?", (ids["bob4"],))
    c.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,?,?)", (ids["bob4"], ago(100), "in", "test"))
    c.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,?,?)", (ids["bob4"], ago(90), "out", "test")); c.commit()
    s, d = bob("/api/punch", {"lat": 24.75, "lng": 121.75, "acc": 10, "kind": "in"}); check("兩頭班：下班後再上班不會被擋", s == 200 and d["kind"] == "in", d)
    c.execute("UPDATE punches SET at=? WHERE user_id=? AND source='phone'", (ago(5), ids["bob4"])); c.commit()
    s, d = bob("/api/punch", {"lat": 24.75, "lng": 121.75, "acc": 10, "kind": "in"}); check("連按兩次上班才擋", s == 400 and "已經打過上班" in d["error"], d)
    c.close()
    s, ib = mgr("/api/inbox"); s2, ib2 = boss("/api/inbox"); check("打卡通知店長和老闆", any(x["title"].startswith("阿寶四 上班") for x in ib) and any(x["title"].startswith("阿寶四 上班") for x in ib2))
    # ── 排休規則（老闆 10/12）：一天只能一人休、老闆可強制；人數不足、休假太近會提醒
    D9 = "2030-03-05"; D9b = "2030-03-07"; D9c = "2030-03-20"
    s, r = mgr("/api/schedule/off", {"day": D9, "user_id": ids["amy4"], "on": True}); check("排休：阿美 3/5", s == 200, r)
    s, r = mgr("/api/schedule/off", {"day": D9, "user_id": ids["bob4"], "on": True}); check("同一天第二個人排休擋下", s == 409 and "一天只能一個人" in r.get("error", ""), r)
    check("店長不能強制", mgr("/api/schedule/off", {"day": D9, "user_id": ids["bob4"], "on": True, "force": True})[0] == 409)
    s, r = boss("/api/schedule/off", {"day": D9, "user_id": ids["bob4"], "on": True, "force": True}); check("老闆可以強制，並提醒人數不夠", s == 200 and any("人上班" in w for w in r["warn"]), r)
    boss("/api/schedule/off", {"day": D9, "user_id": ids["bob4"], "on": False})
    s, r = mgr("/api/schedule/off", {"day": D9b, "user_id": ids["amy4"], "on": True}); check("同一人休假只差 2 天會提醒", s == 200 and any("太近" in w for w in r["warn"]), r)
    s, r = mgr("/api/schedule/off", {"day": D9c, "user_id": ids["amy4"], "on": True}); check("隔很久就不提醒太近", s == 200 and not any("太近" in w for w in r["warn"]), r)
    s, sc = mgr("/api/schedule?month=2030-03"); x = next(d for d in sc["days"] if d["day"] == D9)
    check("班表顯示每天上班人數（排班的人看得到）", "work" in x and "阿美四" not in x["work"], x.get("work"))
    s, sc = amy("/api/schedule?month=2030-03"); check("夥伴看不到上班人數", all("work" not in d for d in sc["days"]))
    for dd in (D9, D9b, D9c): mgr("/api/schedule/off", {"day": dd, "user_id": ids["amy4"], "on": False})
    # ── 薪資設定分月生效（老闆 10/13：Sakura 10 月月休 5 天、11 月加薪）
    c = app.db()
    c.execute("UPDATE pay_profile SET amount=37000, off_days=5 WHERE user_id=?", (ids["bob4"],))
    c.execute("INSERT INTO pay_hist(user_id,until_month,kind,amount,off_days) VALUES(?,?,?,?,?)", (ids["bob4"], "2030-01", "monthly", 36000, 6))
    c.execute("INSERT INTO pay_hist(user_id,until_month,kind,amount,off_days) VALUES(?,?,?,?,?)", (ids["bob4"], "2030-02", "monthly", 36000, 5)); c.commit()
    import payroll as PP
    g = lambda m: next(r for r in PP.compute(c, m, today="2030-06-01") if r["id"] == ids["bob4"])
    check("分月生效：1 月照舊（36,000、休 6）", (g("2030-01")["amount"], g("2030-01")["off_days"]) == (36000, 6))
    check("分月生效：2 月月休先改 5 天", (g("2030-02")["amount"], g("2030-02")["off_days"]) == (36000, 5))
    check("分月生效：3 月起新月薪", (g("2030-03")["amount"], g("2030-03")["off_days"]) == (37000, 5))
    c.execute("DELETE FROM pay_hist"); c.execute("UPDATE pay_profile SET amount=36000, off_days=6 WHERE user_id=?", (ids["bob4"],)); c.commit(); c.close()
    # ── 導覽紀錄
    s, _ = amy("/api/tour/done", {"k": "welcome"}); s2, me = amy("/api/me"); check("導覽看過會記住", "welcome" in me["tours"])
    amy("/api/tour/reset", {}); s, me = amy("/api/me"); check("重看導覽：清掉紀錄", not me["tours"])
    time.sleep(2)
    check("測試不會動到真正的股東網站", SITE_MT is None or os.path.getmtime(SITE) == SITE_MT)
finally:
    srv.terminate(); srv.wait()
    shutil.rmtree(tmp, ignore_errors=True)
print("全部通過" if not fails else "有 %d 項不對：%s" % (len(fails), fails))
sys.exit(1 if fails else 0)
