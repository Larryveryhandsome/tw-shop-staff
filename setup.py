# -*- coding: utf-8 -*-
"""安裝精靈：回答幾個問題，就能開始用。

用法：
  python setup.py                       # 一題一題問（Windows 也可以雙擊「安裝設定.bat」）
  python setup.py --answers 答案.toml    # 照檔案裡的答案直接裝好（不用一題一題問）
  python setup.py --force               # 已經裝過也重裝（舊設定、舊資料庫先備份）

會做的事：
  1. 選產業範本 → 產生 config/store.toml（店名、地址、電話、網址、開始日期）
  2. 股東與出資 → 產生 data/ledger.toml
  3. 建資料庫 app/data/crm.db，設定老闆帳號密碼
  4. 設定股東網站的共用密碼
  5. 要的話建一家示範店給你先看（另外一個資料庫，不會混到正式資料）

答案檔格式見 config/setup_answers.example.toml。
"""
import argparse
import datetime
import getpass
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(ROOT, "app")
STORE_TOML = os.path.join(ROOT, "config", "store.toml")
LEDGER_TOML = os.path.join(ROOT, "data", "ledger.toml")
DB = os.path.join(APP, "data", "crm.db")

if sys.version_info < (3, 11):
    sys.exit("需要 Python 3.11 以上（目前是 %s）。請到 https://www.python.org/downloads/ 下載。" % sys.version.split()[0])
import tomllib  # noqa: E402


# ---------------- 小工具 ----------------
def tq(s):
    return '"%s"' % str(s).replace("\\", "\\\\").replace('"', '\\"')


