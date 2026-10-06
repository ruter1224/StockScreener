# 依序抓完全部 dataset，可中斷續傳。
#
# 用法：
#   開個 PowerShell 視窗，cd 到專案目錄，執行 .venv\Scripts\python.exe run_all.py
#   視窗不要關，關掉就停（Ctrl+C 可安全中斷，重跑會續傳）
#
# 為什麼需要這支：
#   fetch.py 一次只跑一個 dataset，跑完要人接下一個。
#   掛機時人在不在都要能一路跑到底，所以要有迴圈。
#
# 這一版的重點（2026-10-06）：
#   1. 斷線會自己等指數退避後續抓，不用人守著重啟。
#   2. 額度用盡（402）會通知，等待計費週期後自動重試。
#   3. 只有「每個 dataset 都回 0」才寫 ALL_DONE.txt。
#      舊版 402/403/熔斷都 exit 0，run_all 誤當成功 → 資料沒抓完卻寫了完成檔，
#      直接戳破「抓完才上傳雲端」的閘門。

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

# 抓取端輸出 utf-8，重導向到 log 才是可讀的中文。
# 不設的話 Windows 會用 cp950，log 全是亂碼（2026-10-06 踩過）。
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

ROOT = Path(__file__).parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
LOG_DIR = ROOT / "logs"
DONE_FILE = LOG_DIR / "ALL_DONE.txt"

DATASETS = [
    "TaiwanStockFinancialStatements",
    "TaiwanStockBalanceSheet",
    "TaiwanStockMonthRevenue",
    "TaiwanStockPER",
    "TaiwanStockCashFlowsStatement",
    "TaiwanStockPrice",
    "TaiwanStockDividendResult",
]

# ⚠️ 這七個值必須與 fetch.py 的 EXIT_* 完全一致。
# tests/test_run_all.py 有測試擋這條契約，改一邊忘了另一邊會被測試抓到。
EXIT_OK = 0        # 這個 dataset 抓完了
EXIT_FATAL = 1     # 環境問題（缺 .venv、參數錯）
EXIT_NETWORK = 2   # 斷線 / 5xx 連續失敗
EXIT_QUOTA = 3     # 額度用盡（402）
EXIT_IP_BAN = 4    # IP 被封鎖（403），官方 30 分鐘自動解除
EXIT_CIRCUIT = 5   # 4xx 熔斷，需要人工確認參數
EXIT_PARTIAL = 6   # 抓完但有失敗檔

EXIT_LABEL = {
    EXIT_OK: "完成",
    EXIT_FATAL: "致命錯誤",
    EXIT_NETWORK: "斷線",
    EXIT_QUOTA: "額度用盡",
    EXIT_IP_BAN: "IP 被封鎖",
    EXIT_CIRCUIT: "4xx 熔斷",
    EXIT_PARTIAL: "部分失敗",
}

# 退出碼 → (第一次等多久, 之後每次等多久, 最多重試幾次)
# None 的地方代表「等一下重試次數」；回傳 None 代表不重試、直接放棄。
RETRY_POLICY: dict[int, tuple[int, int, int | None]] = {
    # 斷線：指數退避 60→120→240…封頂 900s（15 分），沒有重試上限。
    # 掛機本來就會跑 28 小時，斷網幾小時是正常狀況，不該放棄。
    EXIT_NETWORK: (60, 900, None),
    # 額度：FinMind 每小時重置，等滿 1 小時，最多試 4 次（4 小時），
    # 都用盡就放棄——繼續空轉沒有意義，要人來看 token 是不是沒錢了。
    EXIT_QUOTA: (3600, 3600, 4),
    # IP 封鎖：官方 30 分鐘自動解除，多等 1 分鐘，試 3 次。
    EXIT_IP_BAN: (1860, 1860, 3),
    # 部分失敗：等 2 分鐘補抓（--retry-errors 邏輯靠續傳自然重抓），最多 2 次。
    EXIT_PARTIAL: (120, 120, 2),
}

# 致命（1）與熔斷（5）不在表裡 → 不重試。
# 熔斷尤其不能自動重試：官方明講 4xx 是「請求本身有問題」，
# 盲目重送只會累積 4xx 直到 IP 被封。


def _ps_quote(s: str) -> str:
    """PowerShell 單引號字串的跳脫（內部單引號要寫兩次）。"""
    return s.replace("'", "''")


def retry_wait_seconds(code: int, attempt: int) -> int | None:
    """回傳這次要等幾秒再重試；None 代表不該重試、直接放棄。

    attempt 從 0 開始。純函式，好測試。
    """
    policy = RETRY_POLICY.get(code)
    if policy is None:
        return None
    first, step, max_attempts = policy
    if max_attempts is not None and attempt >= max_attempts:
        return None
    if attempt == 0:
        return first
    return min(first * (2**attempt), step)


def notify(title: str, message: str) -> None:
    """Windows 通知。失敗就算了，不影響抓取。"""
    ps = (
        "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
        "$n = New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon = [System.Drawing.SystemIcons]::Information;"
        "$n.BalloonTipTitle = 'StockScreener';"
        f"$n.BalloonTipText = '{_ps_quote(title)}：{_ps_quote(message)}';"
        "$n.Visible = $true; $n.ShowBalloonTip(10000); Start-Sleep -Seconds 11"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        check=False,
        timeout=30,
    )


