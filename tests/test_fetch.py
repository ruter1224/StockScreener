"""抓取器核心邏輯測試。

執行：uv run pytest tests/ -v
或用 unittest：uv run python -m unittest discover tests -v

測試重點是那些「會靜默出錯」的地方：
- 錯誤分類（依 msg 內容，不是 HTTP code）
- 4xx 熔斷（官方安全要求）
- 續傳狀態機
- 股票池的 ETF 判斷
"""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.finmind_client import (  # noqa: E402
    CircuitBreaker,
    CircuitOpen,
    FetchError,
    RateLimiter,
    classify,
    load_token,
)
from storage.sync_state import SyncState  # noqa: E402
from storage.writer import ParquetWriter  # noqa: E402


class TestClassify(unittest.TestCase):
    """錯誤分類必須看 msg 內容，不能只看 HTTP code。

    實測依據見 docs/review/data-source-verification.md 測試 24.2、26.3。
    """

    def test_success(self):
        self.assertIs(classify(200, "success"), FetchError.OK)

    def test_bad_params_data_id(self):
        msg = "parameter data_id don't provide on TaiwanStockInfo dataset"
        self.assertIs(classify(400, msg), FetchError.BAD_PARAMS)

    def test_bad_params_start_date(self):
        self.assertIs(classify(400, "start_date parameter is missing."), FetchError.BAD_PARAMS)

    def test_needs_subscription_without_token(self):
        msg = "Your level is free. Please update your user level."
        self.assertIs(classify(400, msg), FetchError.NEEDS_SUBSCRIPTION)

    def test_needs_subscription_with_token(self):
        msg = "Your level is register. Please update your user level."
        self.assertIs(classify(400, msg), FetchError.NEEDS_SUBSCRIPTION)

    def test_dataset_not_found(self):
        self.assertIs(classify(422, "Input should be 'A', 'B'"), FetchError.NOT_FOUND)

    def test_quota_exceeded_by_status(self):
        self.assertIs(classify(402, ""), FetchError.QUOTA_EXCEEDED)

    def test_quota_exceeded_by_msg(self):
        msg = "Requests reach the upper limit. https://finmindtrade.com/"
        self.assertIs(classify(400, msg), FetchError.QUOTA_EXCEEDED)

    def test_ip_banned(self):
        self.assertIs(classify(403, "ip banned"), FetchError.IP_BANNED)

    def test_server_error(self):
        self.assertIs(classify(500, "internal"), FetchError.SERVER_ERROR)
        self.assertIs(classify(503, ""), FetchError.SERVER_ERROR)

    def test_network_error_zero_status(self):
        self.assertIs(classify(0, "timeout"), FetchError.NETWORK)


class TestCircuitBreaker(unittest.TestCase):
    """4xx 熔斷：官方明載累積 4xx 會被封鎖 IP 30 分鐘。"""

    def test_4xx_trips_after_threshold(self):
        b = CircuitBreaker(threshold=3)
        for _ in range(2):
            b.record(FetchError.BAD_PARAMS)
        with self.assertRaises(CircuitOpen):
            b.record(FetchError.BAD_PARAMS)

    def test_success_resets_counter(self):
        b = CircuitBreaker(threshold=3)
        b.record(FetchError.BAD_PARAMS)
        b.record(FetchError.BAD_PARAMS)
        b.record(FetchError.OK)          # 成功後歸零
        b.record(FetchError.BAD_PARAMS)   # 不應觸發
        b.record(FetchError.BAD_PARAMS)

    def test_5xx_does_not_count(self):
        b = CircuitBreaker(threshold=3)
        for _ in range(10):
            b.record(FetchError.SERVER_ERROR)
            b.record(FetchError.NETWORK)
        b.record(FetchError.BAD_PARAMS)   # 只有 1 次 4xx

    def test_different_4xx_types_all_count(self):
        """不同類型的 4xx 都算入累積，混合也要能觸發。"""
        b = CircuitBreaker(threshold=3)
        b.record(FetchError.BAD_PARAMS)
        b.record(FetchError.NOT_FOUND)
        with self.assertRaises(CircuitOpen):
            b.record(FetchError.NEEDS_SUBSCRIPTION)


class TestRateLimiter(unittest.TestCase):
    def test_interval_math(self):
        rl = RateLimiter(per_hour=600)
        self.assertAlmostEqual(rl.min_interval, 6.0, places=3)

    def test_custom_rate(self):
        rl = RateLimiter(per_hour=540)
        self.assertAlmostEqual(rl.min_interval, 3600 / 540, places=3)


