#!/usr/bin/env python3
import os
import sys
import time
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import statusline


class TestQuotaReconcile(unittest.TestCase):
    def test_authoritative_incoming_overwrites_polluted_cache(self):
        """
        When local cache is polluted with a fake reset cycle (e.g. 4 days later),
        the authoritative incoming Antigravity payload (10h later) must win and
        overwrite the cache.
        """
        now = time.time()
        # Stale polluted cache: 4 days in future, 77% used (remaining 0.23)
        polluted_cache = {
            "remaining_fraction": 0.23,
            "reset_at": now + 396000,
            "recorded_at": now - 100,
        }
        # Authoritative incoming: 10h 27m in future, 79% used (remaining 0.21)
        incoming_item = {
            "remaining_fraction": 0.21,
            "reset_in_seconds": 37620,
            "reset_time": "2026-09-16T03:16:38Z",
        }

        resolved, new_cache = statusline.reconcile_quota_item(
            incoming_item, polluted_cache, now, max_ttl=604800.0
        )

        self.assertIsNotNone(resolved)
        self.assertAlmostEqual(resolved["remaining_fraction"], 0.21, places=2)
        self.assertEqual(resolved["reset_in_seconds"], 37620)
        self.assertIsNotNone(new_cache)
        self.assertAlmostEqual(new_cache["remaining_fraction"], 0.21, places=2)
        self.assertEqual(new_cache["recorded_at"], now)

    def test_same_cycle_peer_window_consumed_more(self):
        """
        In the same reset cycle, if a peer window consumed more tokens (lower remaining),
        we should adopt the peer's consumption to reflect cross-window usage.
        """
        now = time.time()
        target_reset = now + 12000
        cached_item = {
            "remaining_fraction": 0.15,  # Peer window consumed more (85% used)
            "reset_at": target_reset,
            "recorded_at": now - 30,
        }
        incoming_item = {
            "remaining_fraction": 0.30,  # Current window is at 70% used
            "reset_in_seconds": 12000,
        }

        resolved, updated_cache = statusline.reconcile_quota_item(
            incoming_item, cached_item, now, max_ttl=18000.0
        )

        self.assertIsNotNone(resolved)
        self.assertAlmostEqual(resolved["remaining_fraction"], 0.15, places=2)
        self.assertEqual(resolved["reset_in_seconds"], 12000)
        self.assertAlmostEqual(updated_cache["remaining_fraction"], 0.15, places=2)

    def test_same_cycle_current_window_consumed_more(self):
        """
        In the same reset cycle, if current window consumed more tokens,
        current window's incoming remaining wins and updates the cache.
        """
        now = time.time()
        target_reset = now + 12000
        cached_item = {
            "remaining_fraction": 0.40,  # Older peer cache at 60% used
            "reset_at": target_reset,
            "recorded_at": now - 60,
        }
        incoming_item = {
            "remaining_fraction": 0.20,  # Current window just consumed down to 80% used
            "reset_in_seconds": 12000,
        }

        resolved, updated_cache = statusline.reconcile_quota_item(
            incoming_item, cached_item, now, max_ttl=18000.0
        )

        self.assertIsNotNone(resolved)
        self.assertAlmostEqual(resolved["remaining_fraction"], 0.20, places=2)
        self.assertEqual(resolved["reset_in_seconds"], 12000)
        self.assertAlmostEqual(updated_cache["remaining_fraction"], 0.20, places=2)

    def test_fallback_when_incoming_missing(self):
        """
        If incoming has no quota data, fallback to valid cache.
        """
        now = time.time()
        cached_item = {
            "remaining_fraction": 0.65,
            "reset_at": now + 5000,
            "recorded_at": now - 10,
        }
        resolved, _ = statusline.reconcile_quota_item(
            None, cached_item, now, max_ttl=18000.0
        )
        self.assertIsNotNone(resolved)
        self.assertAlmostEqual(resolved["remaining_fraction"], 0.65, places=2)
        self.assertEqual(resolved["reset_in_seconds"], 5000)

    def test_allow_cache_write_protection(self):
        """
        Cache writing must be inhibited when allow_write is False.
        """
        original_cache_file = statusline.CACHE_FILE
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            test_cache_path = tf.name

        try:
            statusline.CACHE_FILE = test_cache_path
            # Initial write
            statusline._write_quota_cache({"pools": {}, "updated_at": 100})
            mtime_before = os.path.getmtime(test_cache_path)

            q_5h = {"remaining_fraction": 0.5, "reset_in_seconds": 3600}
            q_wk = {"remaining_fraction": 0.2, "reset_in_seconds": 7200}

            # Call with allow_write=False
            time.sleep(0.05)
            statusline.sync_shared_quotas(q_5h, q_wk, is_3p=False, allow_write=False)
            mtime_after = os.path.getmtime(test_cache_path)
            self.assertEqual(mtime_before, mtime_after)

            # Call with allow_write=True
            statusline.sync_shared_quotas(q_5h, q_wk, is_3p=False, allow_write=True)
            mtime_updated = os.path.getmtime(test_cache_path)
            self.assertGreater(mtime_updated, mtime_before)
        finally:
            statusline.CACHE_FILE = original_cache_file
            if os.path.isfile(test_cache_path):
                os.remove(test_cache_path)


if __name__ == "__main__":
    unittest.main()
