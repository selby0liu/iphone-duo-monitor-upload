#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双源 Cloud 合并逻辑测试（纯本地，不联网）

运行：python3 tests/test_multi_cloud.py
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cloud_client import merge_cloud_statuses, MultiCloudClient, source_summary  # noqa: E402


class TestSourceSummary(unittest.TestCase):
    def test_offline_summary(self):
        s = source_summary("备", "u2", None, "timeout")
        self.assertFalse(s["online"])
        self.assertEqual(s["error"], "timeout")
        self.assertIsNone(s["api_available"])
        self.assertEqual(s["last_request_per_region"], {})
        self.assertEqual(s["inventory_known"], 0)

    def test_online_summary_counts_and_requests(self):
        st = {
            "monitor": {"check_count": 42, "last_check": 5000.0},
            "pickup": {"api_available": True},
            "rate_limiter": {"global_requests_last_60s": 1,
                             "last_request_per_region": {"pickup_510000": 12.3, "pickup_200000": 72.0, "bad": "x"}},
            "inventory": {
                "a|R1": {"available": True, "last_checked": 4900.0},
                "a|R2": {"available": None, "last_checked": 4990.0},
                "b|R1": {"available": False, "last_checked": 4950.0},
                "a|delivery": {"available": False, "last_checked": 4999.0},
            },
        }
        s = source_summary("主", "u1", st, "", active=True)
        self.assertTrue(s["online"] and s["active"] and s["api_available"])
        self.assertEqual(s["check_count"], 42)
        self.assertEqual(s["requests_last_60s"], 1)
        self.assertEqual(s["last_request_per_region"], {"pickup_510000": 12.3, "pickup_200000": 72.0})
        self.assertEqual((s["inventory_known"], s["inventory_unknown"]), (2, 1))
        self.assertEqual(s["newest_known_checked"], 4950.0)  # delivery 键不计入

    def test_merge_exposes_per_source_metrics(self):
        a = {"monitor": {"check_count": 1, "last_check": 10.0}, "pickup": {"api_available": True},
             "rate_limiter": {"global_requests_last_60s": 2, "last_request_per_region": {"pickup_510000": 3.0}},
             "inventory": {"k|R1": {"available": False, "last_checked": 9.0}}}
        merged, _, _ = merge_cloud_statuses([("主", "u1", a, ""), ("备", "u2", None, "down")])
        srcs = {s["label"]: s for s in merged["cloud_sources"]}
        self.assertEqual(srcs["主"]["requests_last_60s"], 2)
        self.assertEqual(srcs["主"]["last_request_per_region"], {"pickup_510000": 3.0})
        self.assertEqual(srcs["主"]["newest_known_checked"], 9.0)
        self.assertFalse(srcs["备"]["online"])


def status(api_available=True, last_check=1000.0, inventory=None, check_count=1):
    return {
        "monitor": {"running": True, "check_count": check_count, "last_check": last_check},
        "pickup": {"api_available": api_available, "last_http_status": 200 if api_available else None},
        "inventory": inventory or {},
        "trends": {"overview": {"current_available_stores": 0, "total_stores": 16}},
    }


def entry(available, ts):
    return {"available": available, "last_checked": ts, "detail": {"store_name": "x"}}


