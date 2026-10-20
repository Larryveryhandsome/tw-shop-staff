# -*- coding: utf-8 -*-
"""食安紀錄（老闆 10/6）：照總部紙本表格做成系統——冰箱溫度、瓦斯安全、油品管理、廢油回收、廁所清潔。
冰箱溫度、廢油回收「記錄當下一定要拍照」，沒照片不能存；超出標準自動通知店長和老闆；沒記會提醒；店長複檢。
mixin：app.H 繼承 Safety；路由 safety_get / safety_post 沒對到回 O.NOPE。"""
import json, os, threading, time
from datetime import datetime
import ops as O
import payroll as P

SCHEMA = """
CREATE TABLE IF NOT EXISTS safety_target(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, has_freezer INTEGER NOT NULL DEFAULT 1,
  active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS safety_log(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, day TEXT NOT NULL, slot TEXT, target_id INTEGER, data TEXT,
  photo TEXT, alert TEXT, user_id INTEGER, created TEXT, reviewed_by INTEGER, reviewed_at TEXT, removed INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_safety_day ON safety_log(kind, day);
"""
# 總部表格的標準
FREEZE = (-18, -10)        # 冷凍 −10 ～ −18 度（標準 −18）
CHILL = (3, 7)             # 冷藏 3 ～ 7 度（標準 +7）
POLAR_MAX = 25             # 油炸油總極性化合物 ≥ 25% 一定要換（衛福部規定）
KINDS = {"fridge": "冰箱溫度", "gas": "瓦斯安全", "oil": "油品管理", "wasteoil": "廢油回收", "toilet": "廁所清潔"}
SLOTS = {"fridge": ["上午", "下班"], "gas": ["上午", "打烊"], "oil": [""], "wasteoil": [""], "toilet": ["09:00", "11:00", "13:00", "15:00", "17:00", "19:00"]}
# 店長 10/8：冰箱早上記一次、下班記一次就好（中午、下午一直開開關關，量了不準）→ 原本「下午」改「下班」
CLOSE_FROM = "18:30"
LATE_FROM = "16:00"         # 冰箱「下班」、瓦斯「打烊」今天的要這之後才能記       # 這之後打下班卡，冰箱「下班」、瓦斯「打烊」還沒記就提醒他
PHOTO_REQUIRED = {"fridge", "wasteoil"}   # 老闆 10/6：冰箱紀錄當下要拍照，否則不能記錄；廢油回收拍回收單
# 10/9：店裡看的是瓦斯表（m³），夥伴把度數填進「壓力」→ 加「瓦斯表度數」，壓力改成有壓力錶才填
GAS_AM = [("meter", "瓦斯表度數（m³，照表上的數字抄，含小數點）", "num"), ("pressure", "瓦斯壓力（kg/cm²，有壓力錶才填）", "num"), ("pipe", "瓦斯管線安全", "chk"), ("closed_yday", "前一天有關好", "chk"),
          ("main_on", "瓦斯總開關打開", "chk"), ("soup_off", "湯台瓦斯關閉", "chk")]
GAS_PM = [("tank_off", "關閉瓦斯桶頭所有開關及總開關", "chk"), ("branch_off", "關閉所有點火分支開關", "chk"),
          ("branch_n", "點火分支開關數量", "num"), ("meter", "瓦斯表度數（m³，照表上的數字抄，含小數點）", "num"), ("pressure", "瓦斯壓力（kg/cm²，有壓力錶才填）", "num"), ("soup_off", "湯台瓦斯關閉", "chk")]


def migrate(c):
    c.executescript(SCHEMA)
    c.execute("UPDATE safety_log SET slot='下班' WHERE kind='fridge' AND slot='下午'")      # 10/8 改名，舊紀錄跟著改
    if not c.execute("SELECT 1 FROM safety_target WHERE kind='fridge'").fetchone():   # 店裡現在的三台（10 月紙本表）
        c.executemany("INSERT INTO safety_target(kind,name,has_freezer,sort) VALUES('fridge',?,?,?)",
                      [("6 門冰箱", 1, 1), ("4 門冰箱", 1, 2), ("冷藏冰箱", 0, 3)])


