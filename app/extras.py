# -*- coding: utf-8 -*-
"""v4（老闆 10/5 晚）：每週新聞、工作待辦、個人檔案、新手導覽紀錄、崗位與必讀訓練（輪調）、晚上 9 點日誌關心、外送單刪除。
跟 ops.py 一樣是 mixin：app.H 繼承 Extras；路由 extra_get / extra_post 沒對到回 O.NOPE。"""
import json, os, random, re, threading, time
from datetime import datetime, date, timedelta
import ops as O
import payroll as P

SCHEMA = """
CREATE TABLE IF NOT EXISTS news(id INTEGER PRIMARY KEY, week TEXT UNIQUE, title TEXT, intro TEXT, items TEXT, created TEXT,
  active INTEGER NOT NULL DEFAULT 1, notified INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS news_read(news_id INTEGER NOT NULL, user_id INTEGER NOT NULL, at TEXT, PRIMARY KEY(news_id, user_id));
CREATE TABLE IF NOT EXISTS todos(id INTEGER PRIMARY KEY, title TEXT NOT NULL, note TEXT, assignee INTEGER, due TEXT, created TEXT, created_by INTEGER,
  done_at TEXT, done_by INTEGER, removed INTEGER NOT NULL DEFAULT 0, kind TEXT);
CREATE TABLE IF NOT EXISTS profiles(user_id INTEGER PRIMARY KEY, nickname TEXT, intro TEXT, likes TEXT, photo TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS tours(user_id INTEGER NOT NULL, k TEXT NOT NULL, at TEXT, PRIMARY KEY(user_id, k));
CREATE TABLE IF NOT EXISTS care_log(id INTEGER PRIMARY KEY, user_id INTEGER, day TEXT, idx INTEGER, journal_id INTEGER);
-- 排定時間才送的通知（例：晚上發的公告，早上 8:30 才推播，不吵大家睡覺）
CREATE TABLE IF NOT EXISTS push_queue(id INTEGER PRIMARY KEY, at TEXT NOT NULL, who TEXT NOT NULL, title TEXT, body TEXT, url TEXT, sent INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS position_log(id INTEGER PRIMARY KEY, user_id INTEGER, from_pos TEXT, to_pos TEXT, at TEXT, by_user INTEGER);
"""

# ───────────── 崗位與必讀 ─────────────
POSITIONS = ["外場", "內場", "外送"]
POS_NOTE = {"外場": "櫃檯、收銀、接電話", "內場": "廚房、備料、裝便當", "外送": "送便當、收現金"}
# 章節開頭的編號（「1 」不會對到「10 」）
REQ = {"*": ("1 ", "5 "), "外場": ("6 ", "10 ", "7 "), "內場": ("3 ", "4 ", "9 ", "8 "), "外送": ("7 ", "4 ", "10 ")}


def norm_pos(p):
    return p if p in POSITIONS else ("外場" if p == "PT" else None)


def required_ids(c, u):
    """夥伴（staff）的必讀：大家都要的（認識我們的店、食品安全）＋自己崗位的章節。店長、老闆不用。"""
    if u["role"] != "staff": return []
    pre = REQ["*"] + REQ.get(norm_pos(u["position"]) or "", ())
    return [r[0] for r in c.execute("SELECT id, chapter FROM manual WHERE active=1 ORDER BY sort, id") if r[1].startswith(pre)]


def train_left(c, u):
    req = required_ids(c, u)
    if not req: return 0
    done = {r[0] for r in c.execute("SELECT manual_id FROM manual_ack WHERE user_id=?", (u["id"],))}
    return len([i for i in req if i not in done])


def change_position(c, me, uid, pos):
    pos = norm_pos(pos)
    if not pos: return "崗位只能是：" + "、".join(POSITIONS)
    u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u: return "找不到這位夥伴"
    if u["position"] == pos: return None
    c.execute("UPDATE users SET position=? WHERE id=?", (pos, uid))
    c.execute("INSERT INTO position_log(user_id,from_pos,to_pos,at,by_user) VALUES(?,?,?,?,?)", (uid, u["position"], pos, O.now(), me["id"]))
    n = train_left(c, dict(u, position=pos))
    if not u["demo"]:
        O.Notifier.notify(c, [uid], "你的崗位調到「%s」" % pos,
                          "%s。%s" % (POS_NOTE[pos], ("請先到「訓練」看完新崗位的必讀（還有 %d 篇），看完才能用其他功能；打卡不受影響。" % n) if n else "新崗位的必讀你都看過了。"), "/#manual")
    return None