def tv(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(tv(x) for x in v) + "]"
    return tq(v)


def set_key(text, section, key, value):
    """把 TOML 文字裡 [section] 底下的 key 改成 value（保留其他內容和註解）；找不到就加在那一段最後"""
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip() == "[%s]" % section), None)
    if start is None:
        return text.rstrip("\n") + "\n\n[%s]\n%s = %s\n" % (section, key, tv(value))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[")), len(lines))
    pat = re.compile(r'^%s\s*=\s*(?:"(?:[^"\\]|\\.)*"|[^#]*?)(\s+#.*)?$' % re.escape(key))
    for i in range(start + 1, end):
        mm = pat.match(lines[i])
        if mm:
            lines[i] = "%s = %s%s" % (key, tv(value), mm.group(1) or "")      # 保留行尾註解
            return "\n".join(lines)
    ins = end
    while ins > start + 1 and not lines[ins - 1].strip():
        ins -= 1
    lines.insert(ins, "%s = %s" % (key, tv(value)))
    return "\n".join(lines)


def replace_tables(text, name, tables):
    """拿掉所有 [[name]] 區塊，換成 tables（list of dict）"""
    lines, out, skip = text.split("\n"), [], False
    for l in lines:
        if l.strip() == "[[%s]]" % name:
            skip = True
            continue
        if skip and (l.startswith("[") or l.startswith("# ──")):
            skip = False
        if not skip:
            out.append(l)
    body = "\n".join(out).rstrip("\n") + "\n"
    for t in tables:
        body += "\n[[%s]]\n" % name + "".join("%s = %s\n" % (k, tv(v)) for k, v in t.items())
    return body


def backup(path):
    if os.path.exists(path):
        bak = path + ".bak-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        shutil.move(path, bak)
        for ext in ("-wal", "-shm"):
            if os.path.exists(path + ext):
                shutil.move(path + ext, bak + ext)
        return bak


def presets():
    out = []
    d = os.path.join(ROOT, "presets")
    for k in sorted(os.listdir(d)):
        f = os.path.join(d, k, "store.toml")
        if os.path.isfile(f):
            with open(f, encoding="utf-8") as fh:
                out.append((k, fh.readline().replace("# 產業範本：", "").strip()))
    return out


# ---------------- 問答 ----------------
def ask(q, default=None, check=None):
    while True:
        a = input("%s%s：" % (q, "（直接按 Enter＝%s）" % default if default not in (None, "") else "")).strip()
        a = a or (default if default is not None else "")
        err = check(a) if check else None
        if not err:
            return a
        print("　→ " + err)


def ask_int(q, default):
    return int(ask(q, str(default), lambda a: None if re.fullmatch(r"\d+", a.replace(",", "")) else "請填數字").replace(",", ""))


def ask_pw(q):
    while True:
        a = getpass.getpass(q + "（至少 8 碼，輸入時不會顯示）：")
        if len(a) < 8:
            print("　→ 至少 8 碼")
            continue
        if getpass.getpass("再輸入一次：") != a:
            print("　→ 兩次不一樣，請重來")
            continue
        return a


def interactive():
    print("\n＝＝＝ 門市員工系統 安裝精靈 ＝＝＝\n每題都可以直接按 Enter 用預設值，之後都能在 config/store.toml、data/ledger.toml 改。\n")
    ps = presets()
    print("【1／5】你的店是哪一種？")
    for i, (k, t) in enumerate(ps, 1):
        print("  %d. %s（%s）" % (i, t, k))
    n = ask_int("請選號碼", 1)
    preset = ps[max(1, min(n, len(ps))) - 1][0]
    print("\n【2／5】店家資料")
    a = dict(preset=preset)
    a["name"] = ask("店名（完整）", None, lambda x: None if x else "店名要填")
    a["short_name"] = ask("短名（手機圖示下方，6 個字以內）", a["name"][:6])
    a["address"] = ask("地址", "")
    a["phone"] = ask("電話", "")
    a["start"] = ask("從哪天開始用（YYYY-MM-DD）", datetime.date.today().replace(day=1).isoformat(),
                     lambda x: None if re.fullmatch(r"\d{4}-\d{2}-\d{2}", x) else "格式像 2026-11-01")
    a["public_url"] = ask("對外網址（只在店裡用就保持預設）", "http://localhost:8402")
    print("\n【3／5】股東（沒有股東、自己一個人開店就填 0）")
    a["shareholders"] = []
    for i in range(ask_int("有幾位股東", 0)):
        nm = ask("　第 %d 位股東名字" % (i + 1), "股東%d" % (i + 1))
        com = ask_int("　%s 認股金額" % nm, 0)
        paid = ask_int("　%s 已經出資金額" % nm, com)
        a["shareholders"].append(dict(name=nm, committed=com, paid=paid))
    print("\n【4／5】老闆帳號")
    a["admin_name"] = ask("你的名字（顯示用）", "老闆")
    a["admin_username"] = ask("登入帳號", "admin", lambda x: None if re.fullmatch(r"[A-Za-z0-9_.-]{3,20}", x) else "英文、數字，3～20 個字")
    a["admin_password"] = ask_pw("登入密碼")
    print("\n【5／5】股東網站")
    a["ledger_password"] = ask("股東網站共用密碼（直接按 Enter＝隨機產生 8 位數字）", "")
    a["demo"] = ask("要不要另外建一家示範店先看看？(y/n)", "y").lower().startswith("y")
    return a


# ---------------- 安裝 ----------------
def install(a, force=False, log=print):
    for p in (STORE_TOML, LEDGER_TOML, DB):
        if os.path.exists(p) and not force:
            raise SystemExit("已經裝過了（%s 已存在）。要重裝請加 --force（舊的會先備份）。" % os.path.relpath(p, ROOT))
    preset = a.get("preset", "bento")
    pdir = os.path.join(ROOT, "presets", preset)
    if not os.path.isdir(pdir):
        raise SystemExit("沒有這個產業範本：%s" % preset)
    start = a.get("start") or datetime.date.today().replace(day=1).isoformat()
    os.makedirs(os.path.dirname(STORE_TOML), exist_ok=True)
    os.makedirs(os.path.dirname(LEDGER_TOML), exist_ok=True)

    # 1. 店家設定
    with open(os.path.join(pdir, "store.toml"), encoding="utf-8") as f:
        st = f.read()
    for k in ("name", "short_name", "address", "phone", "public_url"):
        if a.get(k) not in (None, ""):
            st = set_key(st, "store", k, a[k])
    m = re.search(r":(\d+)", a.get("public_url") or "")
    if m and "localhost" in a.get("public_url", ""):
        st = set_key(st, "store", "port", int(m.group(1)))
    st = set_key(st, "store", "cookie_name", "shop" + __import__("secrets").token_hex(3))
    for k in ("fin_start", "exp_start", "petty_from"):
        st = set_key(st, "finance", k, start)
    st = st.replace("# 用法：python tools/use_preset.py %s（會複製到 config/store.toml），再把店名、地址、電話改成你自己的。" % preset,
                    "# 由 setup.py 在 %s 產生；可以直接改這個檔，改完重開系統生效。" % datetime.date.today().isoformat())
    tomllib.loads(st)
    b = backup(STORE_TOML)
    if b: log("備份舊的店家設定：%s" % os.path.basename(b))
    with open(STORE_TOML, "w", encoding="utf-8") as f:
        f.write(st)
    log("✔ 店家設定：config/store.toml（範本 %s）" % preset)

    # 2. 股東帳務設定
    with open(os.path.join(pdir, "ledger.toml"), encoding="utf-8") as f:
        lg = f.read()
    lg = replace_tables(lg, "shareholders", a.get("shareholders") or [])
    lg = replace_tables(lg, "entries", [])                        # 範本裡的示範手記不帶進正式設定
    lg = set_key(lg, "ledger", "period_start", start)
    lg = set_key(lg, "opening", "date", start)
    tomllib.loads(lg)
    b = backup(LEDGER_TOML)
    if b: log("備份舊的股東帳務設定：%s" % os.path.basename(b))
    with open(LEDGER_TOML, "w", encoding="utf-8") as f:
        f.write(lg)
    log("✔ 股東帳務設定：data/ledger.toml（%d 位股東）" % len(a.get("shareholders") or []))

    # 3. 資料庫＋老闆帳號（另開程序：app 模組在 import 時就決定資料庫位置）
    b = backup(DB)
    if b: log("備份舊的資料庫：%s" % os.path.basename(b))
    child = (
        "import os, sys; sys.path.insert(0, %r); import app; app.init_db(); c = app.db();"
        "c.execute('UPDATE users SET username=?, name=?, pw=?, must_change=0 WHERE role=\"admin\"', (sys.argv[1], sys.argv[2], app.hash_pw(sys.argv[3])));"
        "c.commit(); c.close();"
        "p = os.path.join(os.path.dirname(app.DB), '首次管理員密碼.txt'); os.path.exists(p) and os.remove(p)" % APP)
    env = dict(os.environ, CRM_DB=DB, PYTHONIOENCODING="utf-8")
    env.pop("SHOP_CONFIG_DIR", None)
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", child, a.get("admin_username") or "admin", a.get("admin_name") or "老闆",
                        a["admin_password"]], env=env, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit("建資料庫失敗：\n" + r.stderr[-1500:])
    log("✔ 資料庫：app/data/crm.db，老闆帳號 %s" % (a.get("admin_username") or "admin"))

    # 4. 股東網站密碼
    cmd = [sys.executable, "-X", "utf8", os.path.join(ROOT, "ledger", "set_password.py")] + ([a["ledger_password"]] if a.get("ledger_password") else [])
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit("設定股東網站密碼失敗：\n" + r.stderr[-1500:])
    log("✔ 股東網站密碼：寫在 data/股東登入密碼_告知股東後刪除.txt")

    # 5. 股東頁先產生一次
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "ledger", "builder", "build_ledger.py"), "--db", DB],
                       env=env, capture_output=True, text=True, encoding="utf-8")
    log("✔ 股東頁已產生" if r.returncode == 0 else "（股東頁還沒產生：%s）" % r.stderr[-300:])

    # 6. 示範店（另一個資料庫）
    if a.get("demo"):
        demo_db = os.path.join(ROOT, "data", "demo", "crm.db")
        if os.path.exists(demo_db):
            backup(demo_db)
        r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(APP, "seed_demo.py"), "--preset", preset, "--db", demo_db, "--no-ledger"],
                           env=env, capture_output=True, text=True, encoding="utf-8")
        log("✔ 示範店：data/demo/（帳號在 data/demo/示範帳號.txt；用「啟動示範店」打開）" if r.returncode == 0 else "（示範店沒建成：%s）" % r.stderr[-300:])
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="安裝精靈")
    ap.add_argument("--answers", help="答案檔（TOML），格式見 config/setup_answers.example.toml")
    ap.add_argument("--force", action="store_true", help="已經裝過也重裝（舊的先備份）")
    x = ap.parse_args(argv)
    if x.answers:
        with open(x.answers, "rb") as f:
            a = tomllib.load(f)
        if len(a.get("admin_password", "")) < 8:
            raise SystemExit("答案檔的 admin_password 至少 8 碼")
    else:
        a = interactive()
    install(a, force=x.force)
    print("\n安裝完成！")
    print("　啟動：Windows 雙擊「啟動.vbs」；macOS／Linux 執行 ./start.sh")
    print("　員工系統：%s" % (a.get("public_url") or "http://localhost:8402"))
    print("　股東網站：http://localhost:8403")
    print("　員工請自己到登入頁按「新夥伴註冊」，你在老闆頁核准、設定薪資和班表。")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消。")
