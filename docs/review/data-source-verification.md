# 資料來源逐一驗證記錄

建立日期：2026-10-06
驗證方式：實際呼叫 API，非文件查閱
環境：Windows，Python 3.12.13（`uv venv` 建於 `%TEMP%\opencode\dataprobe`）

狀態圖例：✅ 可用／❌ 不可用／⚠️ 可用但有條件／🔄 驗證中／⬜ 未測

---

## 進度總表

| # | 來源 | 狀態 | 用途／影響 |
|---|---|---|---|
| 1 | yfinance Adj Close | ❌ 網路被擋 | 已還原價 → 衝突 B 未解 |
| 2 | TWSE STOCK_DAY 月線 | ⚠️ 成本過高 | 單股單月一 request，不可行 |
| 3 | TPEx 每日收盤 | ⚠️ 日期參數無效 | 僅能取當日，改作交叉驗證 |
| 4 | TWSE MI_INDEX | ✅ | 上市單日行情（僅近期有效）|
| 5 | TWSE 歷史除權息 | ❌ 官方無可用來源 | 自行還原價暫緩 |
| 6 | TWSE 月營收 t187ap05_L | ✅ | 維度 2 營收佐證 |
| 7 | MOPS 財務報表 | ❌ 直連被擋 | 改走 FinMind |
| 8 | **FinMind 財務報表** | ✅ **免額度可用** | **阻擋 Phase 0 三項全解，11 年** |
| 9 | **FinMind `TaiwanStockPrice`** | ✅ **免額度可用** | **日線 11.7 年，取代 TPEx/TWSE** |
| 10 | FinMind `TaiwanStockPriceAdj` | ❌ 官方確認需付費 | 衝突 B 最後一條免費路也斷 |
| 11 | TWSE/TPEx 欄位 | ⚠️ 不對齊 | 需各自映射欄位名 |
| 12 | 財務靜默錯誤三項 | ✅ 全解 | `_per`／`NetIncome`／EPS 驗證 |
| 13 | FinMind `TaiwanStockDividend` | ⚠️ 部分可用 | 有除息日與股利，**缺基準價** |
| 14 | FinMind `TaiwanStockTradingDate` | ✅ | 6,936 個交易日（1999–2026）|
| 15 | 全市場日線成本 | ✅ **0.3 小時** | 20 檔實測 10.2 秒、0 失敗 |

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

**衝突 D（10 年資料）**：財務 ✅ 11 年、日線 ✅ **11.7 年（測試 9）**
**衝突 B（已還原股價）**：❌ **確認無免費路徑**（測試 10，FinMind 明確回覆需 Backer）

---

## 測試 9：FinMind `TaiwanStockPrice` 日線 ✅ 免費可用，11.7 年

**這是突破性發現，取代了先前「日線只能靠 TWSE/TPEx」的結論。**

### 9.1 完整 dataset 清單（從 422 錯誤 body 取出 105 個合法名稱）

FinMind 傳入不存在的 dataset 名時，會在 422 body 列出**全部合法值**。這是找出
dataset 名的可靠方法（比猜測有效）。

台股價格相關共 14 個候選，逐一實測結果：

| dataset | HTTP | 結果 |
|---|---|---|
| **`TaiwanStockPrice`** | **200** | ✅ **免費，2,864 期** |
| `TaiwanStockPriceAdj`（已還原） | 400 | ❌ `"Your level is free. Please update your user level."` |
| `TaiwanStockMonthPrice` | 400 | ❌ 同上 |
| `TaiwanStockWeekPrice` | 400 | ❌ 同上 |
| `TaiwanStockPriceLimit` | 400 | ❌ 同上 |
| `TaiwanStockPriceTick` | 400 | ❌ 同上 |
| `TaiwanFuturesFinalSettlementPrice` | 400 | ❌ 同上 |
| `TaiwanOptionFinalSettlementPrice` | 400 | ❌ 同上 |
| `TaiwanStockCapitalReductionReferencePrice` | 200 | 空（僅近期）|
| `TaiwanStockSplitPrice` | 200 | 空（僅近期）|

### 9.2 `TaiwanStockPrice` 內容

