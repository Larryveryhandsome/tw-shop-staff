# 參與貢獻

謝謝你願意幫忙！這個專案的目標是讓台灣的小店**不用懂程式也能用**，所以介面文字、文件都以白話繁體中文為主。

## 可以幫忙的地方

- **產業範本**：複製 `presets/` 裡的一個資料夾，改成你的產業（支出類別、單位、單位成本、示範班表），送 PR。
- **勞基法規則**：特休、病假、變形工時、抽成等，見 [docs/labor-law.md](docs/labor-law.md) 的「還沒做的」。
- **錯字、文件、截圖**。
- **Bug 回報**：開 Issue，附上重現步驟。**不要貼真實的員工、客人、帳務資料**。

## 開發規則

1. **只用 Python 標準庫**。要加套件，請先開 Issue 討論（目前唯一的選用套件是 cryptography，用在推播）。
2. **改計薪邏輯一定要附測試**，放在 `app/tests/test_labor.py`，並寫明依據的法條。
3. **不放真實資料**：測試、範例一律用假資料。電話用 `0900-000-xxx`，公司用「示範○○」，人名用職稱代稱。
4. **不加自動對外發文、自動留言、規避平台偵測的功能**。行銷模組一律「產草稿 → 老闆核准 → 人工發」。
5. 介面和對外文件裡的保證性說法要加「原則上」這類保留語，不寫「保證合法」。
6. Windows 背景程式一律不開視窗（pythonw＋CREATE_NO_WINDOW）。

## 送 PR 前

先跑這三組測試，都要通過：

```bash
python app/tests/test_labor.py
```

```bash
python app/tests/test_seed_demo.py
```

```bash
python tests/test_install.py
```

`app/tests/` 底下其他測試（test_crm、test_v2～v4、test_attendance、test_mk）也請跑過。

## 授權

你送的貢獻會依 [Apache License 2.0](LICENSE) 授權。
