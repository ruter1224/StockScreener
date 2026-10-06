"""查詢 FinMind 實際額度上限，並驗證 token 的實際作用範圍。

用法：在 repo 根目錄建立 .env 檔案，內容為 FINMIND_TOKEN=你的token
然後執行 python check_quota.py

安全：本腳本只讀取 token，不會印出 token 本身，
也不會把 token 寫入任何檔案。
"""

import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.finmindtrade.com/api/v4/data"
USER_INFO = "https://api.web.finmindtrade.com/v2/user_info"
ENV_PATH = ".env"


def load_token():
    if not os.path.exists(ENV_PATH):
        sys.exit("找不到 .env。請在 repo 根目錄建立，內容：FINMIND_TOKEN=你的token")
    with io.open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("FINMIND_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(".env 中找不到 FINMIND_TOKEN= 開頭的行")


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body[:400]}
    except Exception as e:
        return None, {"error": str(e)[:200]}


out = []


def emit(line=""):
    out.append(line)


token = load_token()
emit("token 長度: %d 字元（前 %s… 後 %s…）" % (len(token), token[:4], token[-4:]))

# ── 1. 查額度 ──
emit()
emit("=== 1. /v2/user_info（帶 Authorization header）===")
status, body = get(USER_INFO, {"Authorization": "Bearer " + token})
emit("HTTP %s" % status)
if isinstance(body, dict):
    for k, v in body.items():
        if k == "token":
            continue
        emit("  %s = %s" % (k, v))

# ── 2. token 下的資料存取：確認免費 token 能做什麼 ──
emit()
emit("=== 2. 帶 token 測試已知免費可用的 dataset ===")
for ds in ["TaiwanStockPrice", "TaiwanStockFinancialStatements", "TaiwanStockPER"]:
    url = BASE + "?" + urllib.parse.urlencode(
        {"dataset": ds, "data_id": "2330", "start_date": "2026-09-01"})
    st, b = get(url, {"Authorization": "Bearer " + token})
    n = len(b.get("data") or []) if isinstance(b, dict) else None
    emit("  %-36s HTTP %s  rows=%s  msg=%s" % (
        ds, st, n, (b.get("msg") or "")[:60] if isinstance(b, dict) else ""))

# ── 3. 先前回報「需付費」的 dataset，帶 token 後是否解鎖 ──
emit()
emit("=== 3. 先前回報 400 Your level is free 的 dataset，帶 token 後 ===")
emit("   （若仍為 Your level is free，代表是方案等級限制，不是 token 問題）")
LOCKED = [
    "TaiwanStockCapitalReductionReferencePrice",
    "TaiwanStockMarketValue",
    "TaiwanStockIndustryChainMoneyFlow",
    "TaiwanStockGovernmentBankBuySell",
    "TaiwanStockPriceAdj",
]
for ds in LOCKED:
    url = BASE + "?" + urllib.parse.urlencode(
        {"dataset": ds, "data_id": "2330", "start_date": "2024-01-01"})
    st, b = get(url, {"Authorization": "Bearer " + token})
    msg = (b.get("msg") or "")[:70] if isinstance(b, dict) else ""
    n = len(b.get("data") or []) if isinstance(b, dict) else None
    emit("  %-44s HTTP %s  rows=%s  %s" % (ds, st, n, msg))

# ── 4. 不帶 token 對照，確認 token 是否真的必要 ──
emit()
emit("=== 4. 同一組 dataset 不帶 token（對照組）===")
for ds in ["TaiwanStockPrice", "TaiwanStockPER"]:
    url = BASE + "?" + urllib.parse.urlencode(
        {"dataset": ds, "data_id": "2330", "start_date": "2026-09-01"})
    st, b = get(url)
    n = len(b.get("data") or []) if isinstance(b, dict) else None
    emit("  %-36s HTTP %s  rows=%s" % (ds, st, n))

emit()
emit("=== 結論對照用 ===")
emit("  若 2 與 4 結果相同 → token 對取資料非必要，僅用於查額度")
emit("  若 3 仍為 Your level is free → 該限制是方案等級，token 無法解鎖")

io.open("_quota_report.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))