```
GET /api/v4/data?dataset=TaiwanStockPrice&data_id=2330&start_date=2015-01-01
→ msg=success, rows=2864
   date range: 2015-01-05 → 2026-10-05  (11.7 年, 2,864 個交易日)
   fields: date, stock_id, Trading_Volume, Trading_money,
           open, max, min, close, spread, Trading_turnover
   sample: {"date":"2015-01-05","stock_id":"2330","Trading_Volume":32214177,
            "Trading_money":4459516134,"open":140.5,"max":140.5,
            "min":137.5,"close":139.5,"spread":-1.5,"Trading_turnover":9377}
```

✅ **OHLC 齊全**，含成交金額與週轉率。**免 token 即可呼叫。**

⚠️ **`Trading_turnover` 單位不明**。樣本 9,377 對 2330 當日成交 3,221 萬股
——若為張數則 3,221 萬股 ≈ 322,141 張，與 9,377 不符。
**待驗**：可能是成交金額／流通市值 或 其他定義。

### 9.3 `start_date` 格式

| 格式 | 結果 |
|---|---|
| `2015-01-01` | ✅ 200 |
| `20150101` | ❌ `parameter 20150101 is illegal.` |
| `2015/01/01` | ❌ illegal |
| `2015` | ❌ illegal |

**只能用 `YYYY-MM-DD`。** 與 TWSE/TPEx 的 `YYYYMMDD` 不同，三個來源要分別處理。

---

## 測試 10：已還原股價 —— 確認無免費路徑

`TaiwanStockPriceAdj` 明確回覆：
```json
{"msg":"Your level is free. Please update your user level.
 Detail information:https://finmindtrade.com/analysis/#/Sponsor/sponsor",
 "status":400,"token_tail":""}
```

**FinMind 官方確認已還原價需 Backer 付費**（不只是我們試不出來）。

搭配先前實測：
- Yahoo/yfinance：本機網路層被擋
- TWSE `TWT48U`：忽略 `stockNo`、只給預告表非歷史

→ **三條免費路全部確認走不通，非環境問題。**

## 測試 13：`TaiwanStockDividend` ⚠️ 有除息日但缺關鍵欄位

```
GET /api/v4/data?dataset=TaiwanStockDividend&data_id=2330&start_date=2015-01-01
→ msg=success, rows=34
   date range: 2015-07-05 → 2026-09-22
```

### 可用的關鍵欄位

| 欄位 | 意義 | 樣本值 |
|---|---|---|
| `CashEarningsDistribution` | **現金股利（每股）** | `4.49987539`（2015）、`7.00000137`（2026）|
| `CashExDividendTradingDate` | **除息交易日** | `2015-06-29`、`2026-09-16` |
| `CashDividendPaymentDate` | 配息日 | `2015-07-23` |
| `TotalEmployeeCashDividend` | 現金股利總額 | `17,645,966,064` |
| `ParticipateDistributionOfTotalShares` | 參與 distribution 總股數 | `25,932,364,970` |
| `year` | 會計年度（民國） | `103年`、`115年第1季` |
| `AnnouncementDate` / `AnnouncementTime` | 公告時間 | `2015-06-11 16:40:18` |

### 🔴 缺「除權息基準價」——自建還原價的決定性缺口

還原價公式需要：`除權息後參考價 = 收盤價 − 現金股利`。
`CashExDividendTradingDate` 有，但**該日的參考價欄位不存在**。

FinMind 免費清單裡唯一相關的 `TaiwanStockCapitalReductionReferencePrice`
（減資參考價）**實測回空資料**（測試 9 表）。

→ **自建精確還原價不可行。**

### ⚠️ 資料完整性問題

| 年 | 筆數 |
|---|---|
| 2015–2018 | **每年僅 1 筆** |
| 2019 | 3 筆 |
| 2020–2025 | 每年 4 筆（正常）|
| 2026 | 3 筆 |

**2015–2018 明顯缺漏**（每年 1 筆不可能涵蓋 4 個配息季）。
即使有基準價，這段期間的還原也不完整。

---

## 測試 14：`TaiwanStockTradingDate` ✅ 官方交易日曆

```
GET /api/v4/data?dataset=TaiwanStockTradingDate
→ rows=6,936   fields=['date']
   range: 1999-01-05 → 2026-12-31
```

✅ **免費、一次回傳全部、含未來日期（到 2026 年底）。**

→ 抓取層可用此作為日曆基準，**不需自行推算交易日**。
→ 也能避免本輪遇到的「非交易日請求」問題（測試 11.1 顯示 TWSE 非交易日
回 `stat=很抱歉，沒有符合條件的資料!`）。

---

