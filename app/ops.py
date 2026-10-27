# -*- coding: utf-8 -*-
"""營運功能（2026-10-06 起）：權限、班表（排休、廁所輪值）、店長記帳＋老闆核銷＋同步帳務系統、外送單、
新夥伴註冊審核、公告（店長也能發）、手機推播與通知、每天的提醒排程。
app.py 的 H 繼承 Ops；路由進來先問 ops_get／ops_post，沒有對應就回 NOPE。"""
import base64, json, os, re, subprocess, sys, threading, time
from datetime import datetime, date, timedelta
import payroll as P

HERE = os.path.dirname(os.path.abspath(__file__))
NOPE = object()
import cfg
LEDGER = os.path.normpath(os.path.join(HERE, "..", "ledger", "builder", "build_ledger.py"))   # 股東帳務頁產生器
FIN_START = cfg.FINANCE.get("fin_start", "2026-01-01")
EXP_START = os.environ.get("CRM_EXP_START") or cfg.FINANCE.get("exp_start", FIN_START)
PETTY_FROM = cfg.FINANCE.get("petty_from", FIN_START)    # 這天起店裡花費從零用金出，營收現金不動
FLOAT_CASH = int(cfg.FINANCE.get("float_cash", 5000))     # 找零金（只換零錢，不會變），抽屜點算包含它
DRAWER_BASE = (FIN_START, FLOAT_CASH)                    # 開始用系統那天，抽屜只有找零金
EXP_CATS = list(cfg.FINANCE.get("expense_categories") or ["其他"])
DSTATES = ["新單", "製作中", "已出餐", "配送中", "已送達"]          # 外送單狀態（照 Uber Eats／foodpanda 商家＋外送員兩端合併）
ISSUES = ["聯絡不上客人", "地址錯", "客人改地址", "打翻或損壞", "少品項", "客人拒收", "客人付不出錢", "車禍或事故", "其他"]
HANDOFF = ["交給本人", "放櫃台", "交警衛或管理室", "放門口"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS day_off(user_id INTEGER NOT NULL, day TEXT NOT NULL, note TEXT, created_by INTEGER, created TEXT, PRIMARY KEY(user_id, day));
CREATE TABLE IF NOT EXISTS duty(day TEXT NOT NULL, kind TEXT NOT NULL, user_id INTEGER NOT NULL, PRIMARY KEY(day, kind));
CREATE TABLE IF NOT EXISTS fin_day(day TEXT PRIMARY KEY, total INTEGER, cash INTEGER, stored INTEGER, eticket INTEGER, orders INTEGER, boxes INTEGER,
  voucher INTEGER, topup INTEGER, drawer INTEGER, note TEXT, photo TEXT, status TEXT NOT NULL DEFAULT '待核銷', created_by INTEGER, created TEXT,
  updated TEXT, verified_by INTEGER, verified_at TEXT, verify_note TEXT);
CREATE TABLE IF NOT EXISTS fin_exp(id INTEGER PRIMARY KEY, day TEXT NOT NULL, category TEXT NOT NULL, item TEXT NOT NULL, vendor TEXT,
  amount INTEGER NOT NULL, pay TEXT NOT NULL DEFAULT '店內現金', note TEXT, photo TEXT, status TEXT NOT NULL DEFAULT '待核銷', created_by INTEGER,
  created TEXT, updated TEXT, verified_by INTEGER, verified_at TEXT, verify_note TEXT, removed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY, day TEXT NOT NULL, seq INTEGER, created TEXT, created_by INTEGER, source TEXT,
  customer TEXT, phone TEXT, address TEXT, items TEXT, boxes INTEGER, amount INTEGER, pay TEXT, collect INTEGER NOT NULL DEFAULT 0,
  due TEXT, note TEXT, status TEXT NOT NULL DEFAULT '新單', rider_id INTEGER, assigned_at TEXT, accepted_at TEXT, prep_at TEXT, ready_at TEXT,
  picked_at TEXT, delivered_at TEXT, handoff TEXT, proof TEXT, cash_got INTEGER, settled INTEGER NOT NULL DEFAULT 0, settled_at TEXT,
  settled_by INTEGER, issue TEXT, cancelled INTEGER NOT NULL DEFAULT 0, cancel_reason TEXT, bags INTEGER, receipt TEXT, ready_by TEXT,
  near_at TEXT, part TEXT, checked TEXT, issue_at TEXT, remind_acc INTEGER NOT NULL DEFAULT 0, remind_prep INTEGER NOT NULL DEFAULT 0,
  remind_rider INTEGER NOT NULL DEFAULT 0, cash_ok_by INTEGER);
CREATE INDEX IF NOT EXISTS ix_deliv_day ON deliveries(day);
CREATE TABLE IF NOT EXISTS delivery_events(id INTEGER PRIMARY KEY, delivery_id INTEGER NOT NULL, at TEXT, user_id INTEGER, what TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS push_subs(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, endpoint TEXT UNIQUE NOT NULL, p256dh TEXT NOT NULL,
  auth TEXT NOT NULL, ua TEXT, created TEXT, last_ok TEXT, fails INTEGER NOT NULL DEFAULT 0, last_err TEXT);
CREATE TABLE IF NOT EXISTS inbox(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT, body TEXT, url TEXT, created TEXT, read INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_inbox_user ON inbox(user_id, id);
CREATE TABLE IF NOT EXISTS jobs_done(k TEXT PRIMARY KEY, at TEXT);
-- 零用金：老闆撥給店長（＋），店裡花費 pay='零用金' 從這裡扣；營收現金收走／存銀行
CREATE TABLE IF NOT EXISTS petty(id INTEGER PRIMARY KEY, day TEXT NOT NULL, amount INTEGER NOT NULL, note TEXT, created_by INTEGER, created TEXT, removed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS cash_out(id INTEGER PRIMARY KEY, day TEXT NOT NULL, amount INTEGER NOT NULL, dest TEXT, note TEXT, created_by INTEGER, created TEXT, removed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS fin_day_log(id INTEGER PRIMARY KEY, day TEXT NOT NULL, at TEXT, user_id INTEGER, reason TEXT, before TEXT, after TEXT);
"""
# 到點定位打卡（外送夥伴到客人那裡按「到了」）、送達時的位置
DELIV_COLS = {"arrive_at": "TEXT", "arrive_lat": "REAL", "arrive_lng": "REAL", "arrive_acc": "REAL", "arrive_m": "INTEGER",
              "arrive_note": "TEXT", "drop_lat": "REAL", "drop_lng": "REAL", "deleted": "INTEGER NOT NULL DEFAULT 0"}
USER_COLS = {"removed": "INTEGER NOT NULL DEFAULT 0", "pending": "INTEGER NOT NULL DEFAULT 0", "phone": "TEXT", "position": "TEXT", "rider": "INTEGER NOT NULL DEFAULT 0",
             "demo": "INTEGER NOT NULL DEFAULT 0", "reg_note": "TEXT", "left_at": "TEXT", "title": "TEXT"}   # title：職稱（例：副店長）


def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def today(): return date.today().isoformat()
def add_days(d, n): return (date.fromisoformat(d) + timedelta(days=n)).isoformat()
def ymd(x): return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", x or ""))
def hhmm(x): return bool(re.fullmatch(r"\d{2}:\d{2}", x or ""))
def num(x, default=0):
    try: return int(round(float(str(x).replace(",", "")))) if str(x).strip() != "" else default
    except Exception: return default


def migrate(c):
    c.executescript(SCHEMA)
    have = {r[1] for r in c.execute("PRAGMA table_info(users)")}
    for k, t in USER_COLS.items():
        if k not in have: c.execute(f"ALTER TABLE users ADD COLUMN {k} {t}")
    have = {r[1] for r in c.execute("PRAGMA table_info(deliveries)")}
    for k, t in DELIV_COLS.items():
        if k not in have: c.execute(f"ALTER TABLE deliveries ADD COLUMN {k} {t}")
    have = {r[1] for r in c.execute("PRAGMA table_info(advances)")}
    if "pay_month" not in have: c.execute("ALTER TABLE advances ADD COLUMN pay_month TEXT")       # 從哪個月的薪資扣
    if "exp_id" not in have: c.execute("ALTER TABLE advances ADD COLUMN exp_id INTEGER")          # 從抽屜拿 → 對應的帳務支出
    sh = {r[1] for r in c.execute("PRAGMA table_info(shifts)")}
    if sh and "days" not in sh: c.execute("ALTER TABLE shifts ADD COLUMN days TEXT")            # 一週哪幾天有班（空的＝每天）
    if "kind" not in {r[1] for r in c.execute("PRAGMA table_info(petty)")}:   # 撥款＝老闆撥給店長；收入＝廢油回收這類不走 POS 的錢（10/9）
        c.execute("ALTER TABLE petty ADD COLUMN kind TEXT NOT NULL DEFAULT '撥款'")
    if "deposited" not in {r[1] for r in c.execute("PRAGMA table_info(petty)")}:   # 其他收入存進銀行的日期（空的＝還沒存）
        c.execute("ALTER TABLE petty ADD COLUMN deposited TEXT")
    if "acting_as" not in {r[1] for r in c.execute("PRAGMA table_info(sessions)")}:   # 老闆切換角色：這個登入目前模擬誰
        c.execute("ALTER TABLE sessions ADD COLUMN acting_as INTEGER")


# ───────────── 老闆切換角色：老闆／模擬店長／模擬夥伴 ─────────────
# 模擬用的是兩個隱藏身分（demo=1），不出現在任何名單、薪資、帳務、通知對象；不能直接登入
DEMO = {"manager": ("demo_mgr", "試用店長"), "staff": ("demo", "試用夥伴")}
# 模擬時只准做「只影響自己」的動作；其他（記帳、公告、班表、外送、名單、通話、帳號、推播設定…）一律擋
DEMO_OK = {"/api/logout", "/api/switch", "/api/punch", "/api/punch/fix", "/api/notice/ack", "/api/manual/ack", "/api/tour/done", "/api/tour/reset", "/api/news/read",
           "/api/journal/post", "/api/journal/remove", "/api/inbox/read"}
DEMO_MSG = "模擬模式：可以看、可以點，但這個動作會動到正式資料，所以不會真的存。切回老闆再做。"


def ensure_demo(c, hash_pw):
    import secrets
    for role_, (un, nm) in DEMO.items():
        r = c.execute("SELECT id FROM users WHERE username=?", (un,)).fetchone()
        if not r:
            c.execute("INSERT INTO users(username,name,pw,role,created,demo,active,target) VALUES(?,?,?,?,?,1,1,0)",
                      (un, nm, hash_pw(secrets.token_urlsafe(24)), role_, now()))
        else:
            c.execute("UPDATE users SET demo=1, active=1, role=?, removed=0, pending=0, must_change=0 WHERE id=?", (role_, r[0]))
        uid = c.execute("SELECT id FROM users WHERE username=?", (un,)).fetchone()[0]
        if role_ == "staff" and not c.execute("SELECT 1 FROM pay_profile WHERE user_id=?", (uid,)).fetchone():   # 模擬夥伴要有班才看得到打卡
            c.execute("INSERT INTO pay_profile(user_id,kind,amount,off_days,punch) VALUES(?,?,?,?,1)", (uid, "monthly", 0, 6))
            c.execute("INSERT INTO shifts(user_id,effective,s1,e1,s2,e2) VALUES(?,?,?,?,?,?)", (uid, "2026-01-01", "09:00", "13:00", "15:30", "19:30"))


def mask_pay(data, me):
    """老闆 10/6：大家的薪資是秘密——薪資相關（預支等）是公司對個人的私事。店長的記帳頁只看得到金額（抽屜才對得起來），看不到是誰、什麼事。"""
    if is_admin(me): return data
    def m(e):
        if e.get("category") == "薪資":
            e.update(item="老闆處理的款項", vendor="", note="", photo=None, category="老闆處理")
        return e
    for e in data.get("exps") or []: m(e)
    for x in (data.get("days") or []) + (data.get("pending") or []):
        for e in x.get("exps") or []: m(e)
    return data


def role(me): return me["role"]
def is_admin(me): return me["role"] == "admin"
def can_fin(me): return me["role"] in ("admin", "manager")
def can_post(me): return me["role"] in ("admin", "manager")
def can_sched(me): return me["role"] in ("admin", "manager")
def can_dispatch(me): return me["role"] in ("admin", "manager") or True     # 櫃檯接到外送單也要能開單、派單


def save_photo(data, folder, name):
    """前端壓好的 JPG／PNG（data URL 或 base64）存檔，回傳檔名；格式不對丟 ValueError"""
    raw = base64.b64decode((data or "").split(",")[-1], validate=True)
    if raw[:3] == b"\xff\xd8\xff": ext = "jpg"
    elif raw[:8] == b"\x89PNG\r\n\x1a\n": ext = "png"
    else: raise ValueError("只收 JPG 或 PNG 照片")
    if len(raw) > 1_800_000: raise ValueError("照片太大，請重新拍一張")
    os.makedirs(folder, exist_ok=True)
    fn = f"{name}.{ext}"
    for old in (f"{name}.jpg", f"{name}.png"):
        if old != fn and os.path.exists(os.path.join(folder, old)): os.remove(os.path.join(folder, old))
    with open(os.path.join(folder, fn), "wb") as f: f.write(raw)
    return fn


# ───────────── 班表：誰上班、誰排休 ─────────────
def offs(c, day1, day2):
    return {(r["user_id"], r["day"]): r["note"] or "" for r in c.execute("SELECT * FROM day_off WHERE day BETWEEN ? AND ?", (day1, day2))}


def on_duty(c, day):
    """那天有班（照班表）而且沒排休的夥伴；店休日回空的"""
    S = P.settings(c)
    closed = P.is_closed(c, day, S)
    off = offs(c, day, day)
    on, rest = [], []
    for u in c.execute("""SELECT u.id, u.name FROM users u JOIN pay_profile p ON p.user_id=u.id
                          WHERE u.active=1 AND COALESCE(u.demo,0)=0 AND p.punch=1 ORDER BY u.id""").fetchall():
        sched = P.shift_on(P.shifts_of(c, u["id"]), day)
        if not sched: continue
        if (u["id"], day) in off: rest.append(u["name"])
        else: on.append({"name": u["name"], "sched": P.shift_txt(sched)})
    return {"day": day, "closed": closed or "", "on": [] if closed else on, "off": rest}


# ───────────── 推播＋站內通知 ─────────────
class Notifier:
    sender = None          # app 啟動時塞 push.Sender

    @classmethod
    def notify(cls, c, uids, title, body, url="/"):
        uids = sorted({int(u) for u in uids if u})
        for u in uids:
            c.execute("INSERT INTO inbox(user_id,title,body,url,created) VALUES(?,?,?,?,?)", (u, title, body, url, now()))
        c.commit()
        if cls.sender and uids: cls.sender.push(uids, {"title": title, "body": body, "url": url, "tag": url})


def admins(c): return [r[0] for r in c.execute("SELECT id FROM users WHERE role='admin' AND active=1 AND COALESCE(demo,0)=0")]
def managers(c): return [r[0] for r in c.execute("SELECT id FROM users WHERE role='manager' AND active=1 AND COALESCE(demo,0)=0")]
def everyone(c, but=None): return [r[0] for r in c.execute("SELECT id FROM users WHERE active=1 AND COALESCE(demo,0)=0") if r[0] != but]


# ───────────── 帳務同步：老闆核銷後重跑帳務主檔（股東網站跟著更新） ─────────────
_sync_lock = threading.Lock()
DIRTY = {"t": 0.0, "synced": 0.0}


def touch():
    DIRTY["t"] = time.time()


def sync_ledger(db_factory):
    # 只有正式資料庫才同步帳務：測試用暫存資料庫（有設 CRM_DB）絕對不能去重跑帳務主檔、蓋掉股東網站（10/5 晚出過一次事）
    if os.environ.get("CRM_DB"): return

    def run():
        with _sync_lock:
            t0 = time.time(); DIRTY["synced"] = t0
            try:
                r = subprocess.run([sys.executable, "-X", "utf8", LEDGER], cwd=os.path.dirname(LEDGER), capture_output=True, text=True,
                                   timeout=180, encoding="utf-8", errors="replace")
                ok, msg = r.returncode == 0, (r.stdout if r.returncode == 0 else r.stderr)[-600:]
            except Exception as e:
                ok, msg = False, str(e)
            c = db_factory()
            c.execute("INSERT INTO settings(k,v) VALUES('ledger_sync',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                      (json.dumps({"at": now(), "ok": ok, "sec": round(time.time() - t0, 1), "msg": msg}, ensure_ascii=False),))
            c.commit(); c.close()
    if os.path.exists(LEDGER): threading.Thread(target=run, daemon=True).start()


# ───────────── 每天的提醒（背景執行緒，每 30 秒看一次） ─────────────
def once(c, key):
    try:
        c.execute("INSERT INTO jobs_done(k,at) VALUES(?,?)", (key, now())); c.commit(); return True
    except Exception:
        return False


def ai_leads(c, day):
    return [dict(x) for x in c.execute("SELECT * FROM leads WHERE code LIKE ? ORDER BY COALESCE(priority,'')='D', code", ("D" + day.replace("-", "") + "%",))]


def late_reminders(c, day):
    """今天有遲到、明天要上班的夥伴 → 晚上提醒明天準時（回傳發了幾則）"""
    tmr = add_days(day, 1)
    duty_tmr = {d["name"]: d["sched"] for d in on_duty(c, tmr)["on"]}
    n = 0
    for r in P.compute(c, day[:7], today=day):
        lt = [x for x in r["lates"] if x[0] == day]
        if not lt or r["name"] not in duty_tmr: continue
        mins = max(x[3] for x in lt)
        body = "今天上班晚了 %d 分鐘（這個月第 %d 次）。明天 %s 上班，請提早一點到、準時打卡。" % (mins, r["late_n"], duty_tmr[r["name"]].split("／")[0].split("–")[0])
        Notifier.notify(c, [r["id"]], "明天不要遲到喔", body, "/#punch"); n += 1
    return n


def deliv_reminders(c, d, n):
    """外送：派了 5 分鐘沒接受、送達前 45 分還沒開做、前 30 分還沒派人 → 通知老闆和店長（每張每種只提醒一次）"""
    disp = admins(c) + managers(c)
    for r in c.execute("SELECT * FROM deliveries WHERE day=? AND cancelled=0 AND status<>'已送達'", (d,)).fetchall():
        if r["rider_id"] and not r["accepted_at"] and not r["remind_acc"] and r["assigned_at"] and \
                (n - datetime.fromisoformat(r["assigned_at"])).total_seconds() > 300:
            c.execute("UPDATE deliveries SET remind_acc=1 WHERE id=?", (r["id"],)); c.commit()
            Notifier.notify(c, disp, "外送單 5 分鐘沒人接受", "%s：派出去還沒按接受，要不要改派？" % r["customer"], "/#deliv")
        if r["due"]:
            left = (datetime.fromisoformat(d + " " + r["due"]) - n).total_seconds() / 60
            if r["status"] == "新單" and left <= 45 and not r["remind_prep"]:
                c.execute("UPDATE deliveries SET remind_prep=1 WHERE id=?", (r["id"],)); c.commit()
                Notifier.notify(c, disp, "該開始做了：%s" % r["customer"], "%s 要送到，%s 個" % (r["due"], r["boxes"] or "?"), "/#deliv")
            if not r["rider_id"] and left <= 30 and not r["remind_rider"]:
                c.execute("UPDATE deliveries SET remind_rider=1 WHERE id=?", (r["id"],)); c.commit()
                Notifier.notify(c, disp, "還沒派外送：%s" % r["customer"], "%s 要送到，還沒有人送" % r["due"], "/#deliv")


def duty_ids(c, d):
    """今天有班、沒排休的夥伴 id"""
    names = [x["name"] for x in on_duty(c, d)["on"]]
    return [r[0] for r in c.execute("SELECT id FROM users WHERE active=1 AND COALESCE(demo,0)=0 AND name IN (%s)" % ",".join("?" * len(names)), names)] if names else []


def call_hint(c):
    """開發名單現況一句話：A 級還沒聯絡幾筆、今天到期要追蹤幾筆"""
    t = today()
    a = c.execute("SELECT COUNT(*) FROM leads WHERE dnc=0 AND priority='A' AND status IN ('未聯絡','未接')").fetchone()[0]
    f = c.execute("SELECT COUNT(*) FROM leads WHERE dnc=0 AND next_follow IS NOT NULL AND next_follow<=? AND status NOT IN ('已成交','暫無需求')", (t,)).fetchone()[0]
    return "".join(["A 級還有 %d 筆沒聯絡。" % a if a else "", "今天要追蹤 %d 筆。" % f if f else ""])


def cron(db_factory):
    def loop():
        while True:
            c = None
            try:
                c = db_factory(); n = datetime.now(); d = n.date().isoformat(); hm = n.strftime("%H:%M")
                S = P.settings(c); open_today = not P.is_closed(c, d, S)
                # 老闆 10/9：每天都要提醒大家打開發電話 → 09:00 一定推（有 AI 新名單就一起講）；AI 名單晚到另外推一次；
                # 15:45 今天還沒打過的夥伴再提醒一次
                k = len(ai_leads(c, d)) if open_today and "09:00" <= hm < "17:00" else 0
                if open_today and "09:00" <= hm < "17:00" and once(c, "callday:" + d):
                    if k: once(c, "ai:" + d)
                    Notifier.notify(c, duty_ids(c, d) + managers(c), ("今天 AI 新開發 %d 筆，記得打開發電話" % k) if k else "今天記得打開發電話",
                                    call_hint(c) + "到「開發」從最上面開始打，有空檔就打。", "/#crm")
                elif k and once(c, "ai:" + d):
                    Notifier.notify(c, duty_ids(c, d) + admins(c), "今天 AI 新開發 %d 筆電話" % k, "到「開發」最上面看今天新的名單，有空檔就打。", "/#crm")
                if open_today and "15:45" <= hm < "17:00" and once(c, "callpm:" + d):
                    called = {r[0] for r in c.execute("SELECT DISTINCT user_id FROM calls WHERE voided=0 AND substr(at,1,10)=?", (d,))}
                    lazy = [u for u in duty_ids(c, d) if u not in called]
                    if lazy: Notifier.notify(c, lazy, "今天還沒打開發電話", "下午空檔打幾通就好，" + call_hint(c) + "到「開發」從最上面開始。", "/#crm")
                if open_today and hm >= (S.get("late_remind") or "20:30") and once(c, "late:" + d):
                    late_reminders(c, d)
                deliv_reminders(c, d, n)
                if DIRTY["t"] > DIRTY["synced"] and time.time() - DIRTY["synced"] > 600: sync_ledger(db_factory)
                if open_today and hm >= "21:00" and once(c, "fin:" + d):
                    if not c.execute("SELECT 1 FROM fin_day WHERE day=?", (d,)).fetchone():
                        Notifier.notify(c, managers(c), "今天的營收還沒記", "打烊後到「記帳」記今天的營收、拍日結單。", "/#fin")
            except Exception:
                pass
            finally:
                try: c and c.close()
                except Exception: pass
            time.sleep(30)
    threading.Thread(target=loop, daemon=True).start()


# ═════════════ HTTP 路由（mixin） ═════════════
class Ops:
    PHOTO_DIR = None    # app 設定：data/finance、data/delivery

    # ---------- /api/me 多帶的 ----------
    def ops_me(self, c, me):
        out = {"perms": {"admin": is_admin(me), "fin": can_fin(me), "post": can_post(me), "sched": can_sched(me), "rider": bool(me["rider"])},
               "title": me["title"] if "title" in me.keys() else None,
               "inbox_unread": c.execute("SELECT COUNT(*) FROM inbox WHERE user_id=? AND read=0", (me["id"],)).fetchone()[0],
               "notice_unread": c.execute("""SELECT COUNT(*) FROM notices n WHERE n.active=1 AND n.need_ack=1 AND COALESCE(n.created_by,0)<>? AND NOT EXISTS
                   (SELECT 1 FROM notice_ack a WHERE a.notice_id=n.id AND a.user_id=?)""", (me["id"], me["id"])).fetchone()[0],
               "my_deliveries": c.execute("SELECT COUNT(*) FROM deliveries WHERE rider_id=? AND cancelled=0 AND status<>'已送達'", (me["id"],)).fetchone()[0],
               "push_key": getattr(self.server, "vapid_public", "")}
        if can_fin(me) and not is_admin(me):   # 店長：被老闆退回、還沒改的帳
            out["fin_back"] = c.execute("SELECT (SELECT COUNT(*) FROM fin_exp WHERE status='退回' AND removed=0) + (SELECT COUNT(*) FROM fin_day WHERE status='退回')").fetchone()[0]
        if is_admin(me):
            out["pending_fixes"] = c.execute("SELECT COUNT(*) FROM punch_fix f JOIN users u ON u.id=f.user_id WHERE f.status='待審' AND COALESCE(u.demo,0)=0").fetchone()[0]
            out["pending_regs"] = c.execute("SELECT COUNT(*) FROM users WHERE pending=1").fetchone()[0]
            out["fin_pending"] = c.execute("SELECT COUNT(*) FROM fin_exp WHERE status='待核銷' AND removed=0").fetchone()[0]
        return out

    # ---------- GET ----------
    def ops_get(self, c, me, p, q):
        if p == "/api/schedule": return self.send_json(self.schedule(c, me, q.get("month") or today()[:7]))
        if p == "/api/onduty": return self.send_json({"today": on_duty(c, today()), "tomorrow": on_duty(c, add_days(today(), 1))})
        if p == "/api/inbox":
            rows = [dict(x) for x in c.execute("SELECT * FROM inbox WHERE user_id=? ORDER BY id DESC LIMIT 60", (me["id"],))]
            return self.send_json(rows)
        if p == "/api/fin/day":
            if not can_fin(me): return self.err("只有老闆和店長可以記帳", 403)
            return self.send_json(mask_pay(self.fin_day_get(c, q.get("day") or today()), me))
        if p == "/api/fin/list":
            if not can_fin(me): return self.err("只有老闆和店長可以記帳", 403)
            return self.send_json(mask_pay(self.fin_list(c, q.get("month") or today()[:7]), me))
        if p == "/api/fin/photo":
            if not can_fin(me): return self.err("沒有權限", 403)
            if q.get("kind") == "rev":
                r = c.execute("SELECT photo FROM fin_day WHERE day=?", (q.get("day"),)).fetchone()
            else:
                r = c.execute("SELECT photo, category FROM fin_exp WHERE id=?", (int(q.get("id") or 0),)).fetchone()
                if r and r["category"] == "薪資" and not is_admin(me): return self.err("沒有權限", 403)   # 薪資是秘密
            return self.send_file(os.path.join(self.PHOTO_DIR, "finance", r["photo"]) if r and r["photo"] else "", "private, no-cache")
        if p == "/api/deliveries": return self.send_json(self.deliv_list(c, me, q))
        if p == "/api/delivery/photo":
            r = c.execute("SELECT proof, rider_id FROM deliveries WHERE id=?", (int(q.get("id") or 0),)).fetchone()
            if not r or not r["proof"]: return self.err("找不到", 404)
            if not (can_fin(me) or r["rider_id"] == me["id"]): return self.err("沒有權限", 403)
            return self.send_file(os.path.join(self.PHOTO_DIR, "delivery", r["proof"]), "private, no-cache")
        if p == "/api/boss/registrations":
            if not is_admin(me): return self.err("只有老闆可以看", 403)
            return self.send_json([dict(x) for x in c.execute(
                "SELECT id, username, name, phone, position, reg_note, created FROM users WHERE pending=1 ORDER BY id")])
        return NOPE

    # ---------- POST ----------
    def ops_post(self, c, me, p, d):
        if p == "/api/push/subscribe":
            s = d.get("sub") or {}
            if not (s.get("endpoint", "").startswith("https://") and (s.get("keys") or {}).get("p256dh") and s["keys"].get("auth")):
                return self.err("通知設定不完整")
            c.execute("""INSERT INTO push_subs(user_id,endpoint,p256dh,auth,ua,created) VALUES(?,?,?,?,?,?)
                         ON CONFLICT(endpoint) DO UPDATE SET user_id=excluded.user_id, p256dh=excluded.p256dh, auth=excluded.auth, fails=0""",
                      (me["id"], s["endpoint"], s["keys"]["p256dh"], s["keys"]["auth"], (d.get("ua") or "")[:200], now()))
            c.commit(); return self.send_json({"ok": True})
        if p == "/api/push/unsubscribe":
            c.execute("DELETE FROM push_subs WHERE endpoint=? AND user_id=?", ((d.get("endpoint") or ""), me["id"])); c.commit()
            return self.send_json({"ok": True})
        if p == "/api/push/test":
            n = c.execute("SELECT COUNT(*) FROM push_subs WHERE user_id=?", (me["id"],)).fetchone()[0]
            if not n: return self.err("這個帳號還沒有開啟手機通知")
            Notifier.notify(c, [me["id"]], "測試通知", "看到這則，手機通知就設定好了。", "/#me")
            return self.send_json({"ok": True, "devices": n})
        if p == "/api/inbox/read":
            c.execute("UPDATE inbox SET read=1 WHERE user_id=?", (me["id"],)); c.commit(); return self.send_json({"ok": True})
        if p in ("/api/notice/save", "/api/notice/remove"):
            if not can_post(me): return self.err("只有老闆和店長可以發公告", 403)
            return self.notice_save(c, me, d) if p.endswith("save") else self.notice_remove(c, me, d)
        if p in ("/api/schedule/off", "/api/schedule/duty"):
            if not can_sched(me): return self.err("只有老闆和店長可以排班", 403)
            return self.sched_save(c, me, p, d)
        if p.startswith("/api/fin/"):
            if not can_fin(me): return self.err("只有老闆和店長可以記帳", 403)
            return self.fin_post(c, me, p, d)
        if p.startswith("/api/delivery/"): return self.deliv_post(c, me, p, d)
        if p == "/api/boss/registration/decide":
            if not is_admin(me): return self.err("只有老闆可以審核", 403)
            return self.reg_decide(c, me, d)
        return NOPE

    # ═════════ 公告 ═════════
    def notice_save(self, c, me, d):
        title, body = (d.get("title") or "").strip(), (d.get("body") or "").strip()
        if not title or not body: return self.err("標題和內容都要填")
        if d.get("id"):
            n = c.execute("SELECT * FROM notices WHERE id=?", (int(d["id"]),)).fetchone()
            if not n: return self.err("找不到這則公告", 404)
            if not is_admin(me) and n["created_by"] != me["id"]: return self.err("只能改自己發的公告", 403)
            c.execute("UPDATE notices SET title=?, body=?, pinned=?, updated=? WHERE id=?", (title, body, 1 if d.get("pinned") else 0, now(), n["id"]))
            if d.get("reack"):
                c.execute("DELETE FROM notice_ack WHERE notice_id=?", (n["id"],))
                Notifier.notify(c, everyone(c, me["id"]), "公告更新：" + title, body[:80], "/#notice")
        else:
            c.execute("INSERT INTO notices(title,body,pinned,need_ack,created,created_by) VALUES(?,?,?,?,?,?)",
                      (title, body, 1 if d.get("pinned") else 0, 1, now(), me["id"]))
            Notifier.notify(c, everyone(c, me["id"]), "新公告：" + title, body[:80], "/#notice")
        c.commit(); return self.send_json({"ok": True})

    def notice_remove(self, c, me, d):
        n = c.execute("SELECT * FROM notices WHERE id=?", (int(d.get("id") or 0),)).fetchone()
        if not n: return self.err("找不到", 404)
        if not is_admin(me) and n["created_by"] != me["id"]: return self.err("只能下架自己發的公告", 403)
        c.execute("UPDATE notices SET active=0, updated=? WHERE id=?", (now(), n["id"])); c.commit()
        return self.send_json({"ok": True})

    # ═════════ 班表 ═════════
    def schedule(self, c, me, month):
        if not re.fullmatch(r"\d{4}-\d{2}", month): month = today()[:7]
        S = P.settings(c); last = P.month_len(month)
        d1, d2 = month + "-01", "%s-%02d" % (month, last)
        names = {r["id"]: r["name"] for r in c.execute("SELECT id, name FROM users")}
        off = offs(c, d1, d2)
        duty = {}
        for r in c.execute("SELECT * FROM duty WHERE day BETWEEN ? AND ?", (d1, d2)): duty.setdefault(r["day"], []).append(
            {"kind": r["kind"], "user_id": r["user_id"], "name": names.get(r["user_id"], "?")})
        days = []
        for i in range(1, last + 1):
            dd = "%s-%02d" % (month, i)
            days.append({"day": dd, "closed": P.is_closed(c, dd, S) or "",
                         "off": [{"user_id": u, "name": names.get(u, "?"), "note": nt} for (u, x), nt in off.items() if x == dd],
                         "duty": duty.get(dd, [])})
        people = [dict(x) for x in c.execute("""SELECT u.id, u.name FROM users u JOIN pay_profile p ON p.user_id=u.id
                    WHERE u.active=1 AND COALESCE(u.demo,0)=0 AND COALESCE(u.removed,0)=0 AND p.punch=1 ORDER BY u.id""")]
        if can_sched(me):   # 排班的人看得到每天幾個人上班（老闆 10/12：最少 3 人、盡量 4 人）
            for x in days: x["work"] = [] if x["closed"] else self.on_duty(c, x["day"])
        mine = [x["day"] for x in days if any(o["user_id"] == me["id"] for o in x["off"])]
        return {"month": month, "days": days, "people": people, "can_edit": can_sched(me), "mine": mine}

    def sched_save(self, c, me, p, d):
        day = d.get("day") or ""
        if not ymd(day): return self.err("日期不對")
        if p.endswith("/off"):
            uid = int(d.get("user_id") or 0)
            if not c.execute("SELECT 1 FROM users WHERE id=? AND active=1", (uid,)).fetchone(): return self.err("找不到這位夥伴")
            warn = []
            if d.get("on"):
                if P.is_closed(c, day): return self.err("這天店休，不用排休")
                names = {r["id"]: r["name"] for r in c.execute("SELECT id, name FROM users")}
                # 老闆 10/12 排班規則 1：排休不可以兩個人排在同一天（老闆確認後可以強制）
                other = [names.get(r[0], "?") for r in c.execute("SELECT user_id FROM day_off WHERE day=? AND user_id<>?", (day, uid))]
                if other and not (is_admin(me) and d.get("force")):
                    return self.err("一天只能一個人排休：%s 這天已經排休了" % "、".join(other), 409)
                c.execute("INSERT OR REPLACE INTO day_off(user_id,day,note,created_by,created) VALUES(?,?,?,?,?)",
                          (uid, day, (d.get("note") or "").strip(), me["id"], now()))
                warn = self.sched_warn(c, uid, day, names)
            else:
                c.execute("DELETE FROM day_off WHERE user_id=? AND day=?", (uid, day))
            c.commit(); return self.send_json({"ok": True, "warn": warn})
        else:
            kind = (d.get("kind") or "廁所").strip()[:10]
            if d.get("user_id"): c.execute("INSERT OR REPLACE INTO duty(day,kind,user_id) VALUES(?,?,?)", (day, kind, int(d["user_id"])))
            else: c.execute("DELETE FROM duty WHERE day=? AND kind=?", (day, kind))
        c.commit(); return self.send_json({"ok": True})

    def on_duty(self, c, day):
        """這天有班、沒排休的人（店休日＝沒人）"""
        if P.is_closed(c, day): return []
        off = {r[0] for r in c.execute("SELECT user_id FROM day_off WHERE day=?", (day,))}
        out = []
        for u in c.execute("""SELECT u.id, u.name FROM users u JOIN pay_profile p ON p.user_id=u.id
                              WHERE u.active=1 AND COALESCE(u.demo,0)=0 AND COALESCE(u.removed,0)=0 AND p.punch=1 ORDER BY u.id"""):
            if u["id"] not in off and P.shift_on(P.shifts_of(c, u["id"]), day): out.append(u["name"])
        return out

    def sched_warn(self, c, uid, day, names):
        """老闆 10/12 排班規則 2、4：店裡最少 3 人（櫃台、包飯、內場）、盡量 4 人；同一個人的休假不要離太近"""
        md_ = lambda x: "%d/%d" % (int(x[5:7]), int(x[8:]))
        out, n = [], len(self.on_duty(c, day))
        if n < 3: out.append("%s 只剩 %d 人上班，店裡最少要 3 人（櫃台、包飯、內場）" % (md_(day), n))
        elif n == 3: out.append("%s 剩 3 人上班，盡量排 4 人" % md_(day))
        prof = c.execute("SELECT kind, amount, off_days FROM pay_profile WHERE user_id=?", (uid,)).fetchone()
        offn = P.profile_for(c, uid, day[:7], prof)["off_days"] if prof else 0
        if offn:
            every = round(P.month_len(day[:7]) / offn); gap = max(3, every - 1)
            d0 = date.fromisoformat(day)
            near = [r[0] for r in c.execute("SELECT day FROM day_off WHERE user_id=? AND day<>? AND day BETWEEN ? AND ? ORDER BY day",
                                            (uid, day, (d0 - timedelta(days=gap - 1)).isoformat(), (d0 + timedelta(days=gap - 1)).isoformat()))]
            if near:
                out.append("%s 的休假太近：%s 跟 %s 只差 %d 天；月休 %d 天大約每 %d 天休一次，盡量平均分開" % (
                    names.get(uid, "?"), md_(day), "、".join(md_(x) for x in near),
                    min(abs((date.fromisoformat(x) - d0).days) for x in near), offn, every))
        return out

    # ═════════ 記帳（店長記、老闆核銷） ═════════
    def fin_day_get(self, c, day):
        if not ymd(day): day = today()
        r = c.execute("SELECT * FROM fin_day WHERE day=?", (day,)).fetchone()
        exps = [dict(x) for x in c.execute("SELECT * FROM fin_exp WHERE day=? AND removed=0 ORDER BY id", (day,))]
        # 抽屜應有現金：前一筆有點算的日子 → 加這幾天現金營收、扣餐券、加儲值、扣店內現金支出
        prev = c.execute("SELECT day, drawer FROM fin_day WHERE day<? AND drawer IS NOT NULL ORDER BY day DESC LIMIT 1", (day,)).fetchone()
        if (not prev or prev["day"] < DRAWER_BASE[0]) and day > DRAWER_BASE[0]: prev = {"day": DRAWER_BASE[0], "drawer": DRAWER_BASE[1]}
        expect = None
        if r and prev:
            span = [dict(x) for x in c.execute("SELECT * FROM fin_day WHERE day>? AND day<=?", (prev["day"], day))]
            spent = c.execute("SELECT COALESCE(SUM(amount),0) FROM fin_exp WHERE day>? AND day<=? AND removed=0 AND pay='店內現金'",
                              (prev["day"], day)).fetchone()[0]
            took = c.execute("SELECT COALESCE(SUM(amount),0) FROM cash_out WHERE day>? AND day<=? AND removed=0", (prev["day"], day)).fetchone()[0]
            expect = prev["drawer"] + sum((x["cash"] or 0) - (x["voucher"] or 0) + (x["topup"] or 0) for x in span) - spent - took
        return {"day": day, "start": FIN_START, "exp_start": EXP_START, "rev": dict(r) if r else None,
                "log": [dict(x) for x in c.execute("SELECT l.at, l.reason, u.name FROM fin_day_log l LEFT JOIN users u ON u.id=l.user_id WHERE l.day=? ORDER BY l.id DESC", (day,))], "exps": exps, "cats": EXP_CATS,
                "closed": P.is_closed(c, day, P.settings(c)) or "", "expect_drawer": expect, "prev_drawer": dict(prev) if prev else None,
                "float": FLOAT_CASH, "petty_from": PETTY_FROM, "petty": self.petty_state(c),
                "cash_out": [dict(x) for x in c.execute("SELECT * FROM cash_out WHERE day=? AND removed=0 ORDER BY id", (day,))]}

    def petty_state(self, c):
        """零用金＝老闆撥的−從零用金付掉的。其他收入（廢油回收等）不放零用金：先收著、存進銀行後標「已存」（老闆 10/9）"""
        given = c.execute("SELECT COALESCE(SUM(amount),0) FROM petty WHERE removed=0 AND kind<>'收入'").fetchone()[0]
        pend = c.execute("SELECT COALESCE(SUM(amount),0) FROM petty WHERE removed=0 AND kind='收入' AND deposited IS NULL").fetchone()[0]
        spent = c.execute("SELECT COALESCE(SUM(amount),0) FROM fin_exp WHERE removed=0 AND pay='零用金'").fetchone()[0]
        return {"given": given, "pending": pend, "spent": spent, "left": given - spent,
                "rows": [dict(x) for x in c.execute("SELECT * FROM petty WHERE removed=0 AND kind<>'收入' ORDER BY day DESC, id DESC LIMIT 10")],
                "inc_rows": [dict(x) for x in c.execute("SELECT p.*, u.name FROM petty p LEFT JOIN users u ON u.id=p.created_by WHERE p.removed=0 AND p.kind='收入' ORDER BY p.deposited IS NOT NULL, p.day DESC, p.id DESC LIMIT 10")]}

    def fin_list(self, c, month):
        days = {}
        for r in c.execute("SELECT * FROM fin_day WHERE substr(day,1,7)=?", (month,)):
            days.setdefault(r["day"], {"day": r["day"], "rev": None, "exps": []})["rev"] = dict(r)
        for r in c.execute("SELECT * FROM fin_exp WHERE substr(day,1,7)=? AND removed=0 ORDER BY id", (month,)):
            days.setdefault(r["day"], {"day": r["day"], "rev": None, "exps": []})["exps"].append(dict(r))
        sync = c.execute("SELECT v FROM settings WHERE k='ledger_sync'").fetchone()
        rows = sorted(days.values(), key=lambda x: x["day"], reverse=True)
        pend = {}
        for r in c.execute("SELECT * FROM fin_exp WHERE status='待核銷' AND removed=0 ORDER BY day, id"):
            pend.setdefault(r["day"], {"day": r["day"], "rev": None, "exps": []})["exps"].append(dict(r))
        return {"month": month, "days": rows, "sync": json.loads(sync[0]) if sync else None,
                "pending": sorted(pend.values(), key=lambda x: x["day"]),
                "recent_rev": [x["rev"] for x in rows if x["rev"]][:7]}

    def fin_post(self, c, me, p, d):
        day = d.get("day") or ""
        if p == "/api/fin/rev":
            if not ymd(day) or day < FIN_START or day > today(): return self.err("日期要在 %s 到今天之間" % FIN_START)
            cur = c.execute("SELECT * FROM fin_day WHERE day=?", (day,)).fetchone()
            if cur and cur["status"] == "已核銷" and not is_admin(me): return self.err("這天老闆已經確認過，要改請找老闆退回")
            if cur and not is_admin(me) and day < add_days(today(), -7) and cur["status"] != "退回": return self.err("超過 7 天的營收要改請找老闆")
            why = (d.get("reason") or "").strip()
            if cur and cur["status"] != "退回" and not why: return self.err("這天已經記過了，改的話要寫原因（例：現金打錯）")
            f = {k: num(d.get(k), None) for k in ("cash", "stored", "eticket", "orders", "boxes", "voucher", "topup", "drawer")}
            if f["cash"] is None: return self.err("現金一定要填（POS 日結單上的現金）")
            for k in ("stored", "eticket", "voucher", "topup"): f[k] = f[k] or 0
            total = f["cash"] + f["stored"] + f["eticket"]
            photo = cur["photo"] if cur else None
            if d.get("photo"):
                try: photo = save_photo(d["photo"], os.path.join(self.PHOTO_DIR, "finance"), "rev_" + day.replace("-", "") + ("_" + now()[11:19].replace(":", "") if cur else ""))
                except ValueError as e: return self.err(str(e))
            if not photo: return self.err("要拍 POS 日結單照片")
            st = "已入帳"
            if cur:
                c.execute("INSERT INTO fin_day_log(day,at,user_id,reason,before,after) VALUES(?,?,?,?,?,?)",
                          (day, now(), me["id"], why or "退回後修改", json.dumps(dict(cur), ensure_ascii=False), json.dumps(dict(f, photo=photo, total=total), ensure_ascii=False)))
            c.execute("""INSERT INTO fin_day(day,total,cash,stored,eticket,orders,boxes,voucher,topup,drawer,note,photo,status,created_by,created,updated,
                         verified_by,verified_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(day) DO UPDATE SET total=excluded.total, cash=excluded.cash, stored=excluded.stored, eticket=excluded.eticket,
                         orders=excluded.orders, boxes=excluded.boxes, voucher=excluded.voucher, topup=excluded.topup, drawer=excluded.drawer,
                         note=excluded.note, photo=excluded.photo, status=excluded.status, updated=excluded.updated, verified_by=excluded.verified_by,
                         verified_at=excluded.verified_at, verify_note=NULL""",
                      (day, total, f["cash"], f["stored"], f["eticket"], f["orders"], f["boxes"], f["voucher"], f["topup"], f["drawer"],
                       (d.get("note") or "").strip(), photo, st, me["id"], now(), now(), me["id"] if st == "已核銷" else None, now() if st == "已核銷" else None))
            c.commit()
            sync_ledger(self.server.db_factory)
            if not is_admin(me): Notifier.notify(c, admins(c), "店長記了 %d/%d 營收" % (int(day[5:7]), int(day[8:])), "應收 %s，已自動進帳務；不對可以退回。" % format(total, ","), "/#fin")
            return self.send_json({"ok": True, "total": total})
        if p == "/api/fin/exp":
            if not ymd(day) or day > today(): return self.err("日期不對")
            if day < EXP_START: return self.err("%s 以前的支出不在系統裡記（設定檔 exp_start）" % EXP_START)
            cat, item, amt = (d.get("category") or "").strip(), (d.get("item") or "").strip(), num(d.get("amount"))
            if cat not in EXP_CATS: return self.err("請選類別")
            if not item or amt <= 0: return self.err("品項和金額要填")
            cur = c.execute("SELECT * FROM fin_exp WHERE id=?", (int(d["id"]),)).fetchone() if d.get("id") else None
            if cur and cur["status"] == "已核銷" and not is_admin(me): return self.err("這筆老闆已經核銷，要改請找老闆退回")
            if not cur and not d.get("photo"): return self.err("要拍發票、收據或明細")
            if not cur and c.execute("SELECT 1 FROM fin_exp WHERE day=? AND item=? AND amount=? AND removed=0 AND created>=datetime('now','localtime','-2 minutes')",
                                     (day, item, amt)).fetchone(): return self.err("剛剛已經存過一筆一樣的了（同一天、同品項、同金額）")
            st = "已核銷" if is_admin(me) else "待核銷"
            pay = d.get("pay") if d.get("pay") in ("零用金", "店內現金") else (cur["pay"] if cur else ("零用金" if day >= PETTY_FROM else "店內現金"))
            if cur:
                eid = cur["id"]
                c.execute("""UPDATE fin_exp SET day=?, category=?, item=?, vendor=?, amount=?, pay=?, note=?, status=?, updated=?, verified_by=?, verified_at=?,
                             verify_note=NULL WHERE id=?""", (day, cat, item, (d.get("vendor") or "").strip(), amt, pay, (d.get("note") or "").strip(), st, now(),
                                                             me["id"] if st == "已核銷" else None, now() if st == "已核銷" else None, eid))
            else:
                eid = c.execute("""INSERT INTO fin_exp(day,category,item,vendor,amount,pay,note,status,created_by,created,updated,verified_by,verified_at)
                                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (day, cat, item, (d.get("vendor") or "").strip(), amt, pay, (d.get("note") or "").strip(), st, me["id"], now(), now(),
                                 me["id"] if st == "已核銷" else None, now() if st == "已核銷" else None)).lastrowid
            if d.get("photo"):
                try: fn = save_photo(d["photo"], os.path.join(self.PHOTO_DIR, "finance"), "exp_%d" % eid)
                except ValueError as e:
                    if not cur: c.execute("DELETE FROM fin_exp WHERE id=?", (eid,))
                    c.commit(); return self.err(str(e))
                c.execute("UPDATE fin_exp SET photo=? WHERE id=?", (fn, eid))
            c.commit()
            if st == "已核銷": sync_ledger(self.server.db_factory)
            return self.send_json({"ok": True, "id": eid})
        if p == "/api/fin/exp/delete":
            cur = c.execute("SELECT * FROM fin_exp WHERE id=?", (int(d.get("id") or 0),)).fetchone()
            if not cur: return self.err("找不到", 404)
            if cur["status"] == "已核銷" and not is_admin(me): return self.err("已核銷的不能刪，請找老闆")
            c.execute("UPDATE fin_exp SET removed=1, updated=? WHERE id=?", (now(), cur["id"])); c.commit()
            if cur["status"] == "已核銷": sync_ledger(self.server.db_factory)
            return self.send_json({"ok": True})
        if p == "/api/fin/verify":
            if not is_admin(me): return self.err("只有老闆可以核銷", 403)
            ok_, note = bool(d.get("approve")), (d.get("note") or "").strip()
            if not ok_ and not note: return self.err("退回要寫原因，店長才知道要改什麼")
            st = "已核銷" if ok_ else "退回"
            n = 0
            if d.get("kind") in ("rev", "all"):
                n += c.execute("UPDATE fin_day SET status=?, verified_by=?, verified_at=?, verify_note=? WHERE day=?" +
                               (" AND status='待核銷'" if d.get("kind") == "all" else ""), (st, me["id"], now(), note, day)).rowcount
            if d.get("kind") in ("exp", "all"):
                q_ = "UPDATE fin_exp SET status=?, verified_by=?, verified_at=?, verify_note=? WHERE removed=0 AND "
                if d.get("kind") == "all": n += c.execute(q_ + "day=? AND status='待核銷'", (st, me["id"], now(), note, day)).rowcount
                else: n += c.execute(q_ + "id=?", (st, me["id"], now(), note, int(d.get("id") or 0))).rowcount
            c.commit()
            sync_ledger(self.server.db_factory)
            if not ok_: Notifier.notify(c, managers(c), "老闆退回 %d/%d 的帳" % (int(day[5:7]), int(day[8:])) if ymd(day) else "老闆退回一筆帳", note, "/#fin")
            return self.send_json({"ok": True, "n": n})
        if p == "/api/fin/petty":
            # 撥款：只有老闆；其他收入（廢油回收等，等存銀行）：店長、老闆都能記，店長只能刪自己記的、還沒存的
            if d.get("deposit"):
                if not can_fin(me): return self.err("只有老闆和店長可以標", 403)
                r = c.execute("SELECT * FROM petty WHERE id=? AND removed=0 AND kind='收入'", (int(d["deposit"]),)).fetchone()
                if not r: return self.err("找不到這筆")
                if not ymd(day): return self.err("日期不對")
                if day < r["day"]: return self.err("存的日期不能早於收到的日期")
                c.execute("UPDATE petty SET deposited=? WHERE id=?", (None if d.get("undo") else day, r["id"])); c.commit(); sync_ledger(self.server.db_factory)
                if not is_admin(me) and not d.get("undo"):
                    Notifier.notify(c, admins(c), "%s 把%s %s 元存進銀行了" % (me["name"], r["note"] or "其他收入", format(r["amount"], ",")), "%d/%d 存，對存摺時會看到" % (int(day[5:7]), int(day[8:])), "/#fin")
                return self.send_json({"ok": True})
            if d.get("remove"):
                r = c.execute("SELECT * FROM petty WHERE id=? AND removed=0", (int(d["remove"]),)).fetchone()
                if not r: return self.err("找不到這筆")
                if not (is_admin(me) or (can_fin(me) and r["kind"] == "收入" and r["created_by"] == me["id"] and not r["deposited"])):
                    return self.err("只有老闆可以刪" if r["kind"] != "收入" else "只能刪自己記的，其他請找老闆", 403)
                c.execute("UPDATE petty SET removed=1 WHERE id=?", (r["id"],)); c.commit(); sync_ledger(self.server.db_factory); return self.send_json({"ok": True})
            inc = d.get("kind") == "收入"
            if not (can_fin(me) if inc else is_admin(me)): return self.err("只有老闆可以撥零用金" if not inc else "只有老闆和店長可以記", 403)
            amt = num(d.get("amount")); note = (d.get("note") or "").strip()
            if not ymd(day) or not amt: return self.err("日期、金額要填")
            if inc and amt < 0: return self.err("收入金額要是正的")
            if inc and not note: return self.err("寫一下是什麼收入，例：廢油回收")
            c.execute("INSERT INTO petty(day,amount,note,created_by,created,kind) VALUES(?,?,?,?,?,?)", (day, amt, note, me["id"], now(), "收入" if inc else "撥款"))
            c.commit(); sync_ledger(self.server.db_factory)
            if inc:
                if not is_admin(me): Notifier.notify(c, admins(c), "%s記了其他收入 %s 元" % (me["name"], format(amt, ",")), "%s（%d/%d 收，等存銀行）" % (note, int(day[5:7]), int(day[8:])), "/#fin")
            else:
                Notifier.notify(c, managers(c), "老闆撥零用金 %s 元" % format(amt, ","), note or "店裡花費從零用金出，記帳選「零用金」", "/#fin")
            return self.send_json({"ok": True})
        if p == "/api/fin/cashout":
            if d.get("remove"):
                c.execute("UPDATE cash_out SET removed=1 WHERE id=?", (int(d["remove"]),)); c.commit(); return self.send_json({"ok": True})
            amt = num(d.get("amount")); dest = d.get("dest") if d.get("dest") in ("存銀行", "交老闆") else None
            if not ymd(day) or amt <= 0 or not dest: return self.err("日期、金額、去哪裡（存銀行／交老闆）都要填")
            c.execute("INSERT INTO cash_out(day,amount,dest,note,created_by,created) VALUES(?,?,?,?,?,?)", (day, amt, dest, (d.get("note") or "").strip(), me["id"], now()))
            c.commit()
            if not is_admin(me): Notifier.notify(c, admins(c), "營收現金%s %s 元" % (dest, format(amt, ",")), "%s 記的：%s" % (me["name"], d.get("note") or ""), "/#fin")
            return self.send_json({"ok": True})
        if p == "/api/fin/sync":
            if not is_admin(me): return self.err("只有老闆可以", 403)
            sync_ledger(self.server.db_factory); return self.send_json({"ok": True})
        return self.err("not found", 404)

    # ═════════ 外送單（照 Uber Eats／foodpanda：店長派單、夥伴接受、取餐核對、送達證明、現金每班繳回） ═════════
    def _dv(self, r, names):
        x = dict(r); x["rider"] = names.get(r["rider_id"], "") if r["rider_id"] else ""
        x["creator"] = names.get(r["created_by"], ""); x["proof"] = bool(r["proof"])
        x["late_min"] = None
        if r["due"]:
            due = datetime.fromisoformat(r["day"] + " " + r["due"])
            end = datetime.fromisoformat(r["delivered_at"]) if r["delivered_at"] else (None if r["cancelled"] else datetime.now())
            if end: x["late_min"] = int((end - due).total_seconds() // 60)
        x["waiting_accept"] = bool(r["rider_id"] and not r["accepted_at"] and r["status"] != "已送達" and not r["cancelled"])
        return x

    def deliv_list(self, c, me, q):
        day = q.get("day") or today()
        names = {r["id"]: r["name"] for r in c.execute("SELECT id, name FROM users")}
        rows = [self._dv(r, names) for r in c.execute("SELECT * FROM deliveries WHERE day=? AND COALESCE(deleted,0)=0 ORDER BY COALESCE(due,'99:99'), id", (day,))]
        mine = [self._dv(r, names) for r in c.execute("""SELECT * FROM deliveries WHERE rider_id=? AND cancelled=0 AND (status<>'已送達' OR day=?)
                    ORDER BY day, COALESCE(due,'99:99'), id""", (me["id"], day))]
        cash = [dict(x) for x in c.execute("""SELECT d.rider_id, u.name, COUNT(*) n, SUM(COALESCE(d.cash_got,0)) amt, MIN(d.day) since, GROUP_CONCAT(d.id) ids
                    FROM deliveries d JOIN users u ON u.id=d.rider_id WHERE d.status='已送達' AND d.settled=0 AND d.cancelled=0 AND COALESCE(d.cash_got,0)>0
                    GROUP BY d.rider_id""")]
        live = [r for r in rows if not r["cancelled"]]
        done = [r for r in live if r["status"] == "已送達"]
        ontime = [r for r in done if r["late_min"] is not None and r["late_min"] <= 0]
        mins = [(datetime.fromisoformat(r["delivered_at"]) - datetime.fromisoformat(r["picked_at"])).total_seconds() / 60 for r in done if r["picked_at"]]
        prep_late = [r for r in live if r["ready_by"] and r["ready_at"] and r["ready_at"][11:16] > r["ready_by"]]
        busy = {r["rider_id"] for r in live if r["status"] == "配送中"}
        riders = []
        for u in c.execute("SELECT id, name, rider FROM users WHERE active=1 AND COALESCE(demo,0)=0 AND role<>'admin' ORDER BY rider DESC, id"):
            mine_ = [r for r in live if r["rider_id"] == u["id"]]
            riders.append({"id": u["id"], "name": u["name"], "rider": u["rider"],
                           "state": "配送中" if u["id"] in busy else ("有單" if any(r["status"] != "已送達" for r in mine_) else "空閒"),
                           "n": len(mine_), "done": len([r for r in mine_ if r["status"] == "已送達"]),
                           "ontime": len([r for r in mine_ if r["status"] == "已送達" and r["late_min"] is not None and r["late_min"] <= 0]),
                           "cash": sum(x["amt"] for x in cash if x["rider_id"] == u["id"])})
        return {"day": day, "rows": rows, "mine": mine, "cash": cash, "riders": riders, "states": DSTATES, "issues": ISSUES, "handoffs": HANDOFF,
                "stats": {"n": len(live), "done": len(done), "ontime": len(ontime), "avg_min": round(sum(mins) / len(mins)) if mins else None,
                          "boxes": sum(r["boxes"] or 0 for r in live), "prep_late": len(prep_late), "issues": len([r for r in live if r["issue"]]),
                          "cash_due": sum(x["amt"] for x in cash)}}

    def _ev(self, c, did, me, what, note=""):
        c.execute("INSERT INTO delivery_events(delivery_id,at,user_id,what,note) VALUES(?,?,?,?,?)", (did, now(), me["id"], what, note))

    def _owes(self, c, uid):
        """夥伴前一班還沒繳回的現金（今天以前送達、還沒繳）"""
        return c.execute("""SELECT COALESCE(SUM(cash_got),0) FROM deliveries WHERE rider_id=? AND status='已送達' AND settled=0 AND cancelled=0
                            AND COALESCE(cash_got,0)>0 AND (day<? OR delivered_at<=datetime('now','localtime','-3 hours'))""", (uid, today())).fetchone()[0]

    def deliv_post(self, c, me, p, d):
        if p == "/api/delivery/save":
            g = lambda k: (d.get(k) or "").strip() if isinstance(d.get(k), str) else (d.get(k) or "")
            day = g("day") if ymd(g("day")) else today()
            if not g("customer") or not g("address"): return self.err("客人（單位）和地址要填")
            for k in ("due", "ready_by"):
                if g(k) and not hhmm(g(k)): return self.err("時間格式不對")
            boxes, amount, bags = num(d.get("boxes")), num(d.get("amount")), num(d.get("bags"), None)
            pay = g("pay") or "現金收款"
            if pay == "現金收款" and amount <= 0: return self.err("現金收款一定要填金額（客人要付多少），送到才知道要收多少")
            collect = amount if pay == "現金收款" else 0
            rid_new = int(d["rider_id"]) if d.get("rider_id") else None
            vals = (day, g("source") or "電話", g("customer"), g("phone"), g("address"), g("items"), boxes, amount, pay, collect,
                    g("due") or None, g("note"), bags, g("receipt"), g("ready_by") or None, g("part"))
            if d.get("id"):
                r = c.execute("SELECT * FROM deliveries WHERE id=?", (int(d["id"]),)).fetchone()
                if not r: return self.err("找不到", 404)
                if r["status"] == "已送達": return self.err("已送達的單不能改")
                if not can_fin(me) and r["rider_id"] and (pay != r["pay"] or amount != (r["amount"] or 0)):
                    return self.err("派出去以後，付款方式和金額只有店長或老闆能改")
                if not can_fin(me) and r["rider_id"] and rid_new and rid_new != r["rider_id"]:
                    return self.err("這張已經派給別人了，要改派請找店長")
                lab = {"customer": "客人", "phone": "電話", "address": "地址", "items": "品項", "boxes": "個數", "amount": "金額", "pay": "付款", "due": "送達時間",
                       "note": "備註", "bags": "袋數", "receipt": "收據", "ready_by": "出餐時間"}
                newv = dict(zip(("day", "source", "customer", "phone", "address", "items", "boxes", "amount", "pay", "collect", "due", "note", "bags", "receipt", "ready_by", "part"), vals))
                diff = "；".join("%s %s→%s" % (n, r[k] if r[k] not in (None, "") else "空", newv[k] if newv[k] not in (None, "") else "空")
                                for k, n in lab.items() if str(r[k] or "") != str(newv[k] or ""))
                c.execute("""UPDATE deliveries SET day=?, source=?, customer=?, phone=?, address=?, items=?, boxes=?, amount=?, pay=?, collect=?, due=?,
                             note=?, bags=?, receipt=?, ready_by=?, part=? WHERE id=?""", vals + (r["id"],))
                self._ev(c, r["id"], me, "修改", diff); did = r["id"]
            else:
                if c.execute("SELECT 1 FROM deliveries WHERE day=? AND customer=? AND address=? AND cancelled=0 AND created>=datetime('now','localtime','-2 minutes')",
                             (day, g("customer"), g("address"))).fetchone(): return self.err("剛剛已經開過這張單了")
                if rid_new and collect and self._owes(c, rid_new):
                    return self.err("這位夥伴前面還有 %d 元現金沒繳回，先收回再派現金單（或先不派人）" % self._owes(c, rid_new))
                seq = c.execute("SELECT COUNT(*) FROM deliveries WHERE day=?", (day,)).fetchone()[0] + 1
                did = c.execute("""INSERT INTO deliveries(day,source,customer,phone,address,items,boxes,amount,pay,collect,due,note,bags,receipt,ready_by,part,
                                   seq,created,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", vals + (seq, now(), me["id"])).lastrowid
                self._ev(c, did, me, "開單")
            if rid_new and (not d.get("id") or rid_new != r["rider_id"]):      # 沒換人就不要重設「接受」
                if collect and self._owes(c, rid_new):
                    c.commit(); return self.err("單存好了，但這位夥伴前面還有 %d 元現金沒繳回，先收回再派現金單" % self._owes(c, rid_new))
                self._assign(c, me, did, rid_new)
            c.commit(); return self.send_json({"ok": True, "id": did})
        if p == "/api/delivery/settle":       # 每班結束，外送夥伴把收到的現金當面交給店長，店長按「已收」
            if not can_fin(me): return self.err("只有老闆和店長可以收現金", 403)
            rid = int(d.get("rider_id") or 0)
            ids = [int(x) for x in (d.get("ids") or [])]
            if not ids: ids = [r[0] for r in c.execute("SELECT id FROM deliveries WHERE rider_id=? AND status='已送達' AND settled=0 AND cancelled=0", (rid,))]
            rows = c.execute("SELECT id, cash_got FROM deliveries WHERE id IN (%s) AND rider_id=? AND status='已送達' AND settled=0 AND cancelled=0" % ",".join("?" * len(ids)),
                             ids + [rid]).fetchall() if ids else []
            amt = sum(r["cash_got"] or 0 for r in rows)
            if d.get("amount") is not None and num(d.get("amount")) != amt: return self.err("金額對不上（現在是 %d 元），請重新整理再收" % amt)
            c.executemany("UPDATE deliveries SET settled=1, settled_at=?, settled_by=? WHERE id=?", [(now(), me["id"], r["id"]) for r in rows])
            for r in rows: self._ev(c, r["id"], me, "現金收回", str(r["cash_got"] or 0))
            c.commit(); return self.send_json({"ok": True, "n": len(rows), "amount": amt})
        if p == "/api/delivery/uncancel":
            if not can_fin(me): return self.err("只有店長和老闆可以復原", 403)
            r = c.execute("SELECT * FROM deliveries WHERE id=?", (int(d.get("id") or 0),)).fetchone()
            if not r or not r["cancelled"]: return self.err("這張沒有取消")
            c.execute("UPDATE deliveries SET cancelled=0, cancel_reason=NULL WHERE id=?", (r["id"],)); self._ev(c, r["id"], me, "復原取消")
            c.commit(); return self.send_json({"ok": True})
        r = c.execute("SELECT * FROM deliveries WHERE id=? AND COALESCE(deleted,0)=0", (int(d.get("id") or 0),)).fetchone()
        if not r: return self.err("找不到這張外送單", 404)
        if p == "/api/delivery/delete":       # 測試單、開錯的單：店長老闆刪掉（不留在看板、報表、現金）
            if not can_fin(me): return self.err("只有店長和老闆可以刪除", 403)
            c.execute("UPDATE deliveries SET deleted=1, cancelled=1, cancel_reason=COALESCE(cancel_reason,?) WHERE id=?", ((d.get("note") or "刪除").strip(), r["id"]))
            self._ev(c, r["id"], me, "刪除", (d.get("note") or "").strip()); c.commit(); return self.send_json({"ok": True})
        if r["cancelled"] and p != "/api/delivery/copy": return self.err("這張單已取消")
        if p == "/api/delivery/copy":         # 大單拆給兩三位夥伴：複製一張，份數自己改
            cols = ("day", "source", "customer", "phone", "address", "items", "pay", "due", "note", "bags", "receipt", "ready_by")   # 金額、份數拆出來以後自己填
            seq = c.execute("SELECT COUNT(*) FROM deliveries WHERE day=?", (r["day"],)).fetchone()[0] + 1
            nid = c.execute("INSERT INTO deliveries(%s,boxes,amount,collect,part,seq,created,created_by) VALUES(%s,0,0,0,?,?,?,?)" % (
                ",".join(cols), ",".join("?" * len(cols))), tuple(r[k] for k in cols) + ("拆單", seq, now(), me["id"])).lastrowid
            self._ev(c, nid, me, "從 #%d 拆出" % r["seq"]); c.commit(); return self.send_json({"ok": True, "id": nid})
        if p == "/api/delivery/assign":
            if r["status"] == "已送達": return self.err("這張單已經送達了")
            if r["rider_id"] and r["rider_id"] != me["id"] and not can_fin(me): return self.err("這張已經派給別人了，要改派請找店長")
            if d.get("rider_id") and r["collect"] and self._owes(c, int(d["rider_id"])):
                return self.err("這位夥伴前一班還有 %d 元現金沒繳回，先收回再派現金單" % self._owes(c, int(d["rider_id"])))
            self._assign(c, me, r["id"], d.get("rider_id")); c.commit(); return self.send_json({"ok": True})
        if p == "/api/delivery/accept":
            if r["rider_id"] != me["id"]: return self.err("這張不是派給你的")
            if d.get("accept") is False:
                c.execute("UPDATE deliveries SET rider_id=NULL, assigned_at=NULL, accepted_at=NULL WHERE id=?", (r["id"],))
                self._ev(c, r["id"], me, "沒辦法送", (d.get("note") or "").strip())
                Notifier.notify(c, admins(c) + managers(c), "%s 沒辦法送 %s" % (me["name"], r["customer"]), (d.get("note") or "請改派別人").strip(), "/#deliv")
                c.commit(); return self.send_json({"ok": True})
            if r["collect"] and self._owes(c, me["id"]): return self.err("你前一班還有 %d 元現金沒繳回，先交給店長才能接現金單" % self._owes(c, me["id"]))
            c.execute("UPDATE deliveries SET accepted_at=? WHERE id=?", (now(), r["id"])); self._ev(c, r["id"], me, "接受")
            c.commit(); return self.send_json({"ok": True})
        if p == "/api/delivery/delay":        # 出餐延後 5／10／20／30 分，預計送達一起往後
            m = num(d.get("mins"))
            if m not in (5, 10, 20, 30): return self.err("延後分鐘不對")
            sh = lambda t: min((datetime.strptime(t, "%H:%M") + timedelta(minutes=m)).strftime("%H:%M") if (datetime.strptime(t, "%H:%M") + timedelta(minutes=m)).day == 1 else "23:59", "23:59") if t else t
            c.execute("UPDATE deliveries SET ready_by=?, due=?, remind_prep=0, remind_rider=0 WHERE id=?", (sh(r["ready_by"] or datetime.now().strftime("%H:%M")), sh(r["due"]), r["id"]))
            self._ev(c, r["id"], me, "延後 %d 分" % m)
            if r["rider_id"]: Notifier.notify(c, [r["rider_id"]], "出餐延後 %d 分：%s" % (m, r["customer"]), "預計送達改成 %s" % (sh(r["due"]) or "（沒填）"), "/#deliv")
            c.commit(); return self.send_json({"ok": True})
        if p == "/api/delivery/issue":
            kind = d.get("kind") if d.get("kind") in ISSUES else "其他"
            note = (d.get("note") or "").strip()
            c.execute("UPDATE deliveries SET issue=?, issue_at=? WHERE id=?", ("%s%s" % (kind, "：" + note if note else ""), now(), r["id"]))
            self._ev(c, r["id"], me, "問題：" + kind, note)
            Notifier.notify(c, admins(c) + managers(c), "外送問題：%s（%s）" % (kind, r["customer"]), note or "請打給外送夥伴", "/#deliv")
            c.commit(); return self.send_json({"ok": True})
        if p == "/api/delivery/resolve":
            c.execute("UPDATE deliveries SET issue=NULL WHERE id=?", (r["id"],)); self._ev(c, r["id"], me, "問題解決", (d.get("note") or "").strip())
            c.commit(); return self.send_json({"ok": True})
        if p == "/api/delivery/arrive":       # 到點定位打卡：照 Uber Eats／foodpanda 的「已抵達」
            if r["status"] != "配送中": return self.err("取餐出發以後才能到點打卡")
            if r["rider_id"] != me["id"] and not can_fin(me): return self.err("這張派給別人了")
            lat, lng, acc = d.get("lat"), d.get("lng"), d.get("acc")
            S = P.settings(c); dist = None
            if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
                if S.get("store_lat"): dist = int(P.distance_m(lat, lng, float(S["store_lat"]), float(S["store_lng"])))
                note = "距店 %.1f 公里" % (dist / 1000) if dist is not None else "有定位"
                c.execute("UPDATE deliveries SET arrive_at=?, arrive_lat=?, arrive_lng=?, arrive_acc=?, arrive_m=?, arrive_note=NULL WHERE id=?",
                          (now(), lat, lng, acc if isinstance(acc, (int, float)) else None, dist, r["id"]))
            else:
                why = (d.get("why") or "抓不到定位").strip()[:60]
                note = "沒定位：" + why
                c.execute("UPDATE deliveries SET arrive_at=?, arrive_lat=NULL, arrive_lng=NULL, arrive_acc=NULL, arrive_m=NULL, arrive_note=? WHERE id=?",
                          (now(), note, r["id"]))
            self._ev(c, r["id"], me, "到點打卡", note); c.commit()
            return self.send_json({"ok": True, "dist": dist})
        if p == "/api/delivery/near":
            c.execute("UPDATE deliveries SET near_at=COALESCE(near_at,?) WHERE id=?", (now(), r["id"])); self._ev(c, r["id"], me, "快到了")
            c.commit(); return self.send_json({"ok": True})
        if p == "/api/delivery/cancel":
            if not can_fin(me) and not (r["created_by"] == me["id"] and not r["rider_id"]): return self.err("取消要找店長或老闆")
            if r["status"] == "已送達": return self.err("已送達的單不能取消")
            if not (d.get("note") or "").strip(): return self.err("取消要寫原因")
            c.execute("UPDATE deliveries SET cancelled=1, cancel_reason=? WHERE id=?", (d["note"].strip(), r["id"]))
            self._ev(c, r["id"], me, "取消", d["note"].strip())
            if r["rider_id"] and r["rider_id"] != me["id"]: Notifier.notify(c, [r["rider_id"]], "外送單取消：%s" % r["customer"], d["note"].strip(), "/#deliv")
            c.commit(); return self.send_json({"ok": True})
        if p == "/api/delivery/cash_ok":      # 實收和應收不一樣，店長核可
            if not can_fin(me): return self.err("只有老闆和店長可以核可", 403)
            c.execute("UPDATE deliveries SET cash_ok_by=? WHERE id=?", (me["id"], r["id"])); self._ev(c, r["id"], me, "核可收款差額")
            c.commit(); return self.send_json({"ok": True})
        if p == "/api/delivery/status":
            to = d.get("to")
            if to not in DSTATES: return self.err("狀態不對")
            if DSTATES.index(to) <= DSTATES.index(r["status"]) and not can_fin(me): return self.err("不能往回改，請找店長")
            sets, args = ["status=?"], [to]
            col = {"新單": "created", "製作中": "prep_at", "已出餐": "ready_at", "配送中": "picked_at", "已送達": "delivered_at"}[to]
            sets.append(f"{col}=COALESCE({col},?)"); args.append(now())
            if to == "配送中":
                ck = d.get("checked") or {}
                need = ["品項份數", "袋數", "餐具", "湯和飲料"] + (["收據"] if r["receipt"] else [])
                if not all(ck.get(k) for k in need): return self.err("取餐前要逐項核對：" + "、".join(k for k in need if not ck.get(k)))
                sets.append("checked=?"); args.append(json.dumps(ck, ensure_ascii=False))
                if not r["rider_id"]:
                    sets += ["rider_id=?", "assigned_at=?", "accepted_at=?"]; args += [me["id"], now(), now()]
                elif r["rider_id"] != me["id"] and not can_fin(me): return self.err("這張派給別人了")
            if to == "已送達":
                if r["rider_id"] != me["id"] and not can_fin(me): return self.err("這張不是派給你的")
                if not r["arrive_at"] and not can_fin(me): return self.err("先按「到了・定位打卡」，再按已送達")
                ho = d.get("handoff") if d.get("handoff") in HANDOFF else "交給本人"
                if isinstance(d.get("lat"), (int, float)) and isinstance(d.get("lng"), (int, float)):
                    sets += ["drop_lat=?", "drop_lng=?"]; args += [d["lat"], d["lng"]]
                if ho != "交給本人" and not d.get("photo"): return self.err("放櫃台、門口或交管理室，一定要拍照（拍餐點和門牌或招牌，不要拍到人臉）")
                if d.get("photo"):
                    try: fn = save_photo(d["photo"], os.path.join(self.PHOTO_DIR, "delivery"), "d%d" % r["id"])
                    except ValueError as e: return self.err(str(e))
                    sets.append("proof=?"); args.append(fn)
                got = num(d.get("cash_got"), r["collect"]) if r["collect"] else 0
                sets += ["handoff=?", "cash_got=?"]; args += [ho, got]
                if r["collect"] and got != r["collect"]:
                    Notifier.notify(c, admins(c) + managers(c), "收款跟單上不一樣：%s" % r["customer"], "應收 %d，實收 %d，請核可" % (r["collect"], got), "/#deliv")
            c.execute("UPDATE deliveries SET %s WHERE id=?" % ", ".join(sets), args + [r["id"]])
            self._ev(c, r["id"], me, to, (d.get("note") or "").strip())
            if to == "已出餐" and r["rider_id"]:
                Notifier.notify(c, [r["rider_id"]], "便當好了，可以來取餐", "%s · %s 個%s" % (r["customer"], r["boxes"] or "?", "、%s 袋" % r["bags"] if r["bags"] else ""), "/#deliv")
            c.commit(); return self.send_json({"ok": True})
        return self.err("not found", 404)

    def _assign(self, c, me, did, rider_id):
        rid = int(rider_id) if rider_id else None
        c.execute("UPDATE deliveries SET rider_id=?, assigned_at=?, accepted_at=?, remind_acc=0 WHERE id=?",
                  (rid, now() if rid else None, now() if rid == me["id"] else None, did))
        r = c.execute("SELECT * FROM deliveries WHERE id=?", (did,)).fetchone()
        self._ev(c, did, me, "派給 %s" % (c.execute("SELECT name FROM users WHERE id=?", (rid,)).fetchone()[0] if rid else "（取消指派）"))
        if rid and rid != me["id"]:
            Notifier.notify(c, [rid], "新外送單：%s" % r["customer"], "%s送達 · %s 個 · %s　請打開按「接受」" % (
                (r["due"] + " ") if r["due"] else "", r["boxes"] or "?", r["address"]), "/#deliv")

    # ═════════ 新夥伴註冊 ═════════
    def reg_decide(self, c, me, d):
        u = c.execute("SELECT * FROM users WHERE id=? AND pending=1", (int(d.get("id") or 0),)).fetchone()
        if not u: return self.err("這筆已經處理過了")
        if d.get("approve"):
            rl = d.get("role") if d.get("role") in ("staff", "manager") else "staff"
            c.execute("UPDATE users SET pending=0, active=1, role=?, rider=? WHERE id=?", (rl, 1 if d.get("rider") else 0, u["id"]))
        else:
            c.execute("UPDATE users SET pending=0, active=0, username=username||'#退回'||id WHERE id=?", (u["id"],))
        c.execute("INSERT INTO audit(at,user_id,action,detail) VALUES(?,?,?,?)", (now(), me["id"], "註冊審核", "%s %s" % (u["username"], "核准" if d.get("approve") else "退回")))
        c.commit(); return self.send_json({"ok": True})


def register(c, d, ip, rate):
    """沒登入也能呼叫：新夥伴自己註冊，等老闆審核"""
    t = time.time()
    rate[ip] = [x for x in rate.get(ip, []) if t - x < 3600]
    if len(rate[ip]) >= 5: return "這台裝置一小時內註冊太多次，請晚點再試", None
    name, un, pw = (d.get("name") or "").strip(), (d.get("username") or "").strip().lower(), d.get("password") or ""
    if not name: return "請填名字", None
    if not re.fullmatch(r"[a-z0-9_.-]{3,20}", un): return "帳號用 3–20 個英文小寫、數字（可以用 _ . -）", None
    if len(pw) < 6: return "密碼至少 6 碼", None
    if pw.lower() == un: return "密碼不能跟帳號一樣", None
    if c.execute("SELECT 1 FROM users WHERE lower(username)=?", (un,)).fetchone(): return "這個帳號已經有人用了，換一個", None
    import app as A
    uid = c.execute("""INSERT INTO users(username,name,pw,role,active,target,created,pending,phone,position,reg_note,must_change)
                       VALUES(?,?,?,'staff',0,50,?,1,?,?,?,0)""",
                    (un, name[:20], A.hash_pw(pw), now(), (d.get("phone") or "").strip()[:20], (d.get("position") or "").strip()[:10],
                     (d.get("note") or "").strip()[:200])).lastrowid
    rate[ip].append(t)
    c.commit()
    Notifier.notify(c, admins(c), "新夥伴註冊：%s" % name, "應徵 %s，等你審核。到「老闆 › 帳號」核准。" % ((d.get("position") or "").strip() or "（沒寫）"), "/#boss")
    return None, uid
