# -*- coding: utf-8 -*-
"""考勤與算薪核心：員工系統、老闆頁、股東帳務頁共用同一套。

規則（預設值依《勞動基準法》整理，參數在 config/labor_rules.toml，原則上仍請自行依最新法規核對）
- 工時以打卡為準：每天的打卡依時間排序，上班→下班配成一段；缺一邊的那段不算，列成「漏打卡」給老闆補登。
- 月薪制：應上班分鐘＝(當月天數−表定月休−當月國定假日)×480；平日正常工時做滿給全額月薪，
  沒做滿（例如請事假）依出勤分鐘比例計；平日正常工時超過應上班時數的部分，依每小時工資額加給。
  每小時工資額＝月薪÷240（月薪÷30÷8）。
- 時薪制：時薪×平日正常工時分鐘÷60。
- 固定月薪（不打卡的管理職）：月薪全額，不計加班。
- 平日延長工時（第 24 條第 1 項）：每天超過 8 小時，前 2 小時 ×1.34、再 2 小時 ×1.67；超過 12 小時標警告。
- 休息日出勤（第 24 條第 2 項）：每週（週一到週日）第 6 個出勤日視為休息日，前 2 小時 ×1.34、第 3–8 小時 ×1.67、第 9 小時起 ×2.67。
- 例假日：每週第 7 個出勤日標「例假出勤」警告（第 36、40 條原則上不得出勤），工資加倍。
- 國定假日出勤（第 39 條）：工資加倍發給（月薪制另加給一倍；時薪制給兩倍）。
- 公休日有打卡：照實際工時計薪，另標示給老闆確認（有做事就要給薪）。
- 遲到：遲到的分鐘本來就不算工時（＝依實際分鐘比例），不另外罰扣；晚超過設定分鐘標「需確認」，不自動扣錢。
- 勞保、健保自付額：依每人薪資設定填的金額扣；雇主勞退提繳 6% 只顯示、不從薪水扣。
- 預支：記在哪個月的薪資扣（pay_month），扣到應發為止，沒扣完的定案時轉下個月。
- 老闆調整（加或減）一律寫原因，算在實發裡。
- 基本工資：低於 labor_rules.toml 設定的當年度基本工資，老闆頁會警示。
"""
import calendar
import json
import math
from datetime import date, timedelta

import cfg

L = cfg.LABOR
DEFAULTS = {"radius": "150", "weekly_closed": "", "absent_over": str(L.get("late", {}).get("absent_over_minutes", 10)),
            "store_lat": "", "store_lng": "", "max_acc": "300"}