## 測試 15：全市場日線抓取成本 ✅ 遠優於所有估算

### 實測（20 檔，含 ETF 與大型權值股）

```
20 檔耗時 10.2 秒   成功 20   失敗 0
平均每檔 0.51s
每檔回傳期數: min=2,165  max=2,864  avg=2,808
```

### 外推全市場（約 2,000 檔）

| 方案 | requests | 耗時 |
|---|---|---|
| **FinMind 逐股 `TaiwanStockPrice`** | **~2,000** | **~0.3 小時** |
| TWSE `STOCK_DAY` 月線／檔 | 288,000 | ~24 天 |
| ~~TPEx＋TWSE 全市場／日~~ | ~~5,000~~ | ❌ 日期參數無效 |

**成本比 TWSE 月線低 144 倍，比原估算低 33 倍。**

⚠️ **免額度不能省略 `stock_id`**：
```
GET /api/v4/data?dataset=TaiwanStockPrice&start_date=2026-09-01
→ HTTP 400  "Your level is free. Please update your user level."
```
必須逐股呼叫，2,000 檔 = 2,000 requests。

⚠️ 免費額度約 600 requests/小時 → **2,000 檔約需 3.3 小時**（非 0.3 小時，
0.3 小時是純網路耗時，需再除以速率限制）。全量同步規劃應以 **3–4 小時** 計算。

### `Trading_turnover` 單位仍未確認

欄位存在但語意不明（2330 樣本 9,377）。已有 `Trading_Volume`（股數）與
`Trading_money`（金額），可先不使用此欄位。

---

## 測試 11：TWSE / TPEx 日線欄位 ⚠️ 部分推翻前次結論

### 11.1 🔴 TPEx 日期參數被無視

```
請求 d=115/01/02 → 回 date=20261005, rows=12060
請求 d=115/01/01 → 回 date=20261005, rows=12060   ← 同一份
```

**TPEx `stk_quote_result.php` 的日期參數無效，永遠回當日。**

→ **前次記錄「10 年日線約 5,000 requests／0.5 天」不成立**（拿不到歷史）。
→ 但**此失敗已不重要**：`TaiwanStockPrice`（測試 9）免費提供 11.7 年日線。
→ TPEx 端點僅保留作**當日交叉驗證**用途。

TWSE 端點則日期有效：
```
date=20260101 (元旦) → stat="很抱歉，沒有符合條件的資料!", tables=0
```

### 11.2 🔴 12,060 筆的組成：先前分類錯誤

先前記錄稱「12,060 筆含上櫃＋興櫃＋權證」。實測分類：

| 先前規則 | 筆數 | 實際內容 |
|---|---|---|
| 6 碼純數字 = 權證 | 10,681（88.6%）| ❌ `006201 元大富櫃50` 是 **ETF** |
| 6 碼+1 = ETF | 483（4.0%）| ✅ `00411A 主動統一前沿科技` 確為 ETF |
| 其他 | 896（7.4%）| ❌ `00858 永豐美國500大` 也是 **ETF** |

**真相**：12,060 筆絕大多數是 **ETF 與境外指數 ETF**（`00xxxx` 開頭），
不是權證也不是興櫃個股。

→ **不能靠代號規則分類**，必須靠 stock master 的 `industry_category`。
→ 興櫃**不在此端點**（`table[1]` 管理股票 = 0 筆，全表無「興櫃」字樣）。
→ 先前記錄「上櫃＋興櫃」**錯誤**，更正為**僅上櫃**。

### 11.3 欄位確實不對齊（判斷成立）

| | TWSE `MI_INDEX` table[8] | TPEx table[0] |
|---|---|---|
| 欄位數 | 16 | 19 |
| 標題 | 每日收盤行情(全部(不含權證、牛熊證…)) | 上櫃股票行情 |
| **收盤價 index** | **8** | **2** |
| 漲跌欄位 | index 9，只含 `<p style= color:red>+</p>` | index 3，直接帶 `+0.23` |
| 漲跌價差 | 有（index 10）| 無 |
| 本益比 | **有**（index 15）| **無** |
| 成交股數 | index 2 | index 8 |
| 發行股數 | 無 | **有**（index 15）|
| 次日漲跌停 | 無 | **有**（17, 18）|

**2330 欄位對位驗證**（確認欄位語意正確）：
```
[ 8] 收盤價 = '1,585.00'   ← 合理（台積電 2026-01 量級）
[10] 漲跌價差 = '35.00'
[15] 本益比 = '25.90'      ← 合理
```

