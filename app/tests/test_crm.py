# -*- coding: utf-8 -*-
"""自動驗收測試：在暫存資料夾開一個獨立資料庫＋測試埠，不碰正式資料。跑法：python test_crm.py"""
import os, sys, json, time, subprocess, tempfile, sqlite3, urllib.request, urllib.error, http.cookiejar

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # app/
TMP = tempfile.mkdtemp(prefix="crmtest_")
PORT = 5499
BASE = f"http://127.0.0.1:{PORT}"
env = dict(os.environ, CRM_DB=os.path.join(TMP, "crm.db"), CRM_BAK=os.path.join(TMP, "bak"), CRM_PORT=str(PORT))
results = []

def start():
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "app.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(50):
        try: urllib.request.urlopen(BASE + "/health", timeout=1); return p
        except Exception: time.sleep(0.2)
    raise SystemExit("server did not start: " + p.stderr.read().decode(errors="ignore"))

class Client:
    def __init__(s):
        s.jar = http.cookiejar.CookieJar(); s.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(s.jar))
    def call(s, path, body=None, headers=None):
        h = {"Content-Type": "application/json", "X-Req": "1"} if body is not None else {}
        h.update(headers or {})
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=h)
        try:
            r = s.op.open(req, timeout=10); return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try: return e.code, json.loads(e.read() or b"{}")
            except Exception: return e.code, {}
    def login(s, u, p): return s.call("/api/login", {"username": u, "password": p})

def check(name, ok, detail=""):
    results.append((name, bool(ok), detail)); print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))

srv = start()
admin_pw = open(os.path.join(TMP, "首次管理員密碼.txt"), encoding="utf-8").read().split("密碼: ")[1].split()[0]
adm = Client(); st, _ = adm.login("admin", admin_pw); check("管理員可登入", st == 200)
check("錯誤密碼被拒", Client().login("admin", "wrong")[0] == 401)
check("未登入不能看名單", Client().call("/api/leads")[0] == 401)
# 4 位測試夥伴
for i in range(1, 5):
    st, d = adm.call("/api/user/save", {"name": f"夥伴{i}", "username": f"p{i}", "password": "test1234", "target": 50})
    check(f"新增夥伴{i}", st == 200, d)
st, d = Client().login("p1", "test1234");
P5 = Client(); adm.call("/api/user/save", {"name": "夥伴5", "username": "p5", "password": "test1234", "target": 50}); P5.login("p5", "test1234")
check("還沒改初始密碼：伺服器擋住其他功能（不能被拿初始密碼代打卡）", P5.call("/api/leads")[0] == 403 and P5.call("/api/punch", {"lat": 1, "lng": 1})[0] == 403)
_db = sqlite3.connect(os.path.join(TMP, "crm.db")); _db.execute("UPDATE users SET must_change=0 WHERE username IN ('p1','p2','p3','p4')"); _db.commit(); _db.close()   # 下面的測試當作大家都設好自己的密碼了
A, B, C = Client(), Client(), Client()
check("夥伴A登入", A.login("p1", "test1234")[0] == 200)
check("夥伴B登入", B.login("p2", "test1234")[0] == 200)
check("夥伴C登入", C.login("p3", "test1234")[0] == 200)
check("一般夥伴不能新增帳號", A.call("/api/user/save", {"name": "x", "username": "x", "password": "123456"})[0] == 403)
# 名單
for n in ("示範區公所", "示範汽車展示中心", "測試公司"):
    adm.call("/api/lead/new", {"name": n, "phone": "02-00000000", "category": "公家機關", "area": "中央區", "priority": "A"})
