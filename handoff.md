# handoff.md — Stock Screener

## ⏯️ 目前做到哪

設計階段。**仍未寫任何程式碼**，但 10-06 已完成資料來源實測與架構衝突釐清。

- canonical spec：`docs/superpowers/specs/2026-10-01-finmind-data-pipeline-design.md`（13 節，**部分內容已被推翻，見下**）
- 決策紀錄：`docs/superpowers/specs/2026-10-05-decision-log.md`（499 行，**實際主文件**）
- **資料來源實測**：`docs/review/data-source-verification.md`（8 項測試，含實際 API 回應）
- **架構衝突比對**：`docs/review/conflict-review.html`（瀏覽器開啟）

已確認的決策（細節與依據在 decision-log）：

| 項目 | 決策 |
|---|---|
| 定位 | **研究輔助系統**（非全自動篩選器，10-05 推翻原定位）|
| 資料來源 | FinMind REST API（免 token 即可用）＋ TWSE/TPEx 官方 open data |
| 技術棧 | Python + DuckDB + Streamlit，依賴用 `uv` |
| 順序 | 門檻先決（D3）→ Phase 0 驗證 → Phase 1 取分布 → 架構 → 骨架 |
| Token 落地 | 明文 `.env` + `.gitignore`（**2026-10-06 已建立 .gitignore**）|
| 財務報表 | **已轉單季值**，TTM = 最近 4 季相加，不需相減 |
| 日線 | TPEx + TWSE 全市場單日端點，10 年約 5,000 requests（0.5 天）|
| 估值層 | 安全邊際（5 年願景）與追價安全圈（2 年實際）**兩者並存** |

## 🚦 目前狀態

- 可運行：**否**，專案還沒有可執行的程式
- 介面：未開始
- 資料：尚未下載任何資料（實測僅取少量樣本驗證 schema）
- Git：`master` 分支，已推 `origin/master`（GitHub 私有）
- Obsidian：`OpenCode專區/StockScreener/2026-10-06.md`

## ➡️ 下一步

1. **驗證月營收 `t187ap05_L` 歷史深度** —— 決定營收 CAGR 能算幾年
2. **實測免費額度** —— 600 requests/小時的實際限制，影響全量同步排程
3. 定案衝突 1 的甲乙丙（模式如何分派），以及安全邊際門檻值
4. 之後才建專案骨架與抓取層

## ⚠️ 注意事項

### ✅ 已還原股價：已找到免費官方解法（原先的「無解」結論是錯的）

**因子公式**：`factor = reference_price / before_price`

**資料源**（兩者皆免 token）：
- `TaiwanStockPrice` —— 未還原 OHLC
- `TaiwanStockDividendResult` —— **官方 `reference_price` + `before_price`**

原先判斷無解是因為**測錯 dataset 名稱**（測了 `TaiwanStockCapitalReductionReferencePrice`，
那個才是不存在的）。完整驗證見 `docs/review/data-source-verification.md` §測試 16–19。

⚠️ **不要用 Google 搜到的公式** `(前收 − 現金股利) / 前收`：
只對純現金股利有效，遇股票股利會錯（2317 2016 差 7.59 元），
且換算配股率需要股面額，免費資料不含。

⚠️ 股價資料起於 2015-01-05，該日之前的事件無法還原（2 年／5 年區間不受影響）。

### 三個靜默錯誤陷阱（已記入實測記錄）

1. 損益表 `EquityAttributableToOwnersOfParent` 是「**淨利**歸屬母公司」，**不是權益**
2. `origin_name` 中文名幾乎相同的一堆欄位（`NetIncome` vs `IncomeAfterTaxes`、
   `CapitalStock` vs `CapitalStock_per`）→ **必須用英文 key 硬編碼對應**
3. 「端點回 200」不代表「參數有效」（TPEx 日期參數永遠回當日）

### 資產／權益不在損益 dataset 內

`TaiwanStockFinancialStatements` 的 `TotalAssets`／`TotalEquity`／`Liabilities` 皆 **0 筆**，
必須另抓 `TaiwanStockBalanceSheet`。

### spec §4.3 的 token pre-flight 端點失效

`api.finmindtrade.com/api/v4/user_info` 實測 **404**，
spec 記載的 `api.web.finmindtrade.com/v2/user_info` 需重測。
這代表「同步前檢查 token」的保護機制目前不可靠。

### MOPS 直連不可用

封鎖頁「因為安全性考量」，GET／POST 加 cookie 均無效。
FinMind 提供的即 MOPS 相同資料，走 FinMind 即可。

### opendata 代號不可憑字面推論

`openapi.twse.com.tw/v1/opendata/t187ap05_L` 名稱像除權息，**實際是月營收**
（含當月／去年同月營收＋產業別）。已列入維度 2 的可用來源。

### 方法教訓

- **一次一個測試並記錄**，不要把多檔塞一個 script，失敗時無法定位
- Windows 主控台無法正確顯示 UTF-8 中文，腳本改用「寫檔＋讀檔」輸出
- `TaiwanStockInfo` 是**變更事件流**不是主檔（4,329 列／300+ 個 date），需 upsert

### 已收回的錯誤建議

- 先前建議「併發 5～10」是錯的。瓶頸是帳度額度（0.167/秒），併發只會瞬間燒光當小時額度後吃 402
- 「安全邊際公式概念有誤」這句我講錯了已收回：公式本身是預期報酬率計算，邏輯通。
  真正的問題是**同一個 100% 在 5 年與 2 年模式年化意義不同**（約 14.9% vs 41.4%），
  兩個數字不能放同一把尺讀

## ⚠️ 本機 Chezmoi 待處理

`chezmoi status` 已於 2026-10-06 確認乾淨，無待處理變動。

## 🕐 最後更新

- 時間：2026-10-06
- 更新者：OpenCode @ LAP2021-T153
- Git push：見「Git push」補記（commit `0447415`）
- Chezmoi push：✅ 無待推變動（`chezmoi status` 乾淨）