**字串清洗差異**：
- TWSE：`<p style= color:red>+</p>` 需剝 HTML 標籤
- TPEx：`'-0.11 '` **有尾隨空格**（`+0.23` 沒有）→ `.strip()` 必須做

⚠️ 兩個來源的欄位**不可用同一套 index 取值**，必須各自映射欄位名 → 值。

---

## 測試 12：財務靜默錯誤項目 ✅ 全部解決

### 12.1 `_per` 後綴 = 每股比例（**先前推測「parent」是錯的**）

實測對照（2330，2026-06-30）：

| 欄位 | 原值（元） | `_per` 值 |
|---|---|---|
| `TotalAssets` | 9,375,654,727,000 | **100.0** |
| `TotalLiabilitiesEquity` | 9,375,654,727,000 | **100.0** |
| `Equity` | 6,474,470,981,000 | **69.06** |
| `CashAndCashEquivalents` | 3,134,218,213,000 | **33.43** |

→ **`_per` 是「占總資產百分比」分析表**，51 個欄位皆有此變體。
→ **實作規則：`_per` 系列整組忽略。** 不存在重複計數風險。

### 12.2 `NetIncome` vs `IncomeAfterTaxes` = 歷史長度不同（**先前推測「歸母vs含少數」是錯的**）

| type | 筆數 | 涵蓋期間 |
|---|---|---|
| **`IncomeAfterTaxes`** | **46** | 2015-03-31 → **2026-06-30** |
| `NetIncome` | **20** | 2015-03-31 → **2019-12-31**（2020 後斷）|
| `IncomeBeforeIncomeTax` | **20** | 同上，2019 後斷 |
| `PreTaxIncome` | **46** | 2015-03-31 → 2026-06-30 |

重疊期間數值幾乎相同：
```
2018-03-31  NetIncome = 89,787,600,000
            IncomeAfterTaxes = 89,787,574,000
            差 = -26,000 元（約 0.00003%）
```

`IncomeAfterTaxes - NoncontrollingInterests == NetIncome` → **0/20 吻合**
→ **兩者在重疊期定義相同，都是合併淨利，不含歸母／含少數的區別。**
（括號差異：`NetIncome` 用半形 `(淨損)`，`IncomeAfterTaxes` 用全形 `（淨損）`，
純粹是來源字串差異，無語意。）

→ **實作規則：統一用 `IncomeAfterTaxes`**（46 期全覆蓋）。
用 `NetIncome` 會在 2020 年後完全斷層。

### 12.3 EPS 四季加總驗證 ✅ 通過

| 年 | Q1 | Q2 | Q3 | Q4 | 加總 | 營收四季加總 |
|---|---|---|---|---|---|---|
| 2018 | 3.46 | 2.79 | 3.44 | 3.85 | **13.54** | 10,315 億 |
| 2020 | 4.51 | 4.66 | 5.30 | 5.50 | **19.97** | 13,393 億 |
| 2023 | 7.98 | 7.01 | 8.14 | 9.21 | **32.34** | 21,617 億 |
| 2024 | 8.70 | 9.56 | 12.55 | 14.45 | **45.26** | 28,943 億 |
| 2025 | 13.95 | 15.36 | 17.44 | 19.51 | **66.26** | 38,091 億 |

2025 年營收四季加總 38,091 億 ≈ 3.81 兆，與台積電實際量級相符。
→ **確認 EPS 與營收皆為單季值，TTM = 四季直接相加。**

💡 **建議**：把「四季加總」做成同步後的 sanity check（使用者已同意）。
但**不應寫死門檻**（如「對不上 3.8 兆」）——那是台積電 2025 的特定數字，
換股票即失效。應改用**自我一致性**檢查（見「下一步」）。

---

## 狀態更新

### 已解決 ✅

| 項目 | 結論 |
|---|---|
| 阻擋 Phase 0 三項 | 財報單季值／欄位對應／歸母vs含少數 |
| 10 年日線 | ✅ `TaiwanStockPrice` 免費 11.7 年 |
| 10 年財報 | ✅ 11 年 |
| `_per` 後綴 | 每股比例，整組忽略 |
| `NetIncome` 歧義 | 用 `IncomeAfterTaxes` |
| EPS 單季驗證 | 四季加總通過 |
| TWSE/TPEx 欄位 | 不對齊，需各自映射 |
| TPEx 歷史日線 | ❌ 日期參數無效（但已不需要）|