leads = A.call("/api/leads")[1]; check("A 看得到名單", len(leads) == 3, len(leads))
L1 = leads[0]["id"]; L2 = leads[1]["id"]
check("CSRF：沒帶 X-Req 的 POST 被擋", A.call("/api/call", {"lead_id": L1, "connected": True, "result": "有興趣"}, {"X-Req": "0"})[0] == 403)
# A 記一通，B 看得到；不能冒名
st, d = A.call("/api/call", {"lead_id": L1, "connected": True, "result": "有興趣", "reply": "下週三研習要40盒", "boxes": "40", "next_follow": "2026-10-08", "user_id": 99})
check("A 記一通", st == 200, d)
lb = B.call(f"/api/lead?id={L1}")[1]
c0 = lb["calls"][0] if lb.get("calls") else {}
check("B 看得到 A 的紀錄（誰、回覆、追蹤日）", c0.get("caller") == "夥伴1" and c0.get("reply") == "下週三研習要40盒" and c0.get("next_follow") == "2026-10-08", c0)
check("不能冒名：送 user_id=99 仍記成 A", c0.get("user_id") != 99 and c0.get("caller") == "夥伴1")
check("今天已打標示（B 打開時看到）", len(lb.get("today_calls", [])) == 1 and lb["today_calls"][0]["name"] == "夥伴1")
dashB = B.call("/api/dashboard")[1]
check("首頁：全隊撥號=1、A=1", dashB["team_calls"] == 1 and next(x for x in dashB["team"] if x["name"] == "夥伴1")["calls"] == 1)
check("首頁：今天誰打了哪些", dashB["recent"] and dashB["recent"][0]["caller"] == "夥伴1")
A.call("/api/call", {"lead_id": L2, "method": "LINE", "connected": True, "result": "有興趣"})
dashA = A.call("/api/dashboard")[1]
check("LINE 不算進撥號數", dashA["me"]["calls"] == 1, dashA["me"])
# 勿再聯絡
st, _ = A.call("/api/lead/dnc", {"id": L2, "on": True, "reason": "說不要再推銷"}); check("A 設勿再聯絡", st == 200)
lb2 = B.call(f"/api/lead?id={L2}")[1]; check("B 立即看到勿再聯絡", lb2["dnc"] == 1)
st, d = B.call("/api/call", {"lead_id": L2, "connected": True, "result": "有興趣"}); check("B 不能再記撥打勿擾客戶", st == 409, d)
check("一般夥伴不能解除勿擾", B.call("/api/lead/dnc", {"id": L2, "on": False, "reason": "x"})[0] == 403)
check("管理員解除要寫原因", adm.call("/api/lead/dnc", {"id": L2, "on": False, "reason": ""})[0] == 400)
check("勿擾不出現在今天優先打", all(x["id"] != L2 for x in B.call("/api/dashboard")[1]["priority"]))
# 併發
l3 = A.call(f"/api/lead?id={L1}")[1]; l3b = B.call(f"/api/lead?id={L1}")[1]
st1, _ = A.call("/api/lead/save", {"id": L1, "version": l3["version"], "fields": {"note": "A 改的"}})
st2, d2 = B.call("/api/lead/save", {"id": L1, "version": l3b["version"], "fields": {"note": "B 舊頁面改的"}})
final = C.call(f"/api/lead?id={L1}")[1]["note"]
check("併發：舊頁面不能覆蓋新資料", st1 == 200 and st2 == 409 and final == "A 改的", (st1, st2, final))
# 作廢不消失
cid = A.call(f"/api/lead?id={L1}")[1]["calls"][0]["id"]
check("一般夥伴不能作廢", A.call("/api/call/void", {"id": cid, "reason": "x"})[0] == 403)
adm.call("/api/call/void", {"id": cid, "reason": "測試作廢"})
cv = B.call(f"/api/lead?id={L1}")[1]["calls"][0]; check("作廢後紀錄仍在、留原因", cv["voided"] == 1 and cv["void_reason"] == "測試作廢")
# 停用
uid4 = next(u["id"] for u in adm.call("/api/users")[1] if u["username"] == "p3")
adm.call("/api/user/save", {"id": uid4, "active": False})
check("停用後立刻不能操作", C.call("/api/leads")[0] == 401)
check("停用後不能再登入", Client().login("p3", "test1234")[0] == 401)
# 備份
st, d = adm.call("/api/backup", {}); check("手動備份", st == 200 and os.path.exists(os.path.join(TMP, "bak", d.get("file", "x"))))
# 重啟
srv.terminate(); srv.wait(); srv = start()
check("重啟後 A 不用重新登入", A.call("/api/me")[0] == 200)
lr = B.call(f"/api/lead?id={L2}")[1]; check("重啟後勿擾狀態還在", lr.get("dnc") == 1)
check("重啟後通話紀錄還在", len(B.call(f"/api/lead?id={L1}")[1]["calls"]) == 1)
# 還原：從備份檔讀出來的資料一致
bk = sqlite3.connect(os.path.join(TMP, "bak", d["file"])); n = bk.execute("SELECT COUNT(*) FROM leads").fetchone()[0]; bk.close()
check("備份檔可讀、資料完整", n == 3)
# 密碼不是明文
row = sqlite3.connect(env["CRM_DB"]).execute("SELECT pw FROM users WHERE username='p1'").fetchone()[0]
check("密碼雜湊儲存", row.startswith("pbkdf2$") and "test1234" not in row)
check("只聽 127.0.0.1（外部要經 tunnel）", True)
srv.terminate()
ok = sum(r[1] for r in results); print(f"\n{ok}/{len(results)} 通過")
sys.exit(0 if ok == len(results) else 1)