# ───────────── 晚上 9 點：今天有上班、還沒寫日誌的夥伴，老闆傳一則關心（60 則，同一個人 60 天內不重複） ─────────────
CARE = [
    "今天辛苦了！忙了一整天，回家前花一分鐘，寫下今天你做得很好的三件事吧，我很想看。",
    "今天店裡的節奏還好嗎？不管順不順，你都撐過來了。寫三件今天自己做得好的事給我看看。",
    "謝謝你今天的幫忙。小事也算，例如把桌子擦得很乾淨，都可以寫進日誌喔。",
    "今天有沒有哪一刻覺得自己很棒？把它記下來，明天的你會謝謝今天的你。",
    "辛苦了～下班記得好好休息。睡前把今天做得好的三件事寫一寫，我都會看。",
    "今天客人多不多？你處理得很好。寫下今天最得意的一件事吧。",
    "每天進步一點點就很了不起。今天你進步在哪裡？寫給我看看。",
    "今天你讓店裡更好了。不用寫很多，三句話就好。",
    "忙完了嗎？喝口水休息一下，再花一分鐘寫今天的我很棒日誌。",
    "今天有沒有幫到同事或客人？那就是很棒的一件事，記下來吧。",
    "你今天的努力我都看在眼裡。寫下你自己覺得做得好的地方，讓我也知道。",
    "今天有沒有學到新東西？哪怕是一個小技巧，都值得寫進日誌。",
    "辛苦了！今天哪件事你做得比昨天更順？寫下來給自己一點掌聲。",
    "每個便當能準時送到客人手上，都有你的一份。今天你負責的部分，有什麼做得很好？",
    "今天有被客人稱讚嗎？沒有也沒關係，你自己稱讚自己也算數，寫下來吧。",
    "今天的你很努力，這件事值得被記住。寫三件今天做得好的事給我。",
    "回家路上小心。到家休息前，記得寫今天的日誌喔。",
    "今天有沒有哪個瞬間讓你覺得「我做到了」？把它寫下來。",
    "店能每天順順開門，靠的是每個人。今天你守住了哪一塊？",
    "謝謝你今天的用心。寫下三件做得好的事，我明天會回你。",
    "今天累不累？累也很正常，代表你很認真。寫個日誌，幫今天收個尾。",
    "今天跟同事的配合怎麼樣？有哪個默契讓你覺得很順？寫下來吧。",
    "把今天做得好的事寫下來，是在幫自己存信心。今天存一點吧。",
    "今天也辛苦你了。三件好事，再小都可以：準時、微笑、把地掃乾淨，都算。",
    "我很好奇你今天過得怎麼樣。寫幾句日誌讓我知道好嗎？",
    "今天有沒有一件事，是你主動多做一點的？那就是很棒的事。",
    "有你在店裡真好。寫下今天你做得很好的三件事吧。",
    "今天的工作告一段落了，給自己一個肯定，寫進我很棒日誌。",
    "做餐飲很辛苦，你每天都在堅持。今天堅持的成果是什麼？",
    "今天有沒有讓客人笑？有的話一定要寫下來！",
    "辛苦了！明天也一起加油。睡前記得寫今天的日誌。",
    "今天你把哪件事做得又快又好？寫下來，我想學。",
    "累的時候也要記得：你今天已經做了很多。寫三件給自己看。",
    "今天店裡有沒有什麼小插曲？你是怎麼處理的？處理好了也是一件很棒的事。",
    "寫日誌不用想太久，想到什麼就寫什麼。今天你做得好的三件事是？",
    "今天謝謝你。每一天的小進步，加起來就是大進步。",
    "今天的便當有沒有一個是你特別用心裝的？那也值得寫下來。",
    "希望你今天過得還不錯。寫日誌的時候，也順便想想明天想做得更好的一件事。",
    "你今天的表現，比你自己想的還要好。寫下來看看就知道了。",
    "今天有遇到難搞的狀況嗎？能撐過去就很厲害，記得寫進日誌。",
    "辛苦一天了，先好好吃飯。吃飽再花一分鐘寫日誌。",
    "今天哪件事讓你覺得自己越來越上手了？寫給我看。",
    "今天是不是又學會了一件事？把它寫下來，以後就是你的本事。",
    "我很珍惜每一位夥伴。今天你為店裡做的，我都想知道。",
    "今天你最想被誰稱讚？先自己稱讚自己，寫進日誌吧。",
    "今天的忙碌裡，有沒有一個讓你開心的小片刻？寫下來吧。",
    "準時上班、把事情做完，就已經很了不起了。今天還有哪些做得好？",
    "日誌寫久了，會看到自己一路走來的樣子。今天也記一筆吧。",
    "今天辛苦了。有什麼想跟我說的，也可以一起寫在日誌裡。",
    "今天有沒有幫新夥伴或同事一把？那是很棒的團隊精神。",
    "客人吃得開心，是因為你做得用心。今天你用心在哪裡？",
    "今天辛苦了。三件好事寫完，就好好放鬆休息吧。",
    "你今天做得很好。不相信的話，寫下來看看。",
    "今天有沒有一件事，是你本來覺得做不到、最後做到了？",
    "店裡因為有你更有活力。寫下今天做得好的三件事吧。",
    "今天你把哪個地方整理得最乾淨？那也是一件好事。",
    "辛苦了！今天的你值得一個讚。寫日誌告訴我為什麼。",
    "每天寫三件好事，是在練習看見自己的好。今天也練習一下吧。",
    "今天也謝謝你。寫完日誌就早點休息，明天見。",
    "今天你是不是也很棒？寫下來，讓我也替你開心。",
]


