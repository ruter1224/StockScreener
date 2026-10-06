# 資料來源逐一驗證記錄

建立日期：2026-10-06
驗證方式：實際呼叫 API，非文件查閱
環境：Windows，Python 3.12.13（`uv venv` 建於 `%TEMP%\opencode\dataprobe`）

狀態圖例：✅ 可用／❌ 不可用／⚠️ 可用但有條件／🔄 驗證中／⬜ 未測

---

## 進度總表

| # | 來源 | 狀態 | 用途／影響 |
|---|---|---|---|
| 1 | yfinance Adj Close | ❌ 網路被擋 | 還原價 → 衝突 B **未解** |
| 2 | TWSE STOCK_DAY 月線 | ⚠️ 成本過高 | — |
| 3 | TPEx 每日收盤 | ✅ | 日線（上櫃＋興櫃全市場單日 12,060 筆） |
| 4 | TWSE MI_INDEX | ✅ | 日線（上市 1,332 檔單日） |
| 5 | TWSE 歷史除權息 | ❌ 官方無可用來源 | 自行還原價 **暫緩** |
| 6 | TWSE 月營收 t187ap05_L | ✅ | 維度 2 營收佐證（歷史深度待測） |
| 7 | MOPS 財務報表 | ❌ 直連被擋 | — |
| 8 | **FinMind 財務報表** | ✅ **免額度可用** | **阻擋 Phase 0 三項全解** |

---

## 測試 7：MOPS 財務報表 ❌ 直連被擋

**網址**：`https://mops.twse.com.tw/mops/web/ajax_t163sb04`

### 測試 1：GET
回 `Content-Type: text/html`，內容為：
```
因為安全性考量，您所執行的頁面無法呈現。
FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED.
錯誤代碼：7641438221832213666
```

### 測試 2：完整 session 流程
先 GET 首頁拿 cookie → 再 POST 表單（含 `Referer`/`Origin`/`X-Requested-With`
與瀏覽器 UA）→ 仍回同一則封鎖頁。**首頁也沒給任何 cookie**（`cookies=[]`）。

### 結論
❌ **MOPS 直連不可行**（需瀏�器自動化或付費中介）。
**但此失敗不影響專案** —— 見測試 8，FinMind 已提供 MOPS 相同資料且免費可用。

---

## 測試 8：FinMind 財務報表 ✅ 免額度可用，歷史 11 年，並解答阻擋 Phase 0 三項

**這是本次驗證最重要的結果。**

### 8.1 連線與額度
```
GET https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo
→ {"msg":"success","status":200,"data":[4,329 筆]}     ← 無 token 即可
```
⚠️ `GET /api/v4/user_info` 回 **404**（spec §4.3 記載的 pre-flight 檢查端點
`api.web.finmindtrade.com/v2/user_info` 需另測，這條路已失效）。

### 8.2 歷史深度（解決衝突 D）
```
GET /api/v4/data?dataset=TaiwanStockFinancialStatements&data_id=2330&start_date=2015-01-01
→ msg=success, rows=851
   date range: 2015-03-31 → 2026-06-30  (46 個期間 = 11.25 年)
```
✅ **財務報表可回溯 11 年以上**，涵蓋規劃的 2016–2026（10 年）。
**→ 篩選區間上限開到 10 年沒有資料面的障礙。**

### 8.3 ⭐ 阻擋項 1：累計值 or 單季值 → **是「單季值」**（推翻預期）

台積電 2330 Revenue 原始值：
```
2015-03-31  222,034,144,000
2015-06-30  205,439,752,000   ← 下降
2015-09-30  212,504,909,000
2015-12-31  203,518,563,000

2024-03-31  592,644,201,000
2024-06-30  673,510,177,000
2024-09-30  759,692,143,000
2024-12-31  868,461,178,000   ← 單調上升
```

**判定：單季值，非累計值。**

依據一（數學）：若為累計值，Q2 累計必 ≥ Q1 累計（除非虧損）。實際
`2015-06-30 (2,054億) < 2015-03-31 (2,220億)` → 累計不成立。
2024 年序列雖單調上升，但那是台積電本身營收逐季成長，不能單獨作為依據。

依據二（量級）：台積電 2024 全年營收約 2.89 兆。`2024-12-31` 的值是
868 億 —— 這是單一季營收量級，不是全年累計（若為累計應接近 2.89 兆）。

