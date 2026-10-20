# -*- coding: utf-8 -*-
"""百工百業端對端測試：10 種台灣常見行業情境，每種都實際開一個系統跑一遍。

  python tests/test_industries.py

每個情境：用產業範本的設定開一個暫存系統 → 塞一整個月（2026 年 9 月，有中秋 9/25、教師節 9/28）的打卡 →
老闆登入看薪資 → 夥伴手機打卡 → 店長記營收、支出 → 老闆核銷 → 印簽收單 → 產生股東頁。
薪資用測試自己寫的另一套算法（照勞基法條文）對答案，不是拿系統的算法對自己。
用的埠：18501～18510。不會動到這個資料夾的 config/、data/。
"""
import calendar
import datetime
import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request
import base64

JPG = "data:image/jpeg;base64," + base64.b64encode(bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"0" * 300).decode()   # 假的單據照片
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
MONTH = "2026-09"
HOL = {"2026-09-25", "2026-09-28"}
bad = 0


def check(name, ok, info=""):
    global bad
    print(("OK  " if ok else "BAD ") + name + ("" if ok else "　" + str(info)[:500]))
    bad += 0 if ok else 1


# ---------------- 測試自己的勞基法算法（時薪制，當對照組） ----------------
def tiers(m, caps):
    out, prev = 0.0, 0
    for cap, r in caps:
        out += max(0, min(m, cap) - prev) * r
        prev = cap
    return out


def oracle_hourly(rate, day_mins):
    """day_mins：{日期: 分鐘}（工時算在上班那天）。每週一到週日：第 6 個出勤日＝休息日、第 7 個＝例假；國定假日兩倍"""
    total, wk = 0.0, {}
    for d in sorted(day_mins):
        m = day_mins[d]
        dd = datetime.date.fromisoformat(d)
        k = (dd - datetime.timedelta(days=dd.weekday())).isoformat()
        wk[k] = wk.get(k, 0) + 1
        if d in HOL or wk[k] >= 7:
            total += min(m, 480) * 2 + tiers(m - min(m, 480), [(120, 1.34), (10 ** 9, 1.67)])
        elif wk[k] == 6:
            total += tiers(m, [(120, 1.34), (480, 1.67), (10 ** 9, 2.67)])
        else:
            total += min(m, 480) + tiers(max(0, m - 480), [(120, 1.34), (10 ** 9, 1.67)])
    return round(rate / 60.0 * total)


def days_of(weekdays):
    y, m = map(int, MONTH.split("-"))
    return ["%s-%02d" % (MONTH, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)
            if datetime.date(y, m, d).weekday() in weekdays]


def mins(segs):
    t = 0
    for a, b in segs:
        x = int(a[:2]) * 60 + int(a[3:])
        y = int(b[:2]) * 60 + int(b[3:])
        t += (y - x) % 1440
    return t