WEEK = "一二三四五六日"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pay_profile(user_id INTEGER PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'monthly',
  amount INTEGER NOT NULL DEFAULT 0, off_days INTEGER NOT NULL DEFAULT 8, punch INTEGER NOT NULL DEFAULT 1, note TEXT, updated TEXT,
  li_self INTEGER NOT NULL DEFAULT 0, hi_self INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS shifts(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, effective TEXT NOT NULL,
  s1 TEXT, e1 TEXT, s2 TEXT, e2 TEXT, note TEXT, created TEXT, created_by INTEGER);
CREATE TABLE IF NOT EXISTS punches(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'phone', lat REAL, lng REAL, acc REAL, dist INTEGER, note TEXT, created TEXT, created_by INTEGER,
  voided INTEGER NOT NULL DEFAULT 0, void_by INTEGER, void_at TEXT, void_reason TEXT);
CREATE INDEX IF NOT EXISTS ix_punch_user_at ON punches(user_id, at);
CREATE TABLE IF NOT EXISTS punch_fix(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL,
  time TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT '待審', created TEXT, decided_by INTEGER,
  decided_at TEXT, decide_note TEXT, punch_id INTEGER);
CREATE TABLE IF NOT EXISTS advances(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, day TEXT NOT NULL, amount INTEGER NOT NULL,
  note TEXT, created TEXT, created_by INTEGER, voided INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS adjustments(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, month TEXT NOT NULL, amount INTEGER NOT NULL,
  reason TEXT NOT NULL, created TEXT, created_by INTEGER, voided INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS closed_days(day TEXT PRIMARY KEY, reason TEXT);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS pay_month(month TEXT PRIMARY KEY, status TEXT NOT NULL, at TEXT, by_user INTEGER, paid_on TEXT);
-- 定案／已發薪時把算好的結果整份存起來：之後補登、調薪、停用都不會改到已經發出去的數字
CREATE TABLE IF NOT EXISTS pay_hist(user_id INTEGER NOT NULL, until_month TEXT NOT NULL, kind TEXT, amount INTEGER, off_days INTEGER, note TEXT, created TEXT,
    PRIMARY KEY(user_id, until_month));
CREATE TABLE IF NOT EXISTS pay_snapshot(month TEXT PRIMARY KEY, rows TEXT NOT NULL, at TEXT);
"""
LOCKED = ("已定案", "已發薪")


def _int(v, d):
    try: return int(str(v).strip())
    except Exception: return d


def is_locked(c, month):
    try: r = c.execute("SELECT status FROM pay_month WHERE month=?", (month,)).fetchone()
    except Exception: return False
    return bool(r and r[0] in LOCKED)


def month_rows(c, month, today=None):
    """已定案／已發薪的月份讀快照；其他月份即時算"""
    if is_locked(c, month):
        try:
            r = c.execute("SELECT rows FROM pay_snapshot WHERE month=?", (month,)).fetchone()
            if r: return json.loads(r[0])
        except Exception:
            pass
    return compute(c, month, today=today)


def next_month(month):
    y, m = int(month[:4]), int(month[5:]) + 1
    return "%d-%02d" % (y + (m > 12), m - 12 if m > 12 else m)


def lock_month(c, month, by):
    """定案：存快照＋預支沒扣完的結轉到下個月 1 日"""
    unlock_month(c, month)
    rows = compute(c, month)
    c.execute("INSERT OR REPLACE INTO pay_snapshot(month,rows,at) VALUES(?,?,datetime('now','localtime'))", (month, json.dumps(rows, ensure_ascii=False)))
    for r in rows:
        if r["adv_left"] > 0:
            c.execute("INSERT INTO advances(user_id,day,amount,note,created,created_by,pay_month) VALUES(?,?,?,?,datetime('now','localtime'),?,?)",
                      (r["id"], next_month(month) + "-01", r["adv_left"], "【結轉 %s】上個月預支沒扣完的" % month, by, next_month(month)))
    return rows


def unlock_month(c, month):
    c.execute("DELETE FROM pay_snapshot WHERE month=?", (month,))
    c.execute("UPDATE advances SET voided=1 WHERE voided=0 AND note LIKE ?", ("【結轉 %s】%%" % month,))


def guess_kind(c, uid, day, now_hm):
    """這一下是上班還是下班：看今天最後一筆＋班表。上一筆是上班、而且是早班那段，現在已經過了午休中間 → 當成忘了打下班，這次算上班"""
    ps = c.execute("SELECT at, kind FROM punches WHERE user_id=? AND voided=0 AND substr(at,1,10)=? ORDER BY at", (uid, day)).fetchall()
    if not ps:
        last = c.execute("SELECT at, kind FROM punches WHERE user_id=? AND voided=0 AND at<? ORDER BY at DESC LIMIT 1", (uid, day)).fetchone()
        if last and last["kind"] == "in" and _gap_h(last["at"], day + " " + now_hm + ":00") <= OVERNIGHT_H:
            return "out"           # 跨午夜的班：昨晚上班，現在（凌晨）下班
        return "in"
    if ps[-1]["kind"] == "out":
        return "in"
    t0 = hm(ps[-1]["at"][11:16]); n = hm(now_hm)
    sched = shift_on(shifts_of(c, uid), day)
    for i in range(len(sched) - 1):
        e1, s2 = hm(sched[i][1]), hm(sched[i + 1][0])
        if t0 < e1 and n >= (e1 + s2) // 2:
            return "in"
    return "out"



def migrate(c):
    """舊資料庫補勞健保自付額欄位"""
    cols = {r[1] for r in c.execute("PRAGMA table_info(pay_profile)")}
    for col in ("li_self", "hi_self"):
        if col not in cols:
            c.execute("ALTER TABLE pay_profile ADD COLUMN %s INTEGER NOT NULL DEFAULT 0" % col)


def settings(c):
    s = dict(DEFAULTS)
    for r in c.execute("SELECT k, v FROM settings"):
        s[r[0]] = r[1]
    return s


def hm(t):
    h, m = t.split(":")[:2]
    return int(h) * 60 + int(m)


def month_len(month):
    y, m = map(int, month.split("-"))
    return calendar.monthrange(y, m)[1]


def is_closed(c, day, S=None):
    S = S or settings(c)
    wd = date.fromisoformat(day).weekday()
    if str(wd) in (S.get("weekly_closed") or "").split(","):
        return "每週公休"
    r = c.execute("SELECT reason FROM closed_days WHERE day=?", (day,)).fetchone()
    return (r[0] or "公休") if r else ""


def distance_m(lat1, lng1, lat2, lng2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(2 * R * math.asin(math.sqrt(a)))


def shifts_of(c, uid):
    return [dict(x) for x in c.execute("SELECT * FROM shifts WHERE user_id=? ORDER BY effective, id", (uid,))]


def shift_on(shifts, day):
    cur = None
    for s in shifts:
        if s["effective"] <= day:
            cur = s
    if not cur:
        return []
    wk = cur.get("days")          # 一週哪幾天有班（0=週一 … 6=週日，逗號分開）；空的＝每天
    if wk and str(date.fromisoformat(day).weekday()) not in wk.split(","):
        return []
    return [(a, b) for a, b in ((cur["s1"], cur["e1"]), (cur["s2"], cur["e2"])) if a and b]


def shift_txt(sched):
    return "／".join("%s–%s" % (a, b) for a, b in sched) or "沒有排班"


OVERNIGHT_H = 16      # 上班卡到隔天下班卡最多隔幾小時，還算同一班（跨午夜的班：夜市、宵夜、24 小時店）
CHAIN_BREAK_H = 2     # 夜班中間休息最多幾小時，休息後那段還算同一班


def _gap_h(a, b):
    from datetime import datetime as _dt
    return (_dt.strptime(b[:19], "%Y-%m-%d %H:%M:%S") - _dt.strptime(a[:19], "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600


def stitch_overnight(byday, before=None, after=None):
    """byday：{日期: [打卡...]}（依時間排序）。跨午夜的班：前一天最後一筆是上班、隔天第一筆是下班、相隔 OVERNIGHT_H 小時內
    → 把那筆下班卡移到前一天（工時算在上班那天），標 overnight。
    before：上個月最後一筆打卡（判斷本月 1 號凌晨那筆下班卡是不是上個月的）；after：下個月 1 號的打卡（本月最後一天的夜班）"""
    days = sorted(byday)
    out = {d: [dict(p) for p in byday[d]] for d in days}

    def chain(tail, last_out_at):
        """夜班中間休息後的下一段（休息 CHAIN_BREAK_H 小時內又上班、而且有下班卡）也是同一班：一起拿走"""
        got = []
        while len(tail) >= 2 and tail[0]["kind"] == "in" and tail[1]["kind"] == "out" and _gap_h(last_out_at, tail[0]["at"]) <= CHAIN_BREAK_H:
            a, b = tail.pop(0), tail.pop(0)
            got += [a, b]
            last_out_at = b["at"]
        return got

    if before and dict(before)["kind"] == "in" and days:
        first = out[days[0]]
        if first and first[0]["kind"] == "out" and _gap_h(dict(before)["at"], first[0]["at"]) <= OVERNIGHT_H:
            p = first.pop(0)                                  # 這筆是上個月最後一天夜班的下班卡，算在上個月
            chain(first, p["at"])
    nxt = [dict(p) for p in (after or [])]
    for i, d in enumerate(days):
        cur = out[d]
        if not cur or cur[-1]["kind"] != "in":
            continue
        tail = out.get(days[i + 1]) if i + 1 < len(days) and days[i + 1] == _next_day(d) else None
        if tail is None and i == len(days) - 1:
            tail = nxt
        if tail and tail[0]["kind"] == "out" and _gap_h(cur[-1]["at"], tail[0]["at"]) <= OVERNIGHT_H:
            p = tail.pop(0)
            moved = [p] + chain(tail, p["at"])
            for x in moved:
                x["overnight"] = True                          # 隔天的時間，工時算在上班那天
            cur.extend(moved)
    return {d: v for d, v in out.items() if v}


def _next_day(d):
    from datetime import date as _d, timedelta as _td
    return (_d.fromisoformat(d) + _td(days=1)).isoformat()


def pair_day(ps, ongoing=False):
    """ps：當天打卡（依時間排序）→ 段落 [(上, 下, 分鐘)]、所有上班時間、問題、還開著的上班時間"""
    segs, ins, issues, open_in, open_m = [], [], [], None, 0
    for p in ps:
        t = p["at"][11:16]
        nxt = isinstance(p, dict) and p.get("overnight")        # 跨午夜接過來的打卡：時間是隔天的
        label, minute = ("隔天 " + t if nxt else t), hm(t) + (1440 if nxt else 0)
        if p["kind"] == "in":
            if open_in:
                issues.append("%s 上班後沒打下班卡" % open_in)
            open_in, open_m = label, minute
            ins.append(t)
        else:
            if not open_in:
                issues.append("%s 下班前沒打上班卡" % label)
                continue
            segs.append((open_in, label, max(0, minute - open_m)))
            open_in = None
    if open_in and not ongoing:
        issues.append("%s 上班後沒打下班卡" % open_in)
    return segs, ins, issues, (open_in if ongoing else None)


def lates_of(ins, sched):
    """每個上班時間對到最接近的班（兩小時內），晚於表定就算一次：[(打卡, 表定, 晚幾分)]"""
    out, used = [], set()
    for a in ins:
        best = None
        for i, (s, _e) in enumerate(sched):
            if i in used:
                continue
            d = abs(hm(a) - hm(s))
            inside = hm(s) <= hm(a) < hm(_e)
            if (d <= 120 or inside) and (best is None or d < best[1]):
                best = (i, d)
        if best is None:
            continue
        used.add(best[0])
        s = sched[best[0]][0]
        if hm(a) > hm(s):
            out.append((a, s, hm(a) - hm(s)))
    return out


def mode_text(kind, amount, full, rate, ongoing=False):
    # 老闆 10/12：「未來都不要顯示單位時薪多少錢」——任何畫面、單子都不寫時薪數字
    if kind == "hourly":
        return "時薪制"
    if kind == "fixed":
        return "固定月薪"
    if ongoing:
        return "月中試算：照打卡分鐘"
    if full:
        return "做滿應做時數，多做的照單位時薪加給"
    return "沒做滿應做時數，照打卡分鐘"


def profile_for(c, uid, month, cur):
    """薪資設定分月生效（老闆 10/13：Sakura 10 月起月休 5 天、11 月起加薪）：
    pay_hist 每一列＝「until_month（含）以前照這組設定」；找 until_month ≥ 這個月、最早的那列，沒有就用現在的 pay_profile"""
    cur = dict(cur)
    try: h = c.execute("SELECT kind, amount, off_days FROM pay_hist WHERE user_id=? AND until_month>=? ORDER BY until_month LIMIT 1", (uid, month)).fetchone()
    except Exception: h = None
    if h:
        for i, k in enumerate(("kind", "amount", "off_days")):
            if h[i] is not None: cur[k] = h[i]
    return cur


# ---------------- 勞基法計薪（純函式，方便單元測試） ----------------
def holidays(year):
    h = L.get("holiday", {})
    return set(h.get("dates_%d" % int(year), [])) if h.get("enabled", True) else set()


def min_wage(year):
    mw = L.get("minimum_wage", {})
    keys = sorted(int(k) for k in mw if str(k).isdigit())
    if not keys:
        return {}
    use = [k for k in keys if k <= int(year)]
    return mw.get(str(use[-1] if use else keys[0]), {})


def _tiers(m, tiers):
    """m 分鐘依 [(分鐘上限, 倍率), ...] 分段：回傳 Σ 分鐘×倍率"""
    out, prev = 0.0, 0
    for cap, rate in tiers:
        seg = max(0, min(m, cap) - prev)
        out += seg * rate
        prev = cap
        if m <= cap:
            break
    return out


def classify_days(worked_days, hol):
    """worked_days：有出勤的日期（可含上個月最後 6 天，用來算跨月的那一週）
    回傳 {日期: normal／rest／regular_off／holiday}；每週（週一～週日）第 6 個出勤日＝休息日、第 7 個＝例假"""
    out, count = {}, {}
    rest_on = L.get("rest_day", {}).get("enabled", True)
    for d in sorted(set(worked_days)):
        dd = date.fromisoformat(d)
        wk = (dd - timedelta(days=dd.weekday())).isoformat()
        count[wk] = count.get(wk, 0) + 1
        if d in hol:
            out[d] = "holiday"
        elif rest_on and count[wk] == 6:
            out[d] = "rest"
        elif rest_on and count[wk] >= 7:
            out[d] = "regular_off"
        else:
            out[d] = "normal"
    return out


def legal_pay(kind, amount, off_days, month, day_mins, prev_days=()):
    """kind：monthly／hourly／fixed；day_mins：{日期: 當天工作分鐘}（只含本月）；prev_days：上個月最後 6 天有出勤的日期
    回傳 dict：reg_mins, base_reg, extra_reg, ot_pay, rest_pay, hol_pay, gross, hourly_rate, need, full, flags, detail"""
    ot = L.get("overtime", {})
    rd = L.get("rest_day", {})
    reg_cap = ot.get("daily_regular_minutes", 480)
    ot_tiers = [(120, ot.get("first_2h_rate", 1.34)), (10 ** 9, ot.get("next_2h_rate", 1.67))]
    rest_tiers = [(120, rd.get("first_2h_rate", 1.34)), (480, rd.get("next_6h_rate", 1.67)), (10 ** 9, rd.get("over_8h_rate", 2.67))]
    day_max = ot.get("daily_max_minutes", 720)
    y = int(month[:4])
    ml = month_len(month)
    hol = holidays(y)
    if kind == "fixed":
        return dict(reg_mins=0, base_reg=amount, extra_reg=0, ot_pay=0, rest_pay=0, hol_pay=0, gross=amount, hourly_rate=0, need=None,
                    full=True, flags=[], detail={}, ot_mins=0, rest_mins=0, hol_mins=0)
    if kind == "hourly":
        per_min = amount / 60.0
    else:
        per_min = amount / float(L.get("monthly", {}).get("hourly_divisor", 240)) / 60.0
    kinds = classify_days([d for d, m in day_mins.items() if m > 0] + list(prev_days), hol)
    reg_mins = ot_w = rest_w = hol_w = 0.0
    ot_mins = rest_mins = hol_mins = 0
    flags, detail = [], {}
    for d, m in sorted(day_mins.items()):
        if m <= 0:
            continue
        k = kinds.get(d, "normal")
        detail[d] = k
        if m > day_max:
            flags.append("%s 工作 %d 分鐘，超過一日 %d 小時上限" % (d, m, day_max // 60))
        if k == "rest":
            rest_w += _tiers(m, rest_tiers)
            rest_mins += m
        elif k in ("holiday", "regular_off"):
            if k == "regular_off":
                flags.append("%s 是這週第 7 個出勤日（例假），原則上不得出勤，請確認" % d)
            base = min(m, reg_cap)
            hol_w += base * (2.0 if kind == "hourly" else 1.0)   # 時薪：兩倍；月薪：月薪已含當天，另加給一倍
            ot_w += _tiers(m - base, ot_tiers)
            hol_mins += m
        else:
            reg_mins += min(m, reg_cap)
            if m > reg_cap:
                ot_w += _tiers(m - reg_cap, ot_tiers)
                ot_mins += m - reg_cap
    need, full, extra_reg = None, False, 0
    if kind == "hourly":
        base_reg = int(round(per_min * reg_mins))
    else:
        hol_in_month = sum(1 for h in hol if h.startswith(month))
        wd = max(1, ml - (off_days or 0) - hol_in_month)
        need = wd * reg_cap
        full = reg_mins >= need
        base_reg = amount if full else int(amount * reg_mins // need)
        extra_reg = int(round(per_min * (reg_mins - need))) if full else 0
    ot_pay, rest_pay, hol_pay = int(round(per_min * ot_w)), int(round(per_min * rest_w)), int(round(per_min * hol_w))
    gross = base_reg + extra_reg + ot_pay + rest_pay + hol_pay
    if kind == "monthly" and (off_days or 0) < ml * 2 // 7:
        flags.append("表定月休 %d 天，少於每週兩天（一例一休）約 %d 天" % (off_days or 0, ml * 2 // 7))
    mw = min_wage(y)
    if kind == "monthly" and mw.get("monthly") and amount < mw["monthly"]:
        flags.append("月薪 %s 低於 %d 年基本工資 %s（部分工時請改用時薪制）" % (format(amount, ","), y, format(mw["monthly"], ",")))
    if kind == "hourly" and mw.get("hourly") and amount < mw["hourly"]:
        flags.append("時薪 %d 低於 %d 年基本工資時薪 %d" % (amount, y, mw["hourly"]))
    return dict(reg_mins=int(reg_mins), base_reg=base_reg, extra_reg=extra_reg, ot_pay=ot_pay, rest_pay=rest_pay, hol_pay=hol_pay, gross=gross,
                hourly_rate=round(per_min * 60, 2), need=need, full=full, flags=flags, detail=detail,
                ot_mins=ot_mins, rest_mins=rest_mins, hol_mins=hol_mins)


def break_flags(day, segs):
    """勞基法第 35 條：休息不到 30 分鐘的兩段算同一段；同一段連續超過 4 小時（加容許誤差）就提醒"""
    rb = L.get("rest_break", {})
    after, gap_min, tol = rb.get("after_minutes", 240), rb.get("min_break_minutes", 30), rb.get("tolerance_minutes", 15)
    out, block, last_end = [], 0, None
    for a, b, m in segs:
        start = hm(a[-5:]) + (1440 if a.startswith("隔天") else 0)
        if last_end is not None and start - last_end < gap_min:
            block += m + (start - last_end)
        else:
            block = m
        last_end = hm(b[-5:]) + (1440 if b.startswith("隔天") else 0)
        if block > after + tol:
            out.append("%s 連續工作 %d 分鐘沒有休息，超過 %d 小時應有 %d 分鐘休息（第 35 條）" % (day, block, after // 60, gap_min))
            block = -10 ** 6          # 同一段只提醒一次
    return out


def compute(c, month, today=None, only_uid=None):
    """當月每個有薪資設定的人：工時、應發（含加班、休息日、國定假日）、勞健保自付、預支、調整、實發、逐日明細、問題"""
    S = settings(c)
    today = today or date.today().isoformat()
    ml = month_len(month)
    first = date.fromisoformat(month + "-01")
    prev_from = (first - timedelta(days=6)).isoformat()
    pension_rate = L.get("insurance", {}).get("pension_employer_rate", 0.06)
    rows = []
    q = """SELECT u.*, p.kind, p.amount, p.off_days, p.punch, p.li_self, p.hi_self
           FROM users u JOIN pay_profile p ON p.user_id=u.id %s ORDER BY u.id""" % ("" if only_uid else "WHERE COALESCE(u.demo,0)=0")
    for u in c.execute(q).fetchall():
        if only_uid and u["id"] != only_uid:
            continue
        u = profile_for(c, u["id"], month, u)
        ps = c.execute("SELECT * FROM punches WHERE user_id=? AND voided=0 AND substr(at,1,7)=? ORDER BY at",
                       (u["id"], month)).fetchall()
        gone = not u["active"] or ("removed" in u.keys() and u["removed"])
        if gone and not ps:
            money = c.execute("""SELECT (SELECT COUNT(*) FROM advances WHERE user_id=? AND voided=0 AND COALESCE(pay_month, substr(day,1,7))=?) +
                                        (SELECT COUNT(*) FROM adjustments WHERE user_id=? AND voided=0 AND month=?)""", (u["id"], month, u["id"], month)).fetchone()[0]
            left = u["left_at"] if "left_at" in u.keys() else None
            if not money and not (left and left >= month + "-01" and (u["kind"] == "fixed" or not u["punch"])):
                continue
        shifts = shifts_of(c, u["id"])
        byday = {}
        for p in ps:
            byday.setdefault(p["at"][:10], []).append(p)
        before = c.execute("SELECT at, kind FROM punches WHERE user_id=? AND voided=0 AND at<? ORDER BY at DESC LIMIT 1", (u["id"], month + "-01")).fetchone()
        nm1 = next_month(month) + "-01"
        after = c.execute("SELECT * FROM punches WHERE user_id=? AND voided=0 AND substr(at,1,10)=? ORDER BY at", (u["id"], nm1)).fetchall()
        byday = stitch_overnight(byday, before, after)
        prev_by = {}
        for p in c.execute("SELECT * FROM punches WHERE user_id=? AND voided=0 AND substr(at,1,10)>=? AND substr(at,1,10)<? ORDER BY at",
                           (u["id"], prev_from, first.isoformat())).fetchall():
            prev_by.setdefault(p["at"][:10], []).append(p)
        prev_days = [d for d, x in prev_by.items() if sum(s[2] for s in pair_day(x)[0]) > 0]
        per_day, mins, issues, lates, day_mins = [], 0, [], [], {}
        try: offd = {r[0] for r in c.execute("SELECT day FROM day_off WHERE user_id=? AND substr(day,1,7)=?", (u["id"], month))}
        except Exception: offd = set()
        for d in sorted(byday):
            segs, ins, iss, open_in = pair_day(byday[d], ongoing=(d == today))
            sched = shift_on(shifts, d)
            closed = is_closed(c, d, S)
            lt = [] if closed else lates_of(ins, sched)
            m = sum(x[2] for x in segs)          # 有做事就計薪（含公休日），另標示給老闆確認
            mins += m
            day_mins[d] = m
            issues += [(d, x) for x in iss]
            lates += [(d,) + x for x in lt]
            flag = ("%s有打卡，照實際工時計薪，請確認" % closed) if closed and m else ("排休日有打卡" if d in offd else "")
            per_day.append(dict(day=d, segs=segs, mins=m, issues=iss, lates=lt, open_in=open_in, sched=shift_txt(sched), flag=flag,
                                punches=[dict(id=p["id"], at=p["at"][11:16], kind=p["kind"], source=p["source"], dist=p["dist"],
                                              acc=p["acc"], note=p["note"]) for p in byday[d]]))
        kind, amt = u["kind"], u["amount"]
        lp = legal_pay(kind, amt, u["off_days"], month, day_mins, prev_days)
        if kind != "fixed":
            for x in per_day:
                lp["flags"] += break_flags(x["day"], x["segs"])
        for x in per_day:
            x["type"] = lp["detail"].get(x["day"], "")
        base = lp["gross"]
        ins_ded = min(base, (u["li_self"] or 0) + (u["hi_self"] or 0))
        adv = c.execute("SELECT COALESCE(SUM(amount),0) FROM advances WHERE user_id=? AND voided=0 AND COALESCE(pay_month, substr(day,1,7))=?",
                        (u["id"], month)).fetchone()[0]
        ded = min(adv, base - ins_ded)
        adjs = [dict(x) for x in c.execute("SELECT id, amount, reason FROM adjustments WHERE user_id=? AND month=? AND voided=0",
                                            (u["id"], month))]
        adj = sum(a["amount"] for a in adjs)
        over = [x for x in lates if x[3] > _int(S.get("absent_over"), 10)]
        wd = max(1, ml - (u["off_days"] or 0))
        pension = int(round((amt if kind != "hourly" else base) * pension_rate))
        rows.append(dict(id=u["id"], name=u["name"], username=u["username"], kind=kind, amount=amt, off_days=u["off_days"],
                         punch=u["punch"], work_days=wd, need=lp["need"], days=sum(1 for x in per_day if x["mins"] > 0), mins=mins,
                         full=lp["full"], rate=lp["hourly_rate"], mode=mode_text(kind, amt, lp["full"], lp["hourly_rate"], month >= today[:7]),
                         base_reg=lp["base_reg"], extra_reg=lp["extra_reg"], ot_pay=lp["ot_pay"], rest_pay=lp["rest_pay"], hol_pay=lp["hol_pay"],
                         ot_mins=lp["ot_mins"], rest_mins=lp["rest_mins"], hol_mins=lp["hol_mins"],
                         base=base, adv=adv, ded=ded, adv_left=adv - ded, ins_ded=ins_ded, pension_employer=pension,
                         lates=lates, late_n=len(lates), day_pay=0, penalty_on=False, would=0, late_ded=0, late_per=0, over=over,
                         adjs=adjs, adj=adj, net=base - ins_ded - ded + adj, issues=issues, law_flags=lp["flags"], per_day=per_day,
                         flags=[x["day"] for x in per_day if x.get("flag")]))
    return rows


def board(c, day=None):
    """今日出勤看板"""
    day = day or date.today().isoformat()
    S = settings(c)
    closed = is_closed(c, day, S)
    out = []
    q = """SELECT u.id, u.name, p.punch FROM users u JOIN pay_profile p ON p.user_id=u.id WHERE u.active=1 AND COALESCE(u.demo,0)=0
           AND COALESCE(u.removed,0)=0 ORDER BY u.id"""
    for u in c.execute(q).fetchall():
        ps = c.execute("SELECT * FROM punches WHERE user_id=? AND voided=0 AND substr(at,1,10)=? ORDER BY at", (u["id"], day)).fetchall()
        before = c.execute("SELECT at, kind FROM punches WHERE user_id=? AND voided=0 AND at<? ORDER BY at DESC LIMIT 1", (u["id"], day)).fetchone()
        ps = stitch_overnight({day: ps}, before).get(day, [])      # 凌晨那筆下班卡屬於昨天的夜班，今天的看板不列
        sched = shift_on(shifts_of(c, u["id"]), day)
        segs, ins, iss, open_in = pair_day(ps, ongoing=True)
        lt = lates_of(ins, sched)
        if not ps:
            st = "公休" if closed else ("不用打卡" if not u["punch"] else "沒有排班" if not sched else "還沒打卡")
        elif ps[-1]["kind"] == "in":
            st = "上班中（%s 起）" % ps[-1]["at"][11:16]
        else:
            later = [s for s, _e in sched if hm(s) > hm(ps[-1]["at"][11:16])]
            st = "休息中" if later else "已下班"
        out.append(dict(id=u["id"], name=u["name"], punch=u["punch"], sched=shift_txt(sched), status=st, lates=lt,
                        punches=[dict(at=p["at"][11:16], kind=p["kind"], source=p["source"], dist=p["dist"]) for p in ps],
                        mins=sum(x[2] for x in segs), issues=iss))
    return dict(day=day, closed=closed, rows=out, store_set=bool(S.get("store_lat")))


# ---------------- 月底簽收單（列印成 PDF） ----------------
SLIP_CSS = """<style>
@page{size:A4;margin:12mm 11mm}
:root{--ink:#1d1d1f;--sub:#6e6e73;--line:#d2d2d7;--band:#f5f5f7;--accent:#0071e3;--red:#c4360a}
*{box-sizing:border-box}body{font:12px/1.55 -apple-system,"PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif;color:var(--ink);margin:0}
.pg{position:relative;page-break-after:always;padding-top:2mm}.pg:last-child{page-break-after:auto}
.hd{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px solid var(--ink);padding-bottom:8px;margin-bottom:10px}
.brand{font-size:12px;color:var(--sub)}.ttl{font-size:21px;font-weight:800;margin-top:2px}
.per{text-align:right;font-size:12px;color:var(--sub)}.per b{display:block;font-size:26px;color:var(--ink)}
.info{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin-bottom:12px}
.info div{background:#fff;padding:6px 8px}.info span{display:block;font-size:10.5px;color:var(--sub)}.info b{font-size:14px}
h3{font-size:13px;margin:0 0 6px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
.calc th{background:var(--band);font-size:11px;color:var(--sub);padding:6px 9px;text-align:left}
.calc td{padding:5px 9px;border-bottom:1px solid #eee;font-size:12.5px}.calc td:last-child{text-align:right;font-weight:700;width:120px}
.calc td.f{font-size:11px;color:var(--sub);font-weight:400}.sum td{background:var(--band);font-weight:800;font-size:14px}
.net td{background:var(--ink);color:#fff;font-weight:800;font-size:17px;padding:10px 9px}.minus td:last-child{color:var(--red)}
.days{margin-top:12px}.days table{font-size:10px}.days th{background:var(--band);padding:3px 2px;border:1px solid var(--line)}
.days td{padding:1.5px 2px;border:1px solid #eee;text-align:center}.days td.na{color:#aaa}
.late{margin-top:10px;border:2px solid var(--red);border-radius:8px;padding:8px 12px}.late b.t{font-size:15px;color:var(--red)}
.late div{font-size:12.5px;line-height:1.7}
.sign{margin-top:10px;border:1.5px solid var(--ink);padding:12px 14px}.sign .amt{font-size:16px;font-weight:800;color:var(--red)}
.sign .row{display:flex;gap:26px;margin-top:14px}.sign .row div{flex:1}.sign .lbl{font-size:11px;color:var(--sub)}.sign .box{border:1px solid var(--ink);height:36px}
.note{margin-top:8px;font-size:10px;color:var(--sub);background:var(--band);padding:8px 11px}
.cp{position:absolute;top:0;right:0;background:var(--ink);color:#fff;font-size:11px;font-weight:800;padding:5px 13px;border-bottom-left-radius:10px}
.bar{position:sticky;top:0;background:#fff;padding:10px;border-bottom:1px solid var(--line);font-size:14px}
@media print{.bar{display:none}}
</style>"""


def _esc(s):
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_LOGO = ""
try:
    import base64 as _b64, os as _os
    if cfg.STORE.get("logo"):
        _LOGO = _b64.b64encode(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "static", cfg.STORE["logo"]), "rb").read()).decode()
except Exception:
    pass


def _brand(shop):
    """簽收單表頭：LOGO＋店名"""
    return ('<img src="data:image/png;base64,%s" alt="" style="height:22px;vertical-align:middle;margin-right:6px">' % _LOGO if _LOGO else "") + _esc(shop)


def slips_html(rows, month, shop=None):
    shop = shop or cfg.STORE.get("name", "")
    y, m = month.split("-")
    title = "%s 年 %d 月　薪資明細暨領款簽收單" % (y, int(m))
    ml = month_len(month)
    pages = []
    for r in rows:
        for cp in ("第一聯 · 本人收執", "第二聯 · 店方存查"):
            calc = []
            if r["kind"] == "hourly":
                calc.append(("本薪（時薪）", "平日正常工時 %s 分鐘" % format(r["mins"] - r["ot_mins"] - r["rest_mins"] - r["hol_mins"], ","), r["base_reg"]))
            elif r["kind"] == "fixed":
                calc.append(("本薪（月薪）", "月薪 %s" % format(r["amount"], ","), r["base"]))
            elif r["full"]:
                calc.append(("本薪（月薪）", "月薪 %s，做滿應上班 %s 小時" % (format(r["amount"], ","), format(r["need"] // 60, ",")), r["base_reg"]))
                if r["extra_reg"]:
                    calc.append(("超過應上班時數", "依每小時工資額加給", r["extra_reg"]))
            else:
                calc.append(("本薪（依出勤比例）", "應上班 %s 分鐘，實際 %s 分鐘" % (format(r["need"], ","), format(r["mins"] - r["ot_mins"] - r["rest_mins"] - r["hol_mins"], ",")), r["base_reg"]))
            if r.get("ot_pay"):
                calc.append(("平日加班費", "超過 8 小時共 %s 分鐘（前 2 小時 ×1.34、再 2 小時 ×1.67）" % format(r["ot_mins"], ","), r["ot_pay"]))
            if r.get("rest_pay"):
                calc.append(("休息日出勤", "共 %s 分鐘（勞基法第 24 條第 2 項）" % format(r["rest_mins"], ","), r["rest_pay"]))
            if r.get("hol_pay"):
                calc.append(("國定假日／例假出勤", "共 %s 分鐘，工資加倍（勞基法第 39、40 條）" % format(r["hol_mins"], ","), r["hol_pay"]))
            rows_html = "".join('<tr><td>%s</td><td class="f">%s</td><td>%s</td></tr>' % (a, _esc(b), format(v, ",")) for a, b, v in calc)
            rows_html += '<tr class="sum"><td>應發合計</td><td></td><td>%s</td></tr>' % format(r["base"], ",")
            if r.get("ins_ded"):
                rows_html += '<tr class="minus"><td>減：勞健保自付額</td><td class="f">依投保級距</td><td>−%s</td></tr>' % format(r["ins_ded"], ",")
            rows_html += '<tr class="minus"><td>減：預支扣回</td><td class="f">%s</td><td>%s</td></tr>' % (
                "本月預支 %s" % format(r["adv"], ",") if r["adv"] else "無", "−" + format(r["ded"], ",") if r["ded"] else "0")
            for a in r["adjs"]:
                rows_html += '<tr class="%s"><td>%s</td><td class="f">%s</td><td>%s</td></tr>' % (
                    "minus" if a["amount"] < 0 else "", "調整", _esc(a["reason"]), ("−" if a["amount"] < 0 else "＋") + format(abs(a["amount"]), ","))
            rows_html += '<tr class="net"><td>實發金額</td><td></td><td>%s</td></tr>' % format(r["net"], ",")
            days = ""
            if r["kind"] != "fixed":
                byd = {x["day"]: x for x in r["per_day"]}
                half = (ml + 1) // 2

                def cell(d):
                    if d > ml:
                        return '<td class="na" colspan="4"></td>'
                    x = byd.get("%s-%02d" % (month, d))
                    if not x:
                        return '<td class="na">%d</td><td class="na" colspan="3">—</td>' % d
                    span = " ".join("%s-%s" % (a, b) for a, b, _m in x["segs"]) or "漏打卡"
                    return "<td>%d</td><td style='text-align:left'>%s</td><td>%d</td><td>%.2f</td>" % (d, span, x["mins"], x["mins"] / 60)
                trs = "".join("<tr>%s%s</tr>" % (cell(i), cell(i + half)) for i in range(1, half + 1))
                days = ('<div class="days"><h3>逐日工時（以打卡為準）</h3><table><tr><th>日</th><th>上下班</th><th>分鐘</th><th>時數</th>'
                        '<th>日</th><th>上下班</th><th>分鐘</th><th>時數</th></tr>%s</table></div>' % trs)
            late = ""
            if r["lates"]:
                lst = "、".join("%d/%d 晚 %d 分" % (int(d[5:7]), int(d[8:]), mm) for d, _a, _s, mm in r["lates"])
                how = "遲到的分鐘不計入工時，不另外扣款"
                late = '<div class="late"><b class="t">本月遲到 %d 次（%s）</b><div>%s</div></div>' % (r["late_n"], how, lst)
            info = ('<div class="info"><div><span>%s</span><b>%s</b></div><div><span>出勤天數</span><b>%d 天</b></div>'
                    '<div><span>總工作時數</span><b>%s 分（%.2f H）</b></div></div>') % (
                "時薪" if r["kind"] == "hourly" else "月薪", format(r["amount"], ","), r["days"], format(r["mins"], ","), r["mins"] / 60)
            sign = ('<div class="sign">茲收到 <b>%s 年 %d 月</b> 薪資，實發金額新台幣 <span class="amt">%s</span> 元整，經核對無誤。'
                    '<div class="row"><div><div class="lbl">簽名</div><div class="box"></div></div><div><div class="lbl">領款日期</div><div class="box"></div></div>'
                    '<div><div class="lbl">發放人簽名</div><div class="box"></div></div></div></div>') % (y, int(m), format(r["net"], ","))
            pages.append('<div class="pg"><div class="cp">%s</div><div class="hd"><div><div class="brand">%s</div><div class="ttl">%s</div></div>'
                         '<div class="per">%s<b>%s</b></div></div>%s<h3>薪資計算明細</h3><table class="calc"><tr><th>項目</th><th>計算方式</th>'
                         '<th style="text-align:right">金額（元）</th></tr>%s</table>%s%s%s<div class="note">工時以打卡紀錄為準；加班、休息日、國定假日依勞動基準法計算。'
                         '如對時數或金額有疑義，請於領款前提出。</div></div>' % (cp, _brand(shop), title, "夥伴", _esc(r["name"]), info, rows_html, days, late, sign))
    bar = ('<div class="bar"><a href="/#boss" style="margin-right:14px">‹ 回系統</a>%s 年 %d 月簽收單，共 %d 人。按 Ctrl＋P（手機選「列印」）存成 PDF。</div>'
           % (y, int(m), len(rows)))
    return '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>%s</title>%s</head><body>%s%s</body></html>' % (
        title, SLIP_CSS, bar, "".join(pages))