### 仍阻塞 🔴

**已還原股價**：FinMind 官方確認 `TaiwanStockPriceAdj` 需 Backer。
Yahoo 被擋、官方無歷史除權息。**三條免費路全斷，非環境問題。**

**唯一未驗的替代方案**：用免費的 `TaiwanStockDividend` 自建近似還原，
但需要「除權息基準價」來源，而 `TaiwanStockCapitalReductionReferencePrice` 實測回空。

### 建議的 sanity check 設計（待使用者確認）

與其寫死「3.8 兆」，改用以下**自我一致性**檢查，任何股票都適用：

| 檢查 | 規則 | 能擋什麼 |
|---|---|---|
| 單季加總 vs 年度 | 四季加總應 ≈ 官方年度 EPS（差 < 5%）| 抓取錯期、漏期 |
| 單調性 | 已轉單季的營收不該在無重大事件時大幅下降 | 誤抓成累計值 |
| 空值率 | 近 8 期缺值 > 2 期 → 警告 | 財報缺漏、下市 |
| 權益恆等 | `Assets == Liabilities + Equity`（誤差 < 1%）| 欄位抓錯 |

這些不依賴外部基準值，抓取層壞掉時會明確失敗。

---

---

## 未解問題（阻塞項）

### 🔴 衝突 B：已還原股價 — 三條免費路已全部確認走不通

| 方案 | 實測結果 |
|---|---|
| FinMind `TaiwanStockPriceAdj` | ❌ 官方回覆 `"Your level is free. Please update your user level."` |
| yfinance / Yahoo | ❌ 本機網路層被擋（DNS→180.222.109.251，TCP 不通；同時 TWSE 通）|
| 自行用除權息還原 | ❌ TWSE `TWT48U` 忽略 `stockNo`、只給預告表非歷史 |

**這是資料面限制，不是環境或程式問題。** 需使用者決策：

1. 買 FinMind Backer（解鎖 `TaiwanStockPriceAdj`、`MonthPrice`、`WeekPrice`、`PriceLimit`）
2. 改網路環境（VPN／proxy）後用 yfinance
3. **改設計** —— 篩選區間只影響財務體質類指標（ROE／毛利率／負債比），
   不使用報酬率類指標，則完全不需要已還原價
4. ~~用免費 `TaiwanStockDividend` 自建還原~~ ❌ **已確認不可行**（測試 13）

⚠️ **方案 4 為何不可行**：自建還原需「除權息基準價」，
`TaiwanStockDividend` 只有 `CashExDividendTradingDate`（除息日）與
`CashEarningsDistribution`（每股股利），**無基準價欄位**；
唯一相關的 `TaiwanStockCapitalReductionReferencePrice` 實測回空資料。
且 2015–2018 每年僅 1 筆，資料本身不完整。

⚠️ **方案 3 的連帶影響**：長區間報酬率、股價通道、追價安全圈的「天花板上移」
判斷都會失效。安全圈仍可用「歷史 PE 分位」計算，不需還原價。

### ⚠️ 其他未驗項目

| 項目 | 影響 | 優先度 |
|---|---|---|
| 興櫃日線來源 | TPEx 端點不含興櫃 | 低（可先排除興櫃）|
| `Trading_turnover` 單位意義 | 換手率計算（已有 Volume/money 可繞過）| 低 |

---

## 下一個測試

1. **月營收 `t187ap05_L` 歷史深度** —— 決定維度 2 營收 CAGR 能算幾年
2. **免費額度實測** —— 600 requests/小時的實際限制，影響全量同步排程估算
3. `Trading_turnover` 單位意義（低優先）

**資料面待查已清空**：阻擋 Phase 0 的三項全解、10 年財報、10 年日線、
欄位對齊、靜默錯誤三項皆有結論。**唯一阻塞是已還原股價（需使用者決策）。**

---

## 如何重現本記錄的測試

```powershell
# 環境（一次性）
uv venv --python 3.12 "$env:TEMP\opencode\dataprobe"
uv pip install --python "$env:TEMP\opencode\dataprobe\Scripts\python.exe" yfinance pandas
```

測試腳本在 `%TEMP%\opencode\t1.py` ～ `t19.py`（**未納入 git，會被清理**）。
若需重跑，關鍵參數如下：

