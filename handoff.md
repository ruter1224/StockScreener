# handoff.md — Stock Screener

## ⏯️ 目前做到哪

設計階段全部定稿，**尚未寫任何程式碼**。

- 完整設計文件：`docs/superpowers/specs/2026-10-01-finmind-data-pipeline-design.md`（13 節，canonical）
- repo 狀態：只有 `docs/` 一個目錄，master 分支，無 commit 歷史

已確認的決策（細節與依據在 spec）：

| 項目 | 決策 |
|---|---|
| 定位 | 自用／內部研究 |
| 資料來源 | REST API（`api.finmindtrade.com/api/v4`）+ Python SDK |
| 技術棧 | Python + DuckDB + Streamlit，依賴用 `uv` |
| 順序 | 骨架 → 探勘 → 抓取層 → 掛機全量 → 介面 |
| Token 落地 | 明文 `.env` + `.gitignore` |
| 請求速率 | 單執行緒，每 7.2 秒一次（500/時） |
| raw 層 | Parquet 分區，DuckDB 僅 `read_only` 查詢 |

## 🚦 目前狀態

- 可運行：**否**，專案還沒有可執行的程式
- 介面：未開始
- 資料：尚未下載任何資料
- Git：**尚未建立第一個 commit，且未設定 remote**

## ➡️ 下一步

1. **建專案骨架 + `.gitignore`**（`.env` 必須在第一個 commit 之前擋下，repo 目前還很乾淨，這是唯一時機）
2. **填入 token** 到 `.env`，然後跑 `/user_info` 驗證有效性
3. **階段 1 探勘** 10～20 分鐘，實測 12 個核心資料集 schema，產出 `docs/datasets-schema.md`
4. 寫抓取層，啟動首次全量同步（免費額度約需 1.6 天）

使用者預計 2026-10-01 晚間執行。篩選文件會在實作前提供。

## ⚠️ 注意事項

### Token 期限

免費 token **有效期 7 天**（使用者實際觀察，官方文件未載明）。

架構後果：token 有兩個消費者，壽命需求不同 ——
- Streamlit 介面（人在瀏覽器）
- 下載器／排程同步（掛機 1.6 天，人不在）

所以 **token 必須落地到檔案**，只存 session state 會讓排程同步完全不可用。

### 安全：真正的破口是 git，不是磁碟

FinMind 隱私權政策第 10 條對用戶的唯一要求是「妥善保管存取憑證，避免外洩」，**未要求磁碟加密**。因此採明文 `.env`。

但這個 repo 會進 git、且預期跨電腦共用，所以：
- `.env` 進 `.gitignore`，第一版就要
- token 只走 `Authorization` header，**絕不放在 query string**
- log 只印 token 前 4 碼
- token 不寫入 Obsidian／`handoff.md`／commit message／錯誤訊息

### 重試策略必須分級（IP 封鎖風險）

免費 token 7 天期限直接對應官方 IP 封鎖政策 —— 觸發封鎖原因第一位就是「爬蟲腳本使用過期或錯誤的 token 持續重送」，封鎖 **30 分鐘**。

```
4xx                              → 不重試，立即停該 dataset
402（額度用完）                   → 非錯誤，停止並記錄
5xx                              → exponential backoff，最多 3 次
403 + {"msg":"ip banned"}        → 全域停止，標記 30 分鐘後解除
```

### 維護時段

**每週日凌晨 00:00～03:00 伺服器維護，服務暫停。** 1.6 天掛機必然經過，要能自動暫停並續跑。

### 同步前檢查 token

`GET https://api.web.finmindtrade.com/v2/user_info`
→ `{"user_count": ..., "api_request_limit": ...}`

同步開始前先打這支做 pre-flight 檢查，並可顯示額度條。抓取中每 100 requests 再驗一次，失效就停機寫水位線，換 token 後續跑。

### 未還原價的限制（已知取捨）

免費方案拿不到 `TaiwanStockPriceAdj`，算長區間（>1 年）報酬率會因除權息跳空失真。介面必須明確標示。若篩選重度依賴長區間報酬率，需提早買 Backer。

### 已收回的錯誤建議

先前建議「併發 5～10」是錯的，已收回。官方壓力測試顯示伺服器可承受 10～50 requests/秒，但瓶頸是帳度額度（0.167/秒），併發只會瞬間燒光當小時額度後吃 402。

## 🕐 最後更新

- 時間：2026-10-01
- 更新者：OpenCode @ LAP2021-T153
- Git push：❌ 未推（本 repo 尚未設定 remote）
- Chezmoi push：—（無變動，本次未處理）