def notify_error(title: str, message: str) -> None:
    """錯誤通知。泡泡顯示 30 秒（等待狀態要久到使用者真的看得到）。"""
    ps = (
        "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
        "$n = New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon = [System.Drawing.SystemIcons]::Error;"
        "$n.BalloonTipTitle = 'StockScreener';"
        f"$n.BalloonTipText = '{_ps_quote(title)}：{_ps_quote(message)}';"
        "$n.Visible = $true; $n.ShowBalloonTip(30000); Start-Sleep -Seconds 31"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        check=False,
        timeout=45,
    )


def run_fetch(dataset: str, log_path: Path) -> int:
    """跑一次 fetch.py 抓指定 dataset，輸出導到 log。回傳退出碼。"""
    with log_path.open("a", encoding="utf-8", errors="replace") as fh:
        fh.write(f"\n\n===== {dataset} @ {time.strftime('%H:%M:%S')} =====\n")
        fh.flush()
        proc = subprocess.Popen(
            [str(PYTHON), "fetch.py", "--dataset", dataset],
            cwd=ROOT,
            stdout=fh,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        )
        # Ctrl+C 要能穿透到子行程，否則會變成「只停一半」
        try:
            proc.wait()
        except KeyboardInterrupt:
            print("\n  中斷中，等當前檔案寫完…", flush=True)
            proc.wait()
            print("  已安全停止。重跑本腳本會續傳。", flush=True)
            return 130
    return proc.returncode


def main() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    if DONE_FILE.exists():
        DONE_FILE.unlink()

    stamp = time.strftime("%Y%m%d-%H%M")
    started = time.time()
    log_path = LOG_DIR / f"run_all-{stamp}.log"

    failed: list[tuple[str, int]] = []

    for i, ds in enumerate(DATASETS, 1):
        print(f"\n[{i}/{len(DATASETS)}] === {ds} ===", flush=True)
        print(f"  log → {log_path.name}", flush=True)

        attempt = 0
        code = EXIT_FATAL
        while True:
            code = run_fetch(ds, log_path)
            label = EXIT_LABEL.get(code, f"未知({code})")

            if code == EXIT_OK:
                break

            wait = retry_wait_seconds(code, attempt)
            if wait is None:
                break

            attempt += 1
            msg = f"{ds} {label}（第 {attempt} 次重試前等待）"
            print(f"  … {msg}", flush=True)
            # 同一種等待狀態只在第一次通知，之後的退避迴圈不再狂彈。
            if attempt == 1:
                if code == EXIT_QUOTA:
                    notify_error("額度用盡", f"{ds} 402，等待 {wait // 60} 分鐘後自動續抓")
                else:
                    notify_error(f"{ds} {label}", f"等待 {wait} 秒後自動續抓")
            time.sleep(wait)

        if code == EXIT_OK:
            print(f"  完成（{time.time() - started:.1f}h 累計）", flush=True)
            notify(f"第 {i}/{len(DATASETS)} 個完成", ds)
        else:
            failed.append((ds, code))
            print(f"  !! {ds} 放棄：{EXIT_LABEL.get(code, code)}", flush=True)

        # dataset 沒完成（額度/斷線重試用盡）就別往下跑，
        # 續傳是安全的，但一路空轉只會浪費額度。
        if code != EXIT_OK and code != EXIT_PARTIAL:
            print(f"  中止：{ds} 未完成，後續 dataset 等下次續抓。", flush=True)
            break

    elapsed = (time.time() - started) / 3600

    if not failed:
        DONE_FILE.write_text(
            f"全部 {len(DATASETS)} 個 dataset 抓取完成\n"
            f"結束時間：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"耗時：{elapsed:.1f} 小時\n"
            f"log：{log_path}\n",
            encoding="utf-8",
        )
        print(f"\n全部完成，耗時 {elapsed:.1f} 小時。可以進行階段 2。", flush=True)
        notify("全部完成", f"{len(DATASETS)} 個 dataset，耗時 {elapsed:.1f} 小時")
        return

    # 有 dataset 沒抓完 → 絕不寫 ALL_DONE.txt。
    # 寫一份失敗清單並通知，避免掛機一整夜最後是壞的。
    detail = "\n".join(f"{ds}: {EXIT_LABEL.get(code, code)}" for ds, code in failed)
    partial_path = LOG_DIR / f"PARTIAL-{stamp}.txt"
    partial_path.write_text(
        f"未完成 {len(failed)} 個 dataset\n"
        f"結束時間：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"耗時：{elapsed:.1f} 小時\n"
        f"log：{log_path}\n\n"
        f"{detail}\n",
        encoding="utf-8",
    )
    print(f"\n未完成，詳情見 {partial_path.name}。", flush=True)
    notify_error("抓取未完成", f"{len(failed)} 個 dataset 失敗，見 {partial_path.name}")
    sys.exit(failed[0][1] or EXIT_FATAL)


if __name__ == "__main__":
    main()
