# -*- coding: utf-8 -*-
"""v3 整合測試：角色、班表排休、記帳（營收直接入帳、支出要核銷）＋帳務同步讀取、新夥伴註冊審核、外送單全流程、
店長發公告＋站內通知、推播訂閱、移除夥伴、遲到提醒、團訂今天誰上班。暫存資料庫＋5495 埠。
跑法：python test_v3.py"""
import base64, http.cookiejar, importlib.util, json, os, secrets, shutil, subprocess, sys, tempfile, time, urllib.request
from datetime import date, timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # app/
tmp = tempfile.mkdtemp()
DB = os.path.join(tmp, "crm.db")
env = dict(os.environ, CRM_DB=DB, CRM_BAK=os.path.join(tmp, "bak"), CRM_PORT="5495", CRM_EXP_START="2026-01-01")   # 支出開始日：測試不受 10/6 限制
sys.path.insert(0, HERE)
os.environ.update(CRM_DB=DB, CRM_BAK=os.path.join(tmp, "bak"), CRM_EXP_START="2026-01-01")
import app, ops as O  # noqa: E402

app.init_db()
c = app.db()
PW = {}
T = date.today().isoformat(); TM = (date.today() + timedelta(days=1)).isoformat(); YD = (date.today() - timedelta(days=1)).isoformat()
for un, name, role in (("boss3", "老闆三", "admin"), ("mgr3", "店長三", "manager"), ("amy3", "阿美三", "staff"), ("rid3", "外送三", "staff")):
    PW[un] = secrets.token_urlsafe(10)
    c.execute("INSERT INTO users(username,name,pw,role,created) VALUES(?,?,?,?,?)", (un, name, app.hash_pw(PW[un]), role, app.now()))
ids = {r["username"]: r["id"] for r in c.execute("SELECT id, username FROM users")}
c.execute("UPDATE users SET rider=1 WHERE username='rid3'")
for un in ("amy3", "rid3"):
    c.execute("INSERT INTO pay_profile(user_id,kind,amount,off_days,punch) VALUES(?,?,?,?,1)", (ids[un], "monthly", 36000, 6))
    c.execute("INSERT INTO shifts(user_id,effective,s1,e1,s2,e2) VALUES(?,?,?,?,?,?)", (ids[un], "2026-01-01", "09:00", "13:00", "15:30", "19:30"))