class TestMerge(unittest.TestCase):
    def test_all_offline(self):
        merged, online, err = merge_cloud_statuses([("主", "u1", None, "timeout"), ("备", "u2", None, "refused")])
        self.assertIsNone(merged)
        self.assertFalse(online)
        self.assertIn("主:timeout", err)
        self.assertIn("备:refused", err)

    def test_both_healthy_label_and_newest_wins(self):
        a = status(True, 1000, {"k|R1": entry(False, 1000), "k|R2": entry(True, 900)})
        b = status(True, 1050, {"k|R1": entry(True, 1050), "k|R2": entry(False, 950)})
        merged, online, _ = merge_cloud_statuses([("主", "u1", a, ""), ("备", "u2", b, "")])
        self.assertTrue(online)
        self.assertEqual(merged["cloud_active_label"], "主+备")
        self.assertTrue(merged["pickup"]["api_available"])
        self.assertTrue(merged["inventory"]["k|R1"]["available"])   # 备更新
        self.assertFalse(merged["inventory"]["k|R2"]["available"])  # 备更新
        # 活跃源 = last_check 最新的（备）
        self.assertEqual([s["label"] for s in merged["cloud_sources"] if s["active"]], ["备"])

    def test_known_beats_unknown_even_if_older(self):
        a = status(False, 2000, {"k|R1": entry(None, 2000)})   # 主被 541，UNKNOWN 但更新
        b = status(True, 1900, {"k|R1": entry(True, 1900)})    # 备正常，已知但更旧
        merged, online, _ = merge_cloud_statuses([("主", "u1", a, ""), ("备", "u2", b, "")])
        self.assertTrue(merged["inventory"]["k|R1"]["available"])
        self.assertEqual(merged["cloud_active_label"], "备")
        self.assertTrue(merged["pickup"]["api_available"])
        self.assertEqual([s["label"] for s in merged["cloud_sources"] if s["active"]], ["备"])

    def test_both_unknown_keeps_newest_unknown(self):
        a = status(False, 2000, {"k|R1": entry(None, 2000)})
        b = status(False, 1900, {"k|R1": entry(None, 1900)})
        merged, online, _ = merge_cloud_statuses([("主", "u1", a, ""), ("备", "u2", b, "")])
        self.assertIsNone(merged["inventory"]["k|R1"]["available"])
        self.assertFalse(merged["pickup"]["api_available"])
        self.assertEqual(merged["cloud_active_label"], "主(异常)")

    def test_key_only_in_one_source_is_kept(self):
        a = status(True, 1000, {"k|R1": entry(False, 1000)})
        b = status(True, 1000, {"k|R2": entry(True, 1000)})
        merged, _, _ = merge_cloud_statuses([("主", "u1", a, ""), ("备", "u2", b, "")])
        self.assertEqual(set(merged["inventory"]), {"k|R1", "k|R2"})

    def test_single_source_passthrough(self):
        a = status(True, 1000, {"k|R1": entry(False, 1000)})
        merged, online, _ = merge_cloud_statuses([("主", "u1", a, "")])
        self.assertTrue(online)
        self.assertEqual(merged["cloud_active_label"], "主")
        self.assertEqual(merged["inventory"], a["inventory"])
        self.assertEqual(merged["monitor"]["check_count"], 1)

    def test_backup_offline_primary_ok(self):
        a = status(True, 1000, {"k|R1": entry(False, 1000)})
        merged, online, err = merge_cloud_statuses([("主", "u1", a, ""), ("备", "u2", None, "timeout")])
        self.assertTrue(online)
        self.assertEqual(err, "")
        self.assertEqual(merged["cloud_active_label"], "主")
        srcs = {s["label"]: s for s in merged["cloud_sources"]}
        self.assertFalse(srcs["备"]["online"])
        self.assertEqual(srcs["备"]["error"], "timeout")

    def test_merge_does_not_mutate_inputs(self):
        a = status(True, 1000, {"k|R1": entry(False, 1000)})
        b = status(True, 1100, {"k|R1": entry(True, 1100)})
        merge_cloud_statuses([("主", "u1", a, ""), ("备", "u2", b, "")])
        self.assertFalse(a["inventory"]["k|R1"]["available"])
        self.assertNotIn("cloud_sources", a)
        self.assertNotIn("cloud_sources", b)


class TestMultiCloudClient(unittest.TestCase):
    def test_poll_once_with_injected_fetcher_and_failure(self):
        calls = []

        def fetcher(url, token):
            calls.append((url, token))
            if "bad" in url:
                raise RuntimeError("connection refused")
            return status(True, 1000, {"k|R1": entry(True, 1000)})

        c = MultiCloudClient(["http://good:8765/", "http://bad:8765"], "tok", fetcher=fetcher)
        self.assertEqual(c.server_urls, ["http://good:8765", "http://bad:8765"])
        self.assertEqual(c.labels, ["主", "备"])
        merged, online, err = c.poll_once()
        self.assertTrue(online)
        self.assertEqual(sorted(u for u, _ in calls), ["http://bad:8765", "http://good:8765"])
        self.assertTrue(all(t == "tok" for _, t in calls))
        self.assertEqual(merged["cloud_active_label"], "主")
        srcs = {s["label"]: s for s in merged["cloud_sources"]}
        self.assertIn("connection refused", srcs["备"]["error"])
        ok, msg = c.test_connection()
        self.assertTrue(ok)
        self.assertIn("主: 在线", msg)
        self.assertIn("备: 离线", msg)

    def test_empty_urls_ignored(self):
        c = MultiCloudClient(["http://a:1", "", "   "], "tok", fetcher=lambda u, t: status())
        self.assertEqual(c.server_urls, ["http://a:1"])
        merged, online, _ = c.poll_once()
        self.assertTrue(online)
        self.assertEqual(merged["cloud_active_label"], "主")


if __name__ == "__main__":
    unittest.main(verbosity=2)
