# tw-shop-staff｜台灣小店的員工＋股東系統

給台灣的便當店、飲料店、早餐店、美髮美甲、零售門市用的**員工系統**和**股東帳務網站**。

- 員工用手機打卡，系統依《勞動基準法》算薪水：加班、休息日、國定假日、休息時間都會檢查。
- 店長每天記營收和支出，老闆核銷後，股東網站自動更新。
- 選好產業範本、填幾題資料就能開始用。不用買伺服器，一台店裡的電腦就能跑。
- 主程式只用 Python 標準庫，資料存在你自己電腦的 SQLite，不會上傳到別人的雲端。

> 本專案的計薪規則是依勞基法整理的**預設值**，原則上仍請依勞動部最新公告與你的實際情況自行核對，必要時請洽勞工主管機關或專業人士。股東頁是內部管理用試算，不能取代會計師簽證的財務報表與報稅資料。

---

## 功能

| 給誰 | 功能 |
|---|---|
| 夥伴（員工） | 手機打卡（GPS 確認在店裡）、看本月工時和預估薪資、申請補登、排休、看公告、教育訓練、日誌 |
| 店長 | 記營收日報、支出拍收據、零用金、外送看板、發公告、排休 |
| 老闆 | 今日出勤、本月薪資試算、定案、列印簽收單（PDF）、補登審核、預支、薪資調整、核銷、帳號與新夥伴審核、行銷審核 |
| 股東 | 獨立網站、共用密碼登入：每月損益、支出明細（附單據）、薪資總額、出資與盈餘試算、資金推算、對帳、單位成本 |

可以開關的模組（`config/store.toml` 的 `[modules]`）：

| 模組 | 說明 | 適合 |
|---|---|---|
| `safety` | 食安紀錄：冰箱溫度、瓦斯、油品、廢油、廁所 | 餐飲 |
| `crm` | 團體訂單開發：企業客戶名單、通話紀錄、每日目標 | 便當、飲料、早餐 |
| `delivery` | 外送看板：接單、出餐、派送、收現金 | 有外送的店 |
| `marketing` | 行銷審核：外部 AI 產生的貼文草稿和社群雷達結果，老闆核准才發（一律人工發）。交接格式見 [docs/marketing.md](docs/marketing.md) | 所有 |
| `news` | 每週新聞：自己整理或叫 AI 照格式產生，用 `python tools/import_news.py 新聞.json` 匯入 | 所有 |
| `journal` | 夥伴日誌：夥伴寫、老闆回 | 所有 |

---

## 5 分鐘開始

