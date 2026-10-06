# 股票篩選系統設計：FinMind 資料管線

> ⚠️ **本文件已於 2026-10-06 被取代（superseded）。**
> 現行規格書：**`2026-10-06-stock-screener-spec.md`**
>
> 取代原因：本文件只涵蓋資料管線，且以下內容已被後續查證推翻或修正：
> - §1 定位「篩選系統」→ 改為**研究輔助系統**（非全自動篩選器）
> - §3.4.3 「暫用未還原日線」→ 已找到免費官方解法（`TaiwanStockDividendResult`）
> - §4.3 額度查詢端點 → 實測失效（404 / 回 200 但需 token）
> - §4.4 pre-flight 機制 → 無 token 無法查額度，防護不可靠
> - §8 未納入 `origin_name` 中文名重複等靜默錯誤陷阱
> - 缺 Tier→PER 對應表、五大維度評分、估值層、略過篩選入口等核心設計
>
> 保留本文件僅為歷史追溯之用，**不得作為實作依據**。

日期：2026-10-01
狀態：**已取代（superseded by 2026-10-06-stock-screener-spec.md）**
定位：自用／內部研究（非公開、非營利）

---

## 1. 背景與目標

建立一個台股篩選系統。資料來源為 FinMind（台灣開放金融資料平台，92 種台股資料集）。

核心決策：**資料全部落地本地，篩選邏輯跑本地**。不查詢時直接打 API。

理由：篩選要快、要能回測、要能離線改條件、篩選過程不能燒 API 額度。

---

## 2. 連接方式決策

FinMind 官方提供三種「串接方式」，**本專案不採用任何一種作為資料來源**。

| 方式 | 實際是什麼 | 對本專案的定位 |
|---|---|---|
| Agent Skill（`/finmind` 指令檔） | 一個 Markdown 指令檔，在 CLI 裡一句一句問 | 開發期驗證欄位用 |
| MCP Server（`uvx finmind-mcp`） | AI 自動呼叫、適合多輪追問的 agentic 分析 | 開發期資料探勘用 |
| **REST API / Python SDK** | `api.finmindtrade.com/api/v4` + `FinMind.data.DataLoader` | **唯一資料來源** |

**理由**：Agent Skill 與 MCP Server 都是給 AI 對話工具用的。它們沒有批次排程、沒有本地快取、每次對話重打 API、額度消耗最快。篩選系統需要的是可批次、可增量、可重跑的取資料管道。

---

## 3. 資料方案與額度

**先不用付費，用免費 token 驗證整條流程。**

### 額度與方案

| 方案 | 價格 | 限制 | 資料集 | 授權 |
|---|---|---|---|---|
| Free | NT$0 | 600 次/小時（一天 14,400 次） | 45 | Non-commercial |
| Backer | NT$699/月 | 1,600 次/小時 | 81 | Non-commercial |
| Sponsor | NT$999/月 | 6,000 次/小時 | 97 | Non-commercial |
| Sponsor Pro | NT$3,330/月 | 20,000 次/小時 | 97 + 全市場 parquet | Commercial |

**關鍵限制**：免費方案不能省略 `data_id`，只能逐檔抓。官方文件對 `TaiwanStockPrice` 明確標註「一次拿特定日期，所有資料（只限 backer、sponsor 使用）」。

**授權範圍**：使用者不得將即時資料直接呈現於 web、App 等對外介面，亦不得對外再散布原始資料或建立鏡像服務。本專案自用，符合。

### 免費方案的缺口

| 缺口 | 影響 | 處理方式 |
|---|---|---|
| `TaiwanStockPriceAdj`（還原價） | 拿不到 | **暫用未還原日線，UI 必須明確標示長區間報酬率會失真** |
| `TaiwanStockWeekPrice` / `MonthPrice` | 拿不到 | 自己從日線 aggregate，週期可自選 |
| 免 `data_id` 全市場查詢 | 慢 | 逐檔抓，單執行緒排程 |
| `TaiwanStockKBar`（分 K） | 拿不到 | 不需要，日線自己算 |

---

## 4. Token 機制（7 天期限）

免費 token **有效期 7 天**（使用者實際觀察，官方文件未載明此期限）。

更新方式：官網自助，<https://finmindtrade.com/analysis/#/account/user> 點「更新 token」，舊 token 立即失效，無需聯繫客服。

### 4.1 Token 有兩個消費者

| 消費者 | 需要 token 的時機 |
|---|---|
| Streamlit 介面 | 使用者開著瀏覽器時 |
| 下載器 / 排程同步 | 掛機 1.6 天、或每日 18:30 自動跑，使用者不在瀏覽器裡 |