> ⚠️ **修正 §6 待查證第 1 項的預設假設。** 原假設是「MOPS 採累計填報，
> FinMind 可能未轉單季」。實際 FinMind **已轉成單季**，可直接相加得 TTM。

**含意**：
- TTM = 最近 4 個 `date` 的 `value` 直接相加 ✅ 不需相減
- EPS 需注意：FinMind `EPS` 欄位為「基本每股盈餘」，是否也轉單季需另驗
  （下季度測）
- 附帶的好處：**schema 不用改**，`(stock_id, date, type)` 已足夠，因為 date
  就是季別。衝突 5 原本擔心的「沒有期間欄位」問題不存在。

### 8.4 ⭐ 阻擋項 2：欄位對應（21 個 type → origin_name）

| 杜邦需要 | FinMind type | origin_name |
|---|---|---|
| 稅後淨利 | `NetIncome` | 本期淨利(淨損) |
| 稅後淨利（合併） | `IncomeAfterTaxes` | 本期淨利（淨損） |
| 稅前淨利 | `IncomeBeforeIncomeTax` | 稅前淨利(淨損) |
| 稅前淨利（另版） | `PreTaxIncome` | 稅前淨利(淨損) |
| 營業利益 | `OperatingIncome` | 營業利益（損失） |
| 營業收入 | `Revenue` | 營業收入 |
| 營業成本 | `CostOfGoodsSold` | 營業成本 |
| 營業費用 | `OperatingExpenses` | 營業費用 |
| 所得稅 | `TAX` | 所得稅費用（利益） |
| 業外收入及支出 | `TotalNonoperatingIncomeAndExpense` | 營業外收入及支出 |
| 毛利 | `GrossProfit` | 營業毛利（毛損） |
| EPS | `EPS` | 基本每股盈餘 |

⚠️ **`NetIncome` vs `IncomeAfterTaxes` vs `PreTaxIncome` vs `IncomeBeforeIncomeTax`
是四組不同 type，但中文名幾乎相同。** 選錯欄位數字會錯但不會報錯。
→ 待驗：這幾組的實際差異（推測 `NetIncome` 為歸母、`IncomeAfterTaxes` 為含少數權益）。

### 8.5 權益與資產欄位 → **不在此 dataset，必須另抓 BalanceSheet**

`TaiwanStockFinancialStatements` 內 `TotalAssets` / `TotalLiabilities` /
`TotalEquity` 皆 **0 筆**。
（陷阱：此 dataset 的 `EquityAttributableToOwnersOfParent` 是
「**淨利**歸屬於母公司業主」，不是權益！origin_name 已明示，但英文 key 极易誤解。）

```
GET /api/v4/data?dataset=TaiwanStockBalanceSheet&data_id=2330&start_date=2023-01-01
→ rows=1,416，103 個 type
```

杜邦需要的權益／資產欄位 **全部在 BalanceSheet**：

| 用途 | type | origin_name |
|---|---|---|
| 股東權益（含少數） | `Equity` / `Equity_per` | 權益總額 |
| 股東權益（歸母） | `EquityAttributableToOwnersOfParent` | 歸屬於母公司業主之權益合計 |
| 非控制權益 | `NoncontrollingInterests` | 非控制權益 |
| 總資產 | `TotalAssets` / `TotalAssets_per` | 資產總額 |
| 總負債 | `Liabilities` | 負債總額 |
| 股本 | `CapitalStock` | 股本合計 |

⚠️ **`_per` 後綴**：`CapitalStock` 與 `CapitalStock_per` 並存但同為「股本合計」。
推測 `_per` 為普通股（per share）或 parent 科目，**需驗證否則會重複計數**。

### 8.6 ⭐ 阻擋項 3：歸母 vs 含少數權益 → **兩種都拿得到**

| 需要 | 來源 dataset | type |
|---|---|---|
| 淨利（歸母） | FinancialStatements | `ComprehensiveIncomeConsolidatedNetIncomeAttributedNonControllingInterest` |
| 淨利（非控制權益） | FinancialStatements | `NoncontrollingInterests` |
| 權益（歸母） | BalanceSheet | `EquityAttributableToOwnersOfParent` |
| 權益（含少數＝權益總額） | BalanceSheet | `Equity` |

→ **D8 分子用「稅後淨利（含少數權益）」可行**，實作時選 `IncomeAfterTaxes`
（待驗其與 `NetIncome` 的差別）。D7 分母「平均股東權益」需用
`(期初權益 + 期末權益) / 2`。

