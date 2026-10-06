# handoff.md — StockScreener

## ⏯️ 目前做到哪

**抓取程式已完成（45 測試全過），資料抓取掛機中，UI 與自動接續腳本已上線。**

- **藍圖**：`agents.md`（階段路線圖、文件分工、陷阱、常用指令）
- 程式碼：`fetch.py` ＋ `src/` ＋ `monitor.py`（進度儀表板）＋ `run_all.py`（自動接續）
- 規格書：`docs/superpowers/specs/2026-10-06-stock-screener-spec.md`（14 節，現行實作依據）
- 詞彙表：`CONTEXT.md`
- 決策紀錄：`docs/superpowers/specs/2026-10-05-decision-log.md`
- **資料來源實測**：`docs/review/data-source-verification.md`（26 項測試）

已確認的決策（細節與依據在 decision-log）：

| 項目 | 決策 |
|---|---|
| 定位 | **研究輔助系統**（非全自動篩選器）|
| 資料來源 | FinMind REST API ＋ TWSE/TPEx 官方 open data |
| 技術棧 | Python 3.12 + DuckDB + Streamlit，依賴用 `uv` |
| 財務報表 | **已轉單季值**，TTM = 最近 4 季相加，不需相減 |
| ROE 篩選 | **講義的多年平均**（推翻原 D9 的 TTM），TTM 另留參考顯示 |
| 目標 PER | **只由 Tier 決定**，CAGR 不當獨立上限 |
| 風險折扣 | 講義第 5 維 20 分，**階梯跳級**（14 分差距 → PER 差近 10 倍）|
| 維度 2 | 手動輸入產業 CAGR ＋ 系統換算建議分數 |
| 維度 4 | 維持人工評分，杜邦僅作參考面板 |
| 估值 | 安全邊際（5 年）與追價安全圈（2 年）**兩套並存** |
| 安全圈 EPS | **全手動輸入**，不做自動預測 |
| ETF | **保留在資料庫**（使用者要看技術線圖），但財務類 dataset 不抓 |
| 否決過濾 | 兩個機制 v1 不做，只記錄 |
| align_score | **無資料來源，v1 不實作** |

## 🚦 目前狀態

- 可運行：**抓取器可運行**；財務指標計算、介面尚未開始
- **抓取掛機中**（2026-10-06 晚，DESKTOP-5241OJK）
  - 進度看儀表板 **<http://127.0.0.1:8765/>**（`monitor.py`，每 5 秒刷新）
  - 或 `uv run python fetch.py --status`
  - 全部完成時會寫 `logs/ALL_DONE.txt` ＋ 彈 Windows 通知
- **Git**：`master` = `origin/master`（收工前已推）
- **Obsidian**：`OpenCode專區/StockScreener/2026-10-06.md`

## 📍 專案路徑（重要，2026-10-06 變更）

**專案已從雲端硬碟搬到本機硬碟。**

| 機器 | 路徑 | 說明 |
|---|---|---|
| **DESKTOP-5241OJK** | `E:\OpenCode\Stock Screener(股票篩選)` | **現行工作目錄、data 存這裡** |
| 雲端硬碟上的舊副本 | （不再使用）| 見下方「⚠️ 舊副本狀態」 |

### 資料存在哪裡

`data/`（sync_state.db ＋ parquet）**存在 DESKTOP-5241OJK 的本機硬碟 `E:`**，不在雲端硬碟。

搬移原因與教訓：

1. 舊位置在雲端硬碟，同步軟體會在**檔案還沒寫完時就同步**，造成
   `sync_state.db` 說「已完成」但 `data/raw/` 對應的 parquet 不見（或不完整）。
2. 續傳邏輯原本只讀 SQLite，看不到檔案遺失，會直接跳過 → **資料空洞，且不會報錯**。
3. 已修（commit `f5a488e`）：續傳改以 `writer.exists()` 實際檔案為準，
   檔案遺失就從頭重抓（`last_date` 在檔案不存在時不可信）。
4. 雲端硬碟上的 data 應視為**不可靠**，不要再把抓取產物放回雲端同步路徑。

### ⚠️ 舊副本狀態

