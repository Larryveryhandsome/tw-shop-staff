# -*- coding: utf-8 -*-
"""行銷審核測試（老闆 10/19）：GPT 交貼文（文字＋圖）→ 收進 CRM、只有老闆能審、核准才能發、退回要寫意見、審核結果寫回給 GPT；
海巡結果收進來（網址不重複）、核准回覆、轉開發名單、略過；導覽列待審數字。
暫存資料庫＋暫存交接資料夾＋5487 埠，不碰正式資料。跑法：python test_mk.py"""
import http.cookiejar, json, os, secrets, shutil, subprocess, sys, tempfile, time, urllib.request
from datetime import date

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # app/
tmp = tempfile.mkdtemp()
CFGD = os.path.join(tmp, "config"); os.makedirs(CFGD)
_root = os.path.dirname(HERE)
shutil.copy(os.path.join(_root, "config", "labor_rules.toml"), CFGD)
_st = open(os.path.join(_root, "config", "store.example.toml"), encoding="utf-8").read().replace("area_core = []", 'area_core = ["中央區"]')
open(os.path.join(CFGD, "store.toml"), "w", encoding="utf-8").write(_st)
os.environ["SHOP_CONFIG_DIR"] = CFGD
DB = os.path.join(tmp, "crm.db"); MKD = os.path.join(tmp, "交接"); PTD = os.path.join(tmp, "patrol")
env = dict(os.environ, CRM_DB=DB, CRM_BAK=os.path.join(tmp, "bak"), CRM_PORT="5487", MK_DIR=MKD, PATROL_DIR=PTD)
sys.path.insert(0, HERE)
os.environ.update(CRM_DB=DB, CRM_BAK=os.path.join(tmp, "bak"), MK_DIR=MKD, PATROL_DIR=PTD)
import app  # noqa: E402

app.init_db()
c = app.db()
PW = {}
for un, name, role in (("boss5", "老闆五", "admin"), ("mgr5", "店長五", "manager"), ("amy5", "阿美五", "staff")):
    PW[un] = secrets.token_urlsafe(10)
    c.execute("INSERT INTO users(username,name,pw,role,created) VALUES(?,?,?,?,?)", (un, name, app.hash_pw(PW[un]), role, app.now()))
c.commit(); c.close()
T = date.today().isoformat()
# GPT 交的：兩篇（一篇有圖）＋一篇格式不對
d = os.path.join(MKD, "給CRM", T); os.makedirs(d)
open(os.path.join(d, "p1.jpg"), "wb").write(b"\xff\xd8\xff\xe0" + b"0" * 500)
json.dump({"date": T, "posts": [
    {"id": T + "-01", "channel": "threads", "title": "週三開門", "text": "從 10/21 起週三也有開！", "image": "p1.jpg", "suggest_time": "11:00", "notes": "接 LINE 群發"},
    {"id": T + "-02", "channel": "fb_group", "group": "在地大小事", "title": "團訂", "text": "公司開會要便當嗎？"},
    {"id": "", "text": "沒有 id"}]}, open(os.path.join(d, "posts.json"), "w", encoding="utf-8"), ensure_ascii=False)
