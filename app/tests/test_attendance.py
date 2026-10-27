# -*- coding: utf-8 -*-
"""打卡系統整合測試：暫存資料庫＋5498 埠，從登入、打卡、補登、算薪、公告、權限一路測。
跑法：python test_attendance.py          （不會碰正式資料庫）"""
import http.cookiejar, json, os, secrets, shutil, sqlite3, subprocess, sys, tempfile, time, urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # app/
tmp = tempfile.mkdtemp()
DB = os.path.join(tmp, "crm.db")
env = dict(os.environ, CRM_DB=DB, CRM_BAK=os.path.join(tmp, "bak"), CRM_PORT="5498")
sys.path.insert(0, HERE)
os.environ.update(CRM_DB=DB, CRM_BAK=os.path.join(tmp, "bak"))
import app  # noqa: E402

app.init_db()
c = app.db()
PW = {}
for un, name, role in (("boss_t", "測試老闆", "admin"), ("amy_t", "測試阿美", "staff"), ("pt_t", "測試小時", "staff")):
    PW[un] = secrets.token_urlsafe(10)
    c.execute("INSERT INTO users(username,name,pw,role,created) VALUES(?,?,?,?,?)", (un, name, app.hash_pw(PW[un]), role, app.now()))
c.commit(); c.close()
srv = subprocess.Popen([sys.executable, os.path.join(HERE, "app.py")], env=env, cwd=HERE)
time.sleep(1.5)
BASE = "http://127.0.0.1:5498"
fails = []


def client():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def call(path, body=None):
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-Req": "1"} if body is not None else {})
        try:
            r = op.open(req)
            raw = r.read(); return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw.decode())
        except urllib.error.HTTPError as e:
            raw = e.read()
            try: return e.code, json.loads(raw)
            except Exception: return e.code, raw.decode()
    return call


def check(name, cond, extra=""):
    print(("OK  " if cond else "BAD ") + name + (("　" + str(extra)) if extra and not cond else ""))
    if not cond: fails.append(name)