雲端硬碟上的舊副本**仍存在**，且是**過時的**：缺本次的
`monitor.py`、`run_all.py`，git 也落後 2 個 commit（但工作區有同樣的未提交修改，
打開會看到「有未提交變動」的假象）。

- **一律以 git ＋ `E:\OpenCode\...` 為準，不要再開舊副本**
- 舊副本要不要刪除由使用者手動決定（本 agent 不刪）

## ▶️ 明天在另一台主機怎麼做

### 程式碼

```bash
cd <該機的專案路徑>          # 路徑由使用者提供，尚未確定
git pull
uv sync                       # 首次
uv run python -m unittest discover tests   # 應 45 passed
```

### ⚠️ 兩台不能同時抓

額度是**帳號層級** 600 次/小時。這台（DESKTOP-5241OJK）正在抓，
另一台**不要**跑 fetch，除非這台的抓取已結束（看 `logs/ALL_DONE.txt` 或儀表板）。

### 抓取（若要在那台執行）

```bash
uv run python run_all.py      # 依序抓 7 個 dataset，中斷可續傳
uv run python monitor.py      # 另開，看進度 UI（:8765）
```

### 下一階段（階段 2 財務指標計算）

待辦（詳見 `agents.md` 階段 2 區塊）：

1. 實算篩選剩幾檔（原未解問題 #2）⚠️ `align_score` 無資料來源，可用條件是三個不是四個
2. ROE 多年平均（3 年／5 年）＋ TTM ROE 參考顯示
3. 杜邦五項（`IncomeAfterTaxes`，不可用 `NetIncome`）
4. 營收 CAGR（`revenue_year`+`revenue_month`，**不是 `date`**）
5. 還原股價：`DividendResult` + `ParValueChange` + `SplitPrice`

### 🔒 雙機開發規則（2026-10-06 使用者定案）

**兩邊同時開發，只有程式碼同步，資料一律不同步。**

| 項目 | 同步方式 | 規則 |
|---|---|---|
| 程式碼（`src/`、`fetch.py`、`monitor.py`、`run_all.py`、`tests/`） | **git** | 唯一同步通道，改完就 commit + push |
| `data/`（parquet + `sync_state.db`） | **不同步** | 各機各自存在本機硬碟，**絕不放雲端資料夾** |
| `.venv/`、`uv.lock` | `uv sync` 重建 | `uv.lock` 走 git，各機自己裝 |
| `logs/` | 不同步 | git 忽略，各自留本機 |

**為什麼**：`data/` 被雲端同步 = 今晚掉檔事故的根因
（邊寫邊同步 → db 說完成、檔案不見）。
資料搬運是**一次性 zip 快照**，不是持續同步，且：

1. **抓取在 DESKTOP-5241OJK 一台跑完為止**（`logs/ALL_DONE.txt` 出現）
2. **完整後才上傳**，上傳前先問使用者（本次已定案：不急著動）
3. 搬之前一定先詢問，**不要自己判斷要搬**
4. 搬的方式：`data/` 打成一個 zip → 另一台解壓到**該機本機專案路徑**
   （不要解到雲端資料夾，也不要讓雲端硬碟看到這個 zip 的解壓目錄）

**資料正本在 DESKTOP-5241OJK**；另一台的資料是快照，會過期。
若兩台都跑抓取 → 額度 600/小時 是帳號層級，會互相拖垮，禁止。

另一台主機的專案路徑：**尚未提供**（使用者將於該機建立後告知）。
收到路徑後，先 `git pull` + `uv sync`，**不要動 `data/`**。


## 🛠️ 2026-10-06 晚 在 DESKTOP-5241OJK 遇到的問題與處理

### 1. 專案路徑從雲端硬碟搬到本機（使用者主導）

- 變更：工作目錄改 `E:\OpenCode\Stock Screener(股票篩選)`
- 處理：搬移後在新位置 `uv sync` 重建環境、重跑 45 測試與 ruff 全過
- 影響：data 與 sync_state.db 跟著到本機，雲端副本作廢

### 2. 雲端同步造成 parquet 遺失，續傳會靜默跳過

- 症狀：`sync_state.db` 記錄 5 個全域 dataset 全完成，但 `data/raw/` 檔案不見
- 根因：續傳只信 SQLite 狀態，不看檔案
- 修法：`fetch.py` 續傳改比對 `writer.exists()`；新增 `SyncState.ok_ids()`
  （與 `done_ids` 差在排除 `empty`——empty 本來就沒檔，不能當遺失重抓）
