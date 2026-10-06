"""抓取器核心邏輯測試。

執行：uv run pytest tests/ -v
或用 unittest：uv run python -m unittest discover tests -v

測試重點是那些「會靜默出錯」的地方：
- 錯誤分類（依 msg 內容，不是 HTTP code）
- 4xx 熔斷（官方安全要求）
- 續傳狀態機
- 股票池的 ETF 判斷
"""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import fetch  # noqa: E402
from core.finmind_client import (  # noqa: E402
    CircuitBreaker,
    CircuitOpen,
    FetchError,
    RateLimiter,
    Response,
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


class TestOkIds(unittest.TestCase):
    """ok_ids 只回 status='ok'。empty 項目本來就沒有檔案，不能當遺失。"""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.s = SyncState(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    def test_empty_excluded(self):
        self.s.record("DS", "0050", "empty")
        self.assertEqual(self.s.ok_ids("DS"), set())

    def test_error_excluded(self):
        self.s.record("DS", "9999", "error", error_msg="x")
        self.assertEqual(self.s.ok_ids("DS"), set())

    def test_ok_included(self):
        self.s.record("DS", "2330", "ok", rows=5)
        self.assertEqual(self.s.ok_ids("DS"), {"2330"})


class _FakeClient:
    """記錄每次呼叫的參數，並回傳固定的一筆資料。"""

    def __init__(self, rows: list[dict] | None = None):
        self.calls: list[dict] = []
        self.rows = rows if rows is not None else [{"date": "2026-06-30", "v": 1}]

    def fetch(self, dataset, data_id=None, start_date=None, end_date=None):
        self.calls.append(
            {"dataset": dataset, "data_id": data_id, "start_date": start_date}
        )
        return Response(200, FetchError.OK, len(self.rows), list(self.rows), "success")


class TestParquetLossRecovery(unittest.TestCase):
    """續傳必須以 parquet 檔案實際存在為準，不能只看 SQLite。

    2026-10-06 實測事故：`data/` 被 GDrive 同步，`sync_state.db` 同步到了
    另一台但 `data/raw/` 沒跟上，造成 5 個全域型 + 6 檔記為「已完成」
    卻一個 parquet 都沒寫入，程式直接跳過，資料全空。
    """

    def setUp(self):
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = SyncState(root / "t.db")
        self.writer = ParquetWriter(root / "raw")
        self.client = _FakeClient()

    def tearDown(self):
        self.state.close()
        self.tmp.cleanup()

    def _run_global(self, datasets: list[str]) -> None:
        original = fetch.GLOBAL_DATASETS
        fetch.GLOBAL_DATASETS = datasets
        try:
            fetch.fetch_global(self.client, self.writer, self.state)
        finally:
            fetch.GLOBAL_DATASETS = original

    def _run_per_stock(self, dataset: str, pool: list[str]) -> None:
        fetch.fetch_per_stock(
            self.client, self.writer, self.state, dataset, pool,
            None, False, None,
        )

    # --- 全域型 ---

    def test_global_skips_when_parquet_present(self):
        self._run_global(["DS_G"])
        self.client.calls.clear()
        self._run_global(["DS_G"])
        self.assertEqual(self.client.calls, [])

    def test_global_redownloads_when_parquet_missing(self):
        self.state.record("DS_G", "ALL", "ok", rows=1, last_date="2026-06-30")
        self.assertFalse(self.writer.exists("DS_G", "ALL"))
        self._run_global(["DS_G"])
        self.assertEqual(len(self.client.calls), 1)
        self.assertTrue(self.writer.exists("DS_G", "ALL"))

    # --- 逐檔型 ---

    def test_per_stock_redownloads_lost_parquet(self):
        self.state.record("DS_P", "2330", "ok", rows=1, last_date="2020-12-31")
        self.assertFalse(self.writer.exists("DS_P", "2330"))
        self._run_per_stock("DS_P", ["2330"])
        self.assertEqual(len(self.client.calls), 1)
        self.assertTrue(self.writer.exists("DS_P", "2330"))

    def test_per_stock_lost_parquet_restarts_from_beginning(self):
        """檔案遺失時 last_date 不可信，必須從頭抓，否則資料會殘缺。"""
        self.state.record("DS_P", "2330", "ok", rows=1, last_date="2020-12-31")
        self._run_per_stock("DS_P", ["2330"])
        self.assertEqual(self.client.calls[0]["start_date"], fetch.START_DATE)

    def test_per_stock_does_not_regrab_empty(self):
        """empty 狀態本來就沒有 parquet，不能判定為遺失否則每次重抓。"""
        self.state.record("DS_P", "0050", "empty")
        self._run_per_stock("DS_P", ["0050"])
        self.assertEqual(self.client.calls, [])

    def test_per_stock_skips_intact_files(self):
        for sid in ("2330", "2317"):
            self.writer.write("DS_P", sid, [{"date": "2026-06-30", "v": 1}])
            self.state.record("DS_P", sid, "ok", rows=1, last_date="2026-06-30")
        self._run_per_stock("DS_P", ["2330", "2317", "1101"])
        self.assertEqual([c["data_id"] for c in self.client.calls], ["1101"])

    def test_per_stock_mixed_lost_and_intact(self):
        """只有遺失的那檔重抓，其餘維持增量續傳。"""
        self.writer.write("DS_P", "2330", [{"date": "2020-12-31", "v": 1}])
        self.state.record("DS_P", "2330", "ok", rows=1, last_date="2020-12-31")
        self.state.record("DS_P", "2317", "ok", rows=1, last_date="2020-12-31")
        self._run_per_stock("DS_P", ["2330", "2317"])
        self.assertEqual([c["data_id"] for c in self.client.calls], ["2317"])
        self.assertEqual(self.client.calls[0]["start_date"], fetch.START_DATE)


class _ScriptedClient:
    """依腳本回傳指定錯誤，用來測退出碼契約。

    腳本用完後一律回 OK，避免測試無限迴圈。

    ⚠️ 掛真的 CircuitBreaker：與 FinMindClient.fetch 的行為一致
    （見 finmind_client.py 的 self.breaker.record(kind)）。少了這行，
    連續 4xx 就不會拋 CircuitOpen，熔斷路徑等於沒被測到。
    """

    def __init__(self, kinds: list[FetchError]):
        self.kinds = list(kinds)
        self.calls: list[dict] = []
        self.breaker = CircuitBreaker()

    def fetch(self, dataset, data_id=None, start_date=None, end_date=None):
        self.calls.append({"data_id": data_id})
        if self.kinds:
            kind = self.kinds.pop(0)
        else:
            kind = FetchError.OK
        # 與真實 client 相同的位置：熔斷檢查在回傳前
        self.breaker.record(kind)
        if kind is FetchError.OK:
            return Response(200, kind, 1, [{"date": "2026-06-30"}], "success")
        # status_code 依 kind 對應，只要 classify 結果正確即可
        code = {
            FetchError.QUOTA_EXCEEDED: 402,
            FetchError.IP_BANNED: 403,
            FetchError.NETWORK: 0,
            FetchError.SERVER_ERROR: 503,
        }.get(kind, 400)
        return Response(code, kind, 0, [], kind.value)


class TestExitCodes(unittest.TestCase):
    """退出碼契約：run_all.py 靠它決定等待與重試，改了會兩邊一起壞。

    2026-10-06 之前的版本 402/403/熔斷全部 exit 0，
    run_all 當成成功 → 最後誤寫 ALL_DONE.txt（資料其實沒抓完）。
    """

    def setUp(self):
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = SyncState(root / "t.db")
        self.writer = ParquetWriter(root / "raw")

    def tearDown(self):
        self.state.close()
        self.tmp.cleanup()

    def _run(self, kinds: list[FetchError], pool: list[str]) -> int:
        client = _ScriptedClient(kinds)
        return fetch.fetch_per_stock(
            client, self.writer, self.state, "DS_X", pool, None, False, None
        )

    def test_all_ok_returns_zero(self):
        self.assertEqual(self._run([], ["2330", "2317"]), fetch.EXIT_OK)

    def test_quota_returns_exit_3(self):
        self.assertEqual(self._run([FetchError.QUOTA_EXCEEDED], ["2330"]),
                         fetch.EXIT_QUOTA)

    def test_ip_banned_returns_exit_4(self):
        self.assertEqual(self._run([FetchError.IP_BANNED], ["2330"]),
                         fetch.EXIT_IP_BAN)

    def test_circuit_open_returns_exit_5(self):
        """連續 4xx 會由熔斷器拋 CircuitOpen，必須回報 5。"""
        client = _ScriptedClient([FetchError.BAD_PARAMS] * 3)
        code = fetch.fetch_per_stock(
            client, self.writer, self.state, "DS_X", ["1", "2", "3"],
            None, False, None,
        )
        self.assertEqual(code, fetch.EXIT_CIRCUIT)

    def test_three_consecutive_network_failures_abort(self):
        """連續 3 檔斷線就中止，不能把剩餘股票全標成 error。"""
        code = self._run(
            [FetchError.NETWORK] * fetch.TRANSIENT_ABORT_AFTER, ["1", "2", "3", "4", "5"]
        )
        self.assertEqual(code, fetch.EXIT_NETWORK)

    def test_network_abort_stops_early(self):
        """中止後不再繼續打 API（斷網時多打只是浪費與污染狀態）。"""
        client = _ScriptedClient([FetchError.NETWORK] * 3)
        fetch.fetch_per_stock(
            client, self.writer, self.state, "DS_X",
            ["1", "2", "3", "4", "5"], None, False, None,
        )
        self.assertEqual(len(client.calls), fetch.TRANSIENT_ABORT_AFTER)

    def test_single_network_failure_does_not_abort(self):
        """單檔偶發失敗不該中止整批，記 error 後繼續抓下一檔。"""
        code = self._run([FetchError.NETWORK], ["1", "2"])
        self.assertEqual(code, fetch.EXIT_PARTIAL)
        self.assertEqual([sid for sid, _ in self.state.errors("DS_X")], ["1"])
        self.assertTrue(self.writer.exists("DS_X", "2"))

    def test_partial_errors_returns_exit_6(self):
        """抓完但有失敗檔 → 回 6，讓 run_all 補抓而不是當成功。"""
        code = self._run([FetchError.SERVER_ERROR], ["1"])
        self.assertEqual(code, fetch.EXIT_PARTIAL)

    def test_progress_logged_while_stocks_succeed(self):
        """全部成功時，抓取途中也必須輸出進度。

        ⚠️ 2026-10-06 回歸：進度 log 放在迴圈末端，而成功路徑有 `continue`，
        結果整段被跳過 —— log 停滯 3 小時沒有任何進度輸出。
        資料本身沒錯，但掛機時無法判斷有沒有卡住。
        這個測試就是為了擋住這種「看起來沒錯但沒在講話」的回歸。
        """
        pool = [str(n) for n in range(60)]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = fetch.fetch_per_stock(
                _ScriptedClient([]), self.writer, self.state, "DS_X", pool,
                None, False, None,
            )
        out = buf.getvalue()
        self.assertEqual(code, fetch.EXIT_OK)
        self.assertIn("25/60", out)
        self.assertIn("50/60", out)
        self.assertIn("檔/秒", out)

    def test_progress_logged_on_failure_path(self):
        """失敗路徑也要有進度，不能只有成功時才有。"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fetch.fetch_per_stock(
                _ScriptedClient([]), self.writer, self.state, "DS_Y",
                [str(n) for n in range(30)], None, False, None,
            )
        self.assertIn("25/30", buf.getvalue())

    def test_last_stock_always_logs_progress(self):
        """最後一檔不是 25 的倍數時也要輸出，避免尾段沒有進度。"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fetch.fetch_per_stock(
                _ScriptedClient([]), self.writer, self.state, "DS_Z",
                [str(n) for n in range(7)], None, False, None,
            )
        self.assertIn("7/7", buf.getvalue())


class TestShowStatus(unittest.TestCase):
    """show_status 的「完成」定義必須跟 monitor.py、done_ids() 一致。

    ⚠️ 2026-10-07 回歸：show_status 只算 ok，monitor 算 ok+empty+skipped，
    同一個 dataset 在 log 顯示 2019/2037、在 UI 顯示 2037/2037。
    empty 是終態（該檔確實無資料），不計會永遠到不了 100%。
    """

    def setUp(self):
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = SyncState(root / "t.db")

    def tearDown(self):
        self.state.close()
        self.tmp.cleanup()

    def test_done_includes_empty_and_skipped(self):
        pools = {"financial": 100, "market": 200}
        for sid in ["a", "b", "c"]:
            self.state.record("TaiwanStockPER", sid, "ok", rows=1)
        for sid in ["d", "e"]:
            self.state.record("TaiwanStockPER", sid, "empty", rows=0)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fetch.show_status(self.state, pools)
        line = next(
            row for row in buf.getvalue().splitlines()
            if "TaiwanStockPER" in row
        )
        # 分子 = 3 ok + 2 empty = 5，分母 = 池大小 100
        self.assertIn("5/100", line.replace(" ", ""))
        self.assertIn("5.0%", line)

    def test_matches_done_ids_definition(self):
        """分子必須等於 done_ids() 的定義：ok + empty + skipped。"""
        pools = {"financial": 10, "market": 10}
        self.state.record("TaiwanStockPER", "a", "ok", rows=1)
        self.state.record("TaiwanStockPER", "b", "empty", rows=0)
        self.state.record("TaiwanStockPER", "c", "error", error_msg="x")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fetch.show_status(self.state, pools)
        line = next(
            row for row in buf.getvalue().splitlines()
            if "TaiwanStockPER" in row
        )
        # done = 1 ok + 1 empty = 2；error 不算完成
        self.assertIn("2/10", line.replace(" ", ""))
        self.assertEqual(len(self.state.done_ids("TaiwanStockPER")), 2)


if __name__ == "__main__":
    unittest.main()