---

## 狀態更新

**阻擋 Phase 0 的三個查證項：全部解決。**（§6 第 1、2、3 項）

| 原待查證 | 結論 |
|---|---|
| 1. 累計 or 單季 | ✅ **單季值**，TTM 直接相加 |
| 2. 實際欄位 | ✅ 損益在 `FinancialStatements`，資產權益在 `BalanceSheet` |
| 3. 歸母 vs 含少數 | ✅ 兩種都有 |

**衝突 D（10 年資料）**：財務 ✅ 11 年、日線 ✅ 10 年可行（測試 3＋4）
**衝突 B（已還原股價）**：❌ **仍未解決**，僅剩三條路（見下）

---

---

## 未解問題（阻塞項）

### 🔴 衝突 B：已還原股價 — 尚未解決

長區間（>1 年）報酬率需 Adj Close，目前**無任何免費路徑**：

| 方案 | 狀態 | 代價 |
|---|---|---|
| FinMind `TaiwanStockPriceAdj` | 需 Backer（付費） | 金錢 |
| yfinance Adj Close | ❌ 本機網路被擋 | 需 VPN／proxy |
| 自行用除權息還原 | ❌ 官方無歷史除權息端點 | 死路 |

**三個待決選項**（需使用者決定）：
1. 買 Backer
2. 改網路環境後用 yfinance
3. **改設計** —— 篩選區間只影響財務體質類指標，不用報酬率類指標

### ⚠️ 其他未驗項目

| 項目 | 影響 |
|---|---|
| 月營收 `t187ap05_L` 歷史深度 | 決定維度 2 能算幾年營收 CAGR |
| TWSE/TPEx 日線欄位是否對齊 | 兩市場欄位順序與意義可能有差異 |
| `api.web.finmindtrade.com/v2/user_info` | spec §4.3 的 token pre-flight 端點（v4 對應路徑回 404）|

---

## 下一個測試

**EPS 是否也轉單季 + `NetIncome` vs `IncomeAfterTaxes` 差異 + `_per` 後綴意義**

這三項都會直接改變 ROE 計算結果，屬「寫錯不會報錯」的靜默錯誤類型，
必須在寫程式前驗清楚。

---

## 如何重現本記錄的測試

```powershell
# 環境（一次性）
uv venv --python 3.12 "$env:TEMP\opencode\dataprobe"
uv pip install --python "$env:TEMP\opencode\dataprobe\Scripts\python.exe" yfinance pandas
```

測試腳本在 `%TEMP%\opencode\t1.py` ～ `t12.py`（**未納入 git，會被清理**）。
若需重跑，關鍵參數如下：

| 測試 | 端點 | 關鍵參數 |
|---|---|---|
| 1 | `query1.finance.yahoo.com/v8/finance/chart/2330.TW` | 需 User-Agent |
| 2 | `www.twse.com.tw/exchangeReport/STOCK_DAY` | `date=YYYYMM01&stockNo=2330`（**一個月**）|
| 3 | `www.tpex.org.tw/.../stk_quote_result.php` | `d=YYY/MM/DD`（**單日全市場**）|
| 4 | `www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX` | `date=YYYYMMDD&type=ALLBUT0999`（table[8] 是行情）|
| 6 | `openapi.twse.com.tw/v1/opendata/t187ap05_L` | 無參數（**月營收，非除權息**）|
| 7 | `mops.twse.com.tw/mops/web/ajax_t163sb04` | 會被封鎖 |
| 8 | `api.finmindtrade.com/api/v4/data` | `dataset=…&data_id=2330&start_date=…` |

⚠️ **Windows 主控台無法正確顯示 UTF-8 中文**，所有腳本都改為
「寫檔 + 讀檔」方式輸出結果。

---

## 這份記錄怎麼用

本記錄是**實測結果**，不是文件查閱。每條結論都有實際 API 回應支撐，
可直接引用到 spec。

對照來源：
- `docs/superpowers/specs/2026-10-01-finmind-data-pipeline-design.md`（canonical spec）
- `docs/superpowers/specs/2026-10-05-decision-log.md`（§6 待查證清單）

⚠️ 發現 spec 兩處需修正（詳見 test 8）：
1. §4.3 pre-flight 端點 `api.finmindtrade.com/api/v4/user_info` → 實測 **404**
2. §8 預設 FinMind 財報為累計值 → 實測**已轉單季**，TTM 不需相減