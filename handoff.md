# handoff.md — StockScreener

## ⚡ 一句話摘要

**階段 1 完成（全量抓取進行中 DESKTOP-5241OJK）*

- **藍圖**：`agents.md`（路線圖、陷阱、常用指令）
- 程式碼：`fetch.py`（退出碼契約）、`run_all.py`（自動重試）、`monitor.py`（進度 UI）、`src/`
- 規格書：`docs/superpowers/specs/2026-10-06-stock-screener-spec.md`（現行實作依據）
- 詞彙表：`GLOSSARY.md`、決策紀錄 `docs/superpowers/specs/2026-10-05-decision-log.md`
- **資料來源實測**：`docs/review/data-source-verification.md`（6 項測試）
- Obsidian：`OpenCode專區/StockScreener/` 各日期筆記

已確認決策（細節見 decision-log）：

| 項目 | 決定 |
|---|---|
| 定位 | **研究輔助系統**（非自動篩選器）|
| 資料來源 | FinMind REST API + TWSE/TPEx 官方 open data |
| 技術棧 | Python 3.12 + DuckDB + Streamlit，套件管理用 `uv` |
| 資料模型 | **一檔一檔案**（ETL = 單檔 4 步驟、不跨檔）|
| ROE 分子 | **`IncomeAfterTaxes`**（46 期全覆蓋），不用 TTM、不用 `NetIncome`|
| 目標 PER | **只由 Tier 決定**，CAGR 不作為 PER 的獨立上限 |
| 安全邊際 | 可設定、預設 **50%**、**不設死硬門檻**（4 項理由見 spec）|
| 預測 EPS | **全手動輸入**（不做 CAGR 外推）|
| TTM ROE | 僅參考顯示，不參與篩選 |
| ETF | **保留在全部證券中**（ETF 沒有財報，財務指標計算時排除）|
| 興櫃（emerging）| v1 不啟用（官方無資料、無財報）|
| align_score | **無資料來源，v1 不實作** |
| 資料搬運 | 兩台獨立，完成後一次性 zip 快照，*不持續同步 data/* |

## 📍 目前狀態

- **全量抓取進行中**（2026-10-06 22:04 重啟後續傳），在 DESKTOP-5241OJK
  - 進度儀表板：TaiwanStockFinancialStatements **1722/2037（84.5%）*，Error=0
  - 6 個 per-stock dataset 仍在跑（只剩 Price 約 315 檔未抓 + 6 個錯誤待重試）
  - 進度儀表板網址 **<http://127.0.0.1:8765/>**，每 5 秒自動刷新或 `uv run python fetch.py --status`
  - 7 個 dataset 全部回 0 才寫 `logs/ALL_DONE.txt`，這才是完成的證據
  - 即時 log：`logs/run_all-20261006-2204.log` 或 `logs/runner.out.log`
- **Git**：`master` = `origin/master`，無未提交改動
- **Chezmoi**：無需要同步的變動

### 正在跑的程式（DESKTOP-5241OJK 本機環境才看得到 PID）

| 程式 | PID（env / 底層 python）|
|---|---|
| `run_all.py` | 9468 / 6728 |
| `fetch.py`（執行中）| 2132 / 12316 |
| `monitor.py --no-browser` | 5600 / 16944 |

⚠️ **不要跨機殺 PID**：env 裡的 `python.exe` 是假的，因為 spawn 會重新啟動
python 程序。真正 PID 請用工作管理員或本機 `netstat` 查看。

## 🗂️ 資料夾結構與兩台電腦差異

**專案名稱：`Stock Screener(股票篩選)`（2026-10-06 改名後）*

| 機器 | 路徑 | 角色 |
|---|---|---|
| **DESKTOP-5241OJK** | `E:\OpenCode\Stock Screener(股票篩選)` | **主力機：抓取中、Data 唯一正本** |
| 本機（LAP2021-T153）| 從雲端讀取 | 僅程式開發；data/ 不可寫入 |

`data/`（含 `sync_state.db` 與 parquet）*永不進版控*，兩台各自獨立
（`data/` 被雲端同步時會導致 db 與檔案分離）。VENV 也是 repo 根目錄。

### 兩台電腦差異注意事項

本機電腦應該用 `git` 同步程式碼，**不要複製 data/***！即使你想用雲端同步檔，也只能同步「程式碼（含 `.git`）+ 套件」，而 `data/` 要用**一次性 zip 快照**搬到另一台電腦。

### 抓取說明（本機無 data/ 時）

本機電腦應該做：`git pull` + `uv sync`（安裝套件）即可，但**無法看到抓取進度**，因為 `data/sync_state.db` 是兩台電腦各自獨立。

### 資料搬運（全量抓完後）

1. 先在 DESKTOP-5241OJK 看到 `logs/ALL_DONE.txt` 出現
2. **確認資料期間**：用 `uv run python monitor.py --no-browser` 看
3. 打包：在 DESKTOP-5241OJK 的 `data/` 整包壓縮成 zip，搬到**本機電腦的專案路徑**
   - 解壓縮前確認資料夾名稱、路徑正確，並手動執行 `python monitor.py` 驗證
4. 資料正本在 DESKTOP-5241OJK，後續若換機器請參考上述搬運流程

### ⚠️ 專案資料夾的命名注意

雲端資料夾名稱是 **`Stock Screener(股票篩選)`**，在 Google Drive 上顯示為「股票篩選」

2026-10-06 之前專案搬移過程曾發生編碼問題：原本的 `Stock Screener(股票篩選)`
（`篩` U+7C4C）在這台機器上變成 `Stock Screener(股票篩選)`，
後者字元不同，導致 `.git` 還在、但 `data/` 與 `.venv` 都*消失*（其實是路徑不同步）。
後來 2026-10-06 才手動修回正確路徑。**路徑名稱要特別注意**，
尤其是 Google Drive 同步時可能出現**亂碼或編碼問題**。

**git 路徑與雲端路徑可能不同**：當專案資料夾在雲端硬碟時，雲端路徑可能與本地路徑不同
（Google Drive 的 Filestream 會建立本地虛擬路徑）。所以 `git clone` / `git pull` 時要確認專案路徑
（用 `pwd` 看目前路徑，確認是否為正確的雲端路徑）。

⚠️ **本機電腦收工注意**：2026-10-06 之後，此專案路徑正確，但 `data/` 仍在 DESKTOP-5241OJK。
本機電腦的 `git status` 會顯示未追蹤檔案（`data/` 目錄不存在是正常的，因為 data/ 是不同步的）。
**不要嘗試在本機建立 data/ 目錄或抓取**，因為 FinMind 的 600 次/小時額度是帳號層級的，兩台不能同時抓。

## 📦 同步規則（2026-10-06 兩台確認後）

**程式碼走 git 唯一同步通道，資料走一次性快照*

| 項目 | 同步方式 | 注意 |
|---|---|---|
| 程式碼（`src/`、`fetch.py`、`run_all.py`、`monitor.py`、`tests/`）| **git** | 兩台都可修改，正常 commit + push |
| `data/`（parquet + `sync_state.db`）| **不走版控** | 只在 DESKTOP-5241OJK 抓取；資料搬運用一次性 zip |
| `.venv/` | `uv sync` 重建 | `uv.lock` 進 git，兩台版本自動一致 |
| `logs/` | 不走版控 | git 忽略，兩台各自獨立 |

**重要提醒*：`data/` 被雲端同步 = `sync_state.db` 與 `data/raw/` 分離的風險，
導致 SQLite 狀態與實際 parquet 檔案不一致。**不要嘗試同步 `data/` 目錄**！

**FinMind 額度限制（600 次/小時，兩台共用）**：只有 DESKTOP-5241OJK 能抓取。

### 新電腦接手流程

```bash
cd <專案路徑>              # 路徑要確認是正確的
git pull
uv sync                        # 安裝套件
uv run python -m unittest discover tests    # 確認 69 passed
```

**不要碰 `data/`**：新電腦應該先做：用 `git pull` + `uv sync` 即可，
但看不到完整進度（因為 `data/` 不在版控）。

### 資料搬運：兩台電腦之間

1. 先在 DESKTOP-5241OJK 看到 `logs/ALL_DONE.txt` 出現
2. **確認抓取完成後，先暫停**（避免同步中仍在抓取）*
3. 打包：在 DESKTOP-5241OJK 的 `data/` 整包壓縮成 zip 傳到本機電腦的**專案路徑**
   - 注意要確認資料夾名稱、路徑是否正確
4. 資料正本在 DESKTOP-5241OJK，後續若換機器請參考上述搬運流程

## 🎯 下一步

1. **等資料抓完*：`logs/ALL_DONE.txt` 出現才代表完成，不要提前做階段 2
   - 過程中若資料有問題，可以用 `data/` 驗證
2. **進入階段 2**：在確認資料無誤後，開始計算：
   - `uv run python monitor.py --no-browser` 持續看
   - `uv run python run_all.py`（若有錯誤重試）
3. **ROE 實作*：先確認 `agents.md` 階段 2 的需求
   - 分子用 `IncomeAfterTaxes`（不是 `NetIncome`，後者只有 20 期）
   - 分母 = 總權益（`Equity`），包含非控制權益
   - 營收 CAGR 用 `revenue_year`+`revenue_month`，**不是 `date`**
   - 還原股價：用 `DividendResult` + `ParValueChange` + `SplitPrice`

## ⚠️ 技術筆記

### 抓取層的關鍵設計

- `fetch.py` 決定「什麼時候該停」並回報退出碼，`run_all.py` 決定「等多久再重試」
- 寫入順序：`state.record` 在 `writer.write` 之後，確保寫入中斷不會有半套狀態
- 兩台電腦可以**各自獨立**抓取不同 dataset（各自的 sync_state 與 PID 不衝突）
- 不要跨機殺 PID（env 裡的 python.exe 是假的，因為 spawn 會重啟）

### FinMind 退出碼契約（fetch.py / run_all.py 共用）

`fetch.py` 回傳退出碼，`run_all.py` 依退出碼決定等待策略。

| 退出碼 | fetch.py 觸發 | run_all.py 策略 |
|---|---|---|
| 0 | 抓完 | 繼續下一個 dataset |
| 1 | 環境／參數錯誤 | 不重試，停止 |
| 2 | 連續 3 檔網路/5xx（`TRANSIENT_ABORT_AFTER`）| 60s→900s 指數退避，**無上限** |
| 3 | 402 額度用盡 | 等 3600s，最多 4 次，彈通知 |
| 4 | 403 ip banned | 等 1860s（官方 30 分 + 1 分），最多 3 次 |
| 5 | 4xx 連續 3 次熔斷 | **不重試**（官方要求人工確認參數）|
| 6 | 抓完但有失敗檔 | 等 120s，最多 2 次，用盡記為不完整 |

⚠️ `EXIT_*` 與 `RETRY_POLICY` 必須完全一致，改一邊要跑 `tests/test_run_all.py` 驗證。

### `ALL_DONE.txt` 只在全部 dataset 完成時寫入

**只有 7 個 dataset 全部回 0 才寫 `logs/ALL_DONE.txt`**，有任何未完成改寫
`logs/PARTIAL-<stamp>.txt`。這是「抓完才上傳」的閘門。

2026-10-06 之前曾因 `402/403/熔斷` 都 `exit 0` 導致 `run_all` 誤寫
`ALL_DONE.txt`，這是 2026-10-06 之後才修正的。**改動退出碼時務必跑 `tests/test_run_all.py`**。

### 抓取時的常見錯誤

- 4xx 連續 3 次 → **熔斷停止**
- `403 ip banned` → 立即停止
- `402` 額度用盡 → 立即停止，**不能當成功**，否則會被誤判為完成
- 連續 3 檔網路/5xx 失敗 → 視為斷線，立即中止而非全標 error

### 資料陷阱（寫錯不會報錯）

1. `EquityAttributableToOwnersOfParent`（損益表）是「**淨利**歸屬母公司」**不是權益**
2. `NetIncome` 只有 20 期（止於 2019），**請用 `IncomeAfterTaxes`**，46 期完整
3. `_per` 後綴 = 占總資產百分比分析表 → **整組忽略**
4. `TaiwanStockInfo` 是*變更事件流**（非主檔），需用 `date` 分組取 `latest_by_stock`
5. `origin_name` 不可靠，大量欄位中文名重複，**必須用英文 key 硬編碼對應**
6. 檔案命名注意：**資料夾名稱必須一致**，否則 `industry_category` 等欄位會消失
7. 進度計算：**用 `universe.json`**，不要用 parquet 檔案數推算（因為會包含已下市股）

### 判斷 dataset 可用性的標準流程

| 回應 | 意義 |
|---|---|
| `422` enum 錯誤 | dataset 名稱不存在，需確認 |
| `400 "Your level is free"` | 需登入或付費方案 |
| `400 "parameter data_id don't provide"` | 用法錯誤 |
| `200` + `rows: 0` | 期間無資料（**不是錯誤**）|

### Token 與資料搬運

免費 token 可用所有 dataset，但 `.env` 內有 token 才需要搬運（兩台電腦各自設定）。

### ⚠️ 抓取中的 log 讀取要注意

`logs/run_all-*.log` 在寫入時是 **utf-8 編碼**，但 log 是**逐行**寫入（每次寫一個 dataset 的 log）。
若 dataset 尚未完成，log 會持續追加，但**不保證每次寫入都即時刷新到硬碟**。

- **即時進度**：用 monitor.py（<http://127.0.0.1:8765/>），每 5 秒從 DB 讀取
- 或執行 `uv run python fetch.py --status`

**已知問題與解法*：
- log 尚未寫入完成時，可能無法看到最新 dataset 的 log → 這是正常的
- log 寫入完成時，可能因 continue 跳過進度輸出，導致 log 內容**沒有進度**
  這是 2026-10-07 修改的 bug，已在 `553330b` 修正
  但 `continue` 會跳過進度 log，導致無法看到完整進度。

另外要注意：`data/sync_state.db` 寫入時是**逐行寫入**，而 `logs/*.log` 寫入時是**逐行寫入**。
DB 內容可能比 log 更即時，但內容可能不一致（例如 log 還沒寫入完成）。
所以**不要假設 log 與 DB 完全同步**，要以 DB 為主。

建議：兩台電腦都要確認 `data/sync_state.db` 與 `logs/*.log` 內容一致，
避免發生同步問題（2026-10-07 修改 show_status 與 monitor 不一致後，
`fetch.py` 的 `show_status` 改為用 `ok+empty+skipped` 計算完成度，
與 `monitor.py` 一致）。
`empty` 是終態（該檔確實無資料），必須算入完成度，否則永遠到不了 100%。
**務必確認 `done_ids()` 定義一致**：包含 ok+empty+skipped 三種狀態。
這樣才能確保進度顯示正確，且所有程式碼都用同一個完成定義。

### log 檔案的寫入順序與格式要注意

`run_all.py` 強制設定 `PYTHONIOENCODING=utf-8` 和 `PYTHONUTF8=1`，**log 是 UTF-8 編碼**。
但 Windows 預設 cmd 用 cp950，所以 log **不能直接用 PowerShell 的 `Get-Content` 開啟**
（會顯示「正在寫入」但內容是亂碼）。必須用 `Get-Content -Encoding UTF8` 或文字編輯器開啟。

### PowerShell 5.1 的奇怪問題：`Start-Process -Environment`

某些場景（如本專案的抓取腳本）需要環境變數，但 PowerShell 5.1 的 `Start-Process` 支援 `-Environment` 參數
但實際效果與直接設定 `$env:PYTHONIOENCODING="utf-8"` 不同。
這是 PowerShell 5.1 的已知問題。建議在 `os.environ.setdefault` 內設定 UTF-8。

## 🕐 最後更新

- 日期：2026-10-29
- 更新者：OpenCode @ **LAP2021-T153**
- HEAD：`3730584`
- Git push：✅ 已推（local == origin/master，behind/ahead = 0/0）
- Chezmoi push：—（無變動，`chezmoi status` 與 `chezmoi git -- status` 均乾淨）
- 驗證：✅ 69 個測試全過（`uv run python -m unittest discover tests` → `Ran 69 tests / OK`）
- 驗證：✅ ruff clean（`uv run ruff check src fetch.py monitor.py run_all.py tests`）
- 驗證：✅ 規格書更新（本次修改 §1.4、§2、§2.1、§3.2、§9.2、§11 共 8 處）
- 驗證：✅ 本機無 data/ 目錄（正常，資料在 DESKTOP-5241OJK）
- 驗證：✅ 本機無抓取程式執行中（正常，抓取只在 DESKTOP-5241OJK 執行）
- 驗證：✅ `E:\OpenCode` 路徑正常，無編碼問題（`篩選` 兩字正確）
- 驗證：✅ Obsidian 筆記夾正常（282 字 + `歷史日誌.md` 976 字）