# ---------------- 10 種行業情境 ----------------
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)
S = [
    dict(key="bento", title="便當店（兩頭班、外送）", preset="bento", staff=[
        dict(name="內場", kind="monthly", amount=32000, off=9, days=[MON, TUE, WED, THU, FRI], segs=[("09:00", "13:00"), ("15:00", "19:00")],
             expect=dict(full=True, hol_pay=round(32000 / 240 * 16), flags=0)),
        dict(name="外送", kind="hourly", amount=200, days=[MON, TUE, WED, THU, FRI], segs=[("11:00", "13:30"), ("17:00", "19:00")])]),
    dict(key="drink", title="飲料店（晚班工讀、週末上班）", preset="drink", staff=[
        dict(name="晚班", kind="hourly", amount=200, days=[TUE, THU, SAT, SUN], segs=[("16:00", "20:00"), ("20:30", "22:00")])]),
    dict(key="breakfast", title="早餐店（清晨班、一週六天）", preset="breakfast", staff=[
        dict(name="煎台", kind="hourly", amount=200, days=[MON, TUE, WED, THU, FRI, SAT], segs=[("05:30", "09:30"), ("10:00", "11:00")],
             expect=dict(rest=True))]),
    dict(key="salon", title="美髮沙龍（設計師月薪＋抽成）", preset="salon", staff=[
        dict(name="設計師", kind="monthly", amount=30000, off=9, days=[TUE, WED, THU, FRI, SAT], segs=[("11:00", "15:00"), ("16:00", "20:00")],
             commission=6000, expect=dict(full=True, flags=0))]),
    dict(key="retail", title="零售門市（基本工資邊緣）", preset="retail", staff=[
        dict(name="門市", kind="hourly", amount=196, days=[WED, THU, FRI, SAT, SUN], segs=[("13:00", "17:00"), ("17:30", "21:00")], expect=dict(flags=0)),
        dict(name="低薪", kind="hourly", amount=185, days=[SAT], segs=[("13:00", "17:00")], expect=dict(minwage_flag=True))]),
    dict(key="nightmarket", title="夜市攤（跨午夜的班）", preset="bento", modules=dict(crm=False, delivery=False), staff=[
        dict(name="夜市", kind="hourly", amount=210, days=[THU, FRI, SAT, SUN, MON], segs=[("17:00", "21:00"), ("21:30", "01:30")], expect=dict(flags=0))]),
    dict(key="cvs", title="24 小時便利店（大夜班）", preset="retail", staff=[
        dict(name="大夜", kind="hourly", amount=220, days=[SUN, MON, TUE, WED, THU], segs=[("23:00", "03:00"), ("03:30", "07:00")], expect=dict(flags=0))]),
    dict(key="buffet", title="自助餐（全年無休、有人週休一日）", preset="bento", staff=[
        dict(name="六天", kind="monthly", amount=34000, off=9, days=[MON, TUE, WED, THU, FRI, SAT], segs=[("10:00", "14:00"), ("16:00", "20:00")],
             expect=dict(rest=True)),
        dict(name="七天", kind="hourly", amount=200, days=[MON, TUE, WED, THU, FRI, SAT, SUN], segs=[("11:00", "14:00")], expect=dict(regular_off_flag=True))]),
    dict(key="cram", title="補習班（鐘點老師＋固定薪班主任）", preset="salon", modules=dict(marketing=True), staff=[
        dict(name="老師", kind="hourly", amount=450, days=[MON, WED, FRI], segs=[("18:30", "21:30")], expect=dict(flags=0)),
        dict(name="班主任", kind="fixed", amount=42000, days=[], segs=[], punch=0, expect=dict(gross=42000))]),
    dict(key="cafe", title="咖啡廳（月薪、偶爾加班）", preset="drink", staff=[
        dict(name="咖啡師", kind="monthly", amount=31000, off=9, days=[WED, THU, FRI, SAT, SUN], segs=[("08:00", "12:00"), ("13:00", "17:00")],
             overtime_day="2026-09-10", expect=dict(ot=True, flags=0))]),
]