**需要：** Python 3.11 以上（[python.org 下載](https://www.python.org/downloads/)，Windows 安裝時勾選「Add python.exe to PATH」）。

### Windows

1. 下載這個專案（綠色 Code 按鈕 → Download ZIP），解壓縮。
2. 雙擊 **`安裝設定.bat`**，回答 5 題：產業、店家資料、股東、老闆帳號、股東網站密碼。
3. 雙擊 **`啟動.vbs`**，瀏覽器會打開 http://localhost:8402 。背景執行，不會跳出黑色視窗。
4. 要停止就雙擊 **`停止.vbs`**。

### macOS／Linux

```bash
python3 setup.py
```

```bash
./start.sh
```

```bash
./stop.sh
```

### 想先看看

安裝時第 5 題選「要建示範店」，或自己建一家：

```bash
python app/seed_demo.py --preset drink --db data/demo/crm.db
```

```bash
python tools/launcher.py start --demo --open
```

示範店在 http://localhost:8412 ，帳號密碼在 `data/demo/示範帳號.txt`。全部是假資料，不會混到正式資料。

### 手機推播（選用）

```bash
pip install -r requirements.txt
```

沒裝也能用，只是不會推播通知。iPhone 要先用 Safari「加入主畫面」，再從主畫面打開才收得到。

---

## 產業範本

| 代號 | 產業 | 營收單位 | 預設開啟 |
|---|---|---|---|
| `bento` | 便當／小吃店 | 個 | 全部 |
| `drink` | 飲料店 | 杯 | 全部 |
| `breakfast` | 早餐店 | 份 | 行銷以外全部 |
| `salon` | 美髮／美甲 | 位 | 行銷、新聞、日誌 |
| `retail` | 零售門市 | 件 | 行銷、新聞、日誌 |

每個範本都帶支出類別、單位成本範例，以及合法的示範班表。詳見 [presets/README.md](presets/README.md)。

**你的行業適不適合、要怎麼設定？** 看 [百工百業適用指南](docs/industries.md)。裡面有 10 種行業實際跑過一個月的結果，包括便當、自助餐、飲料、早餐、咖啡廳、夜市攤（跨午夜班）、零售、24 小時便利店（大夜班）、美髮、補習班。

---

## 計薪規則（勞基法預設值）

| 項目 | 系統怎麼算 | 依據 |
|---|---|---|
| 工時 | 以打卡為準；漏打卡的那段不算，列給老闆補登 | — |
| 月薪制 | 做滿應上班時數給全額，沒做滿依出勤分鐘比例；每小時工資額＝月薪÷240 | — |
| 平日加班 | 每天超過 8 小時：前 2 小時 ×1.34、再 2 小時 ×1.67 | 第 24 條第 1 項 |
| 休息日出勤 | 每週第 6 個出勤日：前 2 小時 ×1.34、第 3–8 小時 ×1.67、第 9 小時起 ×2.67 | 第 24 條第 2 項 |
| 例假 | 每週第 7 個出勤日：工資加倍並提醒「原則上不得出勤」 | 第 36、40 條 |
| 國定假日 | 出勤工資加倍；月薪制的應上班天數會扣掉國定假日 | 第 39 條 |
| 休息時間 | 連續工作超過 4 小時沒休 30 分鐘就提醒 | 第 35 條 |
| 遲到 | 遲到的分鐘本來就不算工時，**不另外罰扣** | 第 26 條 |
| 基本工資 | 低於當年度基本工資就提醒 | 第 21 條 |
| 一日上限 | 超過 12 小時就提醒 | 第 32 條 |
| 跨午夜的班 | 夜市、大夜班整班算在上班那天，不會拆成兩天漏打卡 | — |
| 勞健保 | 每人填自付額，從實發扣；雇主勞退 6% 只顯示 | 勞工退休金條例第 14 條 |

所有倍率、國定假日、基本工資都在 [`config/labor_rules.toml`](config/labor_rules.toml)，**每年請自行更新**。完整說明和開店前的檢查表見 [docs/labor-law.md](docs/labor-law.md)。

---

## 設定檔

| 檔案 | 內容 | 進 git |
|---|---|---|
| `config/store.toml` | 店名、地址、網址、埠、財務起始日、支出類別、模組開關 | ❌（由 `setup.py` 產生） |
| `config/store.example.toml` | 範例；沒有 `store.toml` 時用它跑示範模式 | ✅ |
| `config/labor_rules.toml` | 計薪規則 | ✅ |
| `data/ledger.toml` | 股東、期初、系統外手記、對帳點、單位成本 | ❌ |
| `config/ledger.example.toml` | 股東帳務設定範例 | ✅ |
| `app/data/` | 資料庫、照片、推播金鑰、備份 | ❌ |

`data/` 和 `app/data/` 有你店裡的真實資料，**不要上傳、不要分享**。

---

## 從外面連進來（選用）

系統只聽 `127.0.0.1`，預設只有店裡這台電腦連得到。要讓員工用手機連，請自己接一層 HTTPS 通道或反向代理（例如 Cloudflare Tunnel），並把 `config/store.toml` 的 `public_url` 改成對外網址。步驟見 [docs/deploy.md](docs/deploy.md)。

開機自動啟動：

```bash
python tools/install_autostart.py
```

---

## 專案結構

```
app/                員工系統（Python 標準庫 HTTP 伺服器＋原生 JS 前端，PWA）
  payroll.py        考勤與計薪（勞基法規則在 legal_pay）
  seed_demo.py      建示範店
  tests/            測試
ledger/             股東網站（serve.py）與帳務產生器（builder/build_ledger.py）
presets/            產業範本
config/             設定檔與範例
tools/              啟動、停止、套用範本、匯入新聞、開機自動啟動
docs/               說明文件
setup.py            安裝精靈
```

## 測試

```bash
python app/tests/test_labor.py
```

```bash
python tests/test_install.py
```

```bash
python tests/test_industries.py
```

`app/tests/` 底下每支都可以單獨跑，`ledger/tests/test_ledger.py` 測股東帳務。

## 授權

[Apache License 2.0](LICENSE)。可以免費商用、修改、再散布，請保留授權與 [NOTICE](NOTICE)。

## 參與

歡迎送 Issue、PR，或分享你的產業範本。請先看 [CONTRIBUTING.md](CONTRIBUTING.md)；回報資安問題請看 [SECURITY.md](SECURITY.md)。