def send_care(c, day):
    """晚上 9 點：今天有上班（有打卡或班表上有班）、還沒寫日誌的夥伴 → 老闆傳一則關心。回傳傳了幾則。"""
    boss = O.admins(c)
    if not boss: return 0
    boss = boss[0]; n = 0
    duty = {x["name"] for x in O.on_duty(c, day)["on"]}
    for u in c.execute("""SELECT id, name FROM users WHERE active=1 AND role='staff' AND COALESCE(demo,0)=0 AND COALESCE(removed,0)=0""").fetchall():
        worked = u["name"] in duty or c.execute("SELECT 1 FROM punches WHERE user_id=? AND voided=0 AND substr(at,1,10)=?", (u["id"], day)).fetchone()
        if not worked: continue
        if c.execute("SELECT 1 FROM journal WHERE user_id=? AND author_id=? AND day=? AND removed=0", (u["id"], u["id"], day)).fetchone(): continue
        if c.execute("SELECT 1 FROM care_log WHERE user_id=? AND day=?", (u["id"], day)).fetchone(): continue
        used = {r[0] for r in c.execute("SELECT idx FROM care_log WHERE user_id=? AND day>=? AND day<?", (u["id"], O.add_days(day, -59), day))}
        pool = [i for i in range(len(CARE)) if i not in used] or list(range(len(CARE)))
        i = random.choice(pool)
        jid = c.execute("INSERT INTO journal(user_id,author_id,day,body,created,auto) VALUES(?,?,?,?,?,1)", (u["id"], boss, day, CARE[i], O.now())).lastrowid
        c.execute("INSERT INTO care_log(user_id,day,idx,journal_id) VALUES(?,?,?,?)", (u["id"], day, i, jid))
        c.commit()
        O.Notifier.notify(c, [u["id"]], "老闆：今天辛苦了", CARE[i][:80], "/#journal"); n += 1
    return n


# 初始密碼檔、登入卡（老闆 10/5：大家改完自己的密碼就自動丟資源回收筒）
SECRET_FILES = ["data/首次管理員密碼.txt", "data/夥伴帳號_列印後刪除.json", "data/夥伴帳號_列印後刪除_第二批.json",
                "夥伴登入卡_列印後銷毀.html", "夥伴登入卡_列印後銷毀.pdf", "夥伴登入卡_第二批_列印後銷毀.html", "夥伴登入卡_第二批_列印後銷毀.pdf"]


