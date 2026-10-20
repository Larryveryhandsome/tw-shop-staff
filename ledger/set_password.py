# -*- coding: utf-8 -*-
"""設定股東網站的共用密碼。
用法：python set_password.py           → 隨機產生 8 位數字密碼
      python set_password.py 自訂密碼  → 用你指定的密碼
密碼只寫進 data/股東登入密碼_告知股東後刪除.txt，不會印在畫面上。改密碼後，所有人的登入都會失效、要重新輸入。"""
import hashlib, json, os, secrets, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
os.makedirs(DATA, exist_ok=True)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))
import cfg as SHOP

pw = sys.argv[1] if len(sys.argv) > 1 else "".join(secrets.choice("0123456789") for _ in range(8))
salt = secrets.token_bytes(16)
it = 200000
auth = {"salt": salt.hex(), "iter": it,
        "hash": hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, it).hex(),
        "secret": secrets.token_hex(32)}
with open(os.path.join(DATA, "ledger_auth.json"), "w", encoding="utf-8") as f:
    json.dump(auth, f, indent=1)
url = SHOP.STORE_ALL.get("ledger", {}).get("public_url", "")
with open(os.path.join(DATA, "股東登入密碼_告知股東後刪除.txt"), "w", encoding="utf-8") as f:
    f.write("%s 股東帳務網站\n網址：%s\n密碼：%s\n\n告訴股東後請刪除這個檔案。要換密碼就再跑一次 set_password.py。\n"
            % (SHOP.STORE.get("name", ""), url, pw))
print("已設定新密碼（寫在 data/股東登入密碼_告知股東後刪除.txt），舊的登入全部失效。")