- 驗證：新增 10 個測試（`TestParquetLossRecovery`），共 45 passed

### 3. 抓取 log 中文變亂碼

- 症狀：`run_all` 的 log 出現 `略??235` 這類問號
- 根因：Windows 主控台預設 cp950，Python 寫檔時用 cp950 編碼
- 修法：`run_all.py` 明確設 `PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`
  （在 `os.environ.setdefault`，子行程繼承）
- 補充：先前用 PowerShell 看到的「??」部分是**顯示層**問題，
  逐位元組驗證 log 本身乾淨（0 個 U+FFFD、0 個 `?`）。看中文 log 請用
  `Get-Content -Encoding UTF8` 或直接開儀表板

### 4. 進度儀表板算出的分母不對

- 症狀：UI 算 2154 檔，fetch.py 實抓 2037 檔 → 進度條永遠到不了 100%
- 根因：UI 從本地 parquet 推股票池（含已下市股），fetch.py 用當期 API 結果
- 修法：`fetch.py` 抓取時寫 `data/raw/universe.json`（權威股票池），
  `monitor.py` 讀它當分母，**兩邊不再各算各的**

### 5. PowerShell 5.1 不支援 `Start-Process -Environment`

- 症狀：參數驗證錯誤，行程沒啟動
- 修法：改在父層先 `$env:PYTHONIOENCODING="utf-8"`，或由腳本內部 `os.environ` 設定

### 6. 抓取進度與排程工具（新增）

| 檔 | 用途 |
|---|---|
| `monitor.py` | 進度 UI，<http://127.0.0.1:8765/>，只讀 DB 不干擾抓取 |
| `run_all.py` | 依序抓 7 個 dataset，可 Ctrl+C 中斷續傳；**會依退出碼自動等待重試**，完成彈通知 |
| `logs/` | 抓取 log（git 忽略）|

掛機指令（DESKTOP-5241OJK，2026-10-06 19:38 起）：

```bash
# 背景執行（無視窗）
.venv\Scripts\python.exe run_all.py     → logs\runner.out.log / run_all-YYYYMMDD-HHMM.log
.venv\Scripts\python.exe monitor.py --no-browser  → logs\monitor.out.log
```

## ✅ 已完成（10-06 晚）

1. 專案搬至本機 E:，環境重建、45 測試 + ruff 全過
2. `monitor.py` 進度儀表板（純標準庫，無新依賴）
3. `run_all.py` 自動接續腳本 ＋ Windows 完成通知
4. parquet 遺失恢復（含 10 個新測試）
5. `universe.json` 統一進度分母
6. 退出碼契約 + 自動重試策略（斷線自癒、額度通知、ALL_DONE 閘門），見「安全機制」
7. 兩個 commit 已推（`f5a488e` 續傳修正、`0e0d038` UI 與腳本）

## ⚠️ 注意事項

### 掛機行程不會活過重開機

`run_all.py` / `monitor.py` 是背景行程，**重開機後不會自己恢復**。
開機後要重跑：

```bash
cd "E:\OpenCode\Stock Screener(股票篩選)"
uv run python monitor.py --no-browser   # 先開 UI
uv run python run_all.py                # 續傳抓取
```

### 抓取中不能關機／休眠

斷網會讓抓該輪停止（續傳可救回）。**2026-10-06 起 `run_all.py` 會自己等**
：指數退避後自動續抓並彈通知，不用守著重啟。重啟機仍是例外——背景行程不會自己恢復。

### Token 不是必需的

免 token 即可取用多數 dataset；`.env` 已建但非抓取必要。

### ETF 保留但不抓財務

- stock master 保留全部 2507 檔（ETF 保留）
- 財務類只抓 2037 檔有財報的個股，行情類抓全部 2507 檔

### 還原股價需要三個來源

`DividendResult` + `ParValueChange` + `SplitPrice`（`CapitalReductionReferencePrice` 實測回空，不可用）

### 三種錯誤性質要分清