def num(x):
    try: return float(str(x).strip())
    except Exception: return None


def check_alert(kind, d, has_freezer=True):
    """超出標準就回傳一句話（會通知店長和老闆）"""
    if kind == "fridge":
        out = []
        f, ch = num(d.get("freeze")), num(d.get("chill"))
        if has_freezer and f is not None and f > FREEZE[1]: out.append("冷凍 %g 度，太高（要 −10 度以下）" % f)
        if ch is not None and ch > CHILL[1]: out.append("冷藏 %g 度，太高（要 7 度以下）" % ch)
        if ch is not None and ch < 0: out.append("冷藏 %g 度，結凍了" % ch)
        return "；".join(out)
    if kind == "gas":
        miss = [n for k, n, t in (GAS_AM if d.get("_slot") == "上午" else GAS_PM) if t == "chk" and not d.get(k)]
        return ("沒做到：" + "、".join(miss)) if miss else ""
    if kind == "oil":
        p = num(d.get("polar"))
        if p is not None and p >= POLAR_MAX and not d.get("changed"): return "極性值 %g%%，超過 %d%% 一定要換油" % (p, POLAR_MAX)
    return ""


def due_missing(c, day, slot_kind):
    """還沒記的：('fridge','上午') → [冰箱名稱...]；('gas','打烊') → ['瓦斯']"""
    kind, slot = slot_kind
    if kind == "fridge":
        done = {r[0] for r in c.execute("SELECT target_id FROM safety_log WHERE kind='fridge' AND day=? AND slot=? AND removed=0", (day, slot))}
        return [r["name"] for r in c.execute("SELECT * FROM safety_target WHERE kind='fridge' AND active=1 ORDER BY sort") if r["id"] not in done]
    return [] if c.execute("SELECT 1 FROM safety_log WHERE kind=? AND day=? AND slot=? AND removed=0", (kind, day, slot)).fetchone() else [KINDS[kind]]


def reminders(c, d, hm):
    """開店日 08:30：早上冰箱、瓦斯沒記 → 通知今天上班的夥伴和店長（每天每種一次）。
    下班的冰箱、打烊的瓦斯不在固定時間催，改成有人打下班卡時提醒（closing_check）；21:00 還沒記才通知店長和老闆。"""
    if P.is_closed(c, d): return
    duty = [x["name"] for x in O.on_duty(c, d)["on"]]
    ids = [r[0] for r in c.execute("SELECT id FROM users WHERE active=1 AND COALESCE(demo,0)=0 AND name IN (%s)" % ",".join("?" * len(duty)), duty)] if duty else []
    for at, sk, title in (("08:30", ("fridge", "上午"), "早上冰箱溫度還沒記"), ("08:30", ("gas", "上午"), "早上瓦斯檢查還沒記"),
                          ):
        if hm >= at and hm < "21:00":
            miss = due_missing(c, d, sk)
            if miss and O.once(c, "safety:%s:%s:%s" % (d, sk[0], sk[1])):
                O.Notifier.notify(c, ids + O.managers(c), title, "還沒記：%s。打開「食安」記錄，冰箱要拍溫度顯示的照片。" % "、".join(miss), "/#safety")
    if "21:00" <= hm < "23:00":
        miss = closing_missing(c, d)
        if miss and O.once(c, "safety:%s:close" % d):
            O.Notifier.notify(c, O.managers(c) + O.admins(c), "今天下班的食安紀錄沒記", "還沒記：%s。" % "、".join(miss), "/#safety")


def closing_missing(c, d):
    """下班冰箱、打烊瓦斯還沒記的項目"""
    fr, gas = due_missing(c, d, ("fridge", "下班")), due_missing(c, d, ("gas", "打烊"))
    return (["冰箱溫度（%s）" % "、".join(fr)] if fr else []) + (["打烊瓦斯檢查"] if gas else [])


