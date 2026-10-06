"""run_all.py 重試策略測試。

執行：uv run python -m unittest discover tests -v

重點：退出碼 → 等待秒數 → 何時放棄。這條規則決定「斷線能不能自己回來」
與「額度用盡會不會誤報完成」，是掛機 28 小時的核心保險。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import run_all  # noqa: E402


class TestRetryWaitSeconds(unittest.TestCase):
    def test_fatal_never_retries(self):
        self.assertIsNone(run_all.retry_wait_seconds(run_all.EXIT_FATAL, 0))

    def test_circuit_never_retries(self):
        """4xx 熔斷官方要求人工確認，不能自動盲重試。"""
        self.assertIsNone(run_all.retry_wait_seconds(run_all.EXIT_CIRCUIT, 0))

    def test_network_backoff_starts_at_60s(self):
        self.assertEqual(run_all.retry_wait_seconds(run_all.EXIT_NETWORK, 0), 60)

    def test_network_backoff_doubles(self):
        self.assertEqual(run_all.retry_wait_seconds(run_all.EXIT_NETWORK, 1), 120)
        self.assertEqual(run_all.retry_wait_seconds(run_all.EXIT_NETWORK, 2), 240)

    def test_network_backoff_capped(self):
        """退避封頂 900 秒，不要 2^n 放大到幾小時。"""
        self.assertEqual(run_all.retry_wait_seconds(run_all.EXIT_NETWORK, 10), 900)
        self.assertEqual(run_all.retry_wait_seconds(run_all.EXIT_NETWORK, 100), 900)

    def test_network_never_gives_up(self):
        """斷線重試無上限——掛機就該等網路回來。"""
        self.assertIsNotNone(run_all.retry_wait_seconds(run_all.EXIT_NETWORK, 999))

    def test_quota_waits_one_hour(self):
        self.assertEqual(run_all.retry_wait_seconds(run_all.EXIT_QUOTA, 0), 3600)

    def test_quota_gives_up_after_four_retries(self):
        """4 次（4 小時）後放棄，避免無限空轉。"""
        self.assertEqual(run_all.retry_wait_seconds(run_all.EXIT_QUOTA, 3), 3600)
        self.assertIsNone(run_all.retry_wait_seconds(run_all.EXIT_QUOTA, 4))

    def test_ip_ban_waits_31_minutes(self):
        """官方 30 分鐘自動解除，多等 1 分鐘。"""
        self.assertEqual(run_all.retry_wait_seconds(run_all.EXIT_IP_BAN, 0), 1860)

    def test_ip_ban_gives_up_after_three(self):
        self.assertEqual(run_all.retry_wait_seconds(run_all.EXIT_IP_BAN, 2), 1860)
        self.assertIsNone(run_all.retry_wait_seconds(run_all.EXIT_IP_BAN, 3))

    def test_partial_waits_two_minutes(self):
        self.assertEqual(run_all.retry_wait_seconds(run_all.EXIT_PARTIAL, 0), 120)

    def test_partial_gives_up_after_two(self):
        self.assertIsNone(run_all.retry_wait_seconds(run_all.EXIT_PARTIAL, 2))

    def test_unknown_code_does_not_retry(self):
        self.assertIsNone(run_all.retry_wait_seconds(99, 0))


class TestExitCodeContract(unittest.TestCase):
    """run_all 與 fetch 的退出碼必須一致，改一邊忘了另一邊會靜默壞掉。"""

    def test_codes_match_fetch_module(self):
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        import fetch  # noqa: E402

        self.assertEqual(run_all.EXIT_OK, fetch.EXIT_OK)
        self.assertEqual(run_all.EXIT_FATAL, fetch.EXIT_FATAL)
        self.assertEqual(run_all.EXIT_NETWORK, fetch.EXIT_NETWORK)
        self.assertEqual(run_all.EXIT_QUOTA, fetch.EXIT_QUOTA)
        self.assertEqual(run_all.EXIT_IP_BAN, fetch.EXIT_IP_BAN)
        self.assertEqual(run_all.EXIT_CIRCUIT, fetch.EXIT_CIRCUIT)
        self.assertEqual(run_all.EXIT_PARTIAL, fetch.EXIT_PARTIAL)

    def test_all_fetch_exit_codes_have_policy_or_stop(self):
        """每一個退出碼都要有明確歸宿：會重試，或明確不重試。"""
        codes = [
            run_all.EXIT_FATAL, run_all.EXIT_NETWORK, run_all.EXIT_QUOTA,
            run_all.EXIT_IP_BAN, run_all.EXIT_CIRCUIT, run_all.EXIT_PARTIAL,
        ]
        for code in codes:
            first = run_all.retry_wait_seconds(code, 0)
            self.assertTrue(
                first is not None or code in (run_all.EXIT_FATAL, run_all.EXIT_CIRCUIT),
                f"退出碼 {code} 沒有重試策略也沒被列為不可恢復",
            )

    def test_ps_quote_escapes_single_quote(self):
        self.assertEqual(run_all._ps_quote("it's"), "it''s")


if __name__ == "__main__":
    unittest.main()
