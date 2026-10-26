#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pickup.stagger_seconds 配置项测试（纯本地：只构造 IPhoneDuoMonitor，不发任何请求）

运行：python3 tests/test_stagger_config.py
"""

import os
import sys
import json
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def make_config_dir(stagger=None):
    d = tempfile.mkdtemp(prefix="stagger_test_")
    for name in ("skus.json", "stores.json"):
        shutil.copy(os.path.join(ROOT, name), d)
    with open(os.path.join(ROOT, "config.json"), "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["delivery"]["enabled"] = False
    cfg["power"]["prevent_sleep"] = False
    cfg["state"]["file"] = os.path.join(d, "state.json")
    cfg["logging"]["file"] = os.path.join(d, "monitor.log")
    if stagger is not None:
        cfg["pickup"]["stagger_seconds"] = stagger
    else:
        cfg["pickup"].pop("stagger_seconds", None)
    with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return d


class TestStaggerConfig(unittest.TestCase):
    def _monitor(self, stagger):
        from monitor import IPhoneDuoMonitor
        d = make_config_dir(stagger)
        try:
            return IPhoneDuoMonitor(d, register_signals=False)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_default_unchanged_when_key_absent(self):
        m = self._monitor(None)
        self.assertEqual(m.pickup_stagger_seconds, 30)
        self.assertEqual(m.pickup_region_interval, 30 * len(m.pickup_postcodes))
        self.assertEqual(m.pickup_region_interval, 90)

    def test_configured_value_is_used(self):
        m = self._monitor(60)
        self.assertEqual(m.pickup_stagger_seconds, 60)
        self.assertEqual(m.pickup_region_interval, 180)

    def test_invalid_values_fall_back_to_default(self):
        for bad in ("abc", -5, 0, None):
            m = self._monitor(bad)
            self.assertEqual(m.pickup_stagger_seconds, 30, f"bad value {bad!r} should fall back")

    def test_initial_schedule_staggered_by_configured_value(self):
        import time
        m = self._monitor(60)
        t0 = time.time()
        offsets = sorted(m.pickup_next_check[pc] - t0 for pc in m.pickup_postcodes)
        for i, off in enumerate(offsets):
            self.assertAlmostEqual(off, i * 60, delta=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