**結論**：token 必須落地到檔案。只存 session state 會讓排程同步完全不可用。

### 4.2 落地方式

**明文 `.env` + `.gitignore`**（已確認採此方案）。

依據：FinMind 隱私權政策第 10 條對用戶的唯一要求是「妥善保管您的存取憑證，避免外洩」，未要求磁碟加密。

### 4.3 額度與有效性查詢

```
GET https://api.web.finmindtrade.com/v2/user_info
Authorization: Bearer {token}
→ { user_count, api_request_limit }
```

用途：一次呼叫同時取得 token 有效性與目前額度用量。UI 顯示額度條，抓取過程中可即時看到是否接近 402。

### 4.4 過期防護三層

1. 記錄 `token_saved_at`，UI 顯示「Token 將於 X 天後過期」倒數
2. **每次同步開始前先打 `/user_info` 做 pre-flight 檢查**，過期直接擋下，不浪費一天抓取才發現
3. 抓取中每 100 requests 再驗一次；失效則停機、寫入 `sync_state`、記錄續跑點

續跑可行性：`sync_state` 冪等設計本來就支援，換新 token 後從水位線繼續即可。

---

## 5. FinMind 安全協議與合規做法

### 5.1 官方協議內容

- **傳輸層**：所有端點皆為 HTTPS/TLS（`api.finmindtrade.com`、`api.web.finmindtrade.com`）
- **認證層**：Bearer token 置於 `Authorization` header
- **儲存層**：無規定。隱私權政策第 10 條全文僅要求用戶「妥善保管存取憑證，避免外洩」

### 5.2 本專案的合規措施

| 措施 | 防什麼 |
|---|---|
| 僅 HTTPS | 傳輸竊聽 |
| Token 走 `Authorization` header，**不放 query string** | token 進伺服器 access log 與中間 proxy |
| **`.env` 進 `.gitignore`** | **真正的外洩管道：此為 git repo 且兩台電腦共用** |
| `.env` 檔案 ACL 限制當前使用者 | 同機器其他帳號讀取 |
| Token 不寫入 Obsidian／`handoff.md`／commit message／錯誤訊息 | 專案既有規則已涵蓋 |
| Log 僅顯示 token 前 4 碼 | 貼 log、截圖時外洩 |

**注意**：`llms.txt` 記載 `/data` 端點也接受 `token` 作為 query parameter。本專案**不使用**該形式。

---

## 6. IP 封鎖政策與請求策略

官方文件明載：短時間內累積大量 4xx 請求會觸發 IP 封鎖，**封鎖 30 分鐘**。

文件列出的觸發原因第一位即「爬蟲腳本使用過期或錯誤的 token 持續重送」。**本專案 7 天 token 期限直接對應此風險。**

### 6.1 分級重試策略

| 回應 | 處理 |
|---|---|
| 4xx（`TokenIllegal`、`TokenLevelTooLow` 等） | **不重試**，立即停止該 dataset，記錄續跑點 |
| 402（額度用完） | 非錯誤，停止並記錄，等下個計費週期 |
| 5xx | exponential backoff，**最多 3 次** |
| 403 + `{"msg": "ip banned"}` | **全域停止**，標記「封鎖中，30 分鐘後解除」 |

### 6.2 請求速率

**單執行緒，每 7.2 秒一次請求（500 次/小時，額度 600 留 100 緩衝）。**

**不使用併發。** 官方壓力測試顯示伺服器可承受 10～50 requests/秒，但本專案的瓶頸是帳號額度 600/小時（0.167 requests/秒），非伺服器能力。併發對額度限制毫無幫助，只會瞬間燒光當小時額度後吃 402。

> 設計修正紀錄：先前建議「併發 5～10」是錯的，已收回。

### 6.3 維護時段

**每週日凌晨 00:00～03:00 伺服器維護，服務暫停。**

1.6 天掛機下載必然經過此時段，同步器需自動暫停並於 03:00 後續跑。

---

## 7. 資料集分級

**不採「全部下載」策略。** 92 個資料集中有多張高頻巨獸，照字面全抓會燒掉磁碟與額度。

### 7.1 陷阱：5 秒頻率資料集

| 資料集 | 頻率 | 全市場估算量 |
|---|---|---|
| `TaiwanStockStatisticsOfOrderBookAndTrade`（每 5 秒委託成交統計） | 每股每 5 秒 | 1,900 檔 × 3,240 筆/日 ≈ **615 萬筆/日**，一年 1.5 億列 |
| `TaiwanVariousIndicators5Seconds`（每 5 秒） | 91 檔指數 | requests 少但每天 30 萬筆 |

