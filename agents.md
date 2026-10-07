# agents.md — Stock Screener 專案藍圖

> 給下一個 session 的任何 Agent、任何電腦。
> **當前進度**看 `handoff.md`（會頻繁更新）；本檔是**穩定的路線圖**（少改）。

---

## 一、專案一句話

台股**研究輔助系統**：系統負責量化初篩與計算，人工負責五維評分與取捨。
**不是全自動篩選器，不產出投資建議。**

---

## 二、階段路線圖

### ✅ 階段 0：專案骨架

- [x] `pyproject.toml`（pandas / pyarrow / requests ＋ ruff）
- [x] `.python-version` 釘 3.12
- [x] `uv.lock` 鎖定版本（**必須進版控**，供兩台電腦一致）
- [x] `.gitignore`
- [x] `README.md`（抓取操作說明）

### ✅ 階段 1：抓取層

- [x] `src/core/finmind_client.py`（classify／CircuitBreaker／RateLimiter）
- [x] `src/storage/sync_state.py`（SQLite 續傳，每檔 commit）
- [x] `src/storage/writer.py`（Parquet 一檔一檔寫，空結果不寫檔）
- [x] `fetch.py`（主程式，回傳 `EXIT_*` 退出碼）
- [x] `run_all.py`（依退出碼自動等待重試＋Windows 通知＋`ALL_DONE` 閘門）
- [x] `monitor.py`（進度儀表板，只讀 DB，:8765）
- [x] `tests/test_fetch.py` ＋ `tests/test_run_all.py`（69 個測試）
- [ ] **全量抓取**（DESKTOP-5241OJK 執行中，2026-10-06 22:04 重啟後續傳）

### ⬜ 階段 2：財務指標計算

- [ ] ROE 多年平均（3 年／5 年）— **篩選用這個**
- [ ] TTM ROE — 僅參考顯示，不參與篩選
- [ ] 杜邦五項 — 參考面板，不決定維度 4 分數
- [ ] TTM EPS（最近 4 季相加）
- [ ] 營收 CAGR（用 `revenue_year`+`revenue_month`，**不是 `date`**）
- [ ] **實算篩選剩幾檔**（原未解問題 #2，需指標算出來才能驗證）

### ⬜ 階段 3：篩選 ＋ 評分 ＋ 估值

- [ ] `screening/` 篩選條件（ROE 門檻由使用者設定，其他三個講義值）
- [ ] `scoring/` 五維評分 → 總分 → Tier → 目標 PER
- [ ] `valuation/` 安全邊際（5 年）＋ 追價安全圈（2 年）＋ PE 提示

### ⬜ 階段 4：Streamlit 介面

- [ ] 篩選頁（設定條件 → 初篩 → 清單與命中理由）
- [ ] 評分頁（含**略過篩選**入口）
- [ ] 估值頁（含兩套估值並列的誤讀警示）

### ⬜ 階段 5（尚未進入規格書）

- [ ] `transform/` 型別正規化與陷阱修正
- [ ] DuckDB 查詢層
- [ ] `config/` 三個設定檔

---

## 三、資料夾結構