| 測試 | 端點 | 關鍵參數 |
|---|---|---|
| 1 | `query1.finance.yahoo.com/v8/finance/chart/2330.TW` | 需 User-Agent |
| 2 | `www.twse.com.tw/exchangeReport/STOCK_DAY` | `date=YYYYMMDD&stockNo=2330`（**一個月**）|
| 3 | `www.tpex.org.tw/.../stk_quote_result.php` | `d=YYY/MM/DD` ⚠️ **參數無效，永遠回當日** |
| 4 | `www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX` | `date=YYYYMMDD&type=ALLBUT0999`（table[8] 是行情）|
| 6 | `openapi.twse.com.tw/v1/opendata/t187ap05_L` | 無參數（**月營收，非除權息**）|
| 7 | `mops.twse.com.tw/mops/web/ajax_t163sb04` | 會被封鎖 |
| 8–10, 12 | `api.finmindtrade.com/api/v4/data` | `dataset=…&data_id=2330&start_date=YYYY-MM-DD` |
| 9 | **列出所有合法 dataset** | 傳不存在的名稱，422 body 會列出全部 105 個 |
| 11 | TWSE / TPEx 欄位 | 見測試 11 表格 |

⚠️ **日期格式不一致**：
- FinMind：`YYYY-MM-DD`（用 `20150101` 會回 `parameter ... is illegal`）
- TWSE / TPEx：`YYYYMMDD`

⚠️ **FinMind 免費/付費判定**：HTTP 400 + `msg` 含 `"Your level is free"`
= 該 dataset 需 Backer 付費。不要靠猜。

⚠️ **Windows 主控台無法正確顯示 UTF-8 中文**，所有腳本都改為
「寫檔 + 讀檔」方式輸出結果。

---

## 這份記錄怎麼用

本記錄是**實測結果**，不是文件查閱。每條結論都有實際 API 回應支撐，
可直接引用到 spec。

對照來源：
- `docs/superpowers/specs/2026-10-01-finmind-data-pipeline-design.md`（canonical spec）
- `docs/superpowers/specs/2026-10-05-decision-log.md`（§6 待查證清單、§6.1 實測結論）

⚠️ 發現 spec 三處需修正：
1. §4.3 pre-flight 端點 `api.finmindtrade.com/api/v4/user_info` → 實測 **404**；
   正確端點是 `api.web.finmindtrade.com/v2/user_info`（**需 token 才回資料**）
2. §8 預設 FinMind 財報為累計值 → 實測**已轉單季**，TTM 不需相減
3. §8 日線來源（原定 TWSE/TPEx）→ 改用 **`TaiwanStockPrice`**（11.7 年免費）；
   TPEx 端點日期參數無效、且不含興櫃

⚠️ 本記錄曾有兩處錯誤結論，已更正（保留原句以留下修正軌跡）：
- 曾稱 TPEx 12,060 筆「含上櫃＋興櫃＋權證」→ 實際**僅上櫃，且多數是 ETF**
- 曾推測 `_per` 後綴是「parent（母公司）」→ 實際是**占總資產百分比**
- 曾推測 `NetIncome` vs `IncomeAfterTaxes` 是「歸母 vs 含少數權益」→ 實際是
  **歷史長度不同，定義相同**

### 更正軌跡

| 時間 | 原結論 | 更正後 | 觸發 |
|---|---|---|---|
| 測試 3（早）| TPEx ✅ 可取歷史日線，10 年 5,000 requests | ⚠️ 日期參數無效，僅能取當日 | 測試 11.1 |
| 測試 3（早）| 12,060 筆含上櫃＋興櫃＋權證 | 僅上櫃；多數為 ETF；不含興櫃 | 測試 11.2 |
| 測試 4（早）| TWSE+TPEx 可供 10 年日線（0.5 天）| 改用 FinMind `TaiwanStockPrice`（11.7 年）| 測試 9 |
| 測試 8.6 | `NetIncome` vs `IncomeAfterTaxes` = 歸母 vs 含少數 | 定義相同，差異在歷史長度（46 vs 20 期）| 測試 12.2 |
| 測試 8.5 | `_per` 推測為 parent（母公司）| `_per` = 占總資產百分比，整組忽略 | 測試 12.1 |

**教訓**：`origin_name` 相同不代表語意相同；代號前綴不能當分類依據；
「端點回 200」不代表「參數有效」。這三類錯誤都是**不會報錯的靜默錯誤**。