pd = os.path.join(PTD, T.replace("-", "")); os.makedirs(pd)
json.dump({"items": [
    {"url": "https://www.threads.net/@a/post/1", "platform": "Threads", "title": "求推薦便當 30 個", "who": "某協會", "need": "研習午餐", "boxes": "30 盒",
     "event_date": "2026-11-02", "area": "中央區", "reply": "您好，我們是示範店…", "score": 5},
    {"url": "https://www.threads.net/@a/post/1", "title": "重複的網址"},
    {"url": "not-a-url", "title": "壞網址"},
    {"url": "https://example.org/event", "platform": "活動公告", "title": "路跑志工", "phone": "03-9000000", "score": 3}]},
    open(os.path.join(pd, "patrol.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(HERE, "app.py")], env=env, cwd=HERE)
time.sleep(1.8)
BASE = "http://127.0.0.1:5487"
fails = []


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
    boss, mgr, amy = client(), client(), client()
    for cl, un in ((boss, "boss5"), (mgr, "mgr5"), (amy, "amy5")):
        s, _ = cl("/api/login", {"username": un, "password": PW[un]}); assert s == 200, un
    s, r = boss("/api/mk/sweep", {})     # 伺服器一啟動排程就先收了，這裡收到的可能是 0
    c = app.db(); n1 = c.execute("SELECT COUNT(*) FROM mk_post").fetchone()[0]; n2 = c.execute("SELECT COUNT(*) FROM mk_patrol").fetchone()[0]; c.close()
    check("收 GPT 貼文 2 篇、海巡 2 則（重複、壞網址、沒 id 的不收）", s == 200 and (n1, n2) == (2, 2), (n1, n2))
    s, r = boss("/api/mk/sweep", {}); check("再收一次不會重複", r["posts"] == 0 and r["patrol"] == 0, r)
    s, ib = boss("/api/inbox"); check("通知老闆有東西要審", any("等你審核" in x["title"] for x in ib)); check("格式不對的有提醒", any("檔案有問題" in x["title"] for x in ib))
    s, me = boss("/api/me"); check("導覽列待審 4（貼文 2＋海巡 2）", me.get("mk_pending") == 4, me.get("mk_pending"))
    check("店長看不到行銷", mgr("/api/mk?tab=review")[0] == 403 and "mk_pending" not in mgr("/api/me")[1])
    check("夥伴不能審", amy("/api/mk/post/review", {"id": 1, "action": "approve"})[0] == 403)
    s, mk = boss("/api/mk?tab=review"); ps = {p["src_id"]: p for p in mk["posts"]}
    p1, p2 = ps[T + "-01"], ps[T + "-02"]
    check("貼文有圖、頻道、建議時間", p1["images"] and p1["channel"] == "threads" and p1["suggest_time"] == "11:00" and p2["grp"] == "在地大小事")
    s, img = boss("/api/mk/img?f=" + p1["images"][0]); check("老闆看得到圖", s == 200 and img[:2] == b"\xff\xd8")
    check("圖片路徑亂填擋掉", boss("/api/mk/img?f=..%5Ccrm.db")[0] in (400, 404))
    check("沒核准不能按發布", boss("/api/mk/post/posted", {"id": p1["id"]})[0] == 400)
    check("退回沒寫意見擋下", boss("/api/mk/post/review", {"id": p2["id"], "action": "reject"})[0] == 400)
    s, _ = boss("/api/mk/post/review", {"id": p2["id"], "action": "reject", "note": "太像廣告"}); check("退回寫意見", s == 200)
    s, _ = boss("/api/mk/post/review", {"id": p1["id"], "action": "approve", "body": "從 10/21 起，週三也有開！（老闆改）"}); check("老闆改字後核准", s == 200)
    fb = json.load(open(os.path.join(MKD, "CRM回饋", T + ".json"), encoding="utf-8"))
    f = {x["id"]: x for x in fb["posts"]}
    check("回饋給 GPT：退回意見、老闆改過的字", f[T + "-02"]["status"] == "退回" and f[T + "-02"]["note"] == "太像廣告" and "老闆改" in (f[T + "-01"]["final_text"] or ""), f)
    s, mk = boss("/api/mk?tab=publish"); check("核准的到待發布", [p["id"] for p in mk["posts"]] == [p1["id"]])
    s, _ = boss("/api/mk/post/posted", {"id": p1["id"], "url": "https://www.threads.net/@woo/post/9"}); check("我發了", s == 200)
    fb = json.load(open(os.path.join(MKD, "CRM回饋", T + ".json"), encoding="utf-8"))
    check("回饋寫發布網址", next(x for x in fb["posts"] if x["id"] == T + "-01")["posted_url"].endswith("/9"))
    s, mk = boss("/api/mk?tab=review"); check("今天發出 1 篇", mk["today"]["posted"] == 1 and mk["today"]["gpt"] == 2, mk["today"])
    # 海巡
    s, mk = boss("/api/mk?tab=patrol"); xs = {x["title"]: x for x in mk["patrol"]}
    a, b = xs["求推薦便當 30 個"], xs["路跑志工"]
    check("海巡依可能性排序、盒數轉數字", mk["patrol"][0]["id"] == a["id"] and a["boxes"] == 30)
    check("核准回覆不能是空的", boss("/api/mk/patrol/review", {"id": a["id"], "action": "reply", "reply": ""})[0] == 400)
    check("還沒核准不能按我回了", boss("/api/mk/patrol/review", {"id": a["id"], "action": "replied"})[0] == 400)
    s, _ = boss("/api/mk/patrol/review", {"id": a["id"], "action": "reply", "reply": "您好，示範店可以幫忙（老闆改）"}); check("核准回覆", s == 200)
    s, _ = boss("/api/mk/patrol/review", {"id": a["id"], "action": "replied"}); check("我回了", s == 200)
    s, _ = boss("/api/mk/patrol/review", {"id": b["id"], "action": "lead"}); check("轉開發名單", s == 200)
    c = app.db(); ld = c.execute("SELECT * FROM leads WHERE category='社群海巡'").fetchone(); c.close()
    check("開發名單有這筆：電話、代碼 S、網址寫在備註", ld and ld["phone"] == "03-9000000" and ld["code"].startswith("S") and "example.org" in ld["note"], dict(ld) if ld else None)
    check("轉過不能再轉", boss("/api/mk/patrol/review", {"id": b["id"], "action": "lead"})[0] == 400)
    s, me = boss("/api/me"); check("審完導覽列歸零", not me.get("mk_pending"), me.get("mk_pending"))
    s, mk = boss("/api/mk?tab=done"); check("紀錄頁有貼文和海巡", len(mk["posts"]) == 2 and len(mk["done_patrol"]) == 2)
    # 社團清單
    check("社團網址要 http", boss("/api/mk/group/save", {"name": "在地大小事", "url": "javascript:alert(1)"})[0] == 400)
    s, _ = boss("/api/mk/group/save", {"name": "在地大小事", "url": "https://www.facebook.com/groups/x", "rule": "週末才能發"}); s2, mk = boss("/api/mk?tab=setup")
    check("加社團", s == 200 and mk["groups"][0]["rule"] == "週末才能發")
    # GPT 改好再送（同一天檔案再改）：只收新的 id
    data = json.load(open(os.path.join(d, "posts.json"), encoding="utf-8"))
    data["posts"].append({"id": T + "-02b", "channel": "fb_group", "group": "在地大小事", "text": "改過的團訂文", "revision_of": T + "-02"})
    time.sleep(1.1); json.dump(data, open(os.path.join(d, "posts.json"), "w", encoding="utf-8"), ensure_ascii=False)
    s, r = boss("/api/mk/sweep", {}); check("GPT 改好再送：只收新的那篇", r["posts"] == 1, r)
    # GPT 排程／發布回報（老闆 10/19：發文由 GPT 那邊發）＋成效數字＋數據頁、週報
    s, mk = boss("/api/mk?tab=review"); q = {p["src_id"]: p for p in mk["posts"]}
    q3 = q[T + "-02b"]
    rd = os.path.join(MKD, "給CRM", "發布回報"); os.makedirs(rd, exist_ok=True)
    json.dump({"posts": [{"id": T + "-02b", "status": "已排程", "scheduled_at": T + " 11:30"}]}, open(os.path.join(rd, T + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    boss("/api/mk/sweep", {}); s, ib = boss("/api/inbox")
    check("沒核准就回報排程 → 不改狀態、通知老闆", any("還沒核准" in x["title"] for x in ib))
    c = app.db(); check("狀態還是待審", c.execute("SELECT status FROM mk_post WHERE id=?", (q3["id"],)).fetchone()[0] == "待審"); c.close()
    boss("/api/mk/post/review", {"id": q3["id"], "action": "approve"})
    time.sleep(1.1); json.dump({"posts": [{"id": T + "-02b", "status": "已排程", "scheduled_at": T + " 11:30"}]}, open(os.path.join(rd, T + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    boss("/api/mk/sweep", {}); s, mk = boss("/api/mk?tab=publish")
    x = next((p for p in mk["posts"] if p["id"] == q3["id"]), None)
    check("核准後回報排程 → 待發布顯示已排程", x and x["status"] == "已排程" and x["scheduled_at"] == T + " 11:30", x)
    time.sleep(1.1)
    json.dump({"posts": [{"id": T + "-02b", "status": "已發布", "posted_url": "https://www.facebook.com/groups/x/posts/1", "posted_at": T + " 11:31",
                          "metrics": {"at": T + " 23:00", "views": "1,234", "likes": 20, "replies": 3, "dms": 2}}]}, open(os.path.join(rd, T + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    boss("/api/mk/sweep", {})
    fb = json.load(open(os.path.join(MKD, "CRM回饋", T + ".json"), encoding="utf-8"))
    check("回報發布 → 回饋寫已發布和網址", next(y for y in fb["posts"] if y["id"] == T + "-02b")["status"] == "已發布")
    s, mk = boss("/api/mk?tab=data"); D = mk["data"]
    check("數據頁：發文 2 篇、觀看 1,234、私訊 2", len(D["posts"]) == 2 and D["total"]["views"] == 1234 and D["total"]["dms"] == 2, D["total"])
    check("數據頁：海巡轉名單有算到", sum(D["leads"].values()) == 1 and D["patrol"].get("轉名單") == 1, (D["leads"], D["patrol"]))
    check("數據頁：還沒回報數字的 1 篇", D["no_metric"] == 1, D["no_metric"])
    import marketing as MKM
    c = app.db(); txt = MKM.weekly_report(c, MKD); c.close()
    check("週報：寫給 GPT 的檔案、退回原因有進去", os.path.exists(os.path.join(MKD, "CRM回饋", "週報_%s.md" % T)) and "太像廣告" in txt, txt[:200])
    # GPT 登入後在社團裡海巡到的，也走同一個格式收進來
    gd = os.path.join(MKD, "給CRM", "海巡"); os.makedirs(gd, exist_ok=True)
    json.dump({"items": [{"url": "https://www.facebook.com/groups/x/posts/77", "platform": "臉書社團", "title": "社團有人問 20 個便當", "score": 4},
                         {"url": "https://www.threads.net/@a/post/1", "title": "跟 Claude 海巡重複"}]}, open(os.path.join(gd, T + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    s, r = boss("/api/mk/sweep", {}); check("GPT 海巡收 1 則（重複網址不收）", r["patrol"] == 1, r)
    # 行銷參數：重點區域（測試設定：中央區）以外不到 20 份、或不到 3 份 → 系統略過；大單排前面
    json.dump({"items": [{"url": "https://example.org/east", "title": "東區研習 50 人", "area": "東區", "boxes": 50, "score": 5},
                         {"url": "https://example.org/east2", "title": "東區小公司 10 個", "area": "東區", "boxes": 10, "score": 4},
                         {"url": "https://example.org/wujie", "title": "南區活動（人數不明）", "area": "南區鄉", "score": 3},
                         {"url": "https://example.org/two", "title": "只要 2 個", "area": "中央區", "boxes": 2, "score": 3},
                         {"url": "https://example.org/north", "title": "北區飯店研討會 80 份", "area": "北區", "boxes": 80, "score": 4},
                         {"url": "https://example.org/west", "title": "西區工地 12 個", "area": "西區", "boxes": 12, "score": 4},
                         {"url": "https://example.org/central5", "title": "中央區辦公室 5 個", "area": "中央區", "boxes": 5, "score": 4}]},
              open(os.path.join(pd, "patrol_c.json"), "w", encoding="utf-8"), ensure_ascii=False)
    boss("/api/mk/sweep", {}); s, mk = boss("/api/mk?tab=patrol"); ts = [x["title"] for x in mk["patrol"] if x["status"] == "待審"]
    check("其他地區 20 人以上照收；不到 20、人數不明、只要 2 個的自動略過",
          "東區研習 50 人" in ts and "東區小公司 10 個" not in ts and "南區活動（人數不明）" not in ts and "只要 2 個" not in ts and "北區飯店研討會 80 份" in ts, ts)
    check("中央區 3 個以上收、西區不到 20 略過", "中央區辦公室 5 個" in ts and "西區工地 12 個" not in ts, ts)
    check("大單排前面", ts.index("北區飯店研討會 80 份") < ts.index("中央區辦公室 5 個"), ts)
    s, mk = boss("/api/mk?tab=done"); r = next(x for x in mk["done_patrol"] if x["title"] == "東區小公司 10 個")
    check("紀錄看得到略過原因", "不到 20 份" in (r["review_note"] or ""), r.get("review_note"))
finally:
    srv.terminate(); srv.wait()
    shutil.rmtree(tmp, ignore_errors=True)
print("全部通過" if not fails else "有 %d 項不對：%s" % (len(fails), fails))
sys.exit(1 if fails else 0)
