# -*- coding: utf-8 -*-
"""v2 整合測試：首次登入設密碼、我很棒日誌（像 LINE）、教育訓練。暫存資料庫＋5496 埠，不碰正式資料。
跑法：python test_v2.py"""
import base64, http.cookiejar, json, os, secrets, shutil, subprocess, sys, tempfile, time, urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # app/
tmp = tempfile.mkdtemp()
DB = os.path.join(tmp, "crm.db")
env = dict(os.environ, CRM_DB=DB, CRM_BAK=os.path.join(tmp, "bak"), CRM_PORT="5496")
sys.path.insert(0, HERE)
os.environ.update(CRM_DB=DB, CRM_BAK=os.path.join(tmp, "bak"))
import app  # noqa: E402

app.init_db()
c = app.db()
PW = {}
for un, name, role in (("boss_v", "測試老闆", "admin"), ("amy_v", "測試阿美", "staff"), ("bea_v", "測試小貝", "staff")):
    PW[un] = secrets.token_urlsafe(10)
    c.execute("INSERT INTO users(username,name,pw,role,created) VALUES(?,?,?,?,?)", (un, name, app.hash_pw(PW[un]), role, app.now()))
c.commit(); c.close()
srv = subprocess.Popen([sys.executable, os.path.join(HERE, "app.py")], env=env, cwd=HERE)
time.sleep(1.5)
BASE = "http://127.0.0.1:5496"
fails = []
JPG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 200).decode()


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
    boss, amy, bea = client(), client(), client()
    for cl, un in ((boss, "boss_v"), (amy, "amy_v"), (bea, "bea_v")):
        cl("/api/login", {"username": un, "password": PW[un]})
    ids = {u["username"]: u["id"] for u in boss("/api/users")[1]}
    # --- 首次登入設密碼
    boss("/api/user/save", {"id": ids["amy_v"], "password": "card1234"})          # 老闆重設＝卡片密碼
    s, _ = amy("/api/me"); check("重設密碼後舊登入失效", s == 401)
    s, _ = amy("/api/login", {"username": "amy_v", "password": "card1234"}); check("用卡片密碼登入", s == 200)
    s, me = amy("/api/me"); check("登入後要求先設自己的密碼", me.get("must_change") is True, me.get("must_change"))
    s, d = amy("/api/password", {"first": True, "new": "card1234"}); check("不能設成跟卡片一樣", s == 400)
    s, d = amy("/api/password", {"first": True, "new": "amy_v"}); check("不能跟帳號一樣", s == 400)
    s, d = amy("/api/password", {"first": True, "new": "amy-own-pw"}); check("設定自己的密碼", s == 200, d)
    s, me = amy("/api/me"); check("設好後不再要求", me.get("must_change") is False)
    s, d = amy("/api/password", {"first": True, "new": "another-pw"}); check("設好後改密碼要舊密碼", s == 400)
    s, _ = boss("/api/user/save", {"username": "new_v", "name": "新人", "password": "start123"})
    nw = client(); nw("/api/login", {"username": "new_v", "password": "start123"})
    check("老闆新開的帳號也要先設密碼", nw("/api/me")[1].get("must_change") is True)
    # --- 日誌
    s, d = amy("/api/journal/post", {"body": "今天我把冷藏庫整理得很乾淨"}); check("夥伴寫日誌", s == 200, d)
    s, d = amy("/api/journal/post", {"body": "", "photo": JPG}); check("夥伴傳照片", s == 200, d); pid = d.get("id")
    s, d = amy("/api/journal/post", {"body": "", "photo": base64.b64encode(b"GIF89a....").decode()}); check("不是 JPG/PNG 擋掉", s == 400)
    s, d = amy("/api/journal/post", {"body": "   "}); check("空白不能送", s == 400)
    s, me = boss("/api/me"); check("老闆看到 2 則未讀", me["journal_unread"] == 2, me["journal_unread"])
    s, ts = boss("/api/journal/threads"); a = next(t for t in ts if t["id"] == ids["amy_v"]); b = next(t for t in ts if t["id"] == ids["bea_v"])
    check("老闆清單：阿美今天寫了、小貝還沒", a["wrote_today"] and not b["wrote_today"] and a["unread"] == 2, (a, b))
    s, th = boss("/api/journal?uid=%d" % ids["amy_v"]); check("老闆看阿美的對話", len(th["messages"]) == 2 and th["wrote_today"])
    s, me = boss("/api/me"); check("看過後老闆未讀歸零", me["journal_unread"] == 0, me["journal_unread"])
    s, d = boss("/api/journal/post", {"uid": ids["amy_v"], "body": "做得好！"}); check("老闆回覆", s == 200)
    s, d = boss("/api/journal/post", {"body": "沒指定夥伴"}); check("老闆回覆要指定夥伴", s == 400)
    s, me = amy("/api/me"); check("阿美看到 1 則老闆回覆未讀", me["journal_unread"] == 1, me["journal_unread"])
    s, th = amy("/api/journal"); check("阿美看到老闆回覆", th["messages"][-1]["body"] == "做得好！" and th["messages"][-1]["author_role"] == "admin")
    s, th = amy("/api/journal?uid=%d" % ids["bea_v"]); check("夥伴不能看別人的日誌（uid 被忽略）", th["thread"]["id"] == ids["amy_v"])
    check("夥伴不能看日誌清單", bea("/api/journal/threads")[0] == 403)
    s, img = boss("/api/journal/photo?id=%d" % pid); check("老闆看得到照片", s == 200 and img[:3] == b"\xff\xd8\xff")
    check("阿美看得到自己的照片", amy("/api/journal/photo?id=%d" % pid)[0] == 200)
    check("小貝看不到阿美的照片", bea("/api/journal/photo?id=%d" % pid)[0] == 403)
    first = th["messages"][0]["id"]
    check("小貝不能收回阿美的", bea("/api/journal/remove", {"id": first})[0] == 403)
    s, _ = amy("/api/journal/remove", {"id": first}); s2, th = amy("/api/journal")
    check("阿美收回自己今天的", s == 200 and th["messages"][0]["removed"] and th["messages"][0]["body"] is None)
    s, st = amy("/api/punch/state"); check("打卡頁知道今天寫過日誌", st.get("journal_today") is True)
    # --- 教育訓練
    s, _ = boss("/api/boss/manual/save", {"chapter": "1 認識我們的店", "title": "菜單", "body": "■ 經典十款\n・**招牌**"}); check("老闆新增一篇", s == 200)
    boss("/api/boss/manual/save", {"chapter": "1 認識我們的店", "title": "價目", "body": "內容"})
    check("夥伴不能新增", amy("/api/boss/manual/save", {"chapter": "x", "title": "y", "body": "z"})[0] == 403)
    s, ms = amy("/api/manual"); check("夥伴看到 2 篇、照順序", [m["title"] for m in ms] == ["菜單", "價目"], [m["title"] for m in ms])
    check("夥伴看不到誰讀過", "readers" not in ms[0])
    s, me = amy("/api/me"); check("手冊未讀 2", me["manual_unread"] == 2)
    amy("/api/manual/ack", {"id": ms[0]["id"]})
    s, ms2 = boss("/api/manual"); rd = {r["name"]: r["at"] for r in ms2[0]["readers"]}
    check("老闆看到阿美讀過第一篇", bool(rd.get("測試阿美")) and not rd.get("測試小貝"), rd)
    boss("/api/boss/manual/save", {"id": ms[0]["id"], "chapter": "1 認識我們的店", "title": "菜單", "body": "改過", "sort": 1, "reack": True})
    s, me = amy("/api/me"); check("改內容勾重讀 → 又變未讀", me["manual_unread"] == 2, me["manual_unread"])
    boss("/api/boss/manual/remove", {"id": ms[1]["id"]})
    s, ms = amy("/api/manual"); check("下架後夥伴看不到", len(ms) == 1)
    s, b = boss("/api/boss/today"); check("今日出勤帶日誌狀態", any(j["name"] == "測試阿美" for j in b.get("journal", [])))
finally:
    srv.terminate(); srv.wait()
    shutil.rmtree(tmp, ignore_errors=True)
print("全部通過" if not fails else "有 %d 項不對：%s" % (len(fails), fails))
sys.exit(1 if fails else 0)