c.execute("INSERT INTO settings(k,v) VALUES('weekly_closed','')")       # 測試日不要剛好碰到週三公休
c.commit(); c.close()
SITE = os.path.normpath(os.path.join(HERE, "..", "_部署(股東帳務網站)", "www", "index.html"))
SITE_MT = os.path.getmtime(SITE) if os.path.exists(SITE) else None
srv = subprocess.Popen([sys.executable, os.path.join(HERE, "app.py")], env=env, cwd=HERE)
time.sleep(1.8)
BASE = "http://127.0.0.1:5495"
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
    boss, mgr, amy, rid, anon = client(), client(), client(), client(), client()
    for cl, un in ((boss, "boss3"), (mgr, "mgr3"), (amy, "amy3"), (rid, "rid3")):
        cl("/api/login", {"username": un, "password": PW[un]})
    s, me = mgr("/api/me"); check("店長權限：記帳、發公告、排班", me["perms"]["fin"] and me["perms"]["post"] and me["perms"]["sched"] and not me["perms"]["admin"], me.get("perms"))
    s, me = amy("/api/me"); check("夥伴沒有記帳權限", not me["perms"]["fin"] and not me["perms"]["post"])
    check("夥伴不能記帳", amy("/api/fin/day")[0] == 403)
    check("夥伴不能排休", amy("/api/schedule/off", {"day": TM, "user_id": ids["amy3"], "on": True})[0] == 403)
    # ── 靜態檔、PWA
    s, b = anon("/sw.js"); check("service worker 拿得到", s == 200 and b"showNotification" in b)
    s, b = anon("/manifest.webmanifest"); check("manifest 拿得到", s == 200 and b"standalone" in b)
    check("static 不能讀上層檔案", anon("/static/..%2Fapp.py")[0] == 404)
    # ── 班表
    s, _ = mgr("/api/schedule/off", {"day": TM, "user_id": ids["amy3"], "on": True, "note": "家裡有事"}); check("店長排休", s == 200)
    mgr("/api/schedule/duty", {"day": TM, "kind": "廁所", "user_id": ids["rid3"]})
    s, sch = amy("/api/schedule?month=" + TM[:7]); dd = next(x for x in sch["days"] if x["day"] == TM)
    check("夥伴看得到誰排休、廁所輪值", any(o["name"] == "阿美三" for o in dd["off"]) and dd["duty"][0]["name"] == "外送三" and TM in sch["mine"], dd)
    s, du = amy("/api/onduty"); check("明天上班名單扣掉排休", [p["name"] for p in du["tomorrow"]["on"]] == ["外送三"] and du["tomorrow"]["off"] == ["阿美三"], du["tomorrow"])
    s, dash = amy("/api/dashboard"); check("團訂首頁有今天明天誰上班、AI 區", "duty" in dash and "ai" in dash)
    # ── 記帳：營收直接入帳、支出要核銷
    s, d = mgr("/api/fin/rev", {"day": T, "cash": 20000, "stored": 300, "eticket": 700, "voucher": 100, "drawer": 19500}); check("營收沒照片擋", s == 400 and "照片" in d["error"], d)
    s, d = mgr("/api/fin/rev", {"day": T, "cash": 20000, "stored": 300, "eticket": 700, "voucher": 100, "orders": 90, "boxes": 180, "drawer": 19500, "photo": JPG})
    check("店長記營收，應收自動算 21,000", s == 200 and d["total"] == 21000, d)
    s, fd = mgr("/api/fin/day?day=" + T); check("營收直接入帳", fd["rev"]["status"] == "已入帳")
    check("營收日期不能早於系統開始", mgr("/api/fin/rev", {"day": (date.fromisoformat(O.FIN_START) - timedelta(days=1)).isoformat(), "cash": 1, "photo": JPG})[0] == 400)
    s, d = mgr("/api/fin/exp", {"day": T, "category": "清潔文具雜支", "item": "垃圾袋", "amount": 120}); check("支出沒照片擋", s == 400)
    s, d = mgr("/api/fin/exp", {"day": T, "category": "清潔文具雜支", "item": "垃圾袋", "vendor": "全聯", "amount": 120, "photo": JPG}); eid = d.get("id")
    check("店長記支出", s == 200 and eid)
    mgr("/api/fin/exp", {"day": T, "category": "自購食材雜貨", "item": "雞蛋", "amount": 300, "photo": JPG})
    s, me = boss("/api/me"); check("老闆看到 2 筆支出待核銷", me["fin_pending"] == 2, me.get("fin_pending"))
    s, lst = boss("/api/fin/list?month=" + T[:7]); check("核銷清單有今天", lst["pending"] and lst["pending"][0]["day"] == T and lst["recent_rev"])
    s, img = boss("/api/fin/photo?kind=exp&id=%d" % eid); check("老闆看得到收據照片", s == 200 and img[:3] == b"\xff\xd8\xff")
    check("夥伴看不到收據照片", amy("/api/fin/photo?kind=exp&id=%d" % eid)[0] == 403)
    check("退回要寫原因", boss("/api/fin/verify", {"kind": "exp", "day": T, "id": eid, "approve": False})[0] == 400)
    boss("/api/fin/verify", {"kind": "exp", "day": T, "id": eid, "approve": False, "note": "收據看不清楚"})
    s, inbox = mgr("/api/inbox"); check("店長收到退回通知", any("退回" in x["title"] for x in inbox), [x["title"] for x in inbox])
    s, d = boss("/api/fin/verify", {"kind": "all", "day": T, "approve": True}); check("這天全部核銷", s == 200 and d["n"] >= 1, d)
    s, fd = mgr("/api/fin/day?day=" + T); st = {e["item"]: e["status"] for e in fd["exps"]}
    check("退回的那筆不跟著核銷、另一筆核銷了", st == {"垃圾袋": "退回", "雞蛋": "已核銷"}, st)
    check("已核銷的店長不能改", mgr("/api/fin/exp", {"id": [e for e in fd["exps"] if e["item"] == "雞蛋"][0]["id"], "day": T, "category": "自購食材雜貨", "item": "雞蛋", "amount": 999})[0] == 400)
    # 股東帳務頁產生器另有自己的測試（ledger/）
    # ── 新夥伴註冊
    s, d = anon("/api/register", {"name": "新人", "username": "new bie", "password": "abc123", "position": "外送", "phone": "0912"})
    check("帳號不能有空白", s == 400)
    s, d = anon("/api/register", {"name": "新人", "username": "newbie", "password": "abc123", "position": "外送", "phone": "0912"}); check("新夥伴註冊", s == 200, d)
    s, d = anon("/api/register", {"name": "新人2", "username": "newbie", "password": "abc123"}); check("同帳號不能再註冊", s == 400)
    nb = client(); s, d = nb("/api/login", {"username": "newbie", "password": "abc123"}); check("還沒審核不能登入、說清楚", s == 403 and "審核" in d["error"], d)
    s, me = boss("/api/me"); check("老闆看到 1 位待審核", me["pending_regs"] == 1)
    s, regs = boss("/api/boss/registrations"); check("審核清單", regs and regs[0]["position"] == "外送")
    check("店長不能審核", mgr("/api/boss/registration/decide", {"id": regs[0]["id"], "approve": True})[0] == 403)
    boss("/api/boss/registration/decide", {"id": regs[0]["id"], "approve": True, "rider": True})
    s, d = nb("/api/login", {"username": "newbie", "password": "abc123"}); s2, me = nb("/api/me")
    check("核准後用自己的密碼登入、不用再改密碼、是外送夥伴", s == 200 and me["must_change"] is False and me["perms"]["rider"], me.get("perms"))
    # ── 公告：店長發 → 大家收到通知
    s, _ = mgr("/api/notice/save", {"title": "明天提早備料", "body": "團訂 80 個"}); check("店長發公告", s == 200)
    check("夥伴不能發公告", amy("/api/notice/save", {"title": "x", "body": "y"})[0] == 403)
    s, me = amy("/api/me"); check("夥伴看到 1 則新公告（驚嘆號）", me["notice_unread"] == 1, me.get("notice_unread"))
    s, inbox = amy("/api/inbox"); check("夥伴收到新公告通知", inbox and inbox[0]["title"].startswith("新公告"))
    s, ns = mgr("/api/notices"); n = ns[0]; check("店長看得到誰讀過、自己發的不用按已讀", n["author"] == "店長" and n["mine"] and n["read"] and "readers" in n)
    s, ns = amy("/api/notices"); check("夥伴看到作者是店長", ns[0]["author"] == "店長")
    check("夥伴不能改店長的公告", amy("/api/notice/save", {"id": n["id"], "title": "改", "body": "改"})[0] == 403)
    # ── 推播訂閱
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/test123", "keys": {"p256dh": "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4", "auth": "BTBZMqHH6r4Tts7J_aSIgg"}}
    s, _ = amy("/api/push/subscribe", {"sub": sub}); check("手機訂閱通知", s == 200)
    check("沒有 https 的訂閱擋掉", amy("/api/push/subscribe", {"sub": {"endpoint": "http://x", "keys": {"p256dh": "a", "auth": "b"}}})[0] == 400)
    s, me = amy("/api/me"); check("有推播公鑰", len(me["push_key"]) > 80)
    # ── 外送全流程
    s, d = mgr("/api/delivery/save", {"customer": "示範訓練場", "address": "行政大樓", "items": "排骨 20", "boxes": 20, "bags": 2, "amount": 2400, "pay": "現金收款",
                                       "due": "23:59", "receipt": "訓練場 統編 12345678", "rider_id": ids["rid3"]})
    did = d.get("id"); check("開外送單並派人", s == 200 and did)
    s, inbox = rid("/api/inbox"); check("外送夥伴收到派單通知", inbox and inbox[0]["title"].startswith("新外送單"))
    s, dv = rid("/api/deliveries"); m = dv["mine"][0]; check("我的外送看到、等我接受、收現 2400", m["waiting_accept"] and m["collect"] == 2400, m)
    check("別人不能接受", amy("/api/delivery/accept", {"id": did})[0] == 400)
    rid("/api/delivery/accept", {"id": did})
    mgr("/api/delivery/status", {"id": did, "to": "製作中"})
    s, _ = mgr("/api/delivery/delay", {"id": did, "mins": 10}); s2, dv = mgr("/api/deliveries"); r = [x for x in dv["rows"] if x["id"] == did][0]
    check("出餐延後 10 分", s == 200 and r["ready_by"] is not None, r.get("ready_by"))
    mgr("/api/delivery/status", {"id": did, "to": "已出餐"})
    s, d = rid("/api/delivery/status", {"id": did, "to": "配送中", "checked": {"品項份數": True, "袋數": True, "餐具": True, "湯和飲料": True}})
    check("要收據的單沒核對收據不能取餐", s == 400 and "收據" in d["error"], d)
    s, d = rid("/api/delivery/status", {"id": did, "to": "配送中", "checked": {"品項份數": True, "袋數": True, "餐具": True, "湯和飲料": True, "收據": True}}); check("核對完取餐出發", s == 200, d)
    rid("/api/delivery/near", {"id": did})
    s, d = rid("/api/delivery/status", {"id": did, "to": "已送達", "handoff": "交給本人", "cash_got": 2400}); check("沒到點打卡不能按送達", s == 400 and "到了" in d["error"], d)
    check("別人不能替他到點打卡", amy("/api/delivery/arrive", {"id": did, "lat": 24.75, "lng": 121.75})[0] == 400)
    s, d = rid("/api/delivery/arrive", {"id": did, "lat": 24.7591, "lng": 121.7530, "acc": 12}); check("到點定位打卡", s == 200, d)
    s, d = rid("/api/delivery/status", {"id": did, "to": "已送達", "handoff": "放櫃台", "cash_got": 2400}); check("放櫃台沒照片不能送達", s == 400)
    s, d = rid("/api/delivery/status", {"id": did, "to": "已送達", "handoff": "放櫃台", "photo": JPG, "cash_got": 2300}); check("拍照送達", s == 200, d)
    s, inbox = boss("/api/inbox"); check("收款不一樣通知老闆", any("收款跟單上不一樣" in x["title"] for x in inbox))
    s, dv = mgr("/api/deliveries"); r = [x for x in dv["rows"] if x["id"] == did][0]
    check("送達紀錄：時間、照片、實收、到點位置", r["status"] == "已送達" and r["proof"] and r["cash_got"] == 2300 and r["picked_at"] and r["near_at"] and r["arrive_at"] and r["arrive_lat"] == 24.7591)
    check("看板：準時 1 單、現金待繳 2300", dv["stats"]["ontime"] == 1 and dv["stats"]["cash_due"] == 2300, dv["stats"])
    check("夥伴看不到別人的送達照片", amy("/api/delivery/photo?id=%d" % did)[0] == 403)
    # 前一班沒繳回的現金 → 不能接新的現金單
    c = app.db(); c.execute("UPDATE deliveries SET day=? WHERE id=?", (YD, did)); c.commit(); c.close()
    s, d = mgr("/api/delivery/save", {"customer": "散客", "address": "示範路", "boxes": 3, "amount": 360, "pay": "現金收款", "rider_id": ids["rid3"]})
    check("前一班現金沒繳不能派現金單（而且不會先多開一張）", s == 400 and "沒繳回" in d["error"] and not [x for x in mgr("/api/deliveries")[1]["rows"] if x["customer"] == "散客"], d)
    check("夥伴不能收現金", amy("/api/delivery/settle", {"rider_id": ids["rid3"]})[0] == 403)
    check("收回金額對不上會擋", mgr("/api/delivery/settle", {"rider_id": ids["rid3"], "ids": [did], "amount": 999})[0] == 400)
    s, d = mgr("/api/delivery/settle", {"rider_id": ids["rid3"], "ids": [did], "amount": 2300}); check("店長收回現金（只結清看到的那張）", s == 200 and d["n"] == 1, d)
    check("現金收款沒填金額擋", mgr("/api/delivery/save", {"customer": "散客2", "address": "示範路", "boxes": 3, "pay": "現金收款"})[0] == 400)
    s, d = mgr("/api/delivery/save", {"customer": "散客", "address": "示範路", "boxes": 3, "amount": 360, "pay": "現金收款"})
    check("重複開單擋", mgr("/api/delivery/save", {"customer": "散客", "address": "示範路", "boxes": 3, "amount": 360, "pay": "現金收款"})[0] == 400)
    s, dv = mgr("/api/deliveries"); new = [x for x in dv["rows"] if x["customer"] == "散客"][0]
    s, d = mgr("/api/delivery/assign", {"id": new["id"], "rider_id": ids["rid3"]}); check("繳回後可以派了", s == 200, d)
    s, d = rid("/api/delivery/issue", {"id": new["id"], "kind": "聯絡不上客人", "note": "打了兩次"}); s2, inbox = mgr("/api/inbox")
    check("回報問題通知店長", s == 200 and any("外送問題" in x["title"] for x in inbox))
    s, d = mgr("/api/delivery/copy", {"id": new["id"]}); check("拆單", s == 200 and d["id"])
    check("取消要寫原因", mgr("/api/delivery/cancel", {"id": new["id"]})[0] == 400)
    s, d = rid("/api/delivery/save", {"id": new["id"], "customer": "散客", "address": "示範路", "boxes": 3, "amount": 360, "pay": "已付款"})
    check("外送夥伴不能把現金單改成已付款", s == 400 and "店長" in d["error"], d)
    check("夥伴不能取消別人的單", rid("/api/delivery/cancel", {"id": new["id"], "note": "x"})[0] == 400)
    check("夥伴不能改派別人的單", amy("/api/delivery/assign", {"id": new["id"], "rider_id": ids["amy3"]})[0] == 400)
    rid("/api/delivery/accept", {"id": new["id"]})
    s, _ = mgr("/api/delivery/save", {"id": new["id"], "customer": "散客", "address": "示範路 99 號", "boxes": 3, "amount": 360, "pay": "現金收款", "rider_id": ids["rid3"]})
    s2, dv = rid("/api/deliveries"); m2 = [x for x in dv["mine"] if x["id"] == new["id"]][0]
    check("改地址不會把「已接受」清掉", s == 200 and m2["accepted_at"] and not m2["waiting_accept"], m2.get("accepted_at"))
    s, _ = mgr("/api/delivery/cancel", {"id": new["id"], "note": "客人改天"}); s2, _ = mgr("/api/delivery/uncancel", {"id": new["id"]})
    check("店長取消後可以復原", s == 200 and s2 == 200)
    # ── 薪資定案：快照、擋寫入、預支結轉
    import payroll as PR
    PM = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    s, _ = boss("/api/boss/advance/save", {"user_id": ids["amy3"], "day": PM + "-20", "amount": 5000}); check("登記上個月預支", s == 200)
    check("連按兩次預支擋掉", boss("/api/boss/advance/save", {"user_id": ids["amy3"], "day": PM + "-20", "amount": 5000})[0] == 400)
    check("這個月還沒結束不能定案", boss("/api/boss/month/set", {"month": T[:7], "status": "已定案"})[0] == 400)
    s, _ = boss("/api/boss/month/set", {"month": PM, "status": "已定案"}); check("上個月定案", s == 200)
    s, st = boss("/api/boss/settings?month=" + T[:7]); carry = [a for a in st["advances"] if "結轉" in (a["note"] or "") and not a["voided"] and a["name"] == "阿美三"]
    check("沒扣完的預支轉到這個月 1 日", carry and carry[0]["amount"] == 5000 and carry[0]["day"] == T[:7] + "-01", carry)
    s, d = boss("/api/boss/punch/add", {"user_id": ids["amy3"], "day": PM + "-21", "time": "09:00", "kind": "in", "reason": "補"}); check("已定案的月份不能補打卡", s == 400 and "試算中" in d["error"], d)
    check("已定案的月份不能加預支", boss("/api/boss/advance/save", {"user_id": ids["amy3"], "day": PM + "-22", "amount": 100})[0] == 400)
    check("夥伴不能補登已結算的月份", amy("/api/punch/fix", {"day": PM + "-28", "kind": "in", "time": "09:00", "reason": "x"})[0] == 400 if (date.today() - date.fromisoformat(PM + "-28")).days <= 35 else True)
    c = app.db(); c.execute("UPDATE pay_profile SET amount=99999 WHERE user_id=?", (ids["amy3"],)); c.commit()
    s, pr = boss("/api/boss/payroll?month=" + PM); check("定案後調薪不會改到已定案的數字", all(r["amount"] == 36000 for r in pr["rows"] if r["name"] == "阿美三"), [r["amount"] for r in pr["rows"]])
    c.execute("UPDATE pay_profile SET amount=36000 WHERE user_id=?", (ids["amy3"],)); c.commit(); c.close()
    s, _ = boss("/api/boss/month/set", {"month": PM, "status": "試算中"}); s2, st = boss("/api/boss/settings?month=" + T[:7])
    check("改回試算中：結轉撤銷", s == 200 and not [a for a in st["advances"] if "結轉" in (a["note"] or "") and not a["voided"]])
    # ── 上班／下班照班表判斷：中午忘了打下班，下午回來那一下算上班
    c = app.db(); c.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,?,?)", (ids["amy3"], T + " 09:00:00", "in", "test")); c.commit()
    check("早上上班後，中午 12:50 按 → 下班", PR.guess_kind(c, ids["amy3"], T, "12:50") == "out")
    check("中午忘了打下班，15:35 按 → 上班", PR.guess_kind(c, ids["amy3"], T, "15:35") == "in")
    check("晚到 2 個半小時也算遲到", PR.lates_of(["11:30"], [("09:00", "13:00"), ("15:30", "19:30")]) == [("11:30", "09:00", 150)])
    c.execute("DELETE FROM punches WHERE source='test' AND user_id=?", (ids["amy3"],)); c.commit(); c.close()
    # ── 老闆切換角色（同一個帳號模擬店長／夥伴）
    s, me = boss("/api/me"); check("老闆可以切換角色", me["can_switch"] and not me["acting"], me.get("can_switch"))
    check("店長不能切換角色", mgr("/api/switch", {"to": "staff"})[0] == 403)
    s, _ = boss("/api/switch", {"to": "manager"}); s2, me = boss("/api/me")
    check("切成模擬店長：店長權限、顯示老闆名字", s == 200 and me["acting"] == "manager" and me["role"] == "manager" and me["perms"]["fin"] and not me["perms"]["admin"] and me["real_name"] == "老闆三", me)
    check("模擬店長看不到老闆頁", boss("/api/boss/today")[0] == 403)
    s, d = boss("/api/notice/save", {"title": "模擬", "body": "x"}); check("模擬時發公告不會真的存", s == 403 and "模擬" in d["error"], d)
    check("模擬時記帳不會真的存", boss("/api/fin/rev", {"day": T, "cash": 1})[0] == 403)
    s, _ = boss("/api/switch", {"to": "staff"}); s2, me = boss("/api/me")
    check("切成模擬夥伴：有打卡、沒記帳", me["acting"] == "staff" and me["role"] == "staff" and me["punch"] and not me["perms"]["fin"], me)
    s, d = boss("/api/journal/post", {"body": "模擬寫日誌"}); check("模擬夥伴可以寫日誌", s == 200, d)
    check("模擬夥伴不能訂閱通知（不會搶走老闆手機）", boss("/api/push/subscribe", {"sub": sub})[0] == 403)
    check("模擬夥伴不能改密碼", boss("/api/password", {"old": "x", "new": "abcdefg"})[0] == 403)
    s, _ = boss("/api/switch", {"to": "admin"}); s2, me = boss("/api/me"); check("切回老闆", me["role"] == "admin" and not me["acting"], me.get("acting"))
    s, inbox = boss("/api/inbox"); check("模擬夥伴寫日誌不會通知老闆", not any("試用" in x["title"] for x in inbox))
    s, us = boss("/api/users"); check("帳號清單看不到模擬身分", not any(u.get("demo") for u in us))
    s, ts = boss("/api/journal/threads"); check("日誌清單看不到模擬身分", all("試用" not in t["name"] for t in ts))
    s, dash = boss("/api/dashboard"); check("開發首頁團隊統計沒有模擬身分", all("試用" not in x["name"] for x in dash["team"]))
    s, pr = boss("/api/boss/payroll"); check("薪資沒有模擬身分", all("試用" not in x["name"] for x in pr["rows"]))
    check("模擬身分不能直接登入", anon("/api/login", {"username": "demo", "password": "x"})[0] == 401)
    # ── 移除夥伴
    s, _ = boss("/api/user/save", {"id": ids["amy3"], "removed": True}); check("老闆移除夥伴", s == 200)
    s, us = boss("/api/users"); check("移除後帳號清單看不到", all(u["id"] != ids["amy3"] for u in us))
    s, st = boss("/api/boss/settings"); check("移除後薪資設定看不到", all(p["id"] != ids["amy3"] for p in st["people"]))
    check("移除後不能登入", amy("/api/me")[0] == 401)
    s, ts = boss("/api/journal/threads"); check("移除後日誌清單看不到", all(t["id"] != ids["amy3"] for t in ts))
    check("不能移除自己", boss("/api/user/save", {"id": ids["boss3"], "removed": True})[0] == 400)
    # ── 遲到提醒（直接呼叫）：今天晚 20 分、明天有班 → 收到提醒
    c = app.db()
    c.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,?,?)", (ids["rid3"], T + " 09:20:00", "in", "test"))
    c.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,?,?)", (ids["rid3"], T + " 13:00:00", "out", "test"))
    c.execute("DELETE FROM day_off"); c.commit()
    n = O.late_reminders(c, T); c.close()
    s, inbox = rid("/api/inbox"); check("遲到的人晚上收到「明天不要遲到」", n == 1 and any(x["title"] == "明天不要遲到喔" and "20 分鐘" in x["body"] for x in inbox), (n, [x["title"] for x in inbox]))
    time.sleep(3)
    check("測試不會動到真正的股東網站", SITE_MT is None or os.path.getmtime(SITE) == SITE_MT)
finally:
    srv.terminate(); srv.wait()
    shutil.rmtree(tmp, ignore_errors=True)
print("全部通過" if not fails else "有 %d 項不對：%s" % (len(fails), fails))
sys.exit(1 if fails else 0)