try:
    boss, amy, pt = client(), client(), client()
    for cl, un in ((boss, "boss_t"), (amy, "amy_t"), (pt, "pt_t")):
        s, _ = cl("/api/login", {"username": un, "password": PW[un]}); check("登入 " + un, s == 200)
    s, d = boss("/api/boss/settings")
    ids = {p["username"]: p["id"] for p in d["people"]}
    check("員工不能進老闆頁", amy("/api/boss/today")[0] == 403)
    s, d = amy("/api/punch", {"lat": 24.75, "lng": 121.74, "acc": 10}); check("還沒設薪資也能打卡（打卡就是一切，先記下來）", s == 200 and d["kind"] == "in", d)
    s, pl = boss("/api/boss/punches"); pid = [x for x in pl if x["user_id"] == ids["amy_t"]][0]["id"]
    s, _ = boss("/api/boss/punch/void", {"id": pid, "reason": "測試：先作廢"}); check("老闆作廢打卡", s == 200)
    boss("/api/boss/profile/save", {"user_id": ids["amy_t"], "kind": "monthly", "amount": 36000, "off_days": 6, "punch": True})
    boss("/api/boss/profile/save", {"user_id": ids["pt_t"], "kind": "hourly", "amount": 200, "off_days": 0, "punch": True})
    boss("/api/boss/shift/save", {"user_id": ids["amy_t"], "effective": "2026-10-01", "s1": "09:00", "e1": "13:00", "s2": "15:30", "e2": "19:30"})
    s, _ = boss("/api/boss/store/set", {"lat": 24.75190, "lng": 121.73890, "acc": 8}); check("老闆設定店家位置", s == 200)
    s, d = amy("/api/punch", {"lat": 24.76500, "lng": 121.75500, "acc": 10}); check("離店太遠被擋", s == 400 and "公尺" in d["error"], d)
    s, d = amy("/api/punch", {"lat": 24.75195, "lng": 121.73895, "acc": 300.5}); check("定位不準被擋", s == 400 and "不準" in d["error"], d)
    s, d = amy("/api/punch", {"lat": 24.75195, "lng": 121.73895, "acc": 12}); check("店裡打上班卡", s == 200 and d["kind"] == "in", d)
    s, d = amy("/api/punch", {"lat": 24.75195, "lng": 121.73895, "acc": 12}); check("一分鐘內不能連打", s == 400, d)
    s, st = amy("/api/punch/state"); check("打卡頁看到今天的卡、下一個是下班", st["next"] == "out" and len(st["punches"]) == 1, st.get("punches"))
    # 補登：昨天的上下班，老闆核准一筆、退回一筆
    y = app.date.fromordinal(app.date.today().toordinal() - 1).isoformat()
    _c = app.db()
    while app.P.is_closed(_c, y): y = app.date.fromordinal(app.date.fromisoformat(y).toordinal() - 1).isoformat()   # 昨天剛好店休（週三）就往前找開店日
    _c.close()
    amy("/api/punch/fix", {"day": y, "kind": "in", "time": "09:05", "reason": "手機沒電"})
    amy("/api/punch/fix", {"day": y, "kind": "out", "time": "13:00", "reason": "手機沒電"})
    s, d = amy("/api/punch/fix", {"day": y, "kind": "out", "time": "19:30", "reason": ""}); check("補登沒寫原因被擋", s == 400)
    s, fx = boss("/api/boss/fixes"); pend = [f for f in fx if f["status"] == "待審"]; check("老闆看到 2 筆待審", len(pend) == 2, len(pend))
    for f in pend: boss("/api/boss/fix/decide", {"id": f["id"], "approve": True})
    s, d = boss("/api/boss/fix/decide", {"id": pend[0]["id"], "approve": True}); check("同一筆不能審兩次", s == 400)
    # 老闆照紙卡補一筆 PT 的打卡
    boss("/api/boss/punch/add", {"user_id": ids["pt_t"], "day": y, "time": "09:00", "kind": "in", "reason": "照紙本打卡卡"})
    boss("/api/boss/punch/add", {"user_id": ids["pt_t"], "day": y, "time": "13:00", "kind": "out", "reason": "照紙本打卡卡"})
    s, d = boss("/api/boss/punch/add", {"user_id": ids["pt_t"], "day": y, "time": "13:00", "kind": "out", "reason": ""}); check("老闆補登沒寫原因被擋", s == 400)
    boss("/api/boss/advance/save", {"user_id": ids["amy_t"], "day": app.today(), "amount": 1000, "note": "測試預支", "pay_month": app.today()[:7], "drawer": False})
    month = app.today()[:7]
    s, pay = boss("/api/boss/payroll?month=" + y[:7])
    rows = {r["username"]: r for r in pay["rows"]}
    a = rows.get("amy_t"); p = rows.get("pt_t")
    check("PT 4 小時 = 800", p and p["base"] == 800 and p["mins"] == 240, p and (p["base"], p["mins"]))
    check("阿美昨天補登的 3 小時 55 分有算、晚 5 分算遲到", a and a["mins"] >= 235 and a["late_n"] >= 1, a and (a["mins"], a["late_n"]))
    if y[:7] == month: check("預支有扣", a["ded"] == min(1000, a["base"]), (a["ded"], a["base"]))
    s, st = amy("/api/punch/state"); check("員工只看到自己的薪資試算", st["month"] and st["month"]["username"] == "amy_t")
    s, html = boss("/boss/slips?month=" + y[:7]); check("老闆產生簽收單", s == 200 and "簽收單" in html)
    check("員工不能產生簽收單", amy("/boss/slips?month=" + y[:7])[0] == 403)
    # 公告
    boss("/api/boss/notice/save", {"title": "測試公告", "body": "內容", "pinned": True})
    s, ns = amy("/api/notices"); n = ns[0]; check("員工看到公告、未讀", n["title"] == "測試公告" and not n["read"])
    amy("/api/notice/ack", {"id": n["id"]})
    s, ns = boss("/api/notices"); rd = {r["name"]: r["at"] for r in ns[0]["readers"]}; check("老闆看到誰讀過", bool(rd.get("測試阿美")) and not rd.get("測試小時"), rd)
    check("員工不能發公告", amy("/api/boss/notice/save", {"title": "x", "body": "y"})[0] == 403)
    s, b = boss("/api/boss/today"); check("今日出勤看板有阿美上班中", any(r["name"] == "測試阿美" and "上班中" in r["status"] for r in b["rows"]), b["rows"])
    s, d = amy("/api/punch", {"lat": 24.75195, "lng": 121.73895, "acc": 12}); check("一分鐘內第二次仍擋", s == 400)
finally:
    srv.terminate(); srv.wait()
    shutil.rmtree(tmp, ignore_errors=True)
print("全部通過" if not fails else "有 %d 項不對：%s" % (len(fails), fails))
sys.exit(1 if fails else 0)
