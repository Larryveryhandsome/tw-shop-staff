# -*- coding: utf-8 -*-
"""設定開機（登入）自動啟動。不開任何視窗。

  python tools/install_autostart.py            # 安裝
  python tools/install_autostart.py --remove   # 移除

Windows：建立工作排程「ShopStaff_Autostart」，登入時用 wscript 執行「背景啟動.vbs」（隱藏、不開瀏覽器）。
macOS／Linux：印出要加進 crontab 的一行，請自己確認後再加。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK = "ShopStaff_Autostart"


def main():
    remove = "--remove" in sys.argv
    if os.name != "nt":
        line = "@reboot cd %s && python3 -X utf8 tools/launcher.py start" % ROOT
        print(("請執行 crontab -e，刪掉這一行：\n" if remove else "請執行 crontab -e，加上這一行：\n") + line)
        return 0
    if remove:
        r = subprocess.run(["schtasks", "/Delete", "/TN", TASK, "/F"], capture_output=True, text=True, creationflags=0x08000000)
        print("已移除開機自動啟動" if r.returncode == 0 else "移除失敗：" + (r.stderr or r.stdout))
        return r.returncode
    vbs = os.path.join(ROOT, "背景啟動.vbs")
    tr = 'wscript.exe "%s"' % vbs
    r = subprocess.run(["schtasks", "/Create", "/TN", TASK, "/SC", "ONLOGON", "/TR", tr, "/F", "/RL", "LIMITED"],
                       capture_output=True, text=True, creationflags=0x08000000)
    print("已設定：每次登入 Windows 會在背景啟動系統（排程名稱 %s）" % TASK if r.returncode == 0 else "設定失敗：" + (r.stderr or r.stdout))
    return r.returncode


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
