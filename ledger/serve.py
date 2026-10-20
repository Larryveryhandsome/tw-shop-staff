# -*- coding: utf-8 -*-
"""股東帳務網站：只聽 127.0.0.1（埠在 config/store.toml 的 [ledger]）；要從外面連請自行接反向代理或通道。

- 只給看 www/index.html 和 www/img/*.jpg，全部要先輸入股東共用密碼。
- 密碼用 pbkdf2-sha256 存在 data/ledger_auth.json（不進 git）；登入後發 HMAC 簽章 cookie（30 天），伺服器重啟不會登出。
- 改密碼：python set_password.py（舊的登入全部失效）。
- 同一個 IP 連錯 8 次，鎖 15 分鐘；所有 IP 合計 15 分鐘內錯 40 次，全站暫停登入 15 分鐘（同時送很多請求、偽造 IP 都繞不過）。
- www/index.html 由帳務產生器自動更新，這裡不用改。
"""
import hashlib, hmac, json, os, re, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))
import cfg as SHOP
WWW = os.environ.get("LEDGER_WWW") or os.path.join(HERE, "www")
CFG = os.environ.get("LEDGER_AUTH") or os.path.join(os.path.dirname(HERE), "data", "ledger_auth.json")   # LEDGER_AUTH：測試用
PORT = int(os.environ.get("LEDGER_PORT") or SHOP.STORE_ALL.get("ledger", {}).get("port", 8403))
COOKIE = "ledger"
DAYS = 30
MAX_FAIL, LOCK_SEC = 8, 900
GLOBAL_MAX = 40          # 15 分鐘內「所有 IP 合計」錯 40 次 → 全站暫停登入 15 分鐘（擋偽造 CF-Connecting-IP 換 IP 猜密碼）
_fails = {}
_gfails = []
_lock = threading.Lock()


def reserve(ip, now):
    """驗密碼之前先佔一次失敗名額（對了再退回）：同時送幾十個請求也繞不過「連錯 8 次鎖 15 分鐘」。回傳 False＝鎖住"""
    with _lock:
        n, t0 = _fails.get(ip, (0, now))
        if now - t0 > LOCK_SEC:
            n, t0 = 0, now
        _gfails[:] = [t for t in _gfails if now - t < LOCK_SEC]
        if n >= MAX_FAIL or len(_gfails) >= GLOBAL_MAX:
            return False
        _fails[ip] = (n + 1, t0)
        _gfails.append(now)
        return True


def release(ip, now):
    with _lock:
        _fails.pop(ip, None)
        if now in _gfails:
            _gfails.remove(now)


def cfg():
    with open(CFG, encoding="utf-8") as f:
        return json.load(f)


def check_pw(pw):
    c = cfg()
    h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(c["salt"]), c["iter"]).hex()
    return hmac.compare_digest(h, c["hash"])


def sign(exp):
    return hmac.new(bytes.fromhex(cfg()["secret"]), str(exp).encode(), "sha256").hexdigest()


def new_token():
    exp = int(time.time()) + DAYS * 86400
    return "%d.%s" % (exp, sign(exp))


LOGIN = """<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex,nofollow">
<title>股東帳務 · 登入</title>
<style>
:root{color-scheme:light}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f5f5f7;
 font:16px/1.5 -apple-system,BlinkMacSystemFont,"PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif;color:#1d1d1f;padding:16px;box-sizing:border-box}
form{background:#fff;border-radius:18px;padding:36px 28px;width:100%%;max-width:360px;box-shadow:0 4px 24px rgba(0,0,0,.06);box-sizing:border-box}
.b{font-size:13px;color:#6e6e73}
h1{font-size:26px;margin:4px 0 22px;letter-spacing:.5px}
input{width:100%%;box-sizing:border-box;font-size:18px;padding:12px 14px;border:1px solid #d2d2d7;border-radius:12px;outline:none}
input:focus{border-color:#0071e3;box-shadow:0 0 0 3px rgba(0,113,227,.15)}
button{margin-top:14px;width:100%%;font-size:17px;padding:12px;border:0;border-radius:12px;background:#0071e3;color:#fff;cursor:pointer}
.e{color:#b3261e;font-size:14px;margin-top:12px;min-height:20px}
</style></head><body>
<form method="post" action="/login" autocomplete="off">
<div class="b">__STORE__</div><h1>股東帳務</h1>
<input type="password" name="pw" placeholder="請輸入股東密碼" inputmode="numeric" autofocus required>
<button type="submit">進入</button><div class="e">%s</div>
</form></body></html>""".replace("__STORE__", SHOP.STORE.get("name", "").replace("&", "&amp;").replace("<", "&lt;").replace("%", "%%"))


