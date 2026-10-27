# -*- coding: utf-8 -*-
"""端對端安裝測試：把整個專案複製到暫存資料夾，跑安裝精靈（答案檔）→ 啟動 → 登入 → 停止。

  python tests/test_install.py

不會動到這個資料夾本身的 config/、data/。用的埠：18402、18403、8412。
"""
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

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bad = 0


def check(name, ok, info=""):
    global bad
    print(("OK  " if ok else "BAD ") + name + ("" if ok else "　" + str(info)[:600]))
    bad += 0 if ok else 1


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def run(args, cwd):
    return subprocess.run([sys.executable, "-X", "utf8"] + args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          env=dict({k: v for k, v in os.environ.items() if k not in ("CRM_DB", "CRM_PORT", "SHOP_CONFIG_DIR", "MK_DIR")}, PYTHONIOENCODING="utf-8"),
                          timeout=180)


for port in (18402, 18403, 8412):
    if listening(port):
        sys.exit("埠 %d 已經有程式在用，先停掉再測" % port)

tmp = tempfile.mkdtemp(prefix="installtest_")
root = os.path.join(tmp, "shop")
_base_ignore = shutil.ignore_patterns("data", "__pycache__", "*.bak*", "www", ".git")


def _ignore(d, names):
    skip = set(_base_ignore(d, names))
    if os.path.normcase(d) == os.path.normcase(os.path.join(SRC, "config")):
        skip.add("store.toml")                       # 只略過這台的店家設定，產業範本裡的 store.toml 要留著
    return skip


shutil.copytree(SRC, root, ignore=_ignore)
try:
    ans = os.path.join(tmp, "answers.toml")
    with open(ans, "w", encoding="utf-8") as f:
        f.write('''preset = "salon"
name = "測試沙龍"
short_name = "測試"
address = "測試路 1 號"
phone = "0900-000-001"
start = "2026-11-01"
public_url = "http://localhost:18402"
admin_name = "測試老闆"
admin_username = "boss"
admin_password = "test-pass-1234"
ledger_password = "13572468"
demo = true
[[shareholders]]
name = "甲"
committed = 500000
paid = 500000
''')
    r = run(["setup.py", "--answers", ans], root)
    check("安裝精靈跑完", r.returncode == 0, r.stdout + r.stderr)
    with open(os.path.join(root, "config", "store.toml"), "rb") as f:
        st = tomllib.load(f)
    check("店家設定寫進去", st["store"]["name"] == "測試沙龍" and st["store"]["port"] == 18402 and st["finance"]["fin_start"] == "2026-11-01"
          and st["modules"]["safety"] is False, st.get("store"))
    with open(os.path.join(root, "data", "ledger.toml"), "rb") as f:
        lg = tomllib.load(f)
    check("股東設定寫進去、範本示範手記沒帶進來", [s["name"] for s in lg["shareholders"]] == ["甲"] and not lg.get("entries")
          and lg["ledger"]["period_start"] == "2026-11-01", lg)
    check("資料庫、股東網站密碼、股東頁、示範店都建好",
          all(os.path.exists(os.path.join(root, p)) for p in ("app/data/crm.db", "data/ledger_auth.json", "ledger/www/index.html", "data/demo/crm.db")),
          os.listdir(os.path.join(root, "data")))
    check("沒有留下首次管理員密碼檔", not os.path.exists(os.path.join(root, "app", "data", "首次管理員密碼.txt")))
    r2 = run(["setup.py", "--answers", ans], root)
    check("再跑一次不加 --force：停下來不蓋", r2.returncode != 0 and "已經裝過" in (r2.stdout + r2.stderr), r2.stdout + r2.stderr)

    # 股東網站改用測試埠，避免和這台電腦上別的程式衝突
    p = os.path.join(root, "config", "store.toml")
    with open(p, encoding="utf-8") as f:
        t = f.read()
    with open(p, "w", encoding="utf-8") as f:
        f.write(t.replace("port = 8403", "port = 18403"))

    r = run(["tools/launcher.py", "start"], root)
    check("一鍵啟動", listening(18402) and listening(18403), r.stdout + r.stderr)
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        html = op.open("http://127.0.0.1:18402/", timeout=10).read().decode()
        check("首頁顯示店名", "測試沙龍" in html)
        req = urllib.request.Request("http://127.0.0.1:18402/api/login", data=json.dumps({"username": "boss", "password": "test-pass-1234"}).encode(),
                                     headers={"Content-Type": "application/json", "X-Req": "1"})   # 系統的 CSRF 防護：只收自家頁面發的請求
        res = json.loads(op.open(req, timeout=10).read())
        check("老闆帳號登得進去", res.get("ok") is not False and any(c.name == st["store"]["cookie_name"] for c in jar), res)
        me = json.loads(op.open("http://127.0.0.1:18402/api/me", timeout=10).read())
        check("登入後是老闆、不用先改密碼", me.get("role") == "admin" or (me.get("me") or {}).get("role") == "admin", str(me)[:300])
        lp = urllib.request.urlopen("http://127.0.0.1:18403/login", timeout=10).read().decode()
        check("股東網站登入頁顯示店名", "測試沙龍" in lp)
    except Exception as e:
        check("連線測試", False, repr(e))
    r = run(["tools/launcher.py", "stop"], root)
    time.sleep(1.5)
    check("一鍵停止", not listening(18402) and not listening(18403), r.stdout + r.stderr)

    r = run(["tools/launcher.py", "start", "--demo"], root)
    check("示範店啟動（埠 8412）", listening(8412), r.stdout + r.stderr)
    r = run(["tools/launcher.py", "stop", "--demo"], root)
    time.sleep(1.5)
    check("示範店停止", not listening(8412), r.stdout + r.stderr)
finally:
    for port_stop in (["stop"], ["stop", "--demo"]):
        run(["tools/launcher.py"] + port_stop, root)
    time.sleep(1)
    shutil.rmtree(tmp, ignore_errors=True)
print("全部通過" if not bad else "有 %d 項沒過" % bad)
sys.exit(1 if bad else 0)
