# handoff.md — Stock Screener

## ⏯️ 目前做到哪

設計階段。**仍未寫任何程式碼**，但 10-06 已完成資料來源實測與架構衝突釐清。

- canonical spec：`docs/superpowers/specs/2026-10-01-finmind-data-pipeline-design.md`（13 節，**部分內容已被推翻，見下**）
- 決策紀錄：`docs/superpowers/specs/2026-10-05-decision-log.md`（499 行，**實際主文件**）
- **資料來源實測**：`docs/review/data-source-verification.md`（21 項測試，含實際 API 回應）
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
| 日線 | **FinMind `TaiwanStockPrice`**（11.7 年免費，取代 TPEx/TWSE）|
| 估值層 | 安全邊際（5 年願景）與追價安全圈（2 年實際）**兩者並存** |
| 已還原股價 | **`TaiwanStockDividendResult`** 官方 `reference_price / before_price`（免費）|
| **營收 CAGR** | **FinMind 季度財報 `Revenue` type**（12 年，加總為年度後計算）|
| **衝突 1** | ✅ **方案 A**：兩套估值獨立計算並存；安全邊際門檻可設定、預設 50%、不設死硬門檻 |
| **衝突 2** | ✅ **ROE 門檻由使用者在一開始設定**，帶入篩選系統；其他三門檻**維持講義值**（業外獲利比 [0.8,1.2]／財務槓桿 <3.0／align_score <8.0），欄位可覆寫 |
| **Tier 對應表** | ✅ 講義原文補入：S 85~100→35~40倍／A 70~84→25~30／B 55~69→15~20／C 40~54→10~15／D <40→5~10 |
| **產品契約** | ✅ 使用者設條件 → 系統初篩 → **使用者人工五維評分**（不可砍）|
| **篩選誤殺** | ✅ 開「略過篩選」入口，硬門檻不是絕對門 |
| **ROE 算法** | ✅ 篩選用**多年平均**（推翻 D9 的 TTM）；TTM 另留作參考顯示 |
| **本益比** | ✅ **只做提示不設門檻**，用「當前 PE ÷ Tier 目標 PER」比值 |
| **維度 4** | ✅ 維持人工評分，杜邦五項僅作**參考面板**（推翻原「杜邦預填維度 4」）|
| **維度 2** | ✅ 手動輸入產業 CAGR ＋ 系統換算建議分數，對照表可編輯 |
| **否決過濾** | ✅ 兩個機制（產業結構／企業體質惡化）**v1 不做，只記錄** |
| **安全圈 EPS** | ✅ **全手動輸入**，系統不做自動預測（FinMind 實測無共識 EPS dataset）|
| **長期價值 CAGR** | ✅ **獨立設定**，不與維度 2 綁定（避免維度 2 影響被算兩次）|
| **目標 PER 來源** | ✅ **只由 Tier 決定**，CAGR 不當獨立上限（關閉原 §6 #12）|

## 🚦 目前狀態

- 可運行：**否**，專案還沒有可執行的程式
- 介面：未開始
- 資料：尚未下載任何資料（實測僅取少量樣本驗證 schema）
- Git：`master` 分支，已推 `origin/master`（GitHub 私有）
- Obsidian：`OpenCode專區/StockScreener/2026-10-06.md`
- **資料來源實測**：21 項測試完成，**資料面零阻塞**（測試 20-21 確認月營收端點不可用，但 FinMind 季度財報完全足夠）

## ➡️ 下一步

1. ~~**定案衝突 1 的甲乙丙（模式如何分派），以及安全邊際門檻值**~~ ✅ **已決定：方案 A（兩套獨立計算並存），安全邊際門檻可設定、預設 50%、不設死硬門檻**
2. ~~**ROE 門檻來源**~~ ✅ **已決定：由使用者在一開始設定，再帶入篩選系統**
3. ~~**定案其他三個門檻**~~ ✅ **已決定：維持講義值**（業外獲利比 [0.8,1.2]／財務槓桿 <3.0／align_score <8.0），欄位設計為可覆寫
4. ~~**grill 設計（8 題）**~~ ✅ 產品契約、五維評分不可砍、略過篩選入口、ROE 多年平均、PE 只提示、維度 2 CAGR 對照表、安全圈 EPS 全手動、長期價值 CAGR 獨立
5. ~~**§6 待決清單全數關閉**~~ ✅ 原 #12／#14／#15／#23／#24／#25 皆已定案
6. **建專案骨架**：`config/boards.yaml`、`config/thresholds.yaml`、`config/industry_cagr.csv`、抓取層 ← **目前位置**

## ✅ 已完成（10-06）

1. ~~**驗證月營收 `t187ap05_L` 歷史深度**~~ ✅ 測試 20-21：端點無歷史，但 FinMind 季度財報 `Revenue` type 涵蓋 12 年，完全足夠計算年度營收 CAGR
2. ~~**實測免費額度**~~ ✅ 測試 21：20 次連續請求無 rate limit，實際限制比預期寬鬆
3. ~~**定案衝突 1**~~ ✅ 方案 A（兩套獨立計算並存）＋ 安全邊際門檻預設 50%
4. ~~**定案衝突 2**~~ ✅ ROE 門檻由使用者設定；其他三門檻維持講義值

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

### spec §4.3 的 token pre-flight 端點已實測（2026-10-06，測試 21.3）

| 端點 | 結果 |
|---|---|
| `api.finmindtrade.com/api/v4/user_info` | **404**，不存在 |
| `api.web.finmindtrade.com/v2/user_info`（spec 記載的） | **200**，但回 `{"msg":"請輸入 token","status":400}` |

→ 兩個端點都**無法在無 token 下查詢額度**。「同步前檢查 token」的保護機制不可靠，
spec §4.3 的 pre-flight 步驟需改寫（實測見 `data-source-verification.md` 測試 21.3）。

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

- 時間：2026-10-06（第三次更新）
- 更新者：OpenCode @ LAP2021-T153
- HEAD：`2995af2`（同步 §4.10 狀態）
- Git 狀態：**工作區乾淨，已與 `origin/master` 同步**
- Chezmoi push：✅ 無待推變動（`chezmoi status` 乾淨）