（依文件標示頻率 × 交易時段推估，**尚未實測**，階段 1 會校準。）

### 7.2 核心層（優先抓，免費可取得）

需逐檔抓的高價值資料集，約 12 個：

```
TaiwanStockPrice                    TaiwanStockFinancialStatements
TaiwanStockPER                      TaiwanStockBalanceSheet
TaiwanStockMonthRevenue             TaiwanStockCashFlowsStatement
TaiwanStockInstitutionalInvestorsBuySell
TaiwanStockMarginPurchaseShortSale
TaiwanStockShareholding             TaiwanStockSecuritiesLending
TaiwanStockDividend                 TaiwanStockDividendResult
```

成本：12 個 × 1,900 檔 ≈ **22,800 requests ≈ 免費方案 1.6 天**（一天 14,400 次）。

### 7.3 中繼層（各 1 次 request，數秒完成）

不需 `data_id`：`TaiwanStockInfo`、`TaiwanStockInfoWithWarrant`、`TaiwanStockTradingDate`、
`TaiwanStockTotalReturnIndex`、`TaiwanStockDayTrading`、`TaiwanStockTotalMarginPurchaseShortSale`、
`TaiwanStockTotalInstitutionalInvestors`、`TaiwanSecuritiesTraderInfo`、`TaiwanStockNews` 等。

### 7.4 排除層

5 秒頻率表、`TaiwanStockInfoWithWarrantSummary`（sponsor）、
`TaiwanStockTradingDailyReport*`（分點，sponsor）、可轉債全系列（backer 起）、
即時快照（sponsor）、`TaiwanOptionVix`（backer 起）。

### 7.5 擴充規則

篩選文件到手後若需目前排除的資料集，依序檢查：免費方案能否取得 → 補抓增量 → 不得已在 `raw_` 層重建。

---

## 8. 已知資料陷阱

FinMind 官方文件明載，四點全部寫進 `transform/` 層，不在 `raw_` 層處理。

1. **興櫃個股 `open` 是「前日均價」不是開盤價**
   可能落在當日 `max`/`min` 之外。興櫃掛牌首日 `open = 0`。
   → 不要用 `open` 計算任何指標。

2. **當日無公告成交價時 `open`/`max`/`min`/`close` 全為 `0`**
   但 `Trading_Volume` 可能是 451（例：9929 秋雨 2025-07-31）。
   → **不要用 `Trading_Volume > 0` 當有效篩選條件**，會漏掉「有量但無價」的列。用 `close > 0` 判斷。

3. **`TaiwanStockInfo` 一檔股票可能有多列**
   興櫃轉上市者同時保留 `emerging` 與 `twse`/`tpex` 兩列。
   → 取同一 `stock_id` 中 `date` 最新的那一列。**不要直接用 `type == "emerging"` 篩選**。

4. **還原價基準**
   以最新交易日為基準往前累乘，事件當日還原價恆等於原始價。

補充：`TaiwanStockPriceTick` / `TaiwanStockKBar` 的 `volume` 單位依市場別而異（上市/上櫃為張、興櫃為股），同日資料混用兩種單位。

---

## 9. 系統架構

```
FinMind REST API / SDK
      │
      ▼
core/finmind_client.py   HTTPS + Bearer header + token bucket + 分級重試
core/quota.py            /user_info 額度與有效性
core/datasets.py         資料集註冊表
core/token_store.py      token 讀寫 + saved_at
      │
      ▼
storage/writer.py        Parquet 分區寫入（raw 層，不可變）
storage/sync_state.py    水位線表
      │
      ▼
DuckDB (read_only)       查詢層
      │
      ▼
transform/               型別正規化、興櫃與無價日修正
      │
      ▼
metrics/                 衍生指標：報酬率、均線、波動、PER/PBR
      │
      ▼
screener/                篩選條件 = 純函式 (DataFrame → DataFrame + 命中理由)
      │
      ▼
app/ (Streamlit)         網頁介面
```

### 9.1 raw 層用 Parquet，不用 DuckDB 寫入

**設計修正**（相較於初稿）：raw 層改為 Parquet 分區落地，DuckDB 僅在查詢時以 `read_only=True` 開啟。

**原因**：DuckDB 單寫者限制。下載器掛機 1.6 天、或每日 18:30 排程同步時，會與同時開啟的 Streamlit 搶檔案鎖而讀取失敗。Parquet 為檔案級追加，兩者不衝突，且備份與增量皆單純。

### 9.2 raw 層不可變

