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
- [x] `fetch.py`（主程式）
- [x] `tests/test_fetch.py`（35 個測試）
- [ ] **全量抓取**（家裡電腦執行中）

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
├── CONTEXT.md                  ← 領域詞彙表
├── README.md                   ← 抓取操作說明
├── pyproject.toml / .python-version / uv.lock
│
├── fetch.py                    ← 抓取主程式（CLI 入口）
├── src/
│   ├── core/finmind_client.py   ← API client
│   └── storage/                 ← sync_state / writer
├── tests/test_fetch.py
│
├── data/                        ← git 忽略
│   ├── sync_state.db
│   └── raw/<dataset>/<stock_id>.parquet
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
| `CONTEXT.md` | 「詞是什麼意思」 | 低 |
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

# 驗證
uv run python -m unittest discover tests -v   # 35 個測試
uv run ruff check src fetch.py tests           # lint
uv run ruff check --fix src fetch.py tests     # 自動修
```

---

## 六、VENV 路徑登記

| # | 路徑 | 機器 | 說明 |
|---|---|---|---|
| 1 | `repo 根目錄/.venv` | LAP2021-T153 | 本機 VENV，由 `uv sync` 建立 |

⚠️ 換電腦時用 `uv sync` 重建，不要複製此路徑。

---

## 七、兩台電腦的額度限制

⚠️ **FinMind 免費額度是帳號層級的 600 次/小時，兩台電腦不能同時抓。**

| 機器 | 預定任務 |
|---|---|
| LAP2021-T153（本機） | 小量測試（`--limit`）＋階段 2 計算 |
| 家裡那台 | 全量抓取（分天） |

程式內建安全機制（**不可移除**）：

- 4xx 連續 3 次 → **熔斷停止**（官方：累積 4xx 會封鎖 IP 30 分鐘）
- `403 ip banned` → 立即停止
- `402` 額度用盡 → 立即停止
- 5xx／網路錯誤 → 才重試（最多 3 次）

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
uv run python -m unittest discover tests   # 應 35 passed
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
| 詞彙表 | `CONTEXT.md` |
| 未解問題分析 | `docs/specs/open-questions.html` |
| 抓取說明 | `README.md` |
| Obsidian | `OpenCode專區/StockScreener/<日期>.md` |

講義來源：NotebookLM「財經」筆記本（16 個來源）。