class TestSyncState(unittest.TestCase):
    """續傳狀態機：2765 檔要跑數小時，中斷續傳是硬需求。"""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.s = SyncState(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    def test_first_run_all_pending(self):
        self.assertEqual(self.s.done_ids("DS"), set())

    def test_done_ids_includes_empty(self):
        """空結果也要標記完成，否則每次 rerun 會重抓。"""
        self.s.record("DS", "2330", "ok", rows=10, last_date="2026-06-30")
        self.s.record("DS", "0050", "empty", rows=0)
        self.assertEqual(self.s.done_ids("DS"), {"2330", "0050"})

    def test_done_ids_excludes_error(self):
        self.s.record("DS", "2330", "ok", rows=10)
        self.s.record("DS", "9999", "error", error_msg="boom")
        self.assertEqual(self.s.done_ids("DS"), {"2330"})

    def test_upsert_overwrites(self):
        self.s.record("DS", "2330", "error", error_msg="x")
        self.s.record("DS", "2330", "ok", rows=5, last_date="2026-06-30")
        self.assertEqual(self.s.done_ids("DS"), {"2330"})
        self.assertEqual(self.s.last_date("DS", "2330"), "2026-06-30")

    def test_last_date_only_for_ok(self):
        self.s.record("DS", "2330", "empty", rows=0, last_date="2026-01-01")
        self.assertIsNone(self.s.last_date("DS", "2330"))

    def test_errors_listed(self):
        self.s.record("DS", "1", "error", error_msg="a")
        self.s.record("DS", "2", "error", error_msg="b")
        self.s.record("DS", "3", "ok", rows=1)
        self.assertEqual(len(self.s.errors("DS")), 2)

    def test_stats(self):
        self.s.record("DS", "1", "ok", rows=1)
        self.s.record("DS", "2", "empty")
        self.s.record("DS", "3", "error", error_msg="x")
        st = self.s.stats("DS")
        self.assertEqual(st["ok"], 1)
        self.assertEqual(st["empty"], 1)
        self.assertEqual(st["error"], 1)

    def test_persistence_across_reopen(self):
        """重開 DB 後資料必須還在，這是中斷後能續傳的前提。"""
        self.s.record("DS", "2330", "ok", rows=10)
        self.s.close()
        s2 = SyncState(Path(self.tmp.name) / "t.db")
        self.assertEqual(s2.done_ids("DS"), {"2330"})
        s2.close()

    def test_run_log(self):
        rid = self.s.start_run("DS", 100)
        self.s.finish_run(rid, 100, "done")
        # 只需不拋例外


class TestParquetWriter(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.w = ParquetWriter(Path(self.tmp.name) / "raw")

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_and_read(self):
        rows = [{"date": "2026-06-30", "type": "Revenue", "value": 381.2}]
        self.w.write("DS", "2330", rows)
        df = self.w.read("DS", "2330")
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["type"], "Revenue")

    def test_empty_rows_no_file(self):
        """空結果不寫檔，避免產生數千個空 parquet。"""
        result = self.w.write("DS", "0050", [])
        self.assertIsNone(result)
        self.assertFalse(self.w.exists("DS", "0050"))

    def test_exists(self):
        self.assertFalse(self.w.exists("DS", "2330"))
        self.w.write("DS", "2330", [{"a": 1}])
        self.assertTrue(self.w.exists("DS", "2330"))

    def test_read_missing_returns_empty(self):
        self.assertEqual(len(self.w.read("DS", "9999")), 0)

    def test_count_files(self):
        for i in range(3):
            self.w.write("DS", str(2330 + i), [{"a": i}])
        self.assertEqual(self.w.count_files("DS"), 3)


class TestLoadToken(unittest.TestCase):
    def test_missing_file_returns_none(self):
        self.assertIsNone(load_token(Path("不存在的檔案.env")))

    def test_empty_value_returns_none(self):
        with TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("FINMIND_TOKEN=\n", encoding="utf-8")
            self.assertIsNone(load_token(p))

    def test_reads_value(self):
        with TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("FINMIND_TOKEN=abc123\n", encoding="utf-8")
            self.assertEqual(load_token(p), "abc123")

    def test_strips_quotes(self):
        with TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text('FINMIND_TOKEN="xyz"\n', encoding="utf-8")
            self.assertEqual(load_token(p), "xyz")


if __name__ == "__main__":
    unittest.main()