`raw_<dataset>` 只追加、不 UPDATE、不轉型。所有修正在 `transform/` 層。

理由：抓錯資料時重跑 transform 即可，不需重打 API 燒額度。

### 9.3 抓取冪等

`storage/sync_state.py` 水位線表：

```
dataset | stock_id | last_date | last_sync | row_count | status
```

- 每次同步只抓 `date > last_date` 的部分
- 每完成一個 `stock_id` 即 commit，中斷後 `--resume` 從水位線繼續
- 1.6 天掛機中斷機率不低，此設計必須一開始就做對
- 失敗的 stock_id 記錄待重試，不讓單筆失敗拖垮整批

### 9.4 screener 是純函式

輸入 DataFrame、輸出篩選結果與命中理由，不碰 IO。篩選邏輯可單獨測試，改條件不需重啟服務。

### 9.5 交易日與排程

先查 `TaiwanStockTradingDate` 判斷是否為交易日，週末與連假不空跑。

| 資料 | 更新時間 |
|---|---|
| `TaiwanStockInfo` | 每天 1:30 |
| `TaiwanStockPrice` 等日線 | 週一至五 17:30 |
| `TaiwanStockTradingDate` | 週一至五 18:00 |

排程時間 **18:30 之後**執行，避開未 complete 的資料。避開週日 00:00～03:00 維護時段。

---

## 10. 一鍵啟動

技術棧：Python + DuckDB + Streamlit。依賴管理用 `uv`。

```bat
:: start.bat
uv sync
uv run streamlit run app\main.py
```

`uv sync` 依 `uv.lock` 自動建環境並對齊版本。搭配 `.python-version` 釘版，滿足兩台電腦 Python 版本一致的約定。

**資料抓取不綁在啟動流程裡。** 啟動只開介面；資料不足時 UI 顯示「資料截至 X 日」並提供同步按鈕。介面不因等待資料而卡住。

同步觸發方式：

- 手動：Streamlit 內「同步今日資料」按鈕
- 排程（選用）：Windows 工作排程每日 18:30 自動觸發

---

## 11. 執行順序

```
階段 0  專案骨架（pyproject / .gitignore / start.bat / AGENTS.md）
   ↓
階段 1  探勘 10～20 分鐘
        實測 12 個核心資料集 schema、免費方案實際範圍、
        抽 3 檔驗證文件未寫的缺陷、校準 5 秒巨獸量級
        產出 docs/datasets-schema.md
   ↓
階段 2  抓取層（client / quota / datasets 註冊表 / token_store）
   ↓
階段 3  資料落地與同步（writer / sync_state / sync / validate）
        掛機抓全量，約 1.6 天
   ↓
階段 4  介面與篩選條件（等篩選文件到手）
```

**為什麼階段 1 不能跳**：raw 表 schema 需依實測結果建 DDL。若照文件猜錯欄位，階段 3 的 1.6 天會白跑。用 20 分鐘實測換掉這個風險。

**順序由使用者提出、並經確認**：先做下載器把資料抓完整，再依資料與篩選文件設計介面。理由是下載器屬長期維護元件、UI 是一次性的，且實際資料內容才能暴露欄位缺口與異常值。

---

## 12. 待確認事項

1. **未還原價的限制能否接受？** 免費拿不到 `TaiwanStockPriceAdj`，算長區間（>1 年）報酬率會因除權息跳空失真。若篩選條件重度依賴長區間報酬率，需提早買 Backer 699。
2. **篩選文件**（他人的篩選方式）尚未提供，收到後才能確定核心層資料集是否足夠。
3. **免費方案實際回傳範圍**未實測，文件標示 45 個與實際可能不符，以階段 1 實測為準。
4. **7 天 token 期限**為使用者實際觀察，官方文件未載明。若實際期限不同，`token_store` 的倒數顯示需調整。

---

## 13. 參考資料

- llms.txt（方案、額度、端點）：<https://finmind.github.io/llms.txt>
- IP 封鎖政策：<https://finmind.github.io/BanIPPolicy/>
- 使用條款與隱私權政策：<https://finmind.github.io/PrivacyPolicy/>
- 壓力測試：<https://finmind.github.io/StressTest/>
- 更新 Token：<https://finmind.github.io/update_token/>
- 技術面（資料陷阱）：<https://finmind.github.io/tutor/TaiwanMarket/Technical/>
- 92 資料集總覽：<https://finmind.github.io/tutor/TaiwanMarket/DataList/>
- Agent Skill：<https://finmind.github.io/tutor/ai/AgentSkill/>
- MCP Server：<https://finmind.github.io/tutor/ai/Mcp/>