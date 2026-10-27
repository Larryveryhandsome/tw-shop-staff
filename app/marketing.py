# -*- coding: utf-8 -*-
"""行銷審核：外部 AI（任何工具皆可）交貼文草稿（文字＋圖片）、社群雷達找到的團體訂單需求 → 全部進系統給老闆審核；
老闆核准的才可以發（一律人工發）；審核結果寫回交接資料夾。只有老闆看得到。
交接（跟 GPT 約好的格式寫在 MK_DIR/README_給GPT.md）：
  MK_DIR/給CRM/YYYY-MM-DD/posts.json＋圖片  → 匯入 mk_post（id 不重複；檔案改過會再讀一次，只收新的 id）
  MK_DIR/CRM回饋/YYYY-MM-DD.json          ← 那一批每篇的審核結果（每次審核、發布都重寫）
  MK_DIR/給CRM/發布回報/*.json             → GPT 排程／發出去之後回報（老闆 10/19：發文由 GPT 那邊發）；
                                            只認老闆核准過的，沒核准就被發 → 不改狀態、馬上通知老闆
  MK_DIR/patrol/YYYYMMDD/patrol*.json（外部社群雷達程式寫的，格式見 docs/marketing.md）→ 匯入 mk_patrol（網址不重複）
只有這個伺服器程序寫資料庫；檔案交接、排程每 5 分鐘收一次。
mixin：app.H 繼承 Marketing；路由 mk_get / mk_post 沒對到回 O.NOPE。"""
import glob, json, os, re, shutil, threading, time
from datetime import datetime
import ops as O

HERE = os.path.dirname(os.path.abspath(__file__))
import cfg
MK_DIR = os.environ.get("MK_DIR") or cfg.path(cfg.PATHS.get("marketing_dir", "data/marketing"))
PATROL_DIR = os.environ.get("PATROL_DIR") or os.path.join(MK_DIR, "patrol")
CHANNELS = {"threads": "Threads", "fb_group": "臉書社團", "fb_page": "臉書粉專", "ig": "Instagram"}
TARGET = {"patrol": (20, 50), "post": (2, 5)}           # 每天社群雷達 20～50 則、貼文草稿 2～5 篇
AREA_IN = tuple(cfg.SALES.get("area_core") or ())         # 重點區域（config/store.toml）
MIN_BOXES = int(cfg.SALES.get("min_order", 3))
MIN_OUTSIDE = int(cfg.SALES.get("area_outside_min", 20))


def out_reason(area, boxes):
    """雷達抓到的這則不在範圍內就回原因（系統自動略過，老闆在「紀錄」看得到）"""
    a = area or ""
    if AREA_IN and a and not any(x in a for x in AREA_IN) and (boxes or 0) < MIN_OUTSIDE:
        return "系統：重點區域以外，%s" % ("不到 %d 份" % MIN_OUTSIDE if boxes else "看不出有 %d 份以上" % MIN_OUTSIDE)
    if boxes is not None and 0 < boxes < MIN_BOXES:
        return "系統：不到 %d 份，不外送" % MIN_BOXES
    return ""
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
IMG_MAX = 15 * 1024 * 1024

SCHEMA = """
CREATE TABLE IF NOT EXISTS mk_post(id INTEGER PRIMARY KEY, src_id TEXT UNIQUE, batch TEXT, channel TEXT, grp TEXT, title TEXT, body TEXT, orig_body TEXT,
  images TEXT, image_note TEXT, cta TEXT, suggest_time TEXT, gpt_note TEXT, revision_of TEXT, status TEXT NOT NULL DEFAULT '待審',
  review_note TEXT, reviewed_by INTEGER, reviewed_at TEXT, posted_url TEXT, posted_at TEXT, posted_by INTEGER, created TEXT);
CREATE TABLE IF NOT EXISTS mk_patrol(id INTEGER PRIMARY KEY, url TEXT UNIQUE, batch TEXT, platform TEXT, title TEXT, snippet TEXT, who TEXT,
  post_date TEXT, need TEXT, boxes INTEGER, event_date TEXT, area TEXT, phone TEXT, why TEXT, action TEXT, reply TEXT, orig_reply TEXT, score INTEGER,
  status TEXT NOT NULL DEFAULT '待審', review_note TEXT, reviewed_by INTEGER, reviewed_at TEXT, lead_id INTEGER, created TEXT);
CREATE TABLE IF NOT EXISTS mk_group(id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT, rule TEXT, active INTEGER NOT NULL DEFAULT 1, created TEXT);
CREATE TABLE IF NOT EXISTS mk_import(k TEXT PRIMARY KEY, at TEXT, n INTEGER, msg TEXT, done TEXT);
CREATE TABLE IF NOT EXISTS mk_metric(id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, at TEXT NOT NULL, views INTEGER, likes INTEGER, replies INTEGER,
  reposts INTEGER, shares INTEGER, dms INTEGER, note TEXT, created TEXT, UNIQUE(post_id, at));
CREATE INDEX IF NOT EXISTS ix_mk_post_status ON mk_post(status);
CREATE INDEX IF NOT EXISTS ix_mk_patrol_status ON mk_patrol(status);
"""