CHILD = r'''
import json, os, sys, datetime
sys.path.insert(0, sys.argv[1])
import app
spec = json.loads(sys.argv[2])
app.init_db()
c = app.db()
c.execute("UPDATE users SET username='boss', name='老闆', pw=?, must_change=0 WHERE role='admin'", (app.hash_pw("boss-pass-123"),))
c.execute("INSERT INTO users(username,name,pw,role,created,must_change) VALUES('mgr','店長',?,'manager',?,0)", (app.hash_pw("mgr-pass-123"), app.now()))
c.execute("INSERT INTO settings(k,v) VALUES('weekly_closed','')")
ids = {}
for i, s in enumerate(spec["staff"]):
    un = "s%d" % i
    c.execute("INSERT INTO users(username,name,pw,role,created,must_change) VALUES(?,?,?,'staff',?,0)", (un, s["name"], app.hash_pw("staff-pass-123"), app.now()))
    uid = c.execute("SELECT id FROM users WHERE username=?", (un,)).fetchone()[0]; ids[s["name"]] = uid
    c.execute("INSERT INTO pay_profile(user_id,kind,amount,off_days,punch) VALUES(?,?,?,?,?)", (uid, s["kind"], s["amount"], s.get("off", 0), s.get("punch", 1)))
    if s["segs"]:
        sg = s["segs"] + [[None, None]]
        c.execute("INSERT INTO shifts(user_id,effective,s1,e1,s2,e2) VALUES(?,?,?,?,?,?)", (uid, "2026-01-01", sg[0][0], sg[0][1], sg[1][0], sg[1][1]))
    for d in s["dates"]:
        base = datetime.date.fromisoformat(d)
        cur = base
        prev_end = None
        segs = [list(x) for x in s["segs"]]
        if d == s.get("overtime_day"):
            segs.append(["17:30", "19:30"])        # 這天多做 2 小時（中間有休息，合法的加班）
        for a, b in segs:
            ta = datetime.datetime.combine(cur, datetime.time(int(a[:2]), int(a[3:])))
            if prev_end and ta < prev_end: ta += datetime.timedelta(days=1)
            tb = datetime.datetime.combine(ta.date(), datetime.time(int(b[:2]), int(b[3:])))
            if tb <= ta: tb += datetime.timedelta(days=1)
            c.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,'in','test')", (uid, ta.strftime("%Y-%m-%d %H:%M:%S")))
            c.execute("INSERT INTO punches(user_id,at,kind,source) VALUES(?,?,'out','test')", (uid, tb.strftime("%Y-%m-%d %H:%M:%S")))
            prev_end, cur = tb, tb.date() if tb.date() != ta.date() else cur
c.commit(); c.close()
print(json.dumps(ids))
'''


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


class Client:
    def __init__(self, base):
        self.base, self.op = base, urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def __call__(self, path, body=None, raw=False):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-Req": "1"} if body is not None else {})
        try:
            r = self.op.open(req, timeout=20)
            b = r.read()
            return r.status, (b.decode("utf-8") if raw else json.loads(b))
        except urllib.error.HTTPError as e:
            b = e.read()
            try:
                return e.code, json.loads(b)
            except Exception:
                return e.code, b.decode("utf-8", "replace")