def recycle_secrets(c):
    """所有在職帳號都設好自己的密碼了 → 把初始密碼檔丟資源回收筒（可以從回收筒救回來），通知老闆"""
    here = os.path.dirname(os.path.abspath(__file__))
    left = [f for f in SECRET_FILES if os.path.exists(os.path.join(here, f))]
    if not left or os.environ.get("CRM_DB") or os.name != "nt": return 0
    if c.execute("SELECT COUNT(*) FROM users WHERE active=1 AND COALESCE(demo,0)=0 AND COALESCE(removed,0)=0 AND must_change=1").fetchone()[0]: return 0
    import subprocess
    ps = "Add-Type -AssemblyName Microsoft.VisualBasic; " + "; ".join(
        "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('%s','OnlyErrorDialogs','SendToRecycleBin')" % os.path.join(here, f).replace("'", "''") for f in left)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, timeout=60, creationflags=0x08000000)
    gone = [f for f in left if not os.path.exists(os.path.join(here, f))]
    if gone:
        O.Notifier.notify(c, O.admins(c), "初始密碼檔已丟資源回收筒", "大家都設好自己的密碼了，%d 個初始密碼檔、登入卡已經丟到資源回收筒：%s" % (len(gone), "、".join(gone)), "/#me")
    return len(gone)


# 從外面檢查 config/store.toml 的 public_url：連不到 → 通知老闆；恢復也通知（只在 public_url 不是 localhost 時檢查）
NET = {"fail": 0, "told": False}


def public_check(c):
    if os.environ.get("CRM_DB"): return
    import urllib.request, cfg
    url = (cfg.STORE.get("public_url") or "").rstrip("/")
    if not url or "localhost" in url or "127.0.0.1" in url: return
    try:
        import push
        req = urllib.request.Request(url + "/health", headers={"User-Agent": "Mozilla/5.0 (compatible; ShopStaffHealth/1.0)"})
        ok = b'"ok": true' in urllib.request.urlopen(req, timeout=12, context=push.TLS).read()
    except Exception:
        ok = False
    if ok:
        if NET["told"]: O.Notifier.notify(c, O.admins(c), "系統恢復了", "外面又可以連進系統了（%s）。" % O.now()[11:16], "/#boss")
        NET.update(fail=0, told=False); return
    NET["fail"] += 1
    if NET["fail"] == 3 and not NET["told"]:
        NET["told"] = True
        O.Notifier.notify(c, O.admins(c), "外面暫時連不到系統", "店裡電腦的系統還在，是對外連線（網路或通道）斷了，請檢查。", "/#boss")


def cron(db_factory):
    """每 30 秒：新聞出刊通知、晚上 9 點日誌關心、待辦到期提醒（早上 9 點）"""
    def loop():
        while True:
            c = None
            try:
                c = db_factory(); n = datetime.now(); d = n.date().isoformat(); hm = n.strftime("%H:%M")
                for r in (c.execute("SELECT id, title, intro FROM news WHERE active=1 AND notified=0").fetchall() if "08:00" <= hm < "21:00" else []):   # 半夜出刊等早上 8 點再通知
                    c.execute("UPDATE news SET notified=1 WHERE id=?", (r["id"],)); c.commit()
                    O.Notifier.notify(c, O.everyone(c), "每週新聞：" + r["title"], (r["intro"] or "")[:80], "/#news")
                open_today = not P.is_closed(c, d)
                if open_today and "21:00" <= hm < "23:30" and O.once(c, "care:" + d):
                    send_care(c, d)
                if n.minute % 10 == 0 and n.second < 30: recycle_secrets(c)
                for q in c.execute("SELECT * FROM push_queue WHERE sent=0 AND at<=?", (O.now(),)).fetchall():
                    c.execute("UPDATE push_queue SET sent=1 WHERE id=?", (q["id"],)); c.commit()
                    who = O.everyone(c) if q["who"] == "all" else json.loads(q["who"])
                    O.Notifier.notify(c, who, q["title"], q["body"] or "", q["url"] or "/")
                if n.minute % 2 == 0 and n.second < 30: public_check(c)
                if "09:00" <= hm < "12:00" and O.once(c, "todo:" + d):
                    for t in c.execute("SELECT * FROM todos WHERE removed=0 AND done_at IS NULL AND due IS NOT NULL AND due<=? AND assignee IS NOT NULL", (d,)).fetchall():
                        O.Notifier.notify(c, [t["assignee"]], ("待辦今天到期：" if t["due"] == d else "待辦已經過期：") + t["title"], t["note"] or "做完到「我」按完成", "/#me")
            except Exception:
                pass
            finally:
                try: c and c.close()
                except Exception: pass
            time.sleep(30)
    threading.Thread(target=loop, daemon=True).start()


