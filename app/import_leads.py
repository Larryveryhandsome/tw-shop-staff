# -*- coding: utf-8 -*-
"""名單匯入（xlsx / csv）。自動找表頭、自動對欄位名稱；匯入前一定先備份。
用法：
  python import_leads.py 檔案.xlsx [--sheet 工作表名] [--dry-run]
  python import_leads.py 檔案.csv  [--dry-run]
規則：
  - 同一「名單ID」已存在 → 略過（不覆蓋任何人已經打過、改過的資料）
  - 沒有名單ID → 用「名稱＋電話」判斷重複
  - 「勿再聯絡」、撥打紀錄、狀態一律不會被匯入檔改動
"""
import csv, os, sys, sqlite3, re, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import app

SYN = {  # 欄位 → 可能的表頭字樣（依序比對，含字即算）
    "code": ["名單ID", "名單編號", "ID", "編號"],
    "name": ["單位名稱", "單位／服務據點", "單位/服務據點", "單位", "機構", "公司", "名稱"],
    "category": ["類型", "分類", "產業", "類別"],
    "area": ["區域", "鄉鎮", "地區"],
    "phone": ["公開電話", "主要電話", "電話"],
    "phone2": ["其他電話", "分機", "行政分機", "第二電話"],
    "address": ["公開地址", "地址"],
    "contact_hint": ["建議聯絡窗口", "建議窗口", "建議轉接", "窗口"],
    "angle": ["訂餐切入情境", "切入情境", "切入", "情境", "為什麼值得打"],
    "priority": ["開發優先級", "優先級", "分級", "等級"],
    "data_status": ["資料查核狀態", "查核狀態", "資料狀態", "查核等級"],
    "note": ["查核／開發備註", "備註", "來源／備註", "來源"],
}

def norm_priority(v):
    s = str(v or "").strip().upper()
    if s[:1] in ("A", "B", "C"): return s[:1]
    if "核心" in s or "高" in s or s in ("1", "P1"): return "A"
    if "中" in s or s in ("2", "P2"): return "B"
    return "C" if s else "C"

def norm_status(v, phone):
    s = str(v or "")
    if not phone: return "缺電話"
    if any(k in s for k in ("待釐清", "泛稱", "不可直接")): return "待釐清"
    if any(k in s for k in ("已有公開聯絡依據", "已核", "官方", "已驗證")) and "待" not in s: return "已核"
    return "待核"

def read_rows(path, sheet=None):
    if path.lower().endswith(".csv"):
        for enc in ("utf-8-sig", "cp950", "utf-8"):
            try:
                with open(path, encoding=enc, newline="") as f: return [list(r) for r in csv.reader(f)], "(csv)"
            except UnicodeDecodeError: continue
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = [wb[sheet]] if sheet else wb.worksheets
    best = None
    for ws in sheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        hi, mp = find_header(rows)
        score = len(mp) if mp else 0
        if "name" in (mp or {}) and (best is None or score > best[0]): best = (score, rows, ws.title)
    if not best: raise SystemExit("找不到含「單位名稱」欄的工作表，請用 --sheet 指定")
    return best[1], best[2]

def find_header(rows):
    for i, r in enumerate(rows[:30]):
        cells = [str(x or "").strip() for x in r]
        mp = {}
        for f, keys in SYN.items():
            for k in keys:
                j = next((j for j, c in enumerate(cells) if c and k in c and j not in mp.values()), None)
                if j is not None: mp[f] = j; break
        if "name" in mp and len(mp) >= 3: return i, mp
    return None, None

def main():
    a = sys.argv[1:]
    if not a: print(__doc__); return
    path = a[0]; dry = "--dry-run" in a
    sheet = a[a.index("--sheet") + 1] if "--sheet" in a else None
    rows, title = read_rows(path, sheet)
    hi, mp = find_header(rows)
    hdr = [str(x or "") for x in rows[hi]]
    print(f"工作表：{title}　表頭在第 {hi+1} 列")
    for f, j in mp.items(): print(f"  {f:13s} ← 「{hdr[j]}」")
    unmapped = [h for j, h in enumerate(hdr) if h and j not in mp.values()]
    if unmapped: print("  （沒對到、會併進備註）：", "、".join(unmapped))
    recs = []
    for r in rows[hi + 1:]:
        g = lambda f: (str(r[mp[f]]).strip() if f in mp and mp[f] < len(r) and r[mp[f]] not in (None, "") else "")
        name = g("name")
        if not name: continue
        extra = "；".join(f"{hdr[j]}：{r[j]}" for j, h in enumerate(hdr) if h and j not in mp.values() and j < len(r)
                         and r[j] not in (None, "") and not isinstance(r[j], datetime.datetime))
        phone = g("phone")
        recs.append(dict(code=g("code") or None, name=name, category=g("category"), area=g("area"), phone=phone, phone2=g("phone2"),
                         address=g("address"), contact_hint=g("contact_hint"), angle=g("angle"), priority=norm_priority(g("priority")),
                         data_status=norm_status(g("data_status"), phone), note="；".join(x for x in (g("note"), extra) if x)))
    app.init_db()
    c = app.db()
    have_code = {x[0] for x in c.execute("SELECT code FROM leads WHERE code IS NOT NULL")}
    have_np = {(x[0], re.sub(r"\D", "", x[1] or "")) for x in c.execute("SELECT name, phone FROM leads")}
    new, dup = [], 0
    for d in recs:
        key = (d["name"], re.sub(r"\D", "", d["phone"]))
        if (d["code"] and d["code"] in have_code) or key in have_np: dup += 1; continue
        have_np.add(key); have_code.add(d["code"]); new.append(d)
    from collections import Counter
    print(f"\n讀到 {len(recs)} 筆；已存在略過 {dup} 筆；將新增 {len(new)} 筆")
    print("  分級：", dict(Counter(d["priority"] for d in new)), "　資料狀態：", dict(Counter(d["data_status"] for d in new)))
    if dry: print("（--dry-run，沒有寫入）"); return
    bk = app.backup("before_import"); print("已先備份：", os.path.basename(bk))
    cols = list(new[0].keys()) if new else []
    for d in new:
        c.execute(f"INSERT INTO leads({','.join(cols)},updated) VALUES({','.join('?'*len(cols))},?)", [d[k] for k in cols] + [app.now()])
    app.audit(c, None, "匯入名單", f"{os.path.basename(path)}：新增 {len(new)}、略過 {dup}")
    c.commit(); c.close(); print("完成")

if __name__ == "__main__":
    main()
