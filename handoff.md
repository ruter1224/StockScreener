# handoff.md — StockScreener

## ⏯️ 目前做到哪

**抓取程式已完成並通過 69 個測試；全量抓取掛機中（DESKTOP-5241OJK）。**

- **藍圖**：`agents.md`（階段路線圖、文件分工、陷阱、常用指令）
- 程式碼：`fetch.py`（抓取＋退出碼契約）＋ `run_all.py`（自癒排程）＋ `monitor.py`（進度 UI）＋ `src/`
- 規格書：`docs/superpowers/specs/2026-10-06-stock-screener-spec.md`（現行實作依據）
- 詞彙表：`CONTEXT.md` ｜ 決策紀錄：`docs/superpowers/specs/2026-10-05-decision-log.md`
- **資料來源實測**：`docs/review/data-source-verification.md`（26 項測試）
- Obsidian：`OpenCode專區/StockScreener/2026-10-06.md`
  （當天筆記只留**最新一次**收工＋收工索引表；更早的收工已歸檔到同資料夾的
  `歷史日誌.md`，內容原樣搬入未改寫）

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
| ETF | **保留在資料庫**（要看技術線圖），但財務類 dataset 不抓 |
| 否決過濾 | 兩個機制 v1 不做，只記錄 |
| align_score | **無資料來源，v1 不實作** |
| 資料搬運 | 抓完才搬，一次性 zip 快照，**搬前必先問使用者** |

## 🚦 目前狀態

- 可運行：**抓取器可運行**；財務指標計算、介面尚未開始
- **抓取掛機中**（2026-10-06 22:04 重啟後的新版排程，DESKTOP-5241OJK）
  - 收工時進度：`TaiwanStockFinancialStatements` **1722/2037（84.5%）**，error=0
  - 6 個 dataset 尚未開始（財務類剩餘約 315 檔，其餘 6 個接續跑，總計仍以小時計）
  - 進度看儀表板 **<http://127.0.0.1:8765/>**（每 5 秒刷新）或 `uv run python fetch.py --status`
  - 7 個 dataset 全部回 0 才會寫 `logs/ALL_DONE.txt` ＋ 彈通知
  - 本輪 log：`logs/run_all-20261006-2204.log`、`logs/runner.out.log`
- **Git**：`master` = `origin/master`（收工前已推）
- **Chezmoi**：無變動，兩側皆乾淨

### 背景行程（重啟機後**不會**自己恢復）

| 角色 | PID（venv / 基底 python）|
|---|---|
| `run_all.py` | 9468 / 6728 |
| `fetch.py`（子行程）| 2132 / 12316 |
| `monitor.py --no-browser` | 5600 / 16944 |

⚠️ **每個角色會是兩個 PID**：venv 的 `python.exe` 是啟動器，會再 spawn 一個基底
python 作為子行程。只殺其中一個，另一個會繼續跑。停程式務必兩個都收。

## 📍 專案路徑與資料位置

**專案已從雲端硬碟搬到本機硬碟（2026-10-06）。**

| 機器 | 路徑 | 說明 |
|---|---|---|
| **DESKTOP-5241OJK** | `E:\OpenCode\Stock Screener(股票篩選)` | **現行工作目錄，data 在這裡** |
| 雲端硬碟舊副本 | （不再使用）| 見「舊副本狀態」 |

`data/`（`sync_state.db` ＋ parquet）**存在本機硬碟，不在雲端**。VENV 在 repo 根目錄。

### 舊副本狀態

雲端硬碟上的舊副本**仍存在且過時**（缺 `monitor.py`、`run_all.py`、git 落後）。
**一律以 git ＋ 上表路徑為準，不要再開舊副本。** 刪不刪由使用者手動決定（本 agent 不刪）。

## 🔒 雙機規則（2026-10-06 使用者定案）

**兩邊同時開發，只有程式碼同步，資料一律不同步。**

| 項目 | 同步方式 | 規則 |
|---|---|---|
| 程式碼（`src/`、`fetch.py`、`run_all.py`、`monitor.py`、`tests/`）| **git** | 唯一同步通道，改完就 commit + push |
| `data/`（parquet + `sync_state.db`）| **不同步** | 各機本機硬碟，**絕不放雲端資料夾** |
| `.venv/` | `uv sync` 重建 | `uv.lock` 走 git，各機自己裝 |
| `logs/` | 不同步 | git 忽略，各自留本機 |

**為什麼**：`data/` 被雲端同步 = 掉檔事故的根因（邊寫邊同步 → db 說完成、檔案不見）。

**額度是帳號層級 600 次/小時，兩台不能同時抓。** 抓取只在 DESKTOP-5241OJK 跑。

### 換到另一台主機時

