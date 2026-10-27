# -*- coding: utf-8 -*-
"""產生夥伴登入卡：python make_login_cards.py 帳號明細.json 輸出.html"""
import json, qrcode, io, base64, html, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg
URL = cfg.STORE.get("public_url", "http://localhost")
cards = json.load(open(sys.argv[1], encoding="utf-8"))
img = qrcode.make(URL, box_size=8, border=1); b = io.BytesIO(); img.save(b, format="PNG")
qr = "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
css = """<style>@page{size:A4;margin:10mm}*{box-sizing:border-box}body{margin:0;font:13px/1.5 "Microsoft JhengHei","PingFang TC",sans-serif;color:#2C2015}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:6mm}
.card{border:1.5px dashed #C9BCA4;border-radius:8px;padding:5mm 6mm;height:86mm;display:flex;flex-direction:column;page-break-inside:avoid}
.hd{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #E07B12;padding-bottom:3mm;margin-bottom:3mm}
.t{font-size:16px;font-weight:900}.s{font-size:11px;color:#7A6A54}.n{font-size:20px;font-weight:900;color:#E07B12}
.row{display:flex;gap:5mm}.qr img{width:28mm;height:28mm}.kv{flex:1}
.kv div{margin:1mm 0}.kv b{display:inline-block;width:12mm;color:#7A6A54;font-weight:600}.kv code{font-size:17px;font-weight:900;letter-spacing:1px;font-family:Consolas,monospace}
ol{margin:2mm 0 0 4.5mm;padding:0;font-size:11.5px}ol li{margin:.6mm 0}.warn{margin-top:auto;font-size:10.5px;color:#C4360A}</style>"""
def card(c):
    return f"""<div class="card"><div class="hd"><div><div class="s">{html.escape(cfg.STORE.get("name", ""))}</div><div class="t">員工系統 登入卡</div></div><div class="n">{html.escape(c['name'])}</div></div>
<div class="row"><div class="qr"><img src="{qr}"></div><div class="kv"><div><b>網址</b>{html.escape(URL.split("://")[-1])}</div>
<div><b>帳號</b><code>{c['username']}</code></div><div><b>密碼</b><code>{c['password']}</code></div></div></div>
<ol><li>手機相機掃左邊 QR，或在瀏覽器輸入網址</li><li>輸入帳號、密碼，按「登入」（之後 90 天不用再登）</li>
<li>分享 →「加入主畫面」，以後點圖示就開</li><li>登入後到「我」可以自己改密碼</li></ol>
<div class="warn">這張卡只給本人，不要拍照傳給別人。忘記密碼找店長重設。</div></div>"""
open(sys.argv[2], "w", encoding="utf-8").write("<title>夥伴登入卡</title>" + css + '<div class="grid">' + "".join(card(c) for c in cards) + "</div>")
print("ok", len(cards))
