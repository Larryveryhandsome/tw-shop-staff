# 行銷審核：貼文草稿與社群雷達的交接格式

行銷模組本身**不會自動發文、不會自動留言**。外部工具（任何 AI 工具、你自己寫的程式，或人工整理都可以）把草稿放進交接資料夾，系統每 5 分鐘收一次，老闆在「行銷」頁審核。核准後由人工發出。

交接資料夾預設是 `data/marketing/`，可以在 `config/store.toml` 的 `[paths] marketing_dir` 改。

> 請遵守各社群平台的使用條款。自動大量留言、自動加入社團、規避偵測等做法可能違反平台規範並導致帳號被停權。本專案不提供這類功能。

## 1. 貼文草稿

位置：`data/marketing/給CRM/<批次名稱>/posts.json`，圖片放在同一個資料夾。

```json
{
  "posts": [
    {
      "id": "2026-11-01-01",
      "channel": "threads",
      "group": "",
      "title": "週一團訂優惠",
      "text": "貼文內容……",
      "images": ["cover.jpg"],
      "image_note": "照片說明",
      "cta": "私訊訂購",
      "suggest_time": "11:00",
      "notes": "給老闆看的備註",
      "revision_of": ""
    }
  ]
}
```

- `channel` 可以填 `threads`、`fb_group`、`fb_page`、`ig`。
- `id` 不能重複；改稿請給新的 `id`，並在 `revision_of` 填舊的 `id`。
- 圖片只收 jpg、png、webp，每張 15MB 以內。

審核結果會寫回 `data/marketing/CRM回饋/<批次>.json`，外部工具可以讀回去調整下一批。

## 2. 社群雷達（有人在問、有活動要辦）

位置：`data/marketing/patrol/<YYYYMMDD>/patrol*.json`

```json
{
  "items": [
    {
      "url": "https://example.org/post/1",
      "platform": "Threads",
      "title": "有人在問哪裡訂便當",
      "snippet": "原文摘要",
      "who": "發文者或單位",
      "post_date": "2026-11-01",
      "need": "研習午餐 30 份",
      "boxes": 30,
      "event_date": "2026-11-15",
      "area": "中正區",
      "phone": "",
      "why": "為什麼值得回",
      "action": "留言",
      "reply": "建議的回覆內容",
      "score": 4
    }
  ]
}
```

- `url` 相同的只收一次。
- `area`、`boxes` 不在 `config/store.toml [sales]` 設定的範圍內，系統會自動略過，並寫明原因。
- `score` 填 1～5，數字越大越優先。

## 3. 每週新聞

```bash
python tools/import_news.py 新聞.json
```

格式見 `tools/import_news.py` 開頭的說明。
