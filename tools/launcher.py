# -*- coding: utf-8 -*-
"""啟動／停止／查看狀態（Windows、macOS、Linux 都能用）。

  python tools/launcher.py start          # 背景啟動員工系統＋股東網站（Windows 不開黑色視窗）
  python tools/launcher.py start --open   # 啟動後打開瀏覽器
  python tools/launcher.py start --demo   # 啟動示範店（data/demo/，埠 8412）
  python tools/launcher.py stop [--demo]
  python tools/launcher.py status

Windows 一般直接雙擊「啟動.vbs」「停止.vbs」就好。
"""
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
import cfg  # noqa: E402

DEMO_PORT = 8412
LOGS = os.path.join(ROOT, "data", "logs")


def services(demo=False):
    if demo:
        d = os.path.join(ROOT, "data", "demo")
        return [dict(name="示範店", script=os.path.join(ROOT, "app", "app.py"), port=DEMO_PORT,
                     env={"CRM_DB": os.path.join(d, "crm.db"), "CRM_BAK": os.path.join(d, "backups"), "CRM_PORT": str(DEMO_PORT)},
                     pid=os.path.join(d, "app.pid"))]
    return [dict(name="員工系統", script=os.path.join(ROOT, "app", "app.py"), port=int(cfg.STORE.get("port", 8402)), env={},
                 pid=os.path.join(ROOT, "app", "data", "app.pid")),
            dict(name="股東網站", script=os.path.join(ROOT, "ledger", "serve.py"), port=int(cfg.STORE_ALL.get("ledger", {}).get("port", 8403)), env={},
                 pid=os.path.join(ROOT, "data", "ledger.pid"))]


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def python_bg():
    """Windows 用 pythonw（沒有視窗）；其他系統用目前的 python"""
    if os.name == "nt":
        w = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(w):
            return w
    return sys.executable


def start(demo=False, open_browser=False):
    os.makedirs(LOGS, exist_ok=True)
    import payroll  # noqa: E402  勞動曆（國定假日、基本工資）今年沒設定 → 啟動時就講清楚
    for w in payroll.calendar_status():
        print("⚠️ 警告：" + w)
    if demo and not os.path.exists(os.path.join(ROOT, "data", "demo", "crm.db")):
        print("還沒有示範店。先跑：python app/seed_demo.py --preset bento --db data/demo/crm.db")
        return 1
    for s in services(demo):
        if listening(s["port"]):
            print("%s 已經在跑（埠 %d）" % (s["name"], s["port"]))
            continue
        env = dict(os.environ, PYTHONIOENCODING="utf-8", **s["env"])
        log = open(os.path.join(LOGS, os.path.basename(os.path.dirname(s["pid"])) + "_" + os.path.basename(s["script"]) + ".log"), "ab")
        kw = dict(cwd=os.path.dirname(s["script"]), env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL)
        if os.name == "nt":
            kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000      # DETACHED｜NEW_PROCESS_GROUP｜CREATE_NO_WINDOW
        else:
            kw["start_new_session"] = True
        subprocess.Popen([python_bg(), "-X", "utf8", s["script"]], **kw)
        for _ in range(40):
            if listening(s["port"]):
                break
            time.sleep(0.25)
        print("%s %s：http://localhost:%d" % (s["name"], "已啟動" if listening(s["port"]) else "啟動失敗（看 data/logs/）", s["port"]))
    if open_browser:
        webbrowser.open("http://localhost:%d" % services(demo)[0]["port"])
    return 0


def stop(demo=False):
    for s in services(demo):
        if not os.path.exists(s["pid"]):
            print("%s 沒有在跑%s" % (s["name"], "（但埠 %d 有東西在聽，不是這個程式啟動的，請自己確認）" % s["port"] if listening(s["port"]) else ""))
            continue
        with open(s["pid"]) as f:
            pid = int(f.read().strip() or 0)
        try:
            os.kill(pid, signal.SIGTERM)
            print("%s 已停止" % s["name"])
        except OSError:
            print("%s 的程序已經不在了" % s["name"])
        try:
            os.remove(s["pid"])
        except OSError:
            pass
    return 0


def status():
    for demo in (False, True):
        for s in services(demo):
            print("%-6s 埠 %-5d %s" % (s["name"], s["port"], "執行中" if listening(s["port"]) else "沒在跑"))
    return 0


if __name__ == "__main__":
    if sys.stdout is None:            # 用 pythonw（啟動.vbs）跑的時候沒有視窗可以印，改寫到 log
        os.makedirs(LOGS, exist_ok=True)
        sys.stdout = sys.stderr = open(os.path.join(LOGS, "launcher.log"), "a", encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
    cmd = (sys.argv[1:] or ["status"])[0]
    demo, op = "--demo" in sys.argv, "--open" in sys.argv
    sys.exit({"start": lambda: start(demo, op), "stop": lambda: stop(demo), "status": status}.get(cmd, status)())