```bash
cd <該機專案路徑>              # 路徑待使用者提供
git pull
uv sync                        # 首次
uv run python -m unittest discover tests    # 應 69 passed
```

**不要動 `data/`。** 另一台主機的專案路徑尚未提供；收到後先 `git pull` + `uv sync`。

### 資料搬運（尚未執行）

1. 抓取在 DESKTOP-5241OJK 跑到 `logs/ALL_DONE.txt` 出現
2. **完整後才上傳，上傳前先問使用者**
3. 搬法：`data/` 打成一個 zip → 另一台解壓到**該機本機專案路徑**
   （不要解到雲端資料夾，也不讓雲端硬碟看到解壓目錄）
4. 資料正本在 DESKTOP-5241OJK；另一台的是快照，會過期

### ⚠️ 專案目錄名有一個字形陷阱

正確目錄名是 **`Stock Screener(股票篩選)`**，注意是 **篩**（U+7BE9，篩選）。

2026-10-06 曾因打字錯誤多建了一個 `Stock Screener(股票籌選)`
（**籌** U+7C4C），裡面只有一份 `run_all.py` 草稿，
沒有 `.git`、沒有 `data/`、沒有 `.venv`，**沒有任何需要同步的東西**。
已確認對抓取與 git 零影響（抓取實際跑在正確目錄），
**並已於 2026-10-06 由使用者手動刪除**。

**git 追蹤內容，不追蹤資料夾名**，所以兩台電腦的資料夾名不必一致，
`git clone` / `git pull` 即可。別為了讓兩台一致而去搬動正在跑的目錄。

📌 **已定案（使用者 2026-10-06）：維持現名 `Stock Screener(股票篩選)`，不改純英文。**
理由：git 不在意資料夾名，兩台名稱不必一致，改名只增加自己打錯字的機會。
**不要再提改名這件事**，也**不要為了統一名稱去搬動正在跑的目錄**。

## ▶️ 下一步

1. **等抓取完成**（`logs/ALL_DONE.txt` 出現）。期間不要關機／休眠。
   期間可做的只有開發，不要動 `data/`。
2. **重啟機後**（若發生）：`uv run python monitor.py --no-browser` ＋
   `uv run python run_all.py`，會自動續傳。
3. **抓完後**：先問使用者要不要上傳資料快照，再進**階段 2 財務指標計算**
   （詳見 `agents.md` 階段 2）：
   - 實算篩選剩幾檔（原未解問題 #2）⚠️ `align_score` 無資料來源，可用條件是三個不是四個
   - ROE 多年平均（3 年／5 年）＋ TTM ROE 參考顯示
   - 杜邦五項（用 `IncomeAfterTaxes`，不可用 `NetIncome`）
   - 營收 CAGR（用 `revenue_year`+`revenue_month`，**不是 `date`**）
   - 還原股價：`DividendResult` + `ParValueChange` + `SplitPrice`

## ⚠️ 注意事項

### 抓取掛機中：不要重啟背景行程以外的操作

- 改 `fetch.py`／`run_all.py` **不會**影響已載入的執行中行程，改了要重啟才生效。
- 重啟是安全的：`state.record` 在 `writer.write` 之後，中斷當前檔會被續傳重抓。
- 停程式要成對收 PID（見上方「背景行程」）。
- 抓完前不要碰 `data/`、不要刪 `logs/`。

### 退出碼契約（兩層分工，不可移除）

`fetch.py` 決定「什麼時候該停」並回報退出碼；`run_all.py` 決定「等多久再重試」。

| 退出碼 | fetch.py 觸發 | run_all.py 策略 |
|---|---|---|
| 0 | 抓完 | 繼續下一個 dataset |
| 1 | 環境／參數錯誤 | 不重試，停止 |
| 2 | 連續 3 檔網路/5xx（`TRANSIENT_ABORT_AFTER`）| 60s→900s 指數退避，**無上限** |
| 3 | 402 額度用盡 | 等 3600s，最多 4 次，彈錯誤通知 |
| 4 | 403 ip banned | 等 1860s（官方 30 分 + 1 分），最多 3 次 |
| 5 | 4xx 連續 3 次熔斷 | **不重試**（官方要求人工確認參數）|
| 6 | 抓完但有失敗檔 | 等 120s，最多 2 次，用盡記為不完整 |

兩邊的 `EXIT_*` 與 `RETRY_POLICY` 必須一致，`tests/test_run_all.py` 有測試擋這條契約。

### ⭐ `ALL_DONE.txt` 是上傳雲端的閘門

**只有 7 個 dataset 全部回 0 才寫 `logs/ALL_DONE.txt`**，有任何未完成改寫
`logs/PARTIAL-<stamp>.txt` 並彈錯誤通知。