def closing_check(c, me, d, hm):
    """打下班卡時（18:30 以後）：冰箱、瓦斯還沒記 → 回傳給打卡頁跳提醒，也發通知給他（一天一次）"""
    if hm < CLOSE_FROM or P.is_closed(c, d): return []
    miss = closing_missing(c, d)
    if miss and O.once(c, "safety:%s:close:%s" % (d, me["id"])):
        O.Notifier.notify(c, [me["id"]], "下班前：食安紀錄還沒記", "還沒記：%s。打開「食安」記錄，冰箱要拍溫度顯示的照片。" % "、".join(miss), "/#safety")
    return miss


def cron(db_factory):
    def loop():
        while True:
            c = None
            try:
                c = db_factory(); n = datetime.now()
                reminders(c, n.date().isoformat(), n.strftime("%H:%M"))
            except Exception:
                pass
            finally:
                try: c and c.close()
                except Exception: pass
            time.sleep(60)
    threading.Thread(target=loop, daemon=True).start()


class Safety:
    def _slog(self, c, kind, month):
        names = {r[0]: r[1] for r in c.execute("SELECT id, name FROM users")}
        rows = []
        for r in c.execute("SELECT * FROM safety_log WHERE kind=? AND substr(day,1,7)=? AND removed=0 ORDER BY day, slot, id", (kind, month)):
            x = dict(r); x["data"] = json.loads(r["data"] or "{}"); x["who"] = names.get(r["user_id"], ""); x["reviewer"] = names.get(r["reviewed_by"], "")
            x["photo"] = bool(r["photo"]); rows.append(x)
        return rows

    def safety_get(self, c, me, p, q):
        if p == "/api/safety":
            kind = q.get("kind") if q.get("kind") in KINDS else "fridge"
            month = q.get("month") or O.today()[:7]
            t = O.today()
            return self.send_json({"kind": kind, "month": month, "kinds": KINDS, "slots": SLOTS, "gas_am": GAS_AM, "gas_pm": GAS_PM,
                                   "freeze": FREEZE, "chill": CHILL, "polar_max": POLAR_MAX, "photo_required": sorted(PHOTO_REQUIRED),
                                   "targets": [dict(x) for x in c.execute("SELECT * FROM safety_target WHERE active=1 ORDER BY kind, sort, id")],
                                   "rows": self._slog(c, kind, month), "can_review": O.can_fin(me),
                                   "today": {k: due_missing(c, t, sk) for k, sk in (("fridge_am", ("fridge", "上午")), ("fridge_pm", ("fridge", "下班")),
                                                                            ("gas_am", ("gas", "上午")), ("gas_pm", ("gas", "打烊")))}})   # 10/9 修：原本 key 重複，下班沒記被當成早上沒記
        if p == "/api/safety/photo":
            r = c.execute("SELECT photo FROM safety_log WHERE id=?", (int(q.get("id") or 0),)).fetchone()
            if not r or not r["photo"]: return self.err("沒有照片", 404)
            return self.send_file(os.path.join(self.PHOTO_DIR, "safety", r["photo"]), "private, no-cache")
        return O.NOPE

    def safety_post(self, c, me, p, d):
        if p == "/api/safety/save":
            kind = d.get("kind")
            if kind not in KINDS: return self.err("沒有這種紀錄")
            day = d.get("day") if O.ymd(d.get("day") or "") else O.today()
            if day > O.today() or day < O.add_days(O.today(), -2): return self.err("只能記今天（或前兩天補記）")
            slot = d.get("slot") or ""
            if slot not in SLOTS[kind]: return self.err("時段不對")
            if slot in ("下班", "打烊") and day == O.today() and datetime.now().strftime("%H:%M") < LATE_FROM:   # 10/9：早上不能先記下班的
                return self.err("「%s」要快下班再記（%s 以後）。早上的請選「上午」。" % (slot, LATE_FROM))
            data = {k: v for k, v in (d.get("data") or {}).items() if k[:1] != "_"}
            tgt = None
            if kind == "fridge":
                tgt = c.execute("SELECT * FROM safety_target WHERE id=? AND kind='fridge'", (int(d.get("target_id") or 0),)).fetchone()
                if not tgt: return self.err("要選哪一台冰箱")
                if num(data.get("chill")) is None or (tgt["has_freezer"] and num(data.get("freeze")) is None): return self.err("溫度要填數字")
                if c.execute("SELECT 1 FROM safety_log WHERE kind='fridge' AND day=? AND slot=? AND target_id=? AND removed=0", (day, slot, tgt["id"])).fetchone():
                    return self.err("這台冰箱這個時段已經記過了")
            elif kind == "gas":
                if c.execute("SELECT 1 FROM safety_log WHERE kind='gas' AND day=? AND slot=? AND removed=0", (day, slot)).fetchone(): return self.err("這個時段已經記過了")
                if num(data.get("pressure")) is None: return self.err("瓦斯壓力要填數字")
            elif kind == "wasteoil":
                if num(data.get("qty")) is None or not (data.get("vendor") or "").strip(): return self.err("數量和回收廠商要填")
            if kind in PHOTO_REQUIRED and not d.get("photo"):
                return self.err("記錄當下一定要拍照（冰箱拍溫度顯示，廢油拍回收單），沒照片不能存")
            alert = check_alert(kind, dict(data, _slot=slot), bool(tgt["has_freezer"]) if tgt else True)
            sid = c.execute("INSERT INTO safety_log(kind,day,slot,target_id,data,alert,user_id,created) VALUES(?,?,?,?,?,?,?,?)",
                            (kind, day, slot, tgt["id"] if tgt else None, json.dumps(data, ensure_ascii=False), alert or None, me["id"], O.now())).lastrowid
            if d.get("photo"):
                try: fn = O.save_photo(d["photo"], os.path.join(self.PHOTO_DIR, "safety"), "s%d" % sid)
                except ValueError as e:
                    c.execute("DELETE FROM safety_log WHERE id=?", (sid,)); c.commit(); return self.err(str(e))
                c.execute("UPDATE safety_log SET photo=? WHERE id=?", (fn, sid))
            c.commit()
            if alert and not me.get("demo"):
                O.Notifier.notify(c, O.admins(c) + O.managers(c), "食安警示：%s%s" % (tgt["name"] + " " if tgt else KINDS[kind], slot),
                                  "%s（%s 記）。冰箱：檢查門邊條、少開門、聯絡維修；瓦斯：馬上處理。" % (alert, me["name"]), "/#safety")
            return self.send_json({"ok": True, "id": sid, "alert": alert})
        if p == "/api/safety/review":
            if not O.can_fin(me): return self.err("店長或老闆才能複檢", 403)
            ids = [int(x) for x in (d.get("ids") or [])]
            c.executemany("UPDATE safety_log SET reviewed_by=?, reviewed_at=? WHERE id=? AND reviewed_by IS NULL", [(me["id"], O.now(), i) for i in ids])
            c.commit(); return self.send_json({"ok": True, "n": len(ids)})
        if p == "/api/safety/remove":
            r = c.execute("SELECT * FROM safety_log WHERE id=?", (int(d.get("id") or 0),)).fetchone()
            if not r: return self.err("找不到", 404)
            if not (O.can_fin(me) or (r["user_id"] == me["id"] and r["day"] == O.today())): return self.err("只能刪自己今天記的，其他請找店長", 403)
            c.execute("UPDATE safety_log SET removed=1 WHERE id=?", (r["id"],)); c.commit(); return self.send_json({"ok": True})
        if p == "/api/safety/target":
            if not O.can_fin(me): return self.err("店長或老闆才能改冰箱清單", 403)
            if d.get("id"):
                c.execute("UPDATE safety_target SET name=?, has_freezer=?, active=? WHERE id=?",
                          ((d.get("name") or "").strip(), 1 if d.get("has_freezer") else 0, 0 if d.get("remove") else 1, int(d["id"])))
            else:
                if not (d.get("name") or "").strip(): return self.err("名稱要填")
                c.execute("INSERT INTO safety_target(kind,name,has_freezer,sort) VALUES('fridge',?,?,99)", (d["name"].strip(), 1 if d.get("has_freezer") else 0))
            c.commit(); return self.send_json({"ok": True})
        return O.NOPE