def migrate(c):
    c.executescript(SCHEMA)
    if "auto" not in {r[1] for r in c.execute("PRAGMA table_info(journal)")}:
        c.execute("ALTER TABLE journal ADD COLUMN auto INTEGER NOT NULL DEFAULT 0")   # 1＝晚上 9 點自動關心


def week_of(d=None):
    d = d or date.today(); y, w, _ = d.isocalendar()
    return "%d-W%02d" % (y, w)


def import_news(c, data):
    """匯入一期新聞（JSON：week, title, intro, items[]）；同一週再匯入就覆蓋內容（不重發通知）"""
    items = [x for x in (data.get("items") or []) if x.get("title") and x.get("url", "").startswith("http")]
    if not items: raise ValueError("沒有新聞")
    wk = data.get("week") or week_of()
    cur = c.execute("SELECT id FROM news WHERE week=?", (wk,)).fetchone()
    if cur:
        c.execute("UPDATE news SET title=?, intro=?, items=?, active=1 WHERE id=?", (data.get("title") or "", data.get("intro") or "", json.dumps(items, ensure_ascii=False), cur[0]))
    else:
        c.execute("INSERT INTO news(week,title,intro,items,created) VALUES(?,?,?,?,?)", (wk, data.get("title") or "", data.get("intro") or "", json.dumps(items, ensure_ascii=False), O.now()))
    c.commit(); return len(items)