2026-10-06 之前的版本 `402/403/熔斷` 全部 `exit 0` → `run_all` 誤當成功 → 資料根本沒抓完
卻寫了 `ALL_DONE.txt`，直接戳破「抓完才上傳」的規則。改動這條時務必跑 `tests/test_run_all.py`。

### 安全機制（不可移除）

- 4xx 連續 3 次 → **熔斷停止**
- `403 ip banned` → 立即停止
- `402` 額度用盡 → 立即停止（**此檔不記 error**，下次從頭抓）
- 連續 3 檔網路/5xx → 判定斷線中止，避免斷網時把幾千檔污染成失敗狀態

### 靜默錯誤陷阱（寫錯不會報錯）

1. 損益表 `EquityAttributableToOwnersOfParent` 是「**淨利**歸屬母公司」，**不是權益**
2. `NetIncome` 只有 20 期（止於 2019），**用 `IncomeAfterTaxes`**（46 期）
3. `_per` 後綴是「占總資產百分比」，**整組忽略**
4. `TaiwanStockInfo` 是**變更事件流**，需取 `date` 最新一列（`latest_by_stock`）
5. `origin_name` 中文名大量重複，**必須用英文 key 硬編碼對應**
6. 普通股判斷**不能只看 4 碼數字**，要結合 `industry_category` ＋ 字母後綴
7. 進度分母**只能用 `universe.json`**，不要從本地 parquet 重推（會含下市股）

### 三種錯誤性質要分清

| 回應 | 性質 |
|---|---|
| `422` enum 錯誤 | 名稱不存在（含大小寫）|
| `400 "Your level is free"` | 需登入或付費 |
| `400 "parameter data_id don't provide"` | 用法錯誤 |
| `200` + `rows: 0` | 期間無資料（**不是錯誤**）|

### Token 不是必需的

免 token 即可取用多數 dataset；`.env` 已建但非抓取必要。

### ⚠️ 抓取途中 log 會「停住」是正常的（但原因要分清）

`logs/run_all-*.log` 只在**每 25 檔**與**每個 dataset 開頭／結尾**寫入。
單一 dataset 跑 4 小時、期間 log 一行都不動是正常的，看實際進度要用：

- **儀表板** <http://127.0.0.1:8765/>（讀 DB，即時準）
- 或 `uv run python fetch.py --status`

**但要分辨兩種情況**：
- log 時間戳停在「該 dataset 的開頭」→ 正常，只是還沒到下一個 25 檔
- log 時間戳停在「很久以前」且 parquet 仍在新增 → **log 寫入管道壞了**，
  資料照跑不誤，但失去可觀測性。2026-10-07 就發生過一次
  （原因：`continue` 跳過進度 log，已於 `553330b` 修復）

判斷手法：比對 `data/sync_state.db` 的修改時間與 `logs/*.log` 的修改時間。
DB 在更新但 log 沒動 → 管道問題，不是沒在抓。

### 看中文 log 會以為亂碼，其實不是

`run_all.py` 已設 `PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`，log **位元組層級已驗證乾淨**
（`續傳` = E7BA8C E582B3，0 個問號）。若在 PowerShell 看到問號，那是**顯示層**編碼問題。
看中文 log 用 `Get-Content -Encoding UTF8` 或直接開儀表板。

### PowerShell 5.1 不支援 `Start-Process -Environment`

參數驗證會報錯、行程沒啟動。改在父層先設 `$env:PYTHONIOENCODING="utf-8"`，
或由腳本內部 `os.environ.setdefault` 設定（子行程會繼承）。

## 🕐 最後更新

- 時間：2026-10-06（收工，第四次／最終）
- 更新者：OpenCode @ **DESKTOP-5241OJK**
- HEAD：見 `git log -1`
- Git push：✅ 已推，local == origin/master（behind/ahead = 0/0）
- Chezmoi push：—（無變動，`chezmoi status` 與 `chezmoi git -- status` 皆乾淨）
- 目標驗證：✅ 69 個單元測試通過（`uv run python -m unittest discover tests` → `Ran 69 tests / OK`）
- 目標驗證：✅ ruff clean（`uv run ruff check src fetch.py monitor.py run_all.py tests`）
- 目標驗證：✅ 續傳正確（新 log 顯示「續傳：略過 1547 檔已完成」）
- 目標驗證：✅ 進度持續增加且 error=0（1563 → 1722/2037，84.5%）
- 目標驗證：✅ `ALL_DONE.txt` 不存在（閘門未被誤觸）
- 目標驗證：✅ 背景行程 6 個 PID 全在（run_all / fetch / monitor 各 2 個）
- 目標驗證：✅ `E:\OpenCode` 下只剩一個專案目錄（誤建的 `股票籌選` 已由使用者刪除）
- 目標驗證：✅ Obsidian 日期筆記 282 行 + `歷史日誌.md` 976 行，三段收工內容逐行比對無遺失