```
.
├── agents.md                   ← 本檔（路線圖，少改）
├── handoff.md                  ← 當前進度（頻繁更新）
├── GLOSSARY.md                 ← 領域詞彙表
├── README.md                   ← 抓取操作說明
├── pyproject.toml / .python-version / uv.lock / pyrightconfig.json
│
├── fetch.py                    ← 抓取主程式（CLI 入口，回傳 EXIT_*）
├── run_all.py                  ← 依序跑完 7 個 dataset，自動等待重試
├── monitor.py                  ← 進度儀表板（http://127.0.0.1:8765/）
├── src/
│   ├── core/finmind_client.py   ← API client
│   └── storage/                 ← sync_state / writer
├── tests/test_fetch.py          ← 45 個測試
├── tests/test_run_all.py        ← 重試策略／退出碼契約（24 個）
│
├── data/                        ← git 忽略，永不同步（雙機規則）
│   ├── sync_state.db
│   └── raw/<dataset>/<stock_id>.parquet
│
├── logs/                        ← git 忽略
│   ├── ALL_DONE.txt             ← ⭐ 全部完成的證據，上傳雲端的閘門
│   ├── PARTIAL-<stamp>.txt      ← 有 dataset 未完成時改寫這個
│   └── run_all-<stamp>.log      ← utf-8
│
└── docs/
    ├── superpowers/specs/
    │   ├── 2026-10-06-stock-screener-spec.md   ← 現行規格書（實作依據）
    │   ├── 2026-10-05-decision-log.md         ← 決策紀錄（理由）
    │   └── 2026-10-01-...design.md            ← 已 superseded
    ├── review/data-source-verification.md     ← 26 項實測
    └── specs/*.html                            ← HTML 呈現用
```

---

## 四、文件分工（不要搞混）

| 文件 | 回答什麼 | 變動頻率 |
|---|---|---|
| `GLOSSARY.md` | 「詞是什麼意思」 | 低 |
| `docs/superpowers/specs/2026-10-06-stock-screener-spec.md` | 「系統長怎樣」→ **實作依據** | 中 |
| `docs/superpowers/specs/2026-10-05-decision-log.md` | 「為什麼這樣決定」 | 低 |
| `docs/review/data-source-verification.md` | 「實測結果」 | 中 |
| `handoff.md` | 「現在做到哪」 | **高** |

---

## 五、常用指令

```bash
# 環境
uv sync                                    # 安裝（首次或換電腦）
uv venv --clear                            # 重置環境（不要用 Remove-Item 刪 .venv）

# 抓取
uv run python fetch.py --status                            # 看進度
uv run python fetch.py --global-only                      # 全域型，約 5 秒
uv run python fetch.py --dataset <名稱>                    # 逐檔抓
uv run python fetch.py --dataset <名稱> --max-seconds 3600  # 限時
uv run python fetch.py --retry-errors                      # 只重試失敗

# 掛機（背景、無視窗）
.venv\Scripts\python.exe run_all.py               # 依序 7 個 dataset，斷線自癒
.venv\Scripts\python.exe monitor.py --no-browser   # 進度 UI :8765

# 驗證
uv run python -m unittest discover tests -v   # 69 個測試
uv run ruff check src fetch.py monitor.py run_all.py tests   # lint
uv run ruff check --fix src fetch.py monitor.py run_all.py tests  # 自動修
```

---

## 六、VENV 路徑登記

| # | 路徑 | 機器 | 說明 |
|---|---|---|---|
| 1 | `repo 根目錄/.venv` | DESKTOP-5241OJK | 本機 VENV，由 `uv sync` 建立（2026-10-06 專案搬到此機時重建）|

⚠️ 換電腦時用 `uv sync` 重建，不要複製此路徑。

---

## 七、兩台電腦的額度限制

⚠️ **FinMind 免費額度是帳號層級的 600 次/小時，兩台電腦不能同時抓。**

| 機器 | 預定任務 |
|---|---|
| **DESKTOP-5241OJK** | **全量抓取跑到完**（唯一執行抓取的機器）|
| LAP2021-T153 | 只做程式開發，**不抓取**（額度會共用）|

### 資料搬運規則（2026-10-06 定案）

- `data/`（parquet ＋ `sync_state.db`）**永不同步**，不放雲端，兩台各自獨立
- 程式碼走 git 唯一同步通道
- 抓取只在 DESKTOP-5241OJK 跑，`logs/ALL_DONE.txt` 出現才算完
- 抓完才上傳，上傳前**必先問使用者**；搬法＝一次性 zip 快照解到該機本機路徑
- 資料正本在 DESKTOP-5241OJK

### 安全機制（`EXIT_*` 兩層分工，**不可移除**）

`fetch.py` 決定「什麼時候該停」並回報退出碼，`run_all.py` 決定「等多久再重試」。