| 回應 | 性質 |
|---|---|
| `422` enum 錯誤 | 名稱不存在（含大小寫）|
| `400 "Your level is free"` | 需登入或付費 |
| `400 "parameter data_id don't provide"` | 用法錯誤 |
| `200` + `rows: 0` | 期間無資料（**不是錯誤**）|

### 靜默錯誤陷阱（寫錯不會報錯）

1. 損益表 `EquityAttributableToOwnersOfParent` 是「**淨利**歸屬母公司」，**不是權益**
2. `NetIncome` 只有 20 期（止於 2019），**用 `IncomeAfterTaxes`**（46 期）
3. `_per` 後綴是「占總資產百分比」，**整組忽略**
4. `TaiwanStockInfo` 是**變更事件流**，需取 `date` 最新一列（`latest_by_stock`）
5. `origin_name` 中文名大量重複，**必須用英文 key 硬編碼對應**
6. 普通股判斷**不能只看 4 碼數字**，要結合 `industry_category` ＋ 字母後綴（`classify_universe`）
7. 進度分母**只能用 `universe.json`**，不要從本地 parquet 重推（會含下市股）

### 安全機制（已內建，不要移除）

`fetch.py` 負責「什麼時候該停」，回報退出碼；`run_all.py` 負責「等多久再重試」。

`fetch.py` 端（不可移除）：

- 4xx 連續 3 次 → **熔斷停止**（`EXIT_CIRCUIT = 5`）
- `403 ip banned` → 立即停止（`EXIT_IP_BAN = 4`）
- `402` 額度用盡 → 立即停止（`EXIT_QUOTA = 3`），**此檔不記 error**，下次從頭抓
- 連續 3 檔（`TRANSIENT_ABORT_AFTER`）網路/5xx 失敗 → 判定斷線立即中止（`EXIT_NETWORK = 2`），
  避免斷網時把幾千檔污染成失敗狀態
- 抓完但有失敗檔 → `EXIT_PARTIAL = 6`（不是成功，run_all 會補抓）

`run_all.py` 端（`RETRY_POLICY`）：

| 退出碼 | 等待 | 最多重試 |
|---|---|---|
| 2 斷線 | 60s 起指數退避，封頂 900s | **無上限**（掛機就等網路回來）|
| 3 額度用盡 | 3600s | 4 次 |
| 4 IP 封鎖 | 1860s（官方 30 分 + 1 分）| 3 次 |
| 6 部分失敗 | 120s | 2 次，用盡則記為不完整、繼續下一個 |
| 1 致命 / 5 熔斷 | 不重試 | — （5 需人工確認參數，官方明講不要盲重試）|

### ⚠️ ALL_DONE.txt 是上傳雲端的閘門

**只有 7 個 dataset 全部回 0 才寫 `logs/ALL_DONE.txt`**，有任何一個沒完成就改寫
`logs/PARTIAL-<stamp>.txt` 並彈錯誤通知。

2026-10-06 之前的版本 402/403/熔斷全部 `exit 0` → run_all 誤當成功 → 資料根本沒抓完卻寫了
`ALL_DONE.txt`，直接戳破「抓完才上傳雲端」的規則。改動這條時務必跑 `tests/test_run_all.py`。

## 🕐 最後更新

- 時間：2026-10-06（收工，第三次）
- 更新者：OpenCode @ **DESKTOP-5241OJK**
- HEAD：見 `git log -1`
- Git push：✅ 已推
- Chezmoi push：—（`chezmoi status` 於 2026-10-06 確認乾淨）
- 目標驗證：✅ 69 個單元測試通過（`uv run python -m unittest discover tests`）
- 目標驗證：✅ ruff 全過（`uv run ruff check src fetch.py monitor.py run_all.py tests`）
- 目標驗證：✅ 儀表板可讀（HTTP 200，12 個 dataset 進度正確，分母與 fetch.py 一致）
- 目標驗證：✅ 抓取實際進行中（`TaiwanStockFinancialStatements` 持續增加，0 錯誤）
- ⚠️ **新程式碼要重啟背景行程才生效**（舊行程仍載入舊版 fetch.py/run_all.py）
- ⚠️ **抓取掛機中，重開機會停**（重啟方式見「掛機行程不會活過重開機」）
- ⚠️ 舊雲端副本未清理（由使用者決定，見「舊副本狀態」）
