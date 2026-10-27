# -*- coding: utf-8 -*-
"""給排程每 5 分鐘跑一次：埠沒在聽就在背景啟動 app.py（開機、當機都會自動恢復）。Windows 用 pythonw、不開視窗。"""
import socket, subprocess, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cfg
PORT = int(os.environ.get("CRM_PORT") or cfg.STORE.get("port", 8402))
def up():
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=2): return True
    except OSError: return False
if not up():
    py = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(py): py = sys.executable
    kw = {"creationflags": 0x00000008 | 0x00000200 | 0x08000000} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen([py, os.path.join(HERE, "app.py")], cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