| 退出碼 | fetch.py 觸發 | run_all.py 策略 |
|---|---|---|
| 0 | 抓完 | 繼續下一個 dataset |
| 1 | 環境／參數錯誤 | 不重試，停止 |
| 2 | 連續 3 檔網路/5xx（`TRANSIENT_ABORT_AFTER`）| 60s→900s 指數退避，**無上限** |
| 3 | 402 額度用盡 | 等 3600s，最多 4 次，彈通知 |
| 4 | 403 ip banned | 等 1860s（官方 30 分 + 1 分），最多 3 次 |
| 5 | 4xx 連續 3 次熔斷 | **不重試**（官方要求人工確認參數）|
| 6 | 抓完但有失敗檔 | 等 120s，最多 2 次，用盡記為不完整 |

⭐ **`ALL_DONE.txt` 只在 7 個 dataset 全部回 0 才寫**，有任何未完成改寫
`logs/PARTIAL-<stamp>.txt`。這是「抓完才上傳」的閘門，2026-10-06 之前曾因
402/403/熔斷都 `exit 0` 而誤寫，改動時務必跑 `tests/test_run_all.py`。

---

## 八、動手前必讀的三個陷阱

這三個寫錯**不會報錯**，會靜默產生錯的數字：

1. **ROE 分子用 `IncomeAfterTaxes`，不要用 `NetIncome`**
   後者只有 20 期（止於 2019），前者 46 期完整。

2. **不要用 `origin_name` 匹配欄位**
   中文名大量重複（`NetIncome` vs `IncomeAfterTaxes` 幾乎同名）。
   **必須用英文 key 硬編碼對應。**

3. **`_per` 後綴是「占總資產百分比」分析表，整組忽略**
   損益表的 `EquityAttributableToOwnersOfParent` 是「**淨利**歸屬母公司」，
   **不是權益**。

其他見 `docs/review/data-source-verification.md` 的「靜默錯誤陷阱」章節。

---

## 九、判定 dataset 可用性的標準流程

⚠️ **官方文件本身有 5 個錯誤**（含 casing 錯誤），不可只靠文件。

```
1. 送不存在的名稱 → 從 422 body 取得 API enum（合法名單）
2. 用正確名稱呼叫 → 依回應判斷性質
3. 與文件比對 → 找出文件錯誤
```

| 回應 | 性質 |
|---|---|
| `422` enum 錯誤 | 名稱不存在（含大小寫）|
| `400 "Your level is free"` | 需登入或付費 |
| `400 "parameter data_id don't provide"` | 用法錯誤 |
| `200` + `rows: 0` | 期間無資料（**不是錯誤**）|

⚠️ **同一個 dataset 帶不帶 `data_id` 會得到完全不同的錯誤**。
實測 12 個 dataset 帶 `data_id` 免費層全可用，不帶則需付費方案。

---

## 十、開工前檢查

```bash
git status -sb              # 應乾淨
git fetch origin            # 不 pull，只看差異
uv run python -m unittest discover tests   # 應 69 passed
uv run ruff check src fetch.py monitor.py run_all.py tests   # 應 clean
```

進度看 `handoff.md`。若測試不通，先查 `.venv`
（用 `uv venv --clear` 重置，不要手動刪）。

---

## 十一、相關文件

| 文件 | 位置（皆相對 repo 根目錄）|
|---|---|
| 規格書（現行） | `docs/superpowers/specs/2026-10-06-stock-screener-spec.md` |
| 決策紀錄 | `docs/superpowers/specs/2026-10-05-decision-log.md` |
| 資料來源實測 | `docs/review/data-source-verification.md` |
| 詞彙表 | `GLOSSARY.md` |
| 未解問題分析 | `docs/specs/open-questions.html` |
| 抓取說明 | `README.md` |
| Obsidian | `OpenCode專區/StockScreener/<日期>.md` |

講義來源：NotebookLM「財經」筆記本（16 個來源）。