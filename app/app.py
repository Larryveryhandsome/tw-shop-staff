# -*- coding: utf-8 -*-
"""門市員工系統：打卡算薪＋班表＋記帳＋外送＋團體訂單開發 CRM＋日誌＋教育訓練＋公告＋老闆頁
- 純 Python 標準庫（手機推播另需 cryptography）；SQLite 只由本程序開啟（不要把 data/ 分享出去給別人直接開）
- 只聽 127.0.0.1；要從外面連，請自行用反向代理或通道（例如 Cloudflare Tunnel）接進來
- 店家資料在 config/store.toml；計薪規則在 config/labor_rules.toml
- 啟動：python app.py            首次會建立管理員帳號（見 data/首次管理員密碼.txt）
"""
import traceback, base64, hashlib, hmac, http.server, json, os, re, secrets, socketserver, sqlite3, sys, threading, time, csv, io, shutil
from datetime import datetime, timedelta, date
from urllib.parse import urlsplit, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import payroll as P   # 打卡算薪核心（老闆頁、股東帳務頁共用）
import ops as O       # 權限、班表、記帳、外送、註冊、推播、提醒
import extras as X    # 新聞、待辦、個人檔案、導覽、崗位必讀、9 點關心
import safety as SA   # 食安紀錄：冰箱溫度、瓦斯、油品、廢油、廁所
import marketing as MK   # 行銷審核：AI 貼文、社群雷達，老闆核准才發
import push
import cfg
DB = os.environ.get("CRM_DB") or os.path.join(HERE, "data", "crm.db")
BAK = os.environ.get("CRM_BAK") or os.path.join(HERE, "backups")
PHOTOS = os.path.join(os.path.dirname(DB), "journal")   # 日誌照片（資料庫只存檔名）
STATIC = os.path.join(HERE, "static")                     # 前端程式、圖示、service worker
MIME = {".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".png": "image/png",
        ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml", ".json": "application/json"}
_reg_rate = {}
PORT = int(os.environ.get("CRM_PORT") or cfg.STORE.get("port", 8402))
SESSION_DAYS = 90
COOKIE = cfg.STORE.get("cookie_name", "shopstaff")
STATUSES = ["未聯絡", "未接", "有興趣", "已報價", "已成交", "暫無需求", "勿再聯絡"]
DAILY_TARGET_DEFAULT = int(cfg.SALES.get("daily_call_target", 50))

def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def csv_cell(v):
    """CSV 公式注入：名單是外面匯入、夥伴也能改的，=、+、-、@ 開頭的字串用 Excel 打開會被當公式執行（可外連洩漏資料）→ 前面加 ' 當文字"""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"): return "'" + v
    return v


def _h(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_index():
    """index.html 裡的 {{...}} 換成 config/store.toml 的店家資料"""
    B = cfg.public_brand()
    logo = '<img src="/static/%s" alt="">' % _h(B["logo"]) if B["logo"] else ""
    foot = "　".join(x for x in (_h(B["address"]), ("電話 " + _h(B["phone"])) if B["phone"] else "") if x)
    html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    for k, v in {"STORE_NAME": _h(B["name"]), "SHORT_NAME": _h(B["short_name"]), "LOGO": logo, "FOOTER": foot,
                 "STORE_JSON": json.dumps(B, ensure_ascii=False).replace("<", "\\u003c")}.items():
        html = html.replace("{{%s}}" % k, v)
    return html.encode("utf-8")


def manifest():
    B = cfg.public_brand()
    icon = "/static/" + B["logo"] if B["logo"] else "/static/icon.svg"
    typ = "image/svg+xml" if icon.endswith(".svg") else "image/png"
    return {"name": B["name"], "short_name": B["short_name"], "lang": "zh-Hant-TW", "start_url": "/", "scope": "/", "display": "standalone",
            "background_color": "#f5f5f7", "theme_color": "#f5f5f7", "icons": [{"src": icon, "sizes": "any", "type": typ}]}
def open_today_sql():
    i = date.today().weekday() + 1   # SQLite substr 從 1 起；週一=1
    return f"(open_days IS NULL OR length(open_days)<7 OR substr(open_days,{i},1)<>'0')"
def today(): return date.today().isoformat()

# ---------------- DB ----------------
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  pw TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'staff', active INTEGER NOT NULL DEFAULT 1, target INTEGER NOT NULL DEFAULT 50, created TEXT);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY, code TEXT, name TEXT NOT NULL, category TEXT, area TEXT,
  phone TEXT, phone2 TEXT, address TEXT, contact_hint TEXT, angle TEXT, priority TEXT DEFAULT 'C',
  data_status TEXT DEFAULT '待核', opp_type TEXT, boxes INTEGER, weekly_days INTEGER, event_date TEXT,
  note TEXT, status TEXT NOT NULL DEFAULT '未聯絡', dnc INTEGER NOT NULL DEFAULT 0, assigned_to INTEGER,
  next_follow TEXT, last_call_at TEXT, last_caller INTEGER, version INTEGER NOT NULL DEFAULT 1, updated TEXT);
CREATE INDEX IF NOT EXISTS ix_leads_status ON leads(status);
CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY, lead_id INTEGER NOT NULL, user_id INTEGER NOT NULL, at TEXT NOT NULL,
  method TEXT NOT NULL DEFAULT '電話', connected INTEGER NOT NULL, result TEXT NOT NULL, reply TEXT, boxes INTEGER,
  next_follow TEXT, note TEXT, voided INTEGER NOT NULL DEFAULT 0, void_by INTEGER, void_at TEXT, void_reason TEXT);
CREATE INDEX IF NOT EXISTS ix_calls_lead ON calls(lead_id);
CREATE INDEX IF NOT EXISTS ix_calls_at ON calls(at);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT, user_id INTEGER, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS notices(id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, pinned INTEGER NOT NULL DEFAULT 0,
  need_ack INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1, created TEXT, created_by INTEGER, updated TEXT);
CREATE TABLE IF NOT EXISTS notice_ack(notice_id INTEGER NOT NULL, user_id INTEGER NOT NULL, at TEXT, PRIMARY KEY(notice_id, user_id));
-- 我很棒日誌：每位夥伴一條對話串（thread = 夥伴的 user_id），夥伴寫、老闆回
CREATE TABLE IF NOT EXISTS journal(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, author_id INTEGER NOT NULL, day TEXT NOT NULL,
  body TEXT, photo TEXT, created TEXT NOT NULL, removed INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_journal_user ON journal(user_id, id);
CREATE TABLE IF NOT EXISTS journal_seen(viewer_id INTEGER NOT NULL, thread_id INTEGER NOT NULL, last_id INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(viewer_id, thread_id));
-- 教育訓練手冊：一篇一筆，依 chapter 分章、sort 排序
CREATE TABLE IF NOT EXISTS manual(id INTEGER PRIMARY KEY, chapter TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
  sort INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, updated TEXT, updated_by INTEGER);
CREATE TABLE IF NOT EXISTS manual_ack(manual_id INTEGER NOT NULL, user_id INTEGER NOT NULL, at TEXT, PRIMARY KEY(manual_id, user_id));
"""
_lock = threading.Lock()
_fails = {}   # username -> [失敗次數, 鎖到何時(epoch)]；連錯 8 次鎖 15 分鐘
_fails_lock = threading.Lock()
MAX_FAIL, LOCK_SEC = 8, 900


def _login_reserve(un):
    """登入前先佔一次「失敗」名額（密碼對了再清掉）。同時送幾十個猜密碼請求也只會有 8 個真的被驗證，其他直接鎖。
    回傳 False＝這個帳號現在鎖住"""
    with _fails_lock:
        f = _fails.setdefault(un, [0, 0])
        t = time.time()
        if f[1] > t: return False
        if f[1]: f[:] = [0, 0]                     # 鎖過期了，重新算
        if f[0] >= MAX_FAIL:
            f[:] = [0, t + LOCK_SEC]; return False
        f[0] += 1
        return True


def _login_failed(un):
    with _fails_lock:
        f = _fails.get(un)
        if f and f[0] >= MAX_FAIL: f[:] = [0, time.time() + LOCK_SEC]


def _login_ok(un):
    with _fails_lock:
        _fails.pop(un, None)


def db():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"pbkdf2${salt}${h}"

def check_pw(pw, stored):
    try:
        _, salt, h = stored.split("$")
        return hmac.compare_digest(hash_pw(pw, salt).split("$")[2], h)
    except Exception:
        return False

def audit(c, uid, action, detail=""):
    c.execute("INSERT INTO audit(at,user_id,action,detail) VALUES(?,?,?,?)", (now(), uid, action, detail))

def init_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True); os.makedirs(BAK, exist_ok=True)
    c = db(); c.executescript(SCHEMA); c.executescript(P.SCHEMA); P.migrate(c); O.migrate(c); X.migrate(c); SA.migrate(c); MK.migrate(c); O.ensure_demo(c, hash_pw)
    cols = {r[1] for r in c.execute("PRAGMA table_info(leads)")}
    for col in ("open_days", "hours", "hours_src"):   # open_days：7 碼，週一→週日，1=有營業 0=休 ?=不明
        if col not in cols: c.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT")
    if "must_change" not in {r[1] for r in c.execute("PRAGMA table_info(users)")}:   # 1=下次登入要先設自己的密碼
        c.execute("ALTER TABLE users ADD COLUMN must_change INTEGER NOT NULL DEFAULT 0")
    if not c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        pw = secrets.token_urlsafe(8)
        c.execute("INSERT INTO users(username,name,pw,role,created) VALUES(?,?,?,?,?)", ("admin", os.environ.get("SHOP_ADMIN_NAME") or "老闆", hash_pw(pw), "admin", now()))
        with open(os.path.join(os.path.dirname(DB), "首次管理員密碼.txt"), "w", encoding="utf-8") as f:
            f.write(f"帳號: admin\n密碼: {pw}\n登入後請到「管理」改密碼，然後刪掉這個檔案。\n")
    c.commit(); c.close()

def backup(tag="auto"):
    os.makedirs(BAK, exist_ok=True)
    dst = os.path.join(BAK, f"crm_{datetime.now():%Y%m%d_%H%M%S}_{tag}.db")
    src = sqlite3.connect(DB); out = sqlite3.connect(dst)
    with out: src.backup(out)
    src.close(); out.close()
    files = sorted(f for f in os.listdir(BAK) if f.endswith("_auto.db"))
    for f in files[:-60]: os.remove(os.path.join(BAK, f))   # 自動備份保留最近 60 份
    return dst

def backup_loop():
    while True:
        try: backup("auto")
        except Exception: pass
        time.sleep(12 * 3600)

# ---------------- helpers ----------------
def lead_dict(r, c=None):
    d = dict(r)
    if c is not None:
        t = c.execute("""SELECT u.name, cl.at, cl.result, cl.reply FROM calls cl JOIN users u ON u.id=cl.user_id
                         WHERE cl.lead_id=? AND cl.voided=0 AND substr(cl.at,1,10)=? ORDER BY cl.at DESC""", (d["id"], today())).fetchall()
        d["today_calls"] = [dict(x) for x in t]
        if d.get("last_caller"):
            u = c.execute("SELECT name FROM users WHERE id=?", (d["last_caller"],)).fetchone()
            d["last_caller_name"] = u["name"] if u else ""
        if d.get("assigned_to"):
            u = c.execute("SELECT name FROM users WHERE id=?", (d["assigned_to"],)).fetchone()
            d["assigned_name"] = u["name"] if u else ""
    return d

LEAD_EDITABLE = ["name", "category", "area", "phone", "phone2", "address", "contact_hint", "angle", "priority",
                 "data_status", "opp_type", "boxes", "weekly_days", "event_date", "note", "next_follow", "open_days", "hours", "hours_src"]

# ---------------- HTTP ----------------
class H(O.Ops, X.Extras, SA.Safety, MK.Marketing, http.server.BaseHTTPRequestHandler):
    PHOTO_DIR = os.path.dirname(DB)
    server_version = "shopstaff"
    def log_message(self, *a): pass

    # --- io
    def send_json(self, obj, code=200, cookie=None):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if cookie: self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def err(self, msg, code=400): self.send_json({"error": msg}, code)

    def send_file(self, fp, cache="private, max-age=86400"):
        if not fp or not os.path.isfile(fp): return self.err("找不到", 404)
        b = open(fp, "rb").read()
        ext = os.path.splitext(fp)[1].lower()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext) or ("image/jpeg" if ext in (".jpg", ".jpeg") else "application/octet-stream"))
        self.send_header("Cache-Control", cache); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 2_000_000: raise ValueError("too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def user(self, c):
        raw = self.headers.get("Cookie", "")
        tok = None
        for part in raw.split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE: tok = v
        if not tok: return None
        r = c.execute("""SELECT u.*, s.acting_as FROM sessions s JOIN users u ON u.id=s.user_id
                         WHERE s.token=? AND s.expires>? AND u.active=1""", (tok, now())).fetchone()
        if not r: return None
        real = {"real_id": r["id"], "real_role": r["role"], "real_name": r["name"], "token": tok, "acting": None}
        if r["role"] == "admin" and r["acting_as"]:
            a = c.execute("SELECT * FROM users WHERE id=? AND COALESCE(demo,0)=1 AND active=1", (r["acting_as"],)).fetchone()
            if a: return {**dict(a), **real, "acting": a["role"]}
        return {**dict(r), **real}

    def cookie(self, tok, days=SESSION_DAYS):
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" or self.headers.get("Cf-Visitor") else ""
        return f"{COOKIE}={tok}; HttpOnly; Path=/; Max-Age={days*86400}; SameSite=Lax{secure}"

    # --- routes
    def _crash(self, e):
        try:
            with open(os.path.join(os.path.dirname(DB), "errors.log"), "a", encoding="utf-8") as f:
                f.write("%s %s %s\n%s\n" % (now(), self.command, self.path, traceback.format_exc()))
        except Exception: pass
        try: self.err("系統出錯了，請稍後再試；一直這樣請跟老闆說（%s）" % type(e).__name__, 500)
        except Exception: pass

    def do_GET(self):
        try: return self._get()
        except Exception as e: return self._crash(e)

    def do_POST(self):
        try: return self._post()
        except Exception as e: return self._crash(e)

    def _get(self):
        u = urlsplit(self.path); p = u.path
        if p in ("/", "/index.html"):
            b = render_index()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(b)))
            self.send_header("X-Frame-Options", "DENY"); self.end_headers(); self.wfile.write(b); return
        if p == "/health": return self.send_json({"ok": True, "at": now()})
        if p == "/manifest.webmanifest":
            b = json.dumps(manifest(), ensure_ascii=False).encode()
            self.send_response(200); self.send_header("Content-Type", MIME[".webmanifest"]); self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if p == "/sw.js":
            return self.send_file(os.path.join(STATIC, p[1:]), "no-cache")
        if p.startswith("/static/") and re.fullmatch(r"/static/[A-Za-z0-9_.-]+", p):
            return self.send_file(os.path.join(STATIC, p[8:]), "no-cache")
        if p == "/boss/slips":
            c = db()
            try:
                me = self.user(c)
                if not me or me["role"] != "admin": return self.err("只有老闆可以看", 403)
                month = (parse_qs(u.query).get("month") or [today()[:7]])[0]
                if not re.fullmatch(r"\d{4}-\d{2}", month): return self.err("月份格式不對")
                b = P.slips_html(P.month_rows(c, month), month).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(b)))
                self.end_headers(); self.wfile.write(b); return
            finally:
                c.close()
        if not p.startswith("/api/"): return self.err("not found", 404)
        c = db()
        try:
            me = self.user(c)
            if not me: return self.err("請先登入", 401)
            if me["must_change"] and p != "/api/me": return self.err("請先設定你自己的密碼", 403)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if p == "/api/me": return self.send_json(self.me_payload(c, me))
            if p == "/api/dashboard": return self.send_json(self.dashboard(c, me))
            if p == "/api/leads": return self.send_json(self.leads(c, me, q))
            if p == "/api/lead":
                r = c.execute("SELECT * FROM leads WHERE id=?", (int(q["id"]),)).fetchone()
                if not r: return self.err("找不到", 404)
                d = lead_dict(r, c)
                d["calls"] = [dict(x) for x in c.execute("""SELECT cl.*, u.name AS caller FROM calls cl JOIN users u ON u.id=cl.user_id
                              WHERE cl.lead_id=? ORDER BY cl.at DESC""", (d["id"],))]
                return self.send_json(d)
            if p == "/api/punch/state": return self.send_json(self.punch_state(c, me))
            if p == "/api/notices": return self.send_json(self.notices(c, me))
            if p == "/api/journal": return self.journal_get(c, me, q)
            if p == "/api/journal/threads":
                if me["role"] != "admin": return self.err("只有老闆可以看", 403)
                return self.send_json(self.journal_threads(c, me))
            if p == "/api/journal/photo": return self.journal_photo(c, me, q)
            if p == "/api/manual": return self.send_json(self.manual(c, me))
            r = self.ops_get(c, me, p, q)
            if r is not O.NOPE: return r
            r = self.extra_get(c, me, p, q)
            if r is not O.NOPE: return r
            r = self.safety_get(c, me, p, q)
            if r is not O.NOPE: return r
            r = self.mk_get(c, me, p, q)
            if r is not O.NOPE: return r
            if p.startswith("/api/boss/"):
                if me["role"] != "admin": return self.err("只有老闆可以看", 403)
                return self.boss_get(c, me, p, q)
            if p == "/api/users":
                return self.send_json([{k: x[k] for k in ("id", "username", "name", "role", "active", "target", "rider", "demo", "position", "title")}
                                       for x in c.execute("SELECT * FROM users WHERE pending=0 AND COALESCE(removed,0)=0 AND COALESCE(demo,0)=0 AND username NOT LIKE '%#退回%' ORDER BY active DESC, id")])
            if p == "/api/export" and me["role"] == "admin":
                kind = q.get("kind", "leads")
                rows = c.execute("SELECT * FROM leads ORDER BY id" if kind == "leads" else
                                 "SELECT cl.*, u.name caller, l.name lead FROM calls cl JOIN users u ON u.id=cl.user_id JOIN leads l ON l.id=cl.lead_id ORDER BY cl.at").fetchall()
                buf = io.StringIO(); w = csv.writer(buf)
                if rows: w.writerow(rows[0].keys())
                for r in rows: w.writerow([csv_cell(v) for v in r])
                b = ("﻿" + buf.getvalue()).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f"attachment; filename=crm_{kind}_{today()}.csv")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
            return self.err("not found", 404)
        finally:
            c.close()

    def _post(self):
        p = urlsplit(self.path).path
        # CSRF：只接受自家頁面發出的 JSON 請求
        if self.headers.get("X-Req") != "1" or "application/json" not in (self.headers.get("Content-Type") or ""):
            return self.err("bad request", 403)
        try: data = self.body()
        except Exception: return self.err("bad json")
        if p in ("/api/login", "/api/register"):
            c = db()
            try:
                if p == "/api/login": return self.login(c, data)
                e, uid = O.register(c, data, self.headers.get("Cf-Connecting-Ip") or self.client_address[0], _reg_rate)
                return self.err(e) if e else self.send_json({"ok": True})
            finally:
                c.close()
        with _lock:
            c = db()
            try:
                me = self.user(c)
                if not me: return self.err("請先登入", 401)
                if me["must_change"] and p not in ("/api/password", "/api/logout"): return self.err("請先設定你自己的密碼", 403)
                if p == "/api/switch":
                    if me["real_role"] != "admin": return self.err("只有老闆可以切換角色", 403)
                    to = data.get("to")
                    if to not in ("admin", "manager", "staff"): return self.err("沒有這個角色")
                    aid = None
                    if to != "admin":
                        r = c.execute("SELECT id FROM users WHERE username=? AND COALESCE(demo,0)=1", (O.DEMO[to][0],)).fetchone()
                        if not r: return self.err("找不到模擬身分，請重開系統")
                        aid = r["id"]
                    c.execute("UPDATE sessions SET acting_as=? WHERE token=?", (aid, me["token"])); c.commit()
                    return self.send_json({"ok": True})
                if me["acting"] and p not in O.DEMO_OK: return self.err(O.DEMO_MSG, 403)
                if p == "/api/logout":
                    c.execute("DELETE FROM sessions WHERE user_id=? AND expires>?", (me["real_id"], now())) if data.get("all") else \
                        c.execute("DELETE FROM sessions WHERE token=?", (me["token"],))
                    c.commit(); return self.send_json({"ok": True}, cookie=f"{COOKIE}=; Path=/; Max-Age=0")
                if p == "/api/call": return self.add_call(c, me, data)
                if p == "/api/lead/save": return self.save_lead(c, me, data)
                if p == "/api/lead/dnc": return self.set_dnc(c, me, data)
                if p == "/api/punch": return self.do_punch(c, me, data)
                if p == "/api/punch/fix": return self.punch_fix(c, me, data)
                if p == "/api/notice/ack":
                    c.execute("INSERT OR IGNORE INTO notice_ack(notice_id,user_id,at) VALUES(?,?,?)", (int(data["id"]), me["id"], now()))
                    c.commit(); return self.send_json({"ok": True})
                if p == "/api/password":
                    first = bool(data.get("first")) and me["must_change"]   # 首次登入設密碼：剛用卡片密碼登入，不用再打舊密碼
                    if not first and not check_pw(data.get("old", ""), me["pw"]): return self.err("舊密碼不對")
                    new = data.get("new", "")
                    if len(new) < 6: return self.err("新密碼至少 6 碼")
                    if new.lower() == me["username"].lower(): return self.err("密碼不能跟帳號一樣")
                    if check_pw(new, me["pw"]): return self.err("跟原本的密碼一樣，請換一個你自己記得的")
                    c.execute("UPDATE users SET pw=?, must_change=0 WHERE id=?", (hash_pw(new), me["id"])); c.commit()
                    return self.send_json({"ok": True})
                if p == "/api/journal/post": return self.journal_post(c, me, data)
                if p == "/api/journal/remove": return self.journal_remove(c, me, data)
                if p == "/api/manual/ack":
                    c.execute("INSERT OR IGNORE INTO manual_ack(manual_id,user_id,at) VALUES(?,?,?)", (int(data["id"]), me["id"], now()))
                    c.commit(); return self.send_json({"ok": True})
                r = self.ops_post(c, me, p, data)
                if r is not O.NOPE: return r
                r = self.extra_post(c, me, p, data)
                if r is not O.NOPE: return r
                r = self.safety_post(c, me, p, data)
                if r is not O.NOPE: return r
                r = self.mk_post(c, me, p, data)
                if r is not O.NOPE: return r
                if me["role"] != "admin": return self.err("只有管理員可以做這件事", 403)
                if p == "/api/user/save": return self.save_user(c, me, data)
                if p == "/api/assign": return self.assign(c, me, data)
                if p == "/api/call/void":
                    c.execute("UPDATE calls SET voided=1, void_by=?, void_at=?, void_reason=? WHERE id=?",
                              (me["id"], now(), data.get("reason", ""), int(data["id"])))
                    audit(c, me["id"], "作廢通話", f"call {data['id']}：{data.get('reason','')}"); c.commit()
                    return self.send_json({"ok": True})
                if p == "/api/lead/new":
                    if not (data.get("name") or "").strip(): return self.err("名稱必填")
                    cols = [k for k in LEAD_EDITABLE if k in data]
                    c.execute(f"INSERT INTO leads({','.join(cols)},updated) VALUES({','.join('?'*len(cols))},?)",
                              [data[k] for k in cols] + [now()])
                    audit(c, me["id"], "新增名單", data["name"]); c.commit(); return self.send_json({"ok": True})
                if p == "/api/backup": return self.send_json({"ok": True, "file": os.path.basename(backup("manual"))})
                if p.startswith("/api/boss/"): return self.boss_post(c, me, p, data)
                return self.err("not found", 404)
            finally:
                c.close()

    # --- actions
    def login(self, c, d):
        un = (d.get("username") or "").strip().lower()
        if not _login_reserve(un): return self.err("這個帳號錯太多次，請 15 分鐘後再試，或請店長重設密碼。", 429)
        r = c.execute("SELECT * FROM users WHERE lower(username)=? AND active=1 AND COALESCE(demo,0)=0", (un,)).fetchone()
        time.sleep(0.3)
        if not r:
            pend = c.execute("SELECT * FROM users WHERE lower(username)=? AND pending=1", (un,)).fetchone()
            if pend and check_pw(d.get("password", ""), pend["pw"]): _login_ok(un); return self.err("你的帳號還在等老闆審核，核准後就能登入。", 403)
        if not r or not check_pw(d.get("password", ""), r["pw"]):
            _login_failed(un)
            return self.err("帳號或密碼不對", 401)
        _login_ok(un)
        tok = secrets.token_urlsafe(32)
        c.execute("DELETE FROM sessions WHERE expires<?", (now(),))
        c.execute("INSERT INTO sessions(token,user_id,expires) VALUES(?,?,?)", (tok, r["id"], (datetime.now() + timedelta(days=SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")))
        c.commit()
        return self.send_json({"ok": True}, cookie=self.cookie(tok))

    def me_payload(self, c, me):
        prof = c.execute("SELECT kind, punch FROM pay_profile WHERE user_id=?", (me["id"],)).fetchone()
        return {"id": me["id"], "name": me["name"], "username": me["username"], "role": me["role"], "target": me["target"],
                "has_profile": bool(prof), "punch": bool(prof["punch"]) if prof else me["role"] == "staff", "must_change": bool(me["must_change"]),
                "journal_unread": self.journal_unread(c, me), "manual_unread": self.manual_unread(c, me), **self.ops_me(c, me), **self.extra_me(c, me), **self.mk_me(c, me),
                "statuses": STATUSES, "acting": me.get("acting"), "can_switch": me.get("real_role") == "admin", "real_name": me.get("real_name"),
                "users": [dict(x) for x in c.execute("SELECT id,name FROM users WHERE active=1 AND COALESCE(demo,0)=0 ORDER BY id")],
                "categories": [x[0] for x in c.execute("SELECT DISTINCT category FROM leads WHERE category<>'' ORDER BY 1")],
                "areas": [x[0] for x in c.execute("SELECT DISTINCT area FROM leads WHERE area<>'' ORDER BY 1")]}

    def dashboard(self, c, me):
        t = today()
        per = [dict(x) for x in c.execute("""SELECT u.id, u.name, u.target,
                 SUM(CASE WHEN cl.method='電話' THEN 1 ELSE 0 END) calls,
                 SUM(CASE WHEN cl.method='電話' AND cl.connected=1 THEN 1 ELSE 0 END) connected,
                 SUM(CASE WHEN cl.result IN ('有興趣','已報價','已成交') THEN 1 ELSE 0 END) hot,
                 SUM(CASE WHEN cl.result='已成交' THEN COALESCE(cl.boxes,0) ELSE 0 END) won_boxes
               FROM users u LEFT JOIN calls cl ON cl.user_id=u.id AND cl.voided=0 AND substr(cl.at,1,10)=?
               WHERE u.active=1 AND COALESCE(u.demo,0)=0 GROUP BY u.id ORDER BY calls DESC, u.id""", (t,))]
        for x in per:
            for k in ("calls", "connected", "hot", "won_boxes"): x[k] = x[k] or 0
        mine = next((x for x in per if x["id"] == me["id"]), {"calls": 0, "connected": 0, "hot": 0, "won_boxes": 0})
        recent = [dict(x) for x in c.execute("""SELECT cl.at, cl.result, cl.reply, cl.connected, cl.method, u.name caller, l.name lead, l.id lead_id
               FROM calls cl JOIN users u ON u.id=cl.user_id JOIN leads l ON l.id=cl.lead_id
               WHERE cl.voided=0 AND substr(cl.at,1,10)=? ORDER BY cl.at DESC LIMIT 200""", (t,))]
        # 今天優先打：1 今天/逾期追蹤 2 有興趣/已報價未追 3 指派給我的 A 級未聯絡 4 其他 A 級未聯絡
        base = "SELECT * FROM leads WHERE dnc=0 AND " + open_today_sql() + " AND (last_call_at IS NULL OR substr(last_call_at,1,10)<>?)"
        pri = []
        seen = set()
        def add(sql, args, why, lim):
            for r in c.execute(sql + f" LIMIT {lim}", args):
                if r["id"] in seen: continue
                seen.add(r["id"]); d = lead_dict(r, c); d["why"] = why; pri.append(d)
        add(base + " AND next_follow IS NOT NULL AND next_follow<=? AND status NOT IN ('已成交','暫無需求') ORDER BY next_follow", (t, t), "到期追蹤", 30)
        add(base + " AND status IN ('有興趣','已報價') ORDER BY COALESCE(next_follow,'9999')", (t,), "商機進行中", 20)
        add(base + " AND status='未聯絡' AND assigned_to=? ORDER BY priority, id", (t, me["id"]), "分給我的新名單", 30)
        add(base + " AND status='未聯絡' AND COALESCE(priority,'')<>'D' AND code LIKE ? AND (assigned_to IS NULL OR assigned_to=?) ORDER BY priority, code",
            (t, "D" + t.replace("-", "") + "%", me["id"]), "今天 AI 新開發", 40)
        add(base + " AND status IN ('未聯絡','未接') AND COALESCE(priority,'')<>'D' AND (assigned_to IS NULL OR assigned_to=?) ORDER BY priority, status DESC, id", (t, me["id"]), "高潛力未聯絡", 40)
        # 老闆 10/5：撥打一律 A 級優先；同一級裡，到期追蹤 → 商機 → 分給我 → 今天 AI → 其他
        _pr = {"A": 0, "B": 1, "C": 2}; _wr = {"到期追蹤": 0, "商機進行中": 1, "分給我的新名單": 2, "今天 AI 新開發": 3, "高潛力未聯絡": 4}
        pri.sort(key=lambda x: (_pr.get(x.get("priority") or "", 3), _wr.get(x["why"], 5)))
        stats = dict(c.execute("""SELECT COUNT(*) total, SUM(dnc) dnc,
                 SUM(CASE WHEN status='未聯絡' THEN 1 ELSE 0 END) untouched,
                 SUM(CASE WHEN status IN ('有興趣','已報價') THEN 1 ELSE 0 END) hot,
                 SUM(CASE WHEN status='已成交' THEN 1 ELSE 0 END) won FROM leads""").fetchone())
        ai_day = t
        ai = O.ai_leads(c, t)
        if not ai:
            last = c.execute("SELECT MAX(code) FROM leads WHERE code LIKE 'D2%'").fetchone()[0]
            if last: ai_day = "%s-%s-%s" % (last[1:5], last[5:7], last[7:9]); ai = O.ai_leads(c, ai_day)
        return {"date": t, "me": mine, "target": me["target"], "team": per,
                "duty": {"today": O.on_duty(c, t), "tomorrow": O.on_duty(c, O.add_days(t, 1))},
                "ai": {"day": ai_day, "rows": [lead_dict(r, c) for r in ai]},
                "team_calls": sum(x["calls"] for x in per), "recent": recent,
                "leads_today": len({x["lead_id"] for x in recent}), "priority": pri[:60], "stats": stats}

    def leads(self, c, me, q):
        t = today(); w = ["1=1"]; a = []
        if q.get("q"):
            s = "%" + q["q"].strip() + "%"
            digits = "".join(ch for ch in q["q"] if ch.isdigit())
            w.append("(name LIKE ? OR address LIKE ? OR note LIKE ? OR REPLACE(REPLACE(phone,'-',''),' ','') LIKE ? OR REPLACE(REPLACE(phone2,'-',''),' ','') LIKE ?)")
            a += [s, s, s, f"%{digits or q['q']}%", f"%{digits or q['q']}%"]
        for k in ("category", "area", "status", "priority"):
            if q.get(k): w.append(f"{k}=?"); a.append(q[k])
        f = q.get("f", "")
        if f == "core": w.append("priority='A'")
        elif f == "mine": w.append("assigned_to=?"); a.append(me["id"])
        elif f == "today_done": w.append("substr(last_call_at,1,10)=?"); a.append(t)
        elif f == "today_not": w.append("dnc=0 AND (last_call_at IS NULL OR substr(last_call_at,1,10)<>?)"); a.append(t)
        elif f == "i_called": w.append("id IN (SELECT lead_id FROM calls WHERE user_id=? AND voided=0)"); a.append(me["id"])
        elif f == "team_called": w.append("last_call_at IS NOT NULL")
        elif f == "follow": w.append("next_follow IS NOT NULL AND dnc=0 AND status NOT IN ('已成交','暫無需求')")
        elif f == "follow_due": w.append("next_follow<=? AND dnc=0 AND status NOT IN ('已成交','暫無需求')"); a.append(t)
        elif f == "hot": w.append("status IN ('有興趣','已報價')")
        elif f == "event": w.append("event_date IS NOT NULL AND event_date>=?"); a.append(t)
        elif f == "fixed": w.append("opp_type='固定午餐'")
        elif f == "won": w.append("status='已成交'")
        elif f == "dnc": w.append("dnc=1")
        elif f == "open_today": w.append("dnc=0 AND " + open_today_sql())
        elif f == "hours_unknown": w.append("(open_days IS NULL OR open_days='' OR open_days LIKE '%?%')")
        elif f == "ai_today": w.append("code LIKE ?"); a.append("D" + t.replace("-", "") + "%")
        elif f == "ai_all": w.append("code LIKE 'D2%'")
        rows = c.execute(f"SELECT * FROM leads WHERE {' AND '.join(w)} ORDER BY dnc, priority, CASE status WHEN '有興趣' THEN 0 WHEN '已報價' THEN 0 ELSE 1 END, id LIMIT 500", a).fetchall()
        return [lead_dict(r, c) for r in rows]

    def add_call(self, c, me, d):
        lead = c.execute("SELECT * FROM leads WHERE id=?", (int(d["lead_id"]),)).fetchone()
        if not lead: return self.err("找不到這筆名單", 404)
        if lead["dnc"]: return self.err("這筆已標記「勿再聯絡」，不能再記撥打。", 409)
        connected = 1 if d.get("connected") else 0
        result = d.get("result") or ("未接" if not connected else "")
        if result not in STATUSES or result == "未聯絡": return self.err("請選結果")
        if not connected: result = "未接"
        method = d.get("method") if d.get("method") in ("電話", "LINE", "Email", "拜訪") else "電話"
        boxes = int(d["boxes"]) if str(d.get("boxes") or "").isdigit() else None
        nf = (d.get("next_follow") or "") or None
        c.execute("""INSERT INTO calls(lead_id,user_id,at,method,connected,result,reply,boxes,next_follow,note)
                     VALUES(?,?,?,?,?,?,?,?,?,?)""", (lead["id"], me["id"], now(), method, connected, result,
                     (d.get("reply") or "").strip(), boxes, nf, (d.get("note") or "").strip()))
        # 客戶狀態跟著最新結果走；「未接」不把已有進展的客戶打回去
        new_status = lead["status"] if (result == "未接" and lead["status"] not in ("未聯絡",)) else result
        dnc = 1 if result == "勿再聯絡" else 0
        c.execute("""UPDATE leads SET status=?, dnc=MAX(dnc,?), last_call_at=?, last_caller=?, next_follow=COALESCE(?, next_follow),
                     boxes=COALESCE(?, boxes), version=version+1, updated=? WHERE id=?""",
                  (new_status, dnc, now(), me["id"], nf, boxes, now(), lead["id"]))
        if dnc: audit(c, me["id"], "設為勿再聯絡", f"{lead['name']}（通話紀錄）")
        c.commit(); return self.send_json({"ok": True})

    def save_lead(self, c, me, d):
        lead = c.execute("SELECT * FROM leads WHERE id=?", (int(d["id"]),)).fetchone()
        if not lead: return self.err("找不到", 404)
        if int(d.get("version", -1)) != lead["version"]:
            return self.err("這筆剛被別人改過，請重新打開再改（你的修改沒有存）。", 409)
        f = d.get("fields", {})
        cols = [k for k in LEAD_EDITABLE if k in f]
        if not cols: return self.send_json({"ok": True})
        vals = [(f[k] if f[k] != "" else None) for k in cols]
        c.execute(f"UPDATE leads SET {','.join(k+'=?' for k in cols)}, version=version+1, updated=? WHERE id=?", vals + [now(), lead["id"]])
        audit(c, me["id"], "修改名單", f"{lead['name']}：{','.join(cols)}"); c.commit()
        return self.send_json({"ok": True})

    def set_dnc(self, c, me, d):
        lead = c.execute("SELECT * FROM leads WHERE id=?", (int(d["id"]),)).fetchone()
        if not lead: return self.err("找不到", 404)
        on = bool(d.get("on"))
        if not on:
            if me["role"] != "admin": return self.err("只有管理員可以解除「勿再聯絡」", 403)
            if not (d.get("reason") or "").strip(): return self.err("解除要寫原因")
            c.execute("UPDATE leads SET dnc=0, status='暫無需求', version=version+1, updated=? WHERE id=?", (now(), lead["id"]))
            audit(c, me["id"], "解除勿再聯絡", f"{lead['name']}：{d['reason']}")
        else:
            c.execute("UPDATE leads SET dnc=1, status='勿再聯絡', version=version+1, updated=? WHERE id=?", (now(), lead["id"]))
            audit(c, me["id"], "設為勿再聯絡", f"{lead['name']}：{d.get('reason','')}")
        c.commit(); return self.send_json({"ok": True})

    def save_user(self, c, me, d):
        if d.get("id"):
            uid = int(d["id"])
            if uid == me["id"] and d.get("active") is False: return self.err("不能停用自己")
            sets, vals = [], []
            if d.get("role") not in (None, "staff", "manager", "admin"): return self.err("角色不對")
            if uid == me["id"] and d.get("role") not in (None, "admin"): return self.err("不能改自己的角色")
            for k in ("name", "target", "role"):
                if k in d: sets.append(f"{k}=?"); vals.append(d[k])
            if "rider" in d: sets.append("rider=?"); vals.append(1 if d["rider"] else 0)
            if d.get("position"):
                e = X.change_position(c, me, uid, d["position"])
                if e: return self.err(e)
            if d.get("removed"):
                if uid == me["id"]: return self.err("不能移除自己")
                sets += ["removed=1", "active=0"]
                c.execute("UPDATE leads SET assigned_to=NULL WHERE assigned_to=?", (uid,))
            if "active" in d: sets.append("active=?"); vals.append(1 if d["active"] else 0)
            if d.get("active") is False or d.get("removed"):
                sets.append("left_at=COALESCE(left_at,?)"); vals.append(today())
                c.execute("UPDATE leads SET assigned_to=NULL WHERE assigned_to=?", (uid,))
                c.execute("DELETE FROM day_off WHERE user_id=? AND day>?", (uid, today())); c.execute("DELETE FROM duty WHERE user_id=? AND day>?", (uid, today()))
            elif d.get("active") is True: sets.append("left_at=NULL")
            if d.get("password"): sets.append("pw=?"); vals.append(hash_pw(d["password"])); sets.append("must_change=1")
            if sets: c.execute(f"UPDATE users SET {','.join(sets)} WHERE id=?", vals + [uid])
            if d.get("active") is False or d.get("password") or d.get("removed"): c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            audit(c, me["id"], "修改夥伴", json.dumps({k: v for k, v in d.items() if k != "password"}, ensure_ascii=False))
        else:
            un = (d.get("username") or "").strip()
            if not un or not d.get("name") or len(d.get("password", "")) < 6: return self.err("帳號、名字必填，密碼至少 6 碼")
            try:
                c.execute("INSERT INTO users(username,name,pw,role,target,created,must_change) VALUES(?,?,?,?,?,?,1)",
                          (un, d["name"], hash_pw(d["password"]), d.get("role") or "staff", int(d.get("target") or DAILY_TARGET_DEFAULT), now()))
            except sqlite3.IntegrityError: return self.err("帳號已存在")
            audit(c, me["id"], "新增夥伴", un)
        c.commit(); return self.send_json({"ok": True})

    def assign(self, c, me, d):
        ids = [int(x) for x in d.get("ids", [])]
        uid = int(d["user_id"]) if d.get("user_id") else None
        c.executemany("UPDATE leads SET assigned_to=?, version=version+1 WHERE id=?", [(uid, i) for i in ids])
        audit(c, me["id"], "分配名單", f"{len(ids)} 筆 → {uid}"); c.commit()
        return self.send_json({"ok": True, "n": len(ids)})


    # ================= 打卡（員工） =================
    def punch_state(self, c, me):
        S = P.settings(c); t = today()
        prof = c.execute("SELECT * FROM pay_profile WHERE user_id=?", (me["id"],)).fetchone()
        ps = c.execute("SELECT * FROM punches WHERE user_id=? AND voided=0 AND substr(at,1,10)=? ORDER BY at", (me["id"], t)).fetchall()
        sched = P.shift_on(P.shifts_of(c, me["id"]), t)
        row = P.compute(c, t[:7], today=t, only_uid=me["id"]) if prof else []
        fixes = [dict(x) for x in c.execute("SELECT id, day, kind, time, reason, status, decide_note FROM punch_fix WHERE user_id=? ORDER BY id DESC LIMIT 20", (me["id"],))]
        return {"now": now(), "today": t, "closed": P.is_closed(c, t, S), "has_profile": bool(prof),
                "punch_required": bool(prof and prof["punch"]), "next": P.guess_kind(c, me["id"], t, now()[11:16]),
                "punches": [{"at": x["at"][11:16], "kind": x["kind"], "source": x["source"], "dist": x["dist"]} for x in ps],
                "sched": P.shift_txt(sched), "store_set": bool(S.get("store_lat")), "radius": int(S.get("radius") or 150),
                "month": row[0] if row else None, "fixes": fixes,
                "journal_today": bool(c.execute("SELECT 1 FROM journal WHERE user_id=? AND author_id=? AND day=? AND removed=0",
                                                (me["id"], me["id"], t)).fetchone()),
                "off_today": bool(c.execute("SELECT 1 FROM day_off WHERE user_id=? AND day=?", (me["id"], t)).fetchone()),
                "late_last": self._late_last(c, me, row[0] if row else None, ps)}

    def _late_last(self, c, me, m, ps):
        """上一個上班日有遲到、今天還沒打上班卡 → 打卡頁提醒今天準時"""
        if ps: return None
        days = [x for x in (m["per_day"] if m else []) if x["day"] < today() and x["mins"] > 0]
        if not days:
            prev = P.compute(c, O.add_days(today()[:7] + "-01", -1)[:7], today=today(), only_uid=me["id"])
            days = [x for x in (prev[0]["per_day"] if prev else []) if x["mins"] > 0]
        if not days or not days[-1]["lates"]: return None
        return {"day": days[-1]["day"], "mins": max(l[2] for l in days[-1]["lates"])}

    def do_punch(self, c, me, d):
        S = P.settings(c)
        try:
            lat, lng = float(d["lat"]), float(d["lng"]); acc = float(d.get("acc") or 0)
        except Exception:
            return self.err("要允許手機定位才能打卡。")
        if acc > float(S.get("max_acc") or 300):
            return self.err(f"定位不準（誤差約 {int(acc)} 公尺）。請到店門口、打開「精確位置」再試一次。")
        dist, note = None, ""
        if S.get("store_lat"):
            dist = P.distance_m(lat, lng, float(S["store_lat"]), float(S["store_lng"]))
            if dist - min(acc, 100) > int(S.get("radius") or 150):
                return self.err(f"你現在離店大約 {dist} 公尺，要在店裡才能打卡。")
        else:
            note = "店家位置未校正"
        last = c.execute("SELECT at FROM punches WHERE user_id=? AND voided=0 ORDER BY at DESC LIMIT 1", (me["id"],)).fetchone()
        if last and (datetime.now() - datetime.strptime(last["at"], "%Y-%m-%d %H:%M:%S")).total_seconds() < 60:
            return self.err("剛剛已經打過卡了，一分鐘內不用再按。")
        t = today(); at = now()
        kind = d.get("kind") if d.get("kind") in ("in", "out") else P.guess_kind(c, me["id"], t, at[11:16])
        # 兩頭班：上班 → 下班 → 上班 是正常的；只有「上一筆就是同一種卡、而且 2 小時內」才是按重複（10/6 修：原本中間有下班也會擋）
        same = c.execute("SELECT at, kind FROM punches WHERE user_id=? AND voided=0 ORDER BY at DESC LIMIT 1", (me["id"],)).fetchone()
        if same and same["kind"] != kind: same = None
        if same and (datetime.now() - datetime.strptime(same["at"], "%Y-%m-%d %H:%M:%S")).total_seconds() > 7200: same = None
        if same: return self.err("你 %s 已經打過%s卡了。如果是之前忘了打%s，請申請補登。" % (same["at"][11:16], "上班" if kind == "in" else "下班", "下班" if kind == "in" else "上班"))
        c.execute("INSERT INTO punches(user_id,at,kind,source,lat,lng,acc,dist,note,created,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (me["id"], at, kind, "phone", lat, lng, acc, dist, note, at, me["id"]))
        c.commit(); O.touch()
        if not me.get("demo"):   # 老闆 10/6：夥伴打卡要通知店長和老闆
            sched = P.shift_on(P.shifts_of(c, me["id"]), t)
            late = P.lates_of([at[11:16]], sched) if kind == "in" else []
            O.Notifier.notify(c, O.admins(c) + O.managers(c), "%s %s %s" % (me["name"], "上班" if kind == "in" else "下班", at[11:16]),
                              ("晚 %d 分鐘｜" % late[0][2] if late else "") + "今天的班 " + P.shift_txt(sched) + ("｜離店 %d 公尺" % dist if dist is not None else ""), "/#boss")
        miss = SA.closing_check(c, me, t, at[11:16]) if kind == "out" and not me.get("demo") else []   # 店長 10/8：下班要記冰箱
        return self.send_json({"ok": True, "kind": kind, "at": at[11:16], "dist": dist, "safety_missing": miss})

    def punch_fix(self, c, me, d):
        day, kind, tm, reason = (d.get("day") or ""), d.get("kind"), (d.get("time") or ""), (d.get("reason") or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or day > today(): return self.err("日期不對")
        if (date.today() - date.fromisoformat(day)).days > 35: return self.err("只能補登 35 天內的打卡，更早的請直接找老闆。")
        if kind not in ("in", "out"): return self.err("要選上班或下班")
        if not re.fullmatch(r"\d{2}:\d{2}", tm): return self.err("時間不對")
        if not reason: return self.err("要寫原因（例：手機沒電、忘了打）")
        if day == today() and tm > now()[11:16]: return self.err("還沒到的時間不能補登")
        if P.is_locked(c, day[:7]): return self.err("%d 月的薪資已經結算，要補登請直接找老闆" % int(day[5:7]))
        if c.execute("SELECT 1 FROM punch_fix WHERE user_id=? AND day=? AND kind=? AND time=? AND status='待審'", (me["id"], day, kind, tm)).fetchone():
            return self.err("這筆已經申請過了，等老闆審核")
        c.execute("INSERT INTO punch_fix(user_id,day,kind,time,reason,created) VALUES(?,?,?,?,?,?)", (me["id"], day, kind, tm, reason, now()))
        c.commit()
        if not me.get("demo"): O.Notifier.notify(c, O.admins(c), "%s 申請補登打卡" % me["name"], "%s %s %s：%s" % (day[5:], "上班" if kind == "in" else "下班", tm, reason), "/#boss")
        return self.send_json({"ok": True})

    # ================= 公告（含夥伴工作公約） =================
    def notices(self, c, me):
        out = []
        staff = [dict(x) for x in c.execute("SELECT id, name FROM users WHERE active=1 AND role<>'admin' AND COALESCE(demo,0)=0 ORDER BY id")]
        names = {r["id"]: (r["name"], r["role"]) for r in c.execute("SELECT id, name, role FROM users")}
        for n in c.execute("SELECT * FROM notices WHERE active=1 ORDER BY pinned DESC, COALESCE(updated, created) DESC").fetchall():
            d = dict(n)
            acks = {r["user_id"]: r["at"] for r in c.execute("SELECT user_id, at FROM notice_ack WHERE notice_id=?", (n["id"],))}
            d["read"] = me["id"] in acks or n["created_by"] == me["id"]
            d["read_at"] = acks.get(me["id"])
            a = names.get(n["created_by"], ("", ""))
            d["author"] = "老闆" if a[1] == "admin" else ("店長" if a[1] == "manager" else a[0])
            d["mine"] = n["created_by"] == me["id"]
            if me["role"] in ("admin", "manager"):
                d["readers"] = [{"name": u["name"], "at": acks.get(u["id"])} for u in staff if u["id"] != n["created_by"]]
            out.append(d)
        return out

    # ================= 我很棒日誌（像 LINE：夥伴寫、老闆回） =================
    def _seen(self, c, viewer, thread):
        r = c.execute("SELECT last_id FROM journal_seen WHERE viewer_id=? AND thread_id=?", (viewer, thread)).fetchone()
        return r[0] if r else 0

    def journal_unread(self, c, me):
        if me["role"] == "admin":   # 老闆：各夥伴寫了、老闆還沒看的
            return sum(self._thread_unread(c, me, u["id"]) for u in c.execute("SELECT id FROM users WHERE active=1 AND role='staff' AND COALESCE(demo,0)=0"))
        return c.execute("SELECT COUNT(*) FROM journal WHERE user_id=? AND author_id<>? AND removed=0 AND id>?",
                         (me["id"], me["id"], self._seen(c, me["id"], me["id"]))).fetchone()[0]

    def _thread_unread(self, c, me, uid):
        return c.execute("SELECT COUNT(*) FROM journal WHERE user_id=? AND author_id=? AND removed=0 AND id>?",
                         (uid, uid, self._seen(c, me["id"], uid))).fetchone()[0]

    def journal_get(self, c, me, q):
        uid = int(q.get("uid") or 0) if me["role"] == "admin" else me["id"]
        if not uid: return self.err("要選一位夥伴")
        u = c.execute("SELECT id, name FROM users WHERE id=?", (uid,)).fetchone()
        if not u: return self.err("找不到這位夥伴", 404)
        msgs = [dict(x) for x in c.execute("""SELECT j.id, j.author_id, a.name AS author, a.role AS author_role, j.day, j.created,
                      CASE WHEN j.removed THEN NULL ELSE j.body END AS body, CASE WHEN j.removed THEN NULL ELSE j.photo END AS photo, j.removed, COALESCE(j.auto,0) AS auto
                      FROM journal j JOIN users a ON a.id=j.author_id WHERE j.user_id=? ORDER BY j.day, j.id""", (uid,))]
        for m in msgs: m["photo"] = bool(m["photo"])
        last = msgs[-1]["id"] if msgs else 0
        c.execute("""INSERT INTO journal_seen(viewer_id,thread_id,last_id) VALUES(?,?,?)
                     ON CONFLICT(viewer_id,thread_id) DO UPDATE SET last_id=MAX(last_id, excluded.last_id)""", (me["id"], uid, last))
        c.commit()
        t = today()
        return self.send_json({"thread": dict(u), "messages": msgs,
                               "wrote_today": any(m["author_id"] == uid and m["day"] == t and not m["removed"] for m in msgs)})

    def journal_threads(self, c, me):
        t, out = today(), []
        for u in c.execute("SELECT id, name FROM users WHERE active=1 AND role='staff' AND COALESCE(demo,0)=0 ORDER BY id").fetchall():
            last = c.execute("""SELECT j.body, j.photo, j.created, j.removed, a.name FROM journal j JOIN users a ON a.id=j.author_id
                                WHERE j.user_id=? ORDER BY j.id DESC LIMIT 1""", (u["id"],)).fetchone()
            out.append({"id": u["id"], "name": u["name"], "unread": self._thread_unread(c, me, u["id"]),
                        "wrote_today": bool(c.execute("SELECT 1 FROM journal WHERE user_id=? AND author_id=? AND day=? AND removed=0",
                                                      (u["id"], u["id"], t)).fetchone()),
                        "days_month": c.execute("SELECT COUNT(DISTINCT day) FROM journal WHERE user_id=? AND author_id=? AND substr(day,1,7)=? AND removed=0",
                                                (u["id"], u["id"], t[:7])).fetchone()[0],
                        "last": None if not last else {"who": last["name"], "at": last["created"],
                                                       "text": "（已收回）" if last["removed"] else (last["body"] or "[照片]")[:60]}})
        return out

    def journal_post(self, c, me, d):
        if me["role"] == "admin":
            uid = int(d.get("uid") or 0)
            if not c.execute("SELECT 1 FROM users WHERE id=? AND active=1 AND role<>'admin'", (uid,)).fetchone():
                return self.err("要回覆哪一位夥伴？")
            day = d.get("day") if O.ymd(d.get("day") or "") and O.add_days(today(), -60) <= d["day"] <= today() else today()   # 老闆回覆某一天的日誌
        else:
            uid = me["id"]; day = today()
        body = (d.get("body") or "").strip()
        if len(body) > 2000: return self.err("一則最多 2,000 字，請分兩則")
        raw = None
        if d.get("photo"):
            try: raw = base64.b64decode(d["photo"].split(",")[-1], validate=True)
            except Exception: return self.err("照片格式不對")
            if not (raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n"): return self.err("只收 JPG 或 PNG 照片")
            if len(raw) > 1_500_000: return self.err("照片太大，請重新選一張")
        if not body and not raw: return self.err("寫點什麼再送出")
        at = now()
        jid = c.execute("INSERT INTO journal(user_id,author_id,day,body,created) VALUES(?,?,?,?,?)",
                        (uid, me["id"], day, body, at)).lastrowid
        if raw:
            os.makedirs(PHOTOS, exist_ok=True)
            fn = "%d.%s" % (jid, "png" if raw[:4] == b"\x89PNG" else "jpg")
            with open(os.path.join(PHOTOS, fn), "wb") as f: f.write(raw)
            c.execute("UPDATE journal SET photo=? WHERE id=?", (fn, jid))
        c.execute("""INSERT INTO journal_seen(viewer_id,thread_id,last_id) VALUES(?,?,?)
                     ON CONFLICT(viewer_id,thread_id) DO UPDATE SET last_id=MAX(last_id, excluded.last_id)""", (me["id"], uid, jid))
        c.commit()
        if me["role"] == "admin":
            O.Notifier.notify(c, [uid], "老闆回你的日誌", (body or "[照片]")[:80], "/#journal")
        else:
            if not me.get("demo"): O.Notifier.notify(c, O.admins(c), "%s 寫了今天的日誌" % me["name"], (body or "[照片]")[:80], "/#journal")
        return self.send_json({"ok": True, "id": jid})

    def journal_remove(self, c, me, d):
        r = c.execute("SELECT * FROM journal WHERE id=?", (int(d.get("id") or 0),)).fetchone()
        if not r or r["author_id"] != me["id"]: return self.err("只能收回自己寫的", 403)
        if r["day"] != today(): return self.err("只能收回今天寫的")
        c.execute("UPDATE journal SET removed=1 WHERE id=?", (r["id"],)); c.commit()
        return self.send_json({"ok": True})

    def journal_photo(self, c, me, q):
        r = c.execute("SELECT user_id, photo, removed FROM journal WHERE id=?", (int(q.get("id") or 0),)).fetchone()
        if not r or not r["photo"] or r["removed"]: return self.err("找不到", 404)
        if me["role"] != "admin" and r["user_id"] != me["id"]: return self.err("不能看別人的日誌", 403)
        fp = os.path.join(PHOTOS, os.path.basename(r["photo"]))
        if not os.path.exists(fp): return self.err("找不到", 404)
        b = open(fp, "rb").read()
        self.send_response(200); self.send_header("Content-Type", "image/png" if fp.endswith(".png") else "image/jpeg")
        self.send_header("Cache-Control", "private, max-age=86400"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    # ================= 教育訓練手冊 =================
    def manual_unread(self, c, me):
        return c.execute("""SELECT COUNT(*) FROM manual m WHERE m.active=1 AND NOT EXISTS
                            (SELECT 1 FROM manual_ack a WHERE a.manual_id=m.id AND a.user_id=?)""", (me["id"],)).fetchone()[0]

    def manual(self, c, me):
        staff = [dict(x) for x in c.execute("SELECT id, name FROM users WHERE active=1 AND role<>'admin' AND COALESCE(demo,0)=0 ORDER BY id")]
        req = set(X.required_ids(c, me)); out = []
        for m in c.execute("SELECT * FROM manual WHERE active=1 ORDER BY sort, id").fetchall():
            d = dict(m)
            acks = {r["user_id"]: r["at"] for r in c.execute("SELECT user_id, at FROM manual_ack WHERE manual_id=?", (m["id"],))}
            d["read_at"] = acks.get(me["id"]); d["required"] = m["id"] in req
            if me["role"] == "admin": d["readers"] = [{"name": u["name"], "at": acks.get(u["id"])} for u in staff]
            out.append(d)
        return out

    # ================= 老闆頁 =================
    def boss_get(self, c, me, p, q):
        if p == "/api/boss/today":
            b = P.board(c, q.get("day"))
            off = {r[0] for r in c.execute("SELECT user_id FROM day_off WHERE day=?", (b["day"],))}
            for r in b["rows"]:
                if r["id"] in off and not r["punches"]: r["status"] = "排休"
            b["journal"] = [{"name": t["name"], "wrote": t["wrote_today"], "unread": t["unread"]} for t in self.journal_threads(c, me)]
            b["setup_missing"] = [r["name"] for r in c.execute("""SELECT u.name FROM users u LEFT JOIN pay_profile p ON p.user_id=u.id
                    WHERE u.active=1 AND COALESCE(u.demo,0)=0 AND COALESCE(u.removed,0)=0 AND u.role<>'admin'
                    AND (p.user_id IS NULL OR (p.punch=1 AND NOT EXISTS (SELECT 1 FROM shifts s WHERE s.user_id=u.id))) ORDER BY u.id""")]
            return self.send_json(b)
        if p == "/api/boss/payroll":
            month = q.get("month") or today()[:7]
            st = c.execute("SELECT * FROM pay_month WHERE month=?", (month,)).fetchone()
            return self.send_json({"month": month, "rows": P.month_rows(c, month), "status": dict(st) if st else None})
        if p == "/api/boss/fixes":
            rows = [dict(x) for x in c.execute("""SELECT f.*, u.name FROM punch_fix f JOIN users u ON u.id=f.user_id WHERE COALESCE(u.demo,0)=0
                       ORDER BY CASE f.status WHEN '待審' THEN 0 ELSE 1 END, f.id DESC LIMIT 100""")]
            return self.send_json(rows)
        if p == "/api/boss/punches":
            month = q.get("month") or today()[:7]
            uid = int(q.get("user_id") or 0)
            rows = [dict(x) for x in c.execute("""SELECT pu.*, u.name FROM punches pu JOIN users u ON u.id=pu.user_id
                       WHERE substr(pu.at,1,7)=? AND (?=0 OR pu.user_id=?) AND COALESCE(u.demo,0)=0 ORDER BY pu.at DESC""", (month, uid, uid))]
            return self.send_json(rows)
        if p == "/api/boss/settings":
            month = q.get("month") or today()[:7]
            return self.send_json({
                "settings": P.settings(c),
                "people": [dict(x) for x in c.execute("""SELECT u.id, u.name, u.username, u.role, u.active, p.kind, p.amount, p.off_days, p.punch, p.li_self, p.hi_self
                            FROM users u LEFT JOIN pay_profile p ON p.user_id=u.id WHERE COALESCE(u.demo,0)=0 AND COALESCE(u.removed,0)=0
                            AND COALESCE(u.pending,0)=0 ORDER BY u.active DESC, u.id""")],
                "shifts": [dict(x) for x in c.execute("SELECT s.*, u.name FROM shifts s JOIN users u ON u.id=s.user_id ORDER BY u.id, s.effective DESC, s.id DESC")],
                "closed": [dict(x) for x in c.execute("SELECT * FROM closed_days WHERE day>=? ORDER BY day", ((date.today() - timedelta(days=60)).isoformat(),))],
                "advances": [dict(x) for x in c.execute("""SELECT a.*, u.name FROM advances a JOIN users u ON u.id=a.user_id
                             WHERE COALESCE(a.pay_month, substr(a.day,1,7))=? OR substr(a.day,1,7)=? ORDER BY a.day DESC""", (month, month))],
                "adjustments": [dict(x) for x in c.execute("SELECT a.*, u.name FROM adjustments a JOIN users u ON u.id=a.user_id WHERE a.month=? ORDER BY a.id DESC", (month,))]})
        return self.err("not found", 404)

    def boss_post(self, c, me, p, d):
        def ok(action, detail):
            audit(c, me["id"], action, detail); c.commit(); O.touch(); return self.send_json({"ok": True})
        hhmm = lambda x: bool(re.fullmatch(r"\d{2}:\d{2}", x or ""))
        ymd = lambda x: bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", x or ""))
        def locked(day_or_month):
            m = (day_or_month or "")[:7]
            return self.err("%d 月薪資已經結算（定案或已發薪），要改請先到「本月薪資」按「改回試算中」" % int(m[5:7])) if m and P.is_locked(c, m) else None
        if p == "/api/boss/fix/decide":
            f = c.execute("SELECT * FROM punch_fix WHERE id=?", (int(d["id"]),)).fetchone()
            if not f or f["status"] != "待審": return self.err("這筆已經處理過了")
            if d.get("approve") and locked(f["day"]): return locked(f["day"])
            pid = None
            if d.get("approve"):
                cur = c.execute("INSERT INTO punches(user_id,at,kind,source,note,created,created_by) VALUES(?,?,?,?,?,?,?)",
                                (f["user_id"], f"{f['day']} {f['time']}:00", f["kind"], "補登", f["reason"], now(), me["id"]))
                pid = cur.lastrowid
            c.execute("UPDATE punch_fix SET status=?, decided_by=?, decided_at=?, decide_note=?, punch_id=? WHERE id=?",
                      ("核准" if d.get("approve") else "退回", me["id"], now(), (d.get("note") or "").strip(), pid, f["id"]))
            return ok("補登審核", f"{f['id']} {'核准' if d.get('approve') else '退回'}")
        if p == "/api/boss/punch/add":
            if not (ymd(d.get("day")) and hhmm(d.get("time")) and d.get("kind") in ("in", "out") and (d.get("reason") or "").strip()):
                return self.err("日期、時間、上下班、原因都要填")
            if locked(d["day"]): return locked(d["day"])
            c.execute("INSERT INTO punches(user_id,at,kind,source,note,created,created_by) VALUES(?,?,?,?,?,?,?)",
                      (int(d["user_id"]), f"{d['day']} {d['time']}:00", d["kind"], d.get("source") or "老闆補登", d["reason"].strip(), now(), me["id"]))
            return ok("新增打卡", json.dumps(d, ensure_ascii=False))
        if p == "/api/boss/punch/void":
            if not (d.get("reason") or "").strip(): return self.err("作廢要寫原因")
            pu = c.execute("SELECT at FROM punches WHERE id=?", (int(d["id"]),)).fetchone()
            if pu and locked(pu["at"]): return locked(pu["at"])
            c.execute("UPDATE punches SET voided=1, void_by=?, void_at=?, void_reason=? WHERE id=?", (me["id"], now(), d["reason"].strip(), int(d["id"])))
            return ok("作廢打卡", f"{d['id']}：{d['reason']}")
        if p == "/api/boss/store/set":
            lat, lng = float(d["lat"]), float(d["lng"])
            c.executemany("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", [("store_lat", str(lat)), ("store_lng", str(lng))])
            return ok("設定店家位置", f"{lat},{lng}（誤差 {d.get('acc')}）")
        if p == "/api/boss/settings/save":
            keys = ("radius", "weekly_closed", "absent_over", "max_acc", "late_remind")
            rng = {"radius": (5, 3000), "max_acc": (5, 3000), "absent_over": (0, 600)}
            for k, (lo, hi) in rng.items():
                if k in d and not (str(d[k]).strip().isdigit() and lo <= int(d[k]) <= hi): return self.err("「%s」要填 %d 到 %d 的數字" % (k, lo, hi))
            if "late_remind" in d and not re.fullmatch(r"\d{2}:\d{2}", str(d["late_remind"])): return self.err("提醒時間格式不對（例：20:30）")
            if "weekly_closed" in d and not re.fullmatch(r"[0-6]?(,[0-6])*", str(d["weekly_closed"])): return self.err("公休日格式不對")
            c.executemany("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                          [(k, str(d[k])) for k in keys if k in d])
            return ok("修改打卡設定", json.dumps({k: d[k] for k in keys if k in d}, ensure_ascii=False))
        if p == "/api/boss/profile/save":
            if d.get("kind") not in ("monthly", "hourly", "fixed"): return self.err("計薪方式不對")
            if O.num(d.get("amount")) <= 0: return self.err("金額要大於 0")
            if not 0 <= O.num(d.get("off_days")) <= 27: return self.err("月休天數不對")
            d["amount"], d["off_days"] = O.num(d.get("amount")), O.num(d.get("off_days"))
            li, hi = O.num(d.get("li_self")), O.num(d.get("hi_self"))
            if li < 0 or hi < 0: return self.err("勞健保自付額不能是負數")
            c.execute("""INSERT INTO pay_profile(user_id,kind,amount,off_days,punch,updated,li_self,hi_self) VALUES(?,?,?,?,?,?,?,?)
                         ON CONFLICT(user_id) DO UPDATE SET kind=excluded.kind, amount=excluded.amount, off_days=excluded.off_days,
                         punch=excluded.punch, updated=excluded.updated, li_self=excluded.li_self, hi_self=excluded.hi_self""",
                      (int(d["user_id"]), d["kind"], int(d["amount"]), int(d.get("off_days") or 0), 1 if d.get("punch") else 0, now(), int(li), int(hi)))
            return ok("修改薪資設定", json.dumps(d, ensure_ascii=False))
        if p == "/api/boss/profile/delete":
            c.execute("DELETE FROM pay_profile WHERE user_id=?", (int(d["user_id"]),))
            return ok("刪除薪資設定", str(d["user_id"]))
        if p == "/api/boss/shift/save":
            if not ymd(d.get("effective")) or not (hhmm(d.get("s1")) and hhmm(d.get("e1"))): return self.err("生效日和第一段班要填")
            if (d.get("s2") or d.get("e2")) and not (hhmm(d.get("s2")) and hhmm(d.get("e2"))): return self.err("第二段班要上下班都填")
            wk = sorted({int(x) for x in (d.get("days") or []) if str(x).isdigit() and 0 <= int(x) <= 6})
            if d.get("days") is not None and not wk: return self.err("至少要勾一天")
            c.execute("INSERT INTO shifts(user_id,effective,s1,e1,s2,e2,note,created,created_by,days) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (int(d["user_id"]), d["effective"], d["s1"], d["e1"], d.get("s2") or None, d.get("e2") or None, d.get("note") or "", now(), me["id"],
                       ",".join(map(str, wk)) if wk and len(wk) < 7 else None))
            return ok("新增班表", json.dumps(d, ensure_ascii=False))
        if p == "/api/boss/shift/delete":
            c.execute("DELETE FROM shifts WHERE id=?", (int(d["id"]),))
            return ok("刪除班表", str(d["id"]))
        if p == "/api/boss/closed/save":
            if not ymd(d.get("day")): return self.err("日期不對")
            if d.get("on"): c.execute("INSERT OR REPLACE INTO closed_days(day,reason) VALUES(?,?)", (d["day"], d.get("reason") or "公休"))
            else: c.execute("DELETE FROM closed_days WHERE day=?", (d["day"],))
            return ok("公休日", json.dumps(d, ensure_ascii=False))
        if p == "/api/boss/advance/save":
            if not ymd(d.get("day")) or O.num(d.get("amount")) <= 0: return self.err("日期、金額要填")
            prev = (date.fromisoformat(d["day"][:7] + "-01") - timedelta(days=1)).strftime("%Y-%m")   # 月初 1–5 號（發薪前）預支 → 預設從上個月薪資扣
            pm = d.get("pay_month") if re.fullmatch(r"\d{4}-\d{2}", d.get("pay_month") or "") else (prev if int(d["day"][8:10]) <= 5 and not P.is_locked(c, prev) else d["day"][:7])
            if locked(pm): return locked(pm)
            if c.execute("SELECT 1 FROM advances WHERE user_id=? AND day=? AND amount=? AND voided=0 AND created>=datetime('now','localtime','-2 minutes')",
                         (int(d["user_id"]), d["day"], O.num(d["amount"]))).fetchone(): return self.err("剛剛已經登記過一筆一樣的預支了")
            aid = c.execute("INSERT INTO advances(user_id,day,amount,note,created,created_by,pay_month) VALUES(?,?,?,?,?,?,?)",
                            (int(d["user_id"]), d["day"], O.num(d["amount"]), d.get("note") or "", now(), me["id"], pm)).lastrowid
            if d.get("drawer", True) and d["day"] >= O.EXP_START:   # 從店內抽屜拿現金 → 自動記帳務支出（類別薪資），股東網站跟著扣
                nm = c.execute("SELECT name FROM users WHERE id=?", (int(d["user_id"]),)).fetchone()[0]
                eid = c.execute("""INSERT INTO fin_exp(day,category,item,vendor,amount,pay,note,status,created_by,created,updated,verified_by,verified_at)
                                   VALUES(?,?,?,?,?,'店內現金',?,'已核銷',?,?,?,?,?)""",
                                (d["day"], "薪資", "%s 預支（%d 月薪資扣）" % (nm, int(pm[5:])), nm, O.num(d["amount"]), "預支單 #%d" % aid,
                                 me["id"], now(), now(), me["id"], now())).lastrowid
                c.execute("UPDATE advances SET exp_id=? WHERE id=?", (eid, aid))
                c.commit(); O.sync_ledger(self.server.db_factory)
            return ok("登記預支", json.dumps(d, ensure_ascii=False))
        if p == "/api/boss/advance/void":
            a = c.execute("SELECT day, pay_month, exp_id FROM advances WHERE id=?", (int(d["id"]),)).fetchone()
            if a and locked(a["pay_month"] or a["day"]): return locked(a["pay_month"] or a["day"])
            c.execute("UPDATE advances SET voided=1 WHERE id=?", (int(d["id"]),))
            if a and a["exp_id"]:
                c.execute("UPDATE fin_exp SET removed=1, updated=? WHERE id=?", (now(), a["exp_id"])); c.commit(); O.sync_ledger(self.server.db_factory)
            return ok("作廢預支", str(d["id"]))
        if p == "/api/boss/adjust/save":
            if not re.fullmatch(r"\d{4}-\d{2}", d.get("month") or "") or not int(d.get("amount") or 0) or not (d.get("reason") or "").strip():
                return self.err("月份、金額（可負數）、原因都要填")
            if locked(d["month"]): return locked(d["month"])
            if c.execute("SELECT 1 FROM adjustments WHERE user_id=? AND month=? AND amount=? AND voided=0 AND created>=datetime('now','localtime','-2 minutes')",
                         (int(d["user_id"]), d["month"], int(d["amount"]))).fetchone(): return self.err("剛剛已經登記過一筆一樣的調整了")
            c.execute("INSERT INTO adjustments(user_id,month,amount,reason,created,created_by) VALUES(?,?,?,?,?,?)",
                      (int(d["user_id"]), d["month"], int(d["amount"]), d["reason"].strip(), now(), me["id"]))
            return ok("薪資調整", json.dumps(d, ensure_ascii=False))
        if p == "/api/boss/adjust/void":
            a = c.execute("SELECT month FROM adjustments WHERE id=?", (int(d["id"]),)).fetchone()
            if a and locked(a["month"]): return locked(a["month"])
            c.execute("UPDATE adjustments SET voided=1 WHERE id=?", (int(d["id"]),)); return ok("作廢調整", str(d["id"]))
        if p == "/api/boss/notice/save":
            title, body = (d.get("title") or "").strip(), (d.get("body") or "").strip()
            if not title or not body: return self.err("標題和內容都要填")
            if d.get("id"):
                c.execute("UPDATE notices SET title=?, body=?, pinned=?, need_ack=?, updated=? WHERE id=?",
                          (title, body, 1 if d.get("pinned") else 0, 1 if d.get("need_ack", True) else 0, now(), int(d["id"])))
                if d.get("reack"): c.execute("DELETE FROM notice_ack WHERE notice_id=?", (int(d["id"]),))
            else:
                c.execute("INSERT INTO notices(title,body,pinned,need_ack,created,created_by) VALUES(?,?,?,?,?,?)",
                          (title, body, 1 if d.get("pinned") else 0, 1 if d.get("need_ack", True) else 0, now(), me["id"]))
            return ok("公告", title)
        if p == "/api/boss/notice/remove":
            c.execute("UPDATE notices SET active=0, updated=? WHERE id=?", (now(), int(d["id"])))
            return ok("下架公告", str(d["id"]))
        if p == "/api/boss/manual/save":
            ch, title, body = (d.get("chapter") or "").strip(), (d.get("title") or "").strip(), (d.get("body") or "").strip()
            if not ch or not title or not body: return self.err("章節、標題、內容都要填")
            sort = int(d.get("sort") or 0)
            if d.get("id"):
                c.execute("UPDATE manual SET chapter=?, title=?, body=?, sort=?, updated=?, updated_by=? WHERE id=?",
                          (ch, title, body, sort, now(), me["id"], int(d["id"])))
                if d.get("reack"): c.execute("DELETE FROM manual_ack WHERE manual_id=?", (int(d["id"]),))
            else:
                if not sort:
                    sort = (c.execute("SELECT MAX(sort) FROM manual WHERE chapter=?", (ch,)).fetchone()[0]
                            or c.execute("SELECT COALESCE(MAX(sort),0) FROM manual").fetchone()[0]) + 1
                c.execute("INSERT INTO manual(chapter,title,body,sort,updated,updated_by) VALUES(?,?,?,?,?,?)", (ch, title, body, sort, now(), me["id"]))
            return ok("教育訓練", title)
        if p == "/api/boss/manual/remove":
            c.execute("UPDATE manual SET active=0, updated=? WHERE id=?", (now(), int(d["id"])))
            return ok("下架教育訓練", str(d["id"]))
        if p == "/api/boss/month/set":
            if d.get("status") not in ("試算中", "已定案", "已發薪"): return self.err("狀態不對")
            if not re.fullmatch(r"\d{4}-\d{2}", d.get("month") or ""): return self.err("月份不對")
            if d["status"] != "試算中" and d["month"] >= today()[:7]: return self.err("月份還沒結束，不能定案")
            if d["status"] == "試算中": P.unlock_month(c, d["month"])
            elif not P.is_locked(c, d["month"]): P.lock_month(c, d["month"], me["id"])
            c.execute("INSERT OR REPLACE INTO pay_month(month,status,at,by_user,paid_on) VALUES(?,?,?,?,?)",
                      (d["month"], d["status"], now(), me["id"], d.get("paid_on") or None))
            return ok("薪資月份狀態", json.dumps(d, ensure_ascii=False))
        return self.err("not found", 404)


class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True; allow_reuse_address = os.name != "nt"   # Windows 上 True 會讓第二個程式也綁得上同一個埠

def write_pid(path):
    """記下程序編號，tools/stop.py 用它停止；正常結束時刪掉"""
    import atexit
    with open(path, "w") as f: f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(path) and os.remove(path))


if __name__ == "__main__":
    init_db()
    write_pid(os.path.join(os.path.dirname(DB), "app.pid"))
    threading.Thread(target=backup_loop, daemon=True).start()
    vapid = push.Vapid(os.path.join(os.path.dirname(DB), "vapid_private.pem"))
    O.Notifier.sender = push.Sender(vapid, db)
    O.cron(db); X.cron(db); SA.cron(db); MK.cron(db, H.PHOTO_DIR)
    with S(("127.0.0.1", PORT), H) as s:
        s.vapid_public = vapid.public; s.db_factory = db
        s.serve_forever()
