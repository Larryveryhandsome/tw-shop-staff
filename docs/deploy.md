# 部署：讓員工從手機連進來

系統預設只聽 `127.0.0.1`，只有跑系統的這台電腦連得到。員工要用手機打卡，需要一個 **HTTPS 網址**。這是因為手機瀏覽器只有在 HTTPS 下才允許 GPS 定位和推播通知。

## 做法一：Cloudflare Tunnel（推薦，免開防火牆、免固定 IP）

1. 準備一個網域，並交給 Cloudflare 管理（免費方案就可以）。
2. 在店裡的電腦安裝 `cloudflared`（[官方說明](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)）。
3. 建立通道，把兩個子網域分別指到兩個服務：

   | 子網域（範例） | 指到 |
   |---|---|
   | `staff.你的網域` | `http://127.0.0.1:8402`（員工系統） |
   | `ledger.你的網域` | `http://127.0.0.1:8403`（股東網站） |

4. 修改 `config/store.toml`，改完重新啟動系統：

   ```toml
   [store]
   public_url = "https://staff.你的網域"

   [ledger]
   public_url = "https://ledger.你的網域"
   ```

5. 讓 cloudflared 開機自動啟動（cloudflared 官方有安裝成系統服務的指令）。

> 透過 HTTPS 通道連進來時，系統會自動把登入 cookie 加上 `Secure`（看 `X-Forwarded-Proto: https` 或 Cloudflare 的 `Cf-Visitor` 標頭）。

## 做法二：自己的反向代理（Nginx、Caddy 等）

- 對外用 HTTPS，往內轉到 `127.0.0.1:8402`、`127.0.0.1:8403`。
- 要帶 `X-Forwarded-Proto: https` 標頭。

## 安全建議

- [ ] 老闆密碼至少 12 碼、不要和其他網站共用
- [ ] 股東網站密碼告訴股東後，刪掉 `data/股東登入密碼_告知股東後刪除.txt`
- [ ] 員工帳號的初始密碼檔、登入卡印出後就刪掉（系統偵測到大家都改過密碼，會自動把初始密碼檔丟進資源回收筒，只限 Windows）
- [ ] 定期備份 `app/data/` 和 `data/`。系統每 12 小時會自動備份資料庫到 `app/backups/`（保留最近 60 份），但那還是在同一台電腦上，請另外複製一份到別的地方
- [ ] 不要把 `app/data/`、`data/` 放進雲端共享資料夾或 git

## 開機自動啟動

```bash
python tools/install_autostart.py
```

Windows 會建立工作排程「ShopStaff_Autostart」：登入時在背景啟動，不開視窗、不開瀏覽器。要移除就加 `--remove`。macOS／Linux 會印出要加進 crontab 的那一行。