def run_scenario(sc, port, tmp):
    print("\n＝＝ %s ＝＝" % sc["title"])
    d = os.path.join(tmp, sc["key"])
    cfgd = os.path.join(d, "config")
    os.makedirs(cfgd)
    with open(os.path.join(ROOT, "presets", sc["preset"], "store.toml"), encoding="utf-8") as f:
        st = f.read()
    st = st.replace('port = 8402', 'port = %d' % port).replace('fin_start = "2026-01-01"', 'fin_start = "2026-09-01"')
    name = "測試" + sc["title"].split("（")[0]
    st = st.replace(st.split("\n")[4], 'name = "%s"' % name) if st.split("\n")[4].startswith("name =") else st
    for k, v in (sc.get("modules") or {}).items():
        st = st.replace("%s = %s" % (k, "true" if not v else "false"), "%s = %s" % (k, "true" if v else "false"), 1)
    with open(os.path.join(cfgd, "store.toml"), "w", encoding="utf-8") as f:
        f.write(st)
    shutil.copy(os.path.join(ROOT, "config", "labor_rules.toml"), cfgd)
    store = tomllib.loads(st)
    for s in sc["staff"]:
        s["dates"] = days_of(s["days"])
    db = os.path.join(d, "crm.db")
    env = dict(os.environ, CRM_DB=db, CRM_BAK=os.path.join(d, "bak"), CRM_PORT=str(port), SHOP_CONFIG_DIR=cfgd,
               MK_DIR=os.path.join(d, "mk"), PYTHONIOENCODING="utf-8", CRM_EXP_START="2026-09-01")
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", CHILD, APP, json.dumps(sc, ensure_ascii=False)], env=env, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        check(sc["key"] + " 建資料", False, r.stderr[-800:])
        return
    ids = json.loads(r.stdout.strip().splitlines()[-1])
    srv = subprocess.Popen([sys.executable, "-X", "utf8", os.path.join(APP, "app.py")], env=env, cwd=APP, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            if listening(port):
                break
            time.sleep(0.25)
        base = "http://127.0.0.1:%d" % port
        boss, mgr, staff = Client(base), Client(base), Client(base)
        _, html = boss("/", raw=True)
        brand = json.loads(html.split("window.STORE = ")[1].split(";</script>")[0])
        check("首頁顯示店名、單位「%s」" % store["finance"]["unit_name"], name in html and brand["unit"] == store["finance"]["unit_name"], brand)
        check("功能開關照產業設定", all(brand["modules"].get(k) == v for k, v in store["modules"].items()), brand["modules"])
        check("老闆登入", boss("/api/login", {"username": "boss", "password": "boss-pass-123"})[0] == 200)
        for s in sc["staff"]:
            if s.get("commission"):
                st_, res = boss("/api/boss/adjust/save", {"user_id": ids[s["name"]], "month": MONTH, "amount": s["commission"], "reason": "9 月抽成"})
        _, pay = boss("/api/boss/payroll?month=" + MONTH)
        rows = {r["name"]: r for r in pay["rows"]}
        for s in sc["staff"]:
            r = rows.get(s["name"])
            if not r:
                check("%s 有薪資" % s["name"], False, list(rows))
                continue
            e = s.get("expect", {})
            dm = {d: mins(s["segs"]) for d in s["dates"]}
            if s["kind"] == "hourly":
                want = oracle_hourly(s["amount"], dm)
                check("%s：時薪 %d、%d 天，應發 %s（對照組 %s）" % (s["name"], s["amount"], len(s["dates"]), format(r["base"], ","), format(want, ",")),
                      abs(r["base"] - want) <= 2, r["base"])
            if s["kind"] == "fixed":
                check("%s：固定月薪 %s" % (s["name"], format(r["base"], ",")), r["base"] == e["gross"], r)
            check("%s：沒有漏打卡" % s["name"], not r["issues"], r["issues"][:3])
            check("%s：出勤天數 %d" % (s["name"], r["days"]), s["kind"] == "fixed" or r["days"] == len(s["dates"]), (r["days"], len(s["dates"])))
            if "full" in e:
                check("%s：月薪做滿" % s["name"], r["full"] == e["full"], (r["mins"], r["need"]))
            if "hol_pay" in e:
                check("%s：國定假日加給 %s" % (s["name"], format(r["hol_pay"], ",")), abs(r["hol_pay"] - e["hol_pay"]) <= 2, r["hol_pay"])
            if e.get("rest"):
                check("%s：休息日出勤有加給（%s）" % (s["name"], format(r["rest_pay"], ",")), r["rest_pay"] > 0, r)
            if e.get("ot"):
                check("%s：加班費（%s）" % (s["name"], format(r["ot_pay"], ",")), r["ot_pay"] == round(s["amount"] / 240 * (1.34 * 2)), r["ot_pay"])
            if "flags" in e:
                check("%s：沒有勞基法提醒" % s["name"], len(r["law_flags"]) == e["flags"], r["law_flags"][:3])
            if e.get("minwage_flag"):
                check("%s：低於基本工資有提醒" % s["name"], any("基本工資" in f for f in r["law_flags"]), r["law_flags"])
            if e.get("regular_off_flag"):
                check("%s：連上 7 天有例假提醒" % s["name"], any("例假" in f for f in r["law_flags"]), r["law_flags"][:2])
            if s.get("commission"):
                check("%s：抽成用薪資調整加進實發" % s["name"], r["adj"] == s["commission"] and r["net"] == r["base"] - r["ins_ded"] + s["commission"], (r["adj"], r["net"]))
        # 夥伴用手機打卡（店家位置還沒校正：照樣可以打，標註）
        if any(s.get("punch", 1) for s in sc["staff"]):
            check("夥伴登入", staff("/api/login", {"username": "s0", "password": "staff-pass-123"})[0] == 200)
            st_, res = staff("/api/punch", {"lat": 25.04, "lng": 121.56, "acc": 20})
            check("夥伴手機打卡", st_ == 200, res)
            st_, res = staff("/api/punch", {"lat": 25.04, "lng": 121.56, "acc": 20})
            check("一分鐘內重複打卡會擋", st_ == 400, res)
        # 店長記帳、老闆核銷
        today = datetime.date.today().isoformat()
        check("店長登入", mgr("/api/login", {"username": "mgr", "password": "mgr-pass-123"})[0] == 200)
        st_, res = mgr("/api/fin/rev", {"day": today, "cash": 15000})
        check("沒拍日結單照片不能記營收", st_ == 400, res)
        st_, res = mgr("/api/fin/rev", {"day": today, "cash": 15000, "eticket": 3000, "orders": 120, "boxes": 150, "photo": JPG})
        check("店長記營收", st_ == 200, res)
        cat = store["finance"]["expense_categories"][0]
        st_, res = mgr("/api/fin/exp", {"day": today, "category": cat, "item": "補貨", "amount": 1200, "pay": "零用金", "photo": JPG})
        check("店長記支出（類別：%s）" % cat, st_ == 200, res)
        st_, res = boss("/api/fin/verify", {"kind": "all", "day": today, "approve": True})
        check("老闆核銷", st_ == 200, res)
        st_, slip = boss("/boss/slips?month=" + MONTH, raw=True)
        want_words = [w for s in sc["staff"] for w, cond in (("平日加班費", s.get("overtime_day")), ("休息日出勤", s.get("expect", {}).get("rest")),
                                                             ("國定假日", s["kind"] != "fixed" and any(d in HOL for d in s["dates"]))) if cond]
        check("簽收單印得出來（含店名%s）" % ("、" + "、".join(sorted(set(want_words))) if want_words else ""),
              st_ == 200 and name in slip and all(w in slip for w in want_words), [w for w in want_words if w not in slip])
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()
    # 股東頁
    sys.path.insert(0, os.path.join(ROOT, "ledger", "builder"))
    out = os.path.join(d, "www")
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "ledger", "builder", "build_ledger.py"), "--db", db,
                        "--config", os.path.join(ROOT, "presets", sc["preset"], "ledger.toml"), "--out", out],
                       env=env, capture_output=True, text=True, encoding="utf-8")
    ok = r.returncode == 0 and os.path.exists(os.path.join(out, "index.html"))
    if ok:
        with open(os.path.join(out, "index.html"), encoding="utf-8") as f:
            data = json.loads(f.read().split("const D = ")[1].split(";\nconst fmt")[0])
        pm = data["payroll"].get(MONTH, {})
        ok = pm.get("gross") == sum(r["base"] + r["adj"] for r in rows.values()) and data["total"]["revenue"] >= 18000
    check("股東頁：9 月薪資總額（應發＋抽成等調整）和老闆頁一致、今天營收有進來", ok,
          r.stderr[-400:] if r.returncode else (pm.get("gross"), sum(x["base"] + x["adj"] for x in rows.values()), data["total"]["revenue"], data["pending"]))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ports = list(range(18501, 18501 + len(S)))
    busy = [p for p in ports if listening(p)]
    if busy:
        sys.exit("這些埠已經有程式在用：%s" % busy)
    tmp = tempfile.mkdtemp(prefix="industries_")
    try:
        for sc, port in zip(S, ports):
            run_scenario(sc, port, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n全部通過" if not bad else "\n有 %d 項沒過" % bad)
    sys.exit(1 if bad else 0)
