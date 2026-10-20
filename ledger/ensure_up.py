# -*- coding: utf-8 -*-
"""給排程每 5 分鐘跑一次：股東網站的埠沒在聽就在背景啟動 serve.py（開機、當機都會自動恢復）。"""
import socket, subprocess, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))
import cfg as SHOP
PORT = int(os.environ.get("LEDGER_PORT") or SHOP.STORE_ALL.get("ledger", {}).get("port", 8403))


def up():
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=2):
            return True
    except OSError:
        return False


if not up():
    py = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(py):
        py = sys.executable
    kw = {"creationflags": 0x00000008 | 0x00000200 | 0x08000000} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen([py, os.path.join(HERE, "serve.py")], cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