class H(BaseHTTPRequestHandler):
    server_version = "ledger"
    sys_version = ""

    def log_message(self, *a):
        pass

    def ip(self):
        return self.headers.get("CF-Connecting-IP") or self.client_address[0]

    def is_https(self):
        return "https" in (self.headers.get("CF-Visitor", "") + self.headers.get("X-Forwarded-Proto", ""))

    def authed(self):
        m = re.search(r"(?:^|;\s*)%s=(\d+)\.([0-9a-f]{64})" % COOKIE, self.headers.get("Cookie", ""))
        if not m:
            return False
        exp = int(m.group(1))
        return exp > time.time() and hmac.compare_digest(sign(exp), m.group(2))

    def send(self, code, body, ctype="text/html; charset=utf-8", cache="no-store", cookie=None, location=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if location:
            self.send_header("Location", location)
        if cookie is not None:
            attrs = "Path=/; HttpOnly; SameSite=Lax" + ("; Secure" if self.is_https() else "")
            if cookie:
                self.send_header("Set-Cookie", "%s=%s; Max-Age=%d; %s" % (COOKIE, cookie, DAYS * 86400, attrs))
            else:
                self.send_header("Set-Cookie", "%s=; Max-Age=0; %s" % (COOKIE, attrs))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/robots.txt":
            return self.send(200, "User-agent: *\nDisallow: /\n", "text/plain; charset=utf-8")
        if path == "/login":
            return self.send(200, LOGIN % "")
        if path == "/logout":
            return self.send(303, "", cookie="", location="/login")
        if not self.authed():
            return self.send(303, "", location="/login")
        if path in ("/", "/index.html"):
            with open(os.path.join(WWW, "index.html"), "rb") as f:
                return self.send(200, f.read())
        m = re.fullmatch(r"/img/([A-Za-z0-9_]+)\.jpg", path)
        if m:
            fp = os.path.join(WWW, "img", m.group(1) + ".jpg")
            if os.path.isfile(fp):
                with open(fp, "rb") as f:
                    return self.send(200, f.read(), "image/jpeg", cache="private, max-age=3600")
        return self.send(404, "找不到", "text/plain; charset=utf-8")

    def do_POST(self):
        if urlsplit(self.path).path != "/login":
            return self.send(404, "找不到", "text/plain; charset=utf-8")
        ip, now = self.ip(), time.time()
        size = max(0, min(int(self.headers.get("Content-Length") or 0), 4096))
        pw = (parse_qs(self.rfile.read(size).decode("utf-8", "replace")).get("pw") or [""])[0]   # 先把內容讀完再回，連線才不會被重設
        if not reserve(ip, now):
            return self.send(429, LOGIN % "錯太多次，請 15 分鐘後再試")
        if pw and check_pw(pw):
            release(ip, now)
            return self.send(303, "", cookie=new_token(), location="/")
        time.sleep(1)
        return self.send(401, LOGIN % "密碼不對")


if __name__ == "__main__":
    import atexit
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    PID = os.path.join(os.path.dirname(CFG), "ledger.pid")
    with open(PID, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(PID) and os.remove(PID))
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
