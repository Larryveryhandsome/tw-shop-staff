# 資安政策

## 回報漏洞

發現資安問題時，**請不要開公開的 Issue**。請用 GitHub 的「Report a vulnerability」（Security → Advisories）私下回報，內容包含：

- 影響範圍（哪個功能、哪個檔案）
- 重現步驟
- 可能的影響（例如看得到別人的薪資、繞過登入）

我們原則上會在 7 天內回覆，修好後在版本說明中致謝（你不想具名也可以）。

## 設計上的安全措施

- 只聽 `127.0.0.1`；要對外請自己接 HTTPS 通道或反向代理。
- 密碼用 PBKDF2-SHA256 雜湊，搭配隨機 salt。
- 連續登入失敗會暫時鎖帳號。
- POST 請求要帶自家頁面才有的標頭（CSRF 防護）。
- 登入 cookie 設 HttpOnly、SameSite=Lax；走 HTTPS 時再加 Secure。
- 薪資只有老闆看得到；店長的記帳頁看不到薪資相關支出的內容。
- 資料庫、照片、金鑰都放在 `app/data/`、`data/`，`.gitignore` 已經排除。

## 使用者自己要注意

- 不要把 `app/data/`、`data/`、`config/store.toml` 上傳到 git 或公開的雲端資料夾。
- 員工離職時，到「帳號」頁停用帳號。
- 定期把備份複製到另一台電腦或外接硬碟。
- 系統依賴的 Python 和 cryptography 要保持更新。