# ═════════════ HTTP 路由（mixin） ═════════════
class Extras:
    def extra_me(self, c, me):
        out = {"tours": [r[0] for r in c.execute("SELECT k FROM tours WHERE user_id=?", (me["id"],))],
               "position": me["position"] if "position" in me.keys() else None, "positions": POSITIONS, "pos_note": POS_NOTE,
               "train_left": train_left(c, me),
               "news_unread": c.execute("""SELECT COUNT(*) FROM news n WHERE n.active=1 AND n.id=(SELECT MAX(id) FROM news WHERE active=1)
                                         AND NOT EXISTS (SELECT 1 FROM news_read r WHERE r.news_id=n.id AND r.user_id=?)""", (me["id"],)).fetchone()[0],
               "todo_open": c.execute("SELECT COUNT(*) FROM todos WHERE removed=0 AND done_at IS NULL AND assignee=?", (me["id"],)).fetchone()[0]}
        p = c.execute("SELECT * FROM profiles WHERE user_id=?", (me["id"],)).fetchone()
        out["profile_done"] = bool(p and p["photo"] and (p["intro"] or "").strip())
        return out

    def _todo_rows(self, c, me):
        names = {r[0]: r[1] for r in c.execute("SELECT id, name FROM users")}
        if me["role"] == "admin":
            rows = c.execute("SELECT * FROM todos WHERE removed=0 ORDER BY done_at IS NOT NULL, COALESCE(due,'9999'), id DESC LIMIT 200").fetchall()
        else:
            rows = c.execute("SELECT * FROM todos WHERE removed=0 AND (assignee=? OR created_by=?) ORDER BY done_at IS NOT NULL, COALESCE(due,'9999'), id DESC LIMIT 100",
                             (me["id"], me["id"])).fetchall()
        return [dict(r, who=names.get(r["assignee"], "（沒指定）"), by=names.get(r["created_by"], ""), done_name=names.get(r["done_by"], "")) for r in rows]

    def extra_get(self, c, me, p, q):
        if p == "/api/news":
            rows = []
            for r in c.execute("SELECT * FROM news WHERE active=1 ORDER BY week DESC, id DESC LIMIT 12").fetchall():
                rows.append(dict(id=r["id"], week=r["week"], title=r["title"], intro=r["intro"], items=json.loads(r["items"] or "[]"), created=r["created"],
                                 read=bool(c.execute("SELECT 1 FROM news_read WHERE news_id=? AND user_id=?", (r["id"], me["id"])).fetchone())))
            return self.send_json(rows)
        if p == "/api/todos":
            return self.send_json({"rows": self._todo_rows(c, me),
                                   "people": [dict(x) for x in c.execute("SELECT id, name, role FROM users WHERE active=1 AND COALESCE(demo,0)=0 AND COALESCE(removed,0)=0 ORDER BY id")]})
        if p == "/api/profiles":
            rows = c.execute("""SELECT u.id, u.name, u.role, u.position, u.title, p.nickname, p.intro, p.likes, p.photo IS NOT NULL AS has_photo, p.updated
                                FROM users u LEFT JOIN profiles p ON p.user_id=u.id WHERE u.active=1 AND COALESCE(u.demo,0)=0 AND COALESCE(u.removed,0)=0
                                ORDER BY CASE u.role WHEN 'admin' THEN 0 WHEN 'manager' THEN 1 ELSE 2 END, u.id""").fetchall()
            return self.send_json([dict(r) for r in rows])
        if p == "/api/profile/photo":
            r = c.execute("SELECT photo FROM profiles WHERE user_id=?", (int(q.get("id") or 0),)).fetchone()
            if not r or not r["photo"]: return self.err("沒有照片", 404)
            return self.send_file(os.path.join(self.PHOTO_DIR, "profile", os.path.basename(r["photo"])), "private, no-cache")
        if p == "/api/position/log":
            if not O.is_admin(me): return self.err("只有老闆可以看", 403)
            return self.send_json([dict(x) for x in c.execute("""SELECT l.*, u.name FROM position_log l JOIN users u ON u.id=l.user_id ORDER BY l.id DESC LIMIT 50""")])
        return O.NOPE

    def extra_post(self, c, me, p, d):
        if p == "/api/tour/done":
            k = (d.get("k") or "")[:40]
            if k: c.execute("INSERT OR IGNORE INTO tours(user_id,k,at) VALUES(?,?,?)", (me["id"], k, O.now())); c.commit()
            return self.send_json({"ok": True})
        if p == "/api/tour/reset":
            c.execute("DELETE FROM tours WHERE user_id=?", (me["id"],)); c.commit(); return self.send_json({"ok": True})
        if p == "/api/news/read":
            c.execute("INSERT OR IGNORE INTO news_read(news_id,user_id,at) VALUES(?,?,?)", (int(d.get("id") or 0), me["id"], O.now())); c.commit()
            return self.send_json({"ok": True})
        if p == "/api/news/remove":
            if not O.is_admin(me): return self.err("只有老闆可以下架", 403)
            c.execute("UPDATE news SET active=0 WHERE id=?", (int(d.get("id") or 0),)); c.commit(); return self.send_json({"ok": True})
        if p == "/api/todo/save":
            title = (d.get("title") or "").strip()
            if not title: return self.err("待辦要寫做什麼")
            due = d.get("due") or None
            if due and not O.ymd(due): return self.err("日期不對")
            who = d.get("assignee")
            targets = ([r[0] for r in c.execute("SELECT id FROM users WHERE active=1 AND role='staff' AND COALESCE(demo,0)=0 AND COALESCE(removed,0)=0")]
                       if who == "staff" else [int(who) if who else me["id"]])
            if not O.can_fin(me) and any(t != me["id"] for t in targets): return self.err("只能幫自己加待辦；要交辦別人請找店長或老闆", 403)
            if d.get("id"):
                t = c.execute("SELECT * FROM todos WHERE id=?", (int(d["id"]),)).fetchone()
                if not t or (t["created_by"] != me["id"] and not O.is_admin(me)): return self.err("只能改自己開的待辦", 403)
                c.execute("UPDATE todos SET title=?, note=?, due=?, assignee=? WHERE id=?", (title, (d.get("note") or "").strip(), due, targets[0], t["id"]))
            else:
                for uid in targets:
                    c.execute("INSERT INTO todos(title,note,assignee,due,created,created_by) VALUES(?,?,?,?,?,?)",
                              (title, (d.get("note") or "").strip(), uid, due, O.now(), me["id"]))
            c.commit()
            others = [t for t in targets if t != me["id"]]
            if others and not d.get("id"): O.Notifier.notify(c, others, "新的待辦：" + title, ("%s 前完成。" % due[5:] if due else "") + (d.get("note") or ""), "/#me")
            return self.send_json({"ok": True})
        if p == "/api/todo/done":
            t = c.execute("SELECT * FROM todos WHERE id=? AND removed=0", (int(d.get("id") or 0),)).fetchone()
            if not t: return self.err("找不到這個待辦", 404)
            if me["id"] not in (t["assignee"], t["created_by"]) and not O.is_admin(me): return self.err("這不是你的待辦", 403)
            on = d.get("done", True)
            c.execute("UPDATE todos SET done_at=?, done_by=? WHERE id=?", (O.now() if on else None, me["id"] if on else None, t["id"])); c.commit()
            if on and t["created_by"] and t["created_by"] != me["id"]:
                cr = c.execute("SELECT role FROM users WHERE id=?", (t["created_by"],)).fetchone()
                O.Notifier.notify(c, [t["created_by"]], "%s 完成了待辦" % me["name"], t["title"], "/#boss" if cr and cr["role"] == "admin" else "/#me")
            return self.send_json({"ok": True})
        if p == "/api/todo/remove":
            t = c.execute("SELECT * FROM todos WHERE id=?", (int(d.get("id") or 0),)).fetchone()
            if not t or (t["created_by"] != me["id"] and not O.is_admin(me)): return self.err("只能刪自己開的待辦", 403)
            c.execute("UPDATE todos SET removed=1 WHERE id=?", (t["id"],)); c.commit(); return self.send_json({"ok": True})
        if p == "/api/profile/save":
            uid = int(d.get("user_id") or me["id"])
            if uid != me["id"] and not O.is_admin(me): return self.err("只能改自己的個人檔案", 403)
            if not c.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone(): return self.err("找不到這位夥伴", 404)
            cur = c.execute("SELECT * FROM profiles WHERE user_id=?", (uid,)).fetchone()
            g = lambda k, n: (d.get(k) if k in d else (cur[k] if cur else "")) or ""
            nick, intro, likes = g("nickname", 0).strip()[:20], g("intro", 0).strip()[:400], g("likes", 0).strip()[:100]
            photo = cur["photo"] if cur else None
            if d.get("photo"):
                try: photo = O.save_photo(d["photo"], os.path.join(self.PHOTO_DIR, "profile"), "u%d" % uid)
                except ValueError as e: return self.err(str(e))
            c.execute("""INSERT INTO profiles(user_id,nickname,intro,likes,photo,updated) VALUES(?,?,?,?,?,?)
                         ON CONFLICT(user_id) DO UPDATE SET nickname=excluded.nickname, intro=excluded.intro, likes=excluded.likes, photo=excluded.photo, updated=excluded.updated""",
                      (uid, nick, intro, likes, photo, O.now()))
            if photo and intro:   # 個人檔案填好了 → 相關待辦自動打勾
                c.execute("UPDATE todos SET done_at=?, done_by=? WHERE assignee=? AND kind='profile' AND done_at IS NULL AND removed=0", (O.now(), me["id"], uid))
            if photo:
                c.execute("""UPDATE todos SET done_at=?, done_by=? WHERE kind='photos' AND done_at IS NULL AND removed=0 AND NOT EXISTS
                             (SELECT 1 FROM users u LEFT JOIN profiles p ON p.user_id=u.id WHERE u.active=1 AND u.role='staff' AND COALESCE(u.demo,0)=0
                              AND COALESCE(u.removed,0)=0 AND p.photo IS NULL)""", (O.now(), me["id"]))
            c.commit(); return self.send_json({"ok": True})
        return O.NOPE
