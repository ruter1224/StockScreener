# 依序抓完全部 dataset，可中斷續傳。
#
# 用法：
#   開個 PowerShell 視窗，cd 到專案目錄，執行 .venv\Scripts\python.exe run_all.py
#   視窗不要關，關掉就停（Ctrl+C 可安全中斷，重跑會續傳）
#
# 為什麼需要這支：
#   fetch.py 一次只跑一個 dataset，跑完要人接下一個。
#   掛機時人在不在都要能一路跑到底，所以要有迴圈。

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


def notify(title: str, message: str) -> None:
    """Windows 通知。失敗就算了，不影響抓取。"""
    ps = (
        "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
        "$n = New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon = [System.Drawing.SystemIcons]::Information;"
        f"$n.BalloonTipTitle = 'StockScreener';"
        f"$n.BalloonTipText = '{title}：{message}';"
        "$n.Visible = $true; $n.ShowBalloonTip(10000); Start-Sleep -Seconds 11"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        check=False,
        timeout=30,
    )


def notify_error(title: str, message: str) -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms')|Out-Null;"
            "$n=New-Object System.Windows.Forms.NotifyIcon;"
            "$n.Icon=[System.Drawing.SystemIcons]::Error;"
            f"$n.BalloonTipTitle='StockScreener';$n.BalloonTipText='{title}：{message}';"
            "$n.Visible=$true;$n.ShowBalloonTip(30000);Start-Sleep -Seconds 31",
        ],
        check=False,
        timeout=45,
    )


def main() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    if DONE_FILE.exists():
        DONE_FILE.unlink()

    stamp = time.strftime("%Y%m%d-%H%M")
    started = time.time()

    for i, ds in enumerate(DATASETS, 1):
        log_path = LOG_DIR / f"run_all-{stamp}.log"
        print(f"\n[{i}/{len(DATASETS)}] === {ds} ===", flush=True)
        print(f"  log → {log_path.name}", flush=True)

        with log_path.open("a", encoding="utf-8", errors="replace") as fh:
            fh.write(f"\n\n===== {ds} @ {time.strftime('%H:%M:%S')} =====\n")
            fh.flush()
            proc = subprocess.Popen(
                [str(PYTHON), "fetch.py", "--dataset", ds],
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
                sys.exit(130)

        if proc.returncode != 0:
            msg = f"{ds} 異常結束（code {proc.returncode}），查看 {log_path.name}"
            print(f"  !! {msg}", flush=True)
            notify_error("抓取異常", msg)
            sys.exit(proc.returncode)

        print(f"  完成（{time.time() - started:.1f}h 累計）", flush=True)
        notify(f"第 {i}/{len(DATASETS)} 個完成", ds)

    elapsed = (time.time() - started) / 3600
    DONE_FILE.write_text(
        f"全部 {len(DATASETS)} 個 dataset 抓取完成\n"
        f"結束時間：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"耗時：{elapsed:.1f} 小時\n"
        f"log：{LOG_DIR / f'run_all-{stamp}.log'}\n",
        encoding="utf-8",
    )
    print(f"\n全部完成，耗時 {elapsed:.1f} 小時。可以進行階段 2。", flush=True)
    notify("全部完成", f"{len(DATASETS)} 個 dataset，耗時 {elapsed:.1f} 小時")


if __name__ == "__main__":
    main()