def migrate(c):
    c.executescript(SCHEMA)
    if "scheduled_at" not in {r[1] for r in c.execute("PRAGMA table_info(mk_post)")}:   # GPT 排程的發文時間（10/19）
        c.execute("ALTER TABLE mk_post ADD COLUMN scheduled_at TEXT")


def _s(x, n):
    return str(x if x is not None else "").strip()[:n]


def _int(x):
    try: return int(re.sub(r"[^\d]", "", str(x))) if re.search(r"\d", str(x or "")) else None
    except Exception: return None


def _http(u):
    u = _s(u, 600)
    return u if re.match(r"https?://", u) else ""


def import_posts(c, photo_dir, mk_dir=None):
    """GPT 交的貼文 → mk_post；回傳 (新增幾篇, 問題清單)"""
    base = os.path.join(mk_dir or MK_DIR, "給CRM")
    if not os.path.isdir(base): return 0, []
    out = os.path.join(photo_dir, "marketing"); os.makedirs(out, exist_ok=True)
    added, errs = 0, []
    for f in sorted(glob.glob(os.path.join(base, "*", "posts.json"))):
        folder = os.path.dirname(f); batch = os.path.basename(folder); key = "posts:" + batch
        mt = str(os.path.getmtime(f))
        r = c.execute("SELECT at FROM mk_import WHERE k=?", (key,)).fetchone()
        if r and r[0] == mt: continue
        bad = []
        try:
            data = json.load(open(f, encoding="utf-8-sig"))
            posts = data.get("posts") if isinstance(data, dict) else data
            if not isinstance(posts, list): raise ValueError("posts 要是清單")
        except Exception as e:
            bad.append("posts.json 讀不到：%s" % e); posts = []
        for p in posts:
            if not isinstance(p, dict): bad.append("有一筆格式不對"); continue
            sid = _s(p.get("id"), 60); body = _s(p.get("text"), 5000)
            if not sid or not body: bad.append("%s：id 或 text 是空的" % (sid or "?")); continue
            if c.execute("SELECT 1 FROM mk_post WHERE src_id=?", (sid,)).fetchone(): continue
            imgs = []
            for fn in (p.get("images") or ([p["image"]] if p.get("image") else [])):
                fn = os.path.basename(str(fn)); src = os.path.join(folder, fn)
                if not fn.lower().endswith(IMG_EXT) or not os.path.isfile(src): bad.append("%s：圖 %s 找不到或格式不對" % (sid, fn)); continue
                if os.path.getsize(src) > IMG_MAX: bad.append("%s：圖 %s 超過 15MB" % (sid, fn)); continue
                dst = re.sub(r"[^A-Za-z0-9_.-]", "_", "%s__%s" % (sid, fn))
                shutil.copy2(src, os.path.join(out, dst)); imgs.append(dst)
            ch = p.get("channel") if p.get("channel") in CHANNELS else "threads"
            c.execute("""INSERT INTO mk_post(src_id,batch,channel,grp,title,body,orig_body,images,image_note,cta,suggest_time,gpt_note,revision_of,created)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (sid, batch, ch, _s(p.get("group"), 80), _s(p.get("title"), 80), body, body, json.dumps(imgs), _s(p.get("image_note"), 300),
                       _s(p.get("cta"), 200), _s(p.get("suggest_time"), 20), _s(p.get("notes"), 800), _s(p.get("revision_of"), 60), O.now()))
            added += 1
        c.execute("INSERT OR REPLACE INTO mk_import(k,at,n,msg,done) VALUES(?,?,?,?,?)", (key, mt, len(posts), "；".join(bad)[:800], O.now()))
        errs += ["%s %s" % (batch, b) for b in bad]
    c.commit()
    return added, errs


def import_patrol(c, pdir=None, gpt=False):
    """海巡結果 → mk_patrol（網址重複的不收）；回傳新增幾則。
    gpt=True：GPT 登入後在 Threads／臉書社團裡找到的（MK_DIR/給CRM/海巡/YYYY-MM-DD.json，同一個格式）"""
    pdir = pdir or (os.path.join(MK_DIR, "給CRM", "海巡") if gpt else PATROL_DIR)
    if not os.path.isdir(pdir): return 0
    added = 0
    for f in sorted(glob.glob(os.path.join(pdir, "*.json") if gpt else os.path.join(pdir, "*", "patrol*.json"))):
        batch = os.path.splitext(os.path.basename(f))[0] if gpt else os.path.basename(os.path.dirname(f))
        key = ("patrol-gpt:%s" if gpt else "patrol:%s") % (os.path.basename(f) if gpt else "%s/%s" % (batch, os.path.basename(f)))
        mt = str(os.path.getmtime(f))
        r = c.execute("SELECT at FROM mk_import WHERE k=?", (key,)).fetchone()
        if r and r[0] == mt: continue
        try:
            data = json.load(open(f, encoding="utf-8-sig"))
            items = data.get("items") if isinstance(data, dict) else data
        except Exception:
            items = []
        n = 0
        for x in items if isinstance(items, list) else []:
            if not isinstance(x, dict): continue
            url = _http(x.get("url"))
            if not url or c.execute("SELECT 1 FROM mk_patrol WHERE url=?", (url,)).fetchone(): continue
            reply = _s(x.get("reply"), 1000)
            score = _int(x.get("score")); boxes = _int(x.get("boxes")); area = _s(x.get("area"), 40)
            why_out = out_reason(area, boxes)
            c.execute("""INSERT INTO mk_patrol(url,batch,platform,title,snippet,who,post_date,need,boxes,event_date,area,phone,why,action,reply,orig_reply,score,
                         status,review_note,reviewed_at,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (url, batch, _s(x.get("platform"), 30) or "其他", _s(x.get("title"), 120), _s(x.get("snippet"), 400), _s(x.get("who"), 80),
                       _s(x.get("post_date"), 20), _s(x.get("need"), 200), boxes, _s(x.get("event_date"), 20), area,
                       _s(x.get("phone"), 40), _s(x.get("why"), 300), _s(x.get("action"), 20) or "留言", reply, reply,
                       max(1, min(5, score)) if score else None, "略過" if why_out else "待審", why_out or None, O.now() if why_out else None, O.now()))
            n += 1
        c.execute("INSERT OR REPLACE INTO mk_import(k,at,n,msg,done) VALUES(?,?,?,?,?)", (key, mt, n, "", O.now()))
        added += n
    c.commit()
    return added


def import_report(c, mk_dir=None):
    """GPT 回報排程／發布 → 改狀態；回傳 (改了幾篇, 違規清單：沒核准就被排程或發出去的)"""
    base = os.path.join(mk_dir or MK_DIR, "給CRM", "發布回報")
    if not os.path.isdir(base): return 0, []
    n, bad, touched = 0, [], set()
    for f in sorted(glob.glob(os.path.join(base, "*.json"))):
        key = "report:" + os.path.basename(f); mt = str(os.path.getmtime(f))
        r = c.execute("SELECT at FROM mk_import WHERE k=?", (key,)).fetchone()
        if r and r[0] == mt: continue
        try:
            data = json.load(open(f, encoding="utf-8-sig"))
            items = data.get("posts") if isinstance(data, dict) else data
        except Exception:
            items = []
        for x in items if isinstance(items, list) else []:
            if not isinstance(x, dict): continue
            p = c.execute("SELECT * FROM mk_post WHERE src_id=?", (_s(x.get("id"), 60),)).fetchone()
            st = x.get("status")
            m = x.get("metrics")
            if p and isinstance(m, dict) and (p["status"] == "已發布" or st == "已發布"):   # 成效數字（老闆 10/19：數據監控 Claude 負責）
                at = _s(m.get("at"), 16) or O.now()[:16]
                c.execute("""INSERT OR REPLACE INTO mk_metric(post_id,at,views,likes,replies,reposts,shares,dms,note,created) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                          (p["id"], at, _int(m.get("views")), _int(m.get("likes")), _int(m.get("replies")), _int(m.get("reposts")),
                           _int(m.get("shares")), _int(m.get("dms")), _s(m.get("note"), 200), O.now()))
                n += 1
            if not p or st not in ("已排程", "已發布"): continue
            if p["status"] not in ("已核准", "已排程", "已發布"):
                bad.append("%s（%s，CRM 狀態是%s）" % (p["src_id"], st, p["status"])); continue
            if st == "已排程" and p["status"] == "已核准":
                c.execute("UPDATE mk_post SET status='已排程', scheduled_at=? WHERE id=?", (_s(x.get("scheduled_at"), 20) or None, p["id"]))
            elif st == "已發布" and p["status"] != "已發布":
                c.execute("UPDATE mk_post SET status='已發布', posted_url=?, posted_at=? WHERE id=?",
                          (_http(x.get("posted_url")) or None, _s(x.get("posted_at"), 20) or O.now(), p["id"]))
            else:
                continue
            n += 1; touched.add(p["batch"])
        c.execute("INSERT OR REPLACE INTO mk_import(k,at,n,msg,done) VALUES(?,?,?,?,?)", (key, mt, n, "；".join(bad)[:800], O.now()))
    c.commit()
    for b in touched: write_feedback(c, b, mk_dir)
    return n, bad


def write_feedback(c, batch, mk_dir=None):
    """審核結果寫回給 GPT：MK_DIR/CRM回饋/<批次>.json"""
    if not batch: return
    rows = c.execute("SELECT * FROM mk_post WHERE batch=? ORDER BY id", (batch,)).fetchall()
    out = []
    for r in rows:
        out.append({"id": r["src_id"], "status": r["status"], "note": r["review_note"] or "",
                    "final_text": r["body"] if r["body"] != r["orig_body"] else None,
                    "posted_url": r["posted_url"] or None, "posted_at": r["posted_at"] or None, "reviewed_at": r["reviewed_at"] or None,
                    "scheduled_at": r["scheduled_at"] if "scheduled_at" in r.keys() else None})
    d = os.path.join(mk_dir or MK_DIR, "CRM回饋")
    try:
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, batch + ".json.tmp")
        json.dump({"batch": batch, "updated": O.now(), "posts": out}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(d, batch + ".json"))
    except Exception:
        pass


def stats(c, days=30):
    """數據監控（老闆 10/19：Claude 負責）：發文、成效、海巡漏斗、海巡轉來的名單、社群來的訂單"""
    since = O.add_days(O.today(), -days + 1)
    last = """SELECT p.id, p.src_id, p.channel, p.grp, p.title, p.body, p.posted_at, p.posted_url, m.at, m.views, m.likes, m.replies, m.reposts, m.shares, m.dms
              FROM mk_post p LEFT JOIN mk_metric m ON m.id=(SELECT id FROM mk_metric WHERE post_id=p.id ORDER BY at DESC LIMIT 1)
              WHERE p.status='已發布' AND substr(p.posted_at,1,10)>=?"""
    posts = [dict(r) for r in c.execute(last + " ORDER BY p.posted_at DESC", (since,))]
    tot = {k: sum(x[k] or 0 for x in posts) for k in ("views", "likes", "replies", "reposts", "shares", "dms")}
    by_ch = {}
    for x in posts: by_ch[x["channel"]] = by_ch.get(x["channel"], 0) + 1
    st = {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM mk_post WHERE COALESCE(substr(reviewed_at,1,10), batch)>=? GROUP BY status", (since,))}
    pt = {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM mk_patrol WHERE substr(created,1,10)>=? GROUP BY status", (since,))}
    leads = {r[0]: r[1] for r in c.execute("""SELECT l.status, COUNT(*) FROM mk_patrol t JOIN leads l ON l.id=t.lead_id
                                                WHERE substr(t.created,1,10)>=? GROUP BY l.status""", (since,))}
    orders = [dict(r) for r in c.execute("""SELECT source, COUNT(*) n, COALESCE(SUM(boxes),0) boxes, COALESCE(SUM(amount),0) amount FROM deliveries
                                            WHERE day>=? AND source IN ('Threads','臉書','IG') AND COALESCE(cancelled,0)=0 AND COALESCE(deleted,0)=0
                                            GROUP BY source""", (since,))]
    daily = []
    for i in range(13, -1, -1):
        d = O.add_days(O.today(), -i)
        daily.append({"day": d,
                      "posted": c.execute("SELECT COUNT(*) FROM mk_post WHERE substr(posted_at,1,10)=?", (d,)).fetchone()[0],
                      "patrol": c.execute("SELECT COUNT(*) FROM mk_patrol WHERE substr(created,1,10)=?", (d,)).fetchone()[0],
                      "replied": c.execute("SELECT COUNT(*) FROM mk_patrol WHERE status='已回覆' AND substr(reviewed_at,1,10)=?", (d,)).fetchone()[0]})
    rej = [dict(r) for r in c.execute("""SELECT src_id, title, review_note FROM mk_post WHERE status IN ('退回','作廢') AND substr(reviewed_at,1,10)>=?
                                         AND COALESCE(review_note,'')<>'' ORDER BY reviewed_at DESC LIMIT 10""", (since,))]
    needs = [dict(r) for r in c.execute("""SELECT need, COUNT(*) n FROM mk_patrol WHERE substr(created,1,10)>=? AND COALESCE(need,'')<>''
                                           GROUP BY need ORDER BY n DESC LIMIT 8""", (since,))]
    top = sorted([x for x in posts if x["views"] is not None], key=lambda x: -(x["views"] or 0))[:5]
    return {"days": days, "since": since, "posts": posts[:40], "total": tot, "by_channel": by_ch, "post_status": st, "patrol": pt,
            "leads": leads, "orders": orders, "daily": daily, "rejected": rej, "needs": needs, "top": top,
            "no_metric": sum(1 for x in posts if x["views"] is None)}


def weekly_report(c, mk_dir=None):
    """每週一 09:30：上週數據通知老闆，也寫一份給 GPT（CRM回饋/週報_日期.md）"""
    S = stats(c, 7); T = S["total"]
    lines = ["# 上週行銷週報（%s 起 7 天）" % S["since"], "",
             "- 發文 %d 篇（%s）" % (len(S["posts"]), "、".join("%s %d" % (CHANNELS.get(k, k), v) for k, v in S["by_channel"].items()) or "無"),
             "- 成效合計：觀看 %d、讚 %d、留言 %d、轉發 %d、私訊 %d（%d 篇還沒回報數字）" % (T["views"], T["likes"], T["replies"], T["reposts"], T["dms"], S["no_metric"]),
             "- 海巡 %d 則：回覆 %d、轉電話名單 %d、略過 %d" % (sum(S["patrol"].values()), S["patrol"].get("已回覆", 0), S["patrol"].get("轉名單", 0), S["patrol"].get("略過", 0)),
             "- 海巡轉來的名單：%s" % ("、".join("%s %d" % kv for kv in S["leads"].items()) or "無"),
             "- 社群來的訂單：%s" % ("、".join("%s %d 單 %d 盒" % (o["source"], o["n"], o["boxes"]) for o in S["orders"]) or "無"), ""]
    if S["top"]:
        lines += ["## 表現最好的貼文"] + ["- %s（%s）觀看 %s、讚 %s、留言 %s：%s" % (x["src_id"], CHANNELS.get(x["channel"], x["channel"]), x["views"], x["likes"],
                                                                         x["replies"], (x["title"] or x["body"][:30])) for x in S["top"]] + [""]
    if S["rejected"]:
        lines += ["## 老闆退回／不要的原因（寫文要避開）"] + ["- %s：%s" % (x["src_id"], x["review_note"]) for x in S["rejected"]] + [""]
    if S["needs"]:
        lines += ["## 海巡看到大家在找的（寫文可以參考）"] + ["- %s（%d 則）" % (x["need"], x["n"]) for x in S["needs"]]
    txt = "\n".join(lines)
    try:
        d = os.path.join(mk_dir or MK_DIR, "CRM回饋"); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "週報_%s.md" % O.today()), "w", encoding="utf-8").write(txt + "\n")
    except Exception:
        pass
    O.Notifier.notify(c, O.admins(c), "行銷週報：上週發文 %d 篇、海巡 %d 則" % (len(S["posts"]), sum(S["patrol"].values())),
                      "觀看 %d、留言 %d、私訊 %d；海巡回覆 %d、轉名單 %d。到「行銷 › 數據」看。" % (
                          T["views"], T["replies"], T["dms"], S["patrol"].get("已回覆", 0), S["patrol"].get("轉名單", 0)), "/#mk")
    return txt


def pending(c):
    return (c.execute("SELECT COUNT(*) FROM mk_post WHERE status='待審'").fetchone()[0],
            c.execute("SELECT COUNT(*) FROM mk_patrol WHERE status='待審'").fetchone()[0])


def sweep(c, photo_dir):
    """收 GPT 的貼文和海巡結果；有新的就通知老闆"""
    a, errs = import_posts(c, photo_dir)
    b = import_patrol(c) + import_patrol(c, gpt=True)
    _, bad = import_report(c)
    if bad:
        O.Notifier.notify(c, O.admins(c), "行銷：GPT 回報發了你還沒核准的貼文", "；".join(bad)[:200], "/#mk")
    if a or b:
        p, q = pending(c)
        O.Notifier.notify(c, O.admins(c), "行銷：%s等你審核" % "、".join(x for x in (a and "GPT 新貼文 %d 篇" % a, b and "海巡 %d 則" % b) if x),
                          "目前待審貼文 %d 篇、海巡 %d 則。" % (p, q), "/#mk")
    if errs:
        O.Notifier.notify(c, O.admins(c), "行銷：GPT 交的檔案有問題", "；".join(errs)[:200], "/#mk")
    return a, b


def cron(db_factory, photo_dir):
    def loop():
        while True:
            c = None
            try:
                c = db_factory(); n = datetime.now(); d = n.date().isoformat(); hm = n.strftime("%H:%M")
                sweep(c, photo_dir)
                if n.weekday() == 0 and "09:30" <= hm < "12:00" and O.once(c, "mk_week:" + d):
                    weekly_report(c)
                # 10:30 外部 AI 還沒交今天的貼文 → 提醒老闆（只在有交接資料夾、而且交過貼文的店才提醒）
                if ("10:30" <= hm < "21:00" and os.path.isdir(os.path.join(MK_DIR, "給CRM")) and c.execute("SELECT 1 FROM mk_post LIMIT 1").fetchone()
                        and not c.execute("SELECT 1 FROM mk_post WHERE batch=?", (d,)).fetchone() and O.once(c, "mk_nogpt:" + d)):
                    O.Notifier.notify(c, O.admins(c), "行銷：今天還沒有貼文草稿", "交接資料夾 給CRM/%s 還沒有 posts.json。" % d, "/#mk")
            except Exception:
                pass
            finally:
                try: c and c.close()
                except Exception: pass
            time.sleep(300)
    threading.Thread(target=loop, daemon=True).start()


def _post_dict(r):
    x = dict(r); x["images"] = json.loads(r["images"] or "[]"); return x


class Marketing:
    def mk_me(self, c, me):
        if me["role"] != "admin": return {}
        p, q = pending(c)
        return {"mk_pending": p + q}

    def mk_get(self, c, me, p, q):
        if not p.startswith("/api/mk"): return O.NOPE
        if me["role"] != "admin": return self.err("只有老闆可以看", 403)
        if p == "/api/mk/img":
            f = os.path.basename(q.get("f") or "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", f): return self.err("檔名不對", 400)
            return self.send_file(os.path.join(self.PHOTO_DIR, "marketing", f), "private, max-age=86400")
        if p == "/api/mk":
            tab = q.get("tab") or "review"; t = O.today()
            P = lambda w, a=(): [_post_dict(r) for r in c.execute("SELECT * FROM mk_post WHERE " + w, a)]
            posts = {"review": lambda: P("status='待審' ORDER BY batch, id"),
                     "publish": lambda: P("status IN ('已核准','已排程') ORDER BY COALESCE(scheduled_at, batch || ' ' || COALESCE(suggest_time,'')), id"),
                     "done": lambda: P("status IN ('已發布','退回','作廢') ORDER BY COALESCE(posted_at, reviewed_at) DESC LIMIT 60")}.get(tab, lambda: [])()
            patrol = [dict(r) for r in c.execute("""SELECT * FROM mk_patrol WHERE status IN ('待審','要回覆')
                        ORDER BY status='待審', COALESCE(score,0) DESC, COALESCE(boxes,0) DESC, id DESC LIMIT 150""")] if tab == "patrol" else []
            done_patrol = [dict(r) for r in c.execute("""SELECT * FROM mk_patrol WHERE status IN ('已回覆','轉名單','略過')
                        ORDER BY COALESCE(reviewed_at, created) DESC LIMIT 60""")] if tab == "done" else []
            counts = {"review": c.execute("SELECT COUNT(*) FROM mk_post WHERE status='待審'").fetchone()[0],
                      "publish": c.execute("SELECT COUNT(*) FROM mk_post WHERE status IN ('已核准','已排程')").fetchone()[0],
                      "patrol": c.execute("SELECT COUNT(*) FROM mk_patrol WHERE status IN ('待審','要回覆')").fetchone()[0]}
            today = {"gpt": c.execute("SELECT COUNT(*) FROM mk_post WHERE batch=?", (t,)).fetchone()[0],
                     "patrol": c.execute("SELECT COUNT(*) FROM mk_patrol WHERE substr(created,1,10)=?", (t,)).fetchone()[0],
                     "posted": c.execute("SELECT COUNT(*) FROM mk_post WHERE substr(posted_at,1,10)=?", (t,)).fetchone()[0],
                     "replied": c.execute("SELECT COUNT(*) FROM mk_patrol WHERE status='已回覆' AND substr(reviewed_at,1,10)=?", (t,)).fetchone()[0]}
            data = stats(c, 30) if tab == "data" else None
            return self.send_json({"tab": tab, "posts": posts, "patrol": patrol, "done_patrol": done_patrol, "counts": counts, "today": today, "data": data,
                                   "target": TARGET, "channels": CHANNELS, "mk_dir": MK_DIR, "area": AREA_IN, "min_boxes": MIN_BOXES, "min_outside": MIN_OUTSIDE,
                                   "groups": [dict(r) for r in c.execute("SELECT * FROM mk_group WHERE active=1 ORDER BY id")],
                                   "imports": [dict(r) for r in c.execute("SELECT * FROM mk_import ORDER BY done DESC LIMIT 8")]})
        return O.NOPE

    def mk_post(self, c, me, p, d):
        if not p.startswith("/api/mk/"): return O.NOPE
        if me["role"] != "admin": return self.err("只有老闆可以審核", 403)
        now = O.now()
        if p == "/api/mk/sweep":       # 老闆按「現在收一次」
            a, b = sweep(c, self.PHOTO_DIR); return self.send_json({"ok": True, "posts": a, "patrol": b})
        if p == "/api/mk/post/review":
            r = c.execute("SELECT * FROM mk_post WHERE id=?", (int(d.get("id") or 0),)).fetchone()
            if not r: return self.err("找不到這篇", 404)
            act, note = d.get("action"), _s(d.get("note"), 500)
            if act == "approve":
                if r["status"] != "待審": return self.err("這篇已經處理過了（%s）" % r["status"])
                body = _s(d.get("body"), 5000) or r["body"]
                c.execute("UPDATE mk_post SET status='已核准', body=?, review_note=?, reviewed_by=?, reviewed_at=? WHERE id=?", (body, note, me["id"], now, r["id"]))
            elif act == "reject":
                if r["status"] not in ("待審", "已核准", "已排程"): return self.err("這篇已經%s，不能退回" % r["status"])
                if not note: return self.err("退回要寫意見，GPT 才知道怎麼改")
                c.execute("UPDATE mk_post SET status='退回', review_note=?, reviewed_by=?, reviewed_at=? WHERE id=?", (note, me["id"], now, r["id"]))
            elif act == "void":
                if r["status"] == "已發布": return self.err("已經發出去了")
                c.execute("UPDATE mk_post SET status='作廢', review_note=?, reviewed_by=?, reviewed_at=? WHERE id=?", (note, me["id"], now, r["id"]))
            elif act == "reopen":
                if r["status"] == "已發布": return self.err("已經發出去了")
                c.execute("UPDATE mk_post SET status='待審' WHERE id=?", (r["id"],))
            else:
                return self.err("動作不對")
            c.commit(); write_feedback(c, r["batch"]); return self.send_json({"ok": True})
        if p == "/api/mk/post/posted":
            r = c.execute("SELECT * FROM mk_post WHERE id=?", (int(d.get("id") or 0),)).fetchone()
            if not r: return self.err("找不到這篇", 404)
            if r["status"] not in ("已核准", "已排程"): return self.err("老闆核准的才能發（現在是%s）" % r["status"])
            url = _http(d.get("url"))
            c.execute("UPDATE mk_post SET status='已發布', posted_url=?, posted_at=?, posted_by=? WHERE id=?", (url or None, now, me["id"], r["id"]))
            c.commit(); write_feedback(c, r["batch"]); return self.send_json({"ok": True})
        if p == "/api/mk/patrol/review":
            r = c.execute("SELECT * FROM mk_patrol WHERE id=?", (int(d.get("id") or 0),)).fetchone()
            if not r: return self.err("找不到這則", 404)
            act, note = d.get("action"), _s(d.get("note"), 500)
            if act == "reply":
                reply = _s(d.get("reply"), 1000)
                if not reply: return self.err("回覆內容是空的")
                c.execute("UPDATE mk_patrol SET status='要回覆', reply=?, reviewed_by=?, reviewed_at=? WHERE id=?", (reply, me["id"], now, r["id"]))
            elif act == "replied":
                if r["status"] != "要回覆": return self.err("要先核准回覆")
                c.execute("UPDATE mk_patrol SET status='已回覆', reviewed_at=? WHERE id=?", (now, r["id"]))
            elif act == "skip":
                c.execute("UPDATE mk_patrol SET status='略過', review_note=?, reviewed_by=?, reviewed_at=? WHERE id=?", (note, me["id"], now, r["id"]))
            elif act == "lead":
                if r["lead_id"]: return self.err("已經轉過了")
                tag = O.today().replace("-", "")
                seq = c.execute("SELECT COUNT(*) FROM leads WHERE code LIKE ?", ("S%s%%" % tag,)).fetchone()[0] + 1
                name = r["who"] or r["title"] or "社群海巡"
                note_ = "\n".join(x for x in ("社群海巡（%s）：%s" % (r["platform"], r["url"]), r["need"] and "需求：" + r["need"],
                                              r["snippet"], r["why"] and "為什麼：" + r["why"], note) if x)
                lid = c.execute("""INSERT INTO leads(code,name,category,area,phone,note,priority,data_status,opp_type,boxes,event_date,status,updated)
                                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (f"S{tag}{seq:03d}", name[:60], "社群海巡", r["area"] or "", r["phone"] or "", note_, "A" if (r["score"] or 0) >= 4 else "B",
                                 "待核電話" if r["phone"] else "缺電話", "活動" if r["event_date"] else "固定午餐", r["boxes"], r["event_date"] or None,
                                 "未聯絡", now)).lastrowid
                c.execute("UPDATE mk_patrol SET status='轉名單', lead_id=?, review_note=?, reviewed_by=?, reviewed_at=? WHERE id=?", (lid, note, me["id"], now, r["id"]))
            elif act == "reopen":
                if r["lead_id"]: return self.err("已經轉成開發名單了")
                c.execute("UPDATE mk_patrol SET status='待審' WHERE id=?", (r["id"],))
            else:
                return self.err("動作不對")
            c.commit(); return self.send_json({"ok": True})
        if p == "/api/mk/group/save":
            name = _s(d.get("name"), 80)
            if not name: return self.err("社團名稱要填")
            url = _http(d.get("url"))
            if d.get("url") and not url: return self.err("網址要 http 開頭")
            if d.get("id"):
                c.execute("UPDATE mk_group SET name=?, url=?, rule=? WHERE id=?", (name, url, _s(d.get("rule"), 300), int(d["id"])))
            else:
                c.execute("INSERT INTO mk_group(name,url,rule,created) VALUES(?,?,?,?)", (name, url, _s(d.get("rule"), 300), now))
            c.commit(); return self.send_json({"ok": True})
        if p == "/api/mk/group/remove":
            c.execute("UPDATE mk_group SET active=0 WHERE id=?", (int(d.get("id") or 0),)); c.commit(); return self.send_json({"ok": True})
        return O.NOPE
