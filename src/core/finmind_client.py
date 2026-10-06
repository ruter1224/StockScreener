"""FinMind API client：分級重試 + 速率控制 + 錯誤訊息判讀。

設計要點（依 2026-10-06 實測結論）：
- 免 token 即可取用多數 dataset；token 僅用於查詢額度
- 錯誤必須看 msg 內容，不能只看 HTTP code
- 免費層可用的是「逐檔查詢」，全域查詢需付費方案
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.finmindtrade.com/api/v4/data"
USER_INFO_URL = "https://api.web.finmindtrade.com/v2/user_info"

# 免費層實測速率上限為 600 次/小時（/v2/user_info 回報值）。
# 每小時用 540 次，留 60 次緩衝給重試與驗證。
REQUESTS_PER_HOUR = 540


class FetchError(Enum):
    """錯誤分類。判斷依據是 msg 內容，不是 HTTP code。"""

    OK = "ok"
    NOT_FOUND = "dataset 不存在（含名稱大小寫錯誤）"
    NEEDS_SUBSCRIPTION = "需付費方案（全域查詢或高階 dataset）"
    BAD_PARAMS = "參數錯誤"
    NO_TOKEN = "需要 token"
    QUOTA_EXCEEDED = "額度用盡（402）"
    IP_BANNED = "IP 被封鎖"
    SERVER_ERROR = "伺服器錯誤（可重試）"
    NETWORK = "網路錯誤（可重試）"
    UNKNOWN = "未分類"


@dataclass
class Response:
    status_code: int
    kind: FetchError
    rows: int
    data: list[dict[str, Any]]
    msg: str

    @property
    def ok(self) -> bool:
        return self.kind is FetchError.OK


class CircuitBreaker:
    """4xx 熔斷器。

    ⚠️ 依官方 IP 封鎖政策（https://finmind.github.io/BanIPPolicy/）：
    「短時間內該 IP 累積大量 4xx 請求（例如：無效 token、Token 格式錯誤、
    **參數錯誤**、超額請求等）將觸發自動封鎖」，
    被封鎖回 `403 {"msg": "ip banned"}`，**30 分鐘**自動解除。

    官方建議第 2 條：「4xx 通常是請求本身的問題……請修正參數後再送，
    **不要無限 retry**」。

    => 因此同一個參數錯誤若在多檔股票上重複發生，就是累積 4xx。
    本熔斷器在連續 N 次 4xx 後**立即停止整個抓取**，
    不再重試、不再繼續下一檔，交由人工判斷。
    """

    def __init__(self, threshold: int = 3) -> None:
        self.threshold = threshold
        self.consecutive = 0

    def record(self, kind: FetchError) -> None:
        """回報一次錯誤結果。回 True 代表已熔斷，應立即停止。"""
        if kind in (
            FetchError.BAD_PARAMS,
            FetchError.NEEDS_SUBSCRIPTION,
            FetchError.NOT_FOUND,
            FetchError.NO_TOKEN,
        ):
            self.consecutive += 1
        elif kind in (FetchError.SERVER_ERROR, FetchError.NETWORK):
            # 5xx / 網路錯誤不算 4xx，不累計
            return
        else:
            # 成功則重置
            self.consecutive = 0
            return

        if self.consecutive >= self.threshold:
            raise CircuitOpen(
                f"連續 {self.consecutive} 次 4xx，已停止抓取以免累積 4xx 觸發 IP 封鎖"
                f"（官方政策：30 分鐘自動解除）。"
                f"請先確認參數或方案權限，再用 --retry-errors 續跑。"
            )


class CircuitOpen(Exception):
    """4xx 累積過多，停止抓取。"""


def classify(status_code: int, msg: str) -> FetchError:
    """把 HTTP code + msg 轉成錯誤分類。

    實測對照（見 data-source-verification.md 測試 24.2、26.3）：
      400 "parameter data_id don't provide"  → BAD_PARAMS（全域型別帶了 data_id）
      400 "Your level is free/register"      → NEEDS_SUBSCRIPTION
      422 enum 錯誤                           → NOT_FOUND
      402 "Requests reach the upper limit"   → QUOTA_EXCEEDED
    """
    m = msg or ""

    if status_code == 200:
        return FetchError.OK
    if "don't provide" in m or "start_date" in m or "parameter" in m:
        return FetchError.BAD_PARAMS
    if "level is" in m:
        return FetchError.NEEDS_SUBSCRIPTION
    if status_code == 422:
        return FetchError.NOT_FOUND
    if status_code == 402 or "upper limit" in m:
        return FetchError.QUOTA_EXCEEDED
    if "ip banned" in m or status_code == 403:
        return FetchError.IP_BANNED
    if status_code in (401, 407):
        return FetchError.NO_TOKEN
    if status_code >= 500:
        return FetchError.SERVER_ERROR
    if status_code >= 400:
        return FetchError.BAD_PARAMS
    if status_code == 0:
        # 連線層級失敗（DNS、逾時、連線遭拒），等同網路錯誤
        return FetchError.NETWORK
    return FetchError.UNKNOWN


class RateLimiter:
    """令牌桶。保證不超過 REQUESTS_PER_HOUR，並支援暫停（額度用盡時）。"""

    def __init__(self, per_hour: int = REQUESTS_PER_HOUR) -> None:
        self.per_hour = per_hour
        self.min_interval = 3600.0 / per_hour
        self._last = 0.0
        self.request_count = 0

    def wait(self) -> None:
        now = time.monotonic()
        gap = now - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.monotonic()
        self.request_count += 1

    def pause(self, seconds: float) -> None:
        time.sleep(seconds)
        self._last = time.monotonic()


def load_token(env_path: Path = Path(".env")) -> str | None:
    """從 .env 讀 token。回傳 None 表示未設定（多數 dataset 不需要）。"""
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("FINMIND_TOKEN="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            return value or None
    return None


class FinMindClient:
    def __init__(
        self,
        token: str | None = None,
        limiter: RateLimiter | None = None,
        timeout: int = 40,
        max_retries: int = 3,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self.limiter = limiter or RateLimiter()
        self.breaker = breaker or CircuitBreaker()
        self.session = requests.Session()

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def fetch(
        self,
        dataset: str,
        data_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Response:
        """抓取單一 dataset（可指定 data_id）。含重試與速率控制。"""
        params: dict[str, str] = {"dataset": dataset}
        if data_id:
            params["data_id"] = data_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        last: Response | None = None

        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            try:
                r = self.session.get(
                    BASE_URL, params=params, headers=self._headers(), timeout=self.timeout
                )
            except requests.RequestException as e:
                last = Response(0, FetchError.NETWORK, 0, [], str(e)[:120])
                if attempt < self.max_retries:
                    self.limiter.pause(2**attempt)
                    continue
                return last

            msg = ""
            try:
                body = r.json()
                msg = str(body.get("msg", "")) if isinstance(body, dict) else ""
                data = body.get("data") or [] if isinstance(body, dict) else []
            except ValueError:
                msg, data = r.text[:120], []

            kind = classify(r.status_code, msg)
            last = Response(r.status_code, kind, len(data), data, msg)

            # 熔斷檢查：連續 4xx 會拋出 CircuitOpen，由呼叫端決定是否續跑
            self.breaker.record(kind)

            if kind is FetchError.OK:
                return last

            # 只重試可重試的錯誤（5xx / 網路）
            if kind in (FetchError.SERVER_ERROR, FetchError.NETWORK):
                if attempt < self.max_retries:
                    self.limiter.pause(2**attempt)
                    continue

            return last

        return last or Response(0, FetchError.UNKNOWN, 0, [], "no response")

    def quota(self) -> dict[str, Any]:
        """查詢額度。需要 token。"""
        if not self.token:
            return {"error": "需要 token 才能查額度"}
        r = self.session.get(
            USER_INFO_URL, headers=self._headers(), timeout=self.timeout
        )
        try:
            body = r.json()
            if isinstance(body, dict):
                return {
                    "level": body.get("level_title"),
                    "limit_hour": body.get("api_request_limit_hour"),
                    "used": body.get("user_count"),
                }
        except ValueError:
            pass
        return {"error": f"HTTP {r.status_code}"}