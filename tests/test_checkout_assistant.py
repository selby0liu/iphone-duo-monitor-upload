#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Checkout Assistant 纯本地测试（不联网、不打开浏览器、不产生任何 Apple 请求）

运行：
  python3 tests/test_checkout_assistant.py
  或 python3 -m pytest tests/test_checkout_assistant.py -v

第二部分（GUI 集成 smoke）仅在 PySide6 可用时运行。
"""

import os
import sys
import json
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from checkout_assistant import CheckoutAssistant, CheckoutState  # noqa: E402


class FakeClock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class FakeOpener:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def __call__(self, url, browser):
        self.calls.append((url, browser))
        return self.ok


def hit(part, store_number, store_name, sku_id="", name="", capacity="", color="", city=""):
    return {
        "sku_id": sku_id or part,
        "part_number": part,
        "sku_name": name,
        "capacity": capacity,
        "color": color,
        "store_number": store_number,
        "store_name": store_name,
        "city": city,
    }


NEUTRAL = {"priority_stores_tier1": [], "priority_stores_tier2": [], "open_only_priority": False}


def make(enabled=True, clock=None, opener=None, **cfg):
    config = {"enabled": enabled, **NEUTRAL}
    config.update(cfg)
    return CheckoutAssistant(config, clock=clock or FakeClock(), opener=opener or FakeOpener())


class TestDefaultsAndConfig(unittest.TestCase):
    def test_default_is_disabled_and_safe(self):
        ca = CheckoutAssistant({}, opener=FakeOpener())
        self.assertFalse(ca.enabled)
        self.assertTrue(ca.auto_open_page)
        self.assertFalse(ca.auto_add_to_cart)
        self.assertFalse(ca.auto_fill_details)
        self.assertFalse(ca.auto_start_checkout)
        self.assertEqual(ca.browser, "default")
        self.assertEqual(ca.cooldown_seconds, 600)
        self.assertEqual(ca.min_open_interval_seconds, 20)
        self.assertEqual(ca.max_tabs_per_wave, 2)

    def test_to_config_roundtrip(self):
        ca = make(browser="safari", cooldown_seconds=300, max_tabs_per_wave=1)
        cfg = ca.to_config()
        self.assertEqual(cfg["enabled"], True)
        self.assertEqual(cfg["browser"], "safari")
        self.assertEqual(cfg["cooldown_seconds"], 300)
        self.assertEqual(cfg["max_tabs_per_wave"], 1)
        self.assertFalse(cfg["auto_add_to_cart"])
        self.assertFalse(cfg["auto_fill_details"])
        self.assertFalse(cfg["auto_start_checkout"])
        ca2 = CheckoutAssistant(cfg, opener=FakeOpener())
        self.assertEqual(ca2.to_config(), cfg)

    def test_invalid_browser_falls_back_to_default(self):
        ca = make(browser="chrome-applescript")
        self.assertEqual(ca.browser, "default")

    def test_open_command(self):
        ca = make()
        self.assertEqual(ca.build_open_command("https://x"), ["open", "https://x"])
        ca.browser = "safari"
        self.assertEqual(ca.build_open_command("https://x"), ["open", "-a", "Safari", "https://x"])


class TestBuyUrl(unittest.TestCase):
    def test_product_url_for_both_families(self):
        ca = make()
        self.assertEqual(ca.get_buy_url("MJYC4CH/A"), "https://www.apple.com.cn/shop/product/MJYC4CH/A")
        self.assertEqual(ca.get_buy_url("MK2P4CH/A"), "https://www.apple.com.cn/shop/product/MK2P4CH/A")
        self.assertNotIn("iphone-duo", ca.get_buy_url("MJYC4CH/A"))


class TestDisabled(unittest.TestCase):
    def test_disabled_never_opens_or_changes_state(self):
        opener = FakeOpener()
        ca = make(enabled=False, opener=opener)
        r = ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])
        self.assertEqual(r, [])
        self.assertEqual(opener.calls, [])
        self.assertEqual(ca.state, CheckoutState.IDLE)
        r2 = ca.on_stock_found("duo_512_starlight", "MK2P4CH/A", {"store_number": "R577", "store_name": "天环广场"})
        self.assertEqual(r2, [])
        self.assertEqual(opener.calls, [])


class TestBaseline(unittest.TestCase):
    def test_initial_snapshot_only_establishes_baseline(self):
        opener = FakeOpener()
        clock = FakeClock()
        ca = make(clock=clock, opener=opener)
        r = ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")], initial_snapshot=True)
        self.assertTrue(ca.baseline_established)
        self.assertEqual(opener.calls, [])
        self.assertEqual(len(r), 1)
        self.assertFalse(r[0]["opened"])
        self.assertEqual(r[0]["reason"], "baseline")
        # 基线不占用冷却：紧接着真正的 AVAILABLE 事件可以打开
        r2 = ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])
        self.assertTrue(r2[0]["opened"])
        self.assertEqual(len(opener.calls), 1)


class TestDedupAndCooldown(unittest.TestCase):
    def test_same_sku_multiple_stores_opens_one_tab_with_merged_stores(self):
        opener = FakeOpener()
        ca = make(opener=opener)
        hits = [
            hit("MK2P4CH/A", "R577", "天环广场", name="iPhone Duo 512GB 星光白色", capacity="512GB", color="星光白色"),
            hit("MK2P4CH/A", "R639", "珠江新城", name="iPhone Duo 512GB 星光白色", capacity="512GB", color="星光白色"),
            hit("MK2P4CH/A", "R390", "香港广场", name="iPhone Duo 512GB 星光白色", capacity="512GB", color="星光白色"),
            hit("MK2P4CH/A", "R390", "香港广场", name="iPhone Duo 512GB 星光白色"),  # 重复门店
        ]
        r = ca.on_stock_wave(hits)
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(opener.calls[0], ("https://www.apple.com.cn/shop/product/MK2P4CH/A", "default"))
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0]["opened"])
        self.assertEqual([s["store_number"] for s in r[0]["stores"]], ["R577", "R639", "R390"])
        msg = r[0]["message"]
        for token in ("已打开购买页", "iPhone Duo 512GB 星光白色", "MK2P4CH/A", "512GB", "星光白色",
                      "天环广场(R577)", "珠江新城(R639)", "香港广场(R390)"):
            self.assertIn(token, msg)

    def test_cooldown_600_seconds_per_part(self):
        opener = FakeOpener()
        clock = FakeClock()
        ca = make(clock=clock, opener=opener)
        self.assertTrue(ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])[0]["opened"])
        clock.advance(100)
        r = ca.on_stock_wave([hit("MK2P4CH/A", "R639", "珠江新城")])
        self.assertFalse(r[0]["opened"])
        self.assertEqual(r[0]["reason"], "cooldown")
        clock.advance(499)  # 累计 599
        self.assertEqual(ca.on_stock_wave([hit("MK2P4CH/A", "R639", "珠江新城")])[0]["reason"], "cooldown")
        clock.advance(2)  # 累计 601
        self.assertTrue(ca.on_stock_wave([hit("MK2P4CH/A", "R639", "珠江新城")])[0]["opened"])
        self.assertEqual(len(opener.calls), 2)

    def test_unknown_to_available_flap_is_absorbed_by_cooldown(self):
        opener = FakeOpener()
        clock = FakeClock()
        ca = make(clock=clock, opener=opener)
        ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])
        for _ in range(5):  # 模拟 541 抖动后 UNKNOWN→AVAILABLE 反复触发
            clock.advance(30)
            ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])
        self.assertEqual(len(opener.calls), 1)

    def test_global_min_interval_20_seconds_between_waves(self):
        opener = FakeOpener()
        clock = FakeClock()
        ca = make(clock=clock, opener=opener)
        self.assertTrue(ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])[0]["opened"])
        clock.advance(5)
        r = ca.on_stock_wave([hit("MJYC4CH/A", "R577", "天环广场")])  # 不同 SKU
        self.assertFalse(r[0]["opened"])
        self.assertEqual(r[0]["reason"], "global_interval")
        clock.advance(16)  # 累计 21
        self.assertTrue(ca.on_stock_wave([hit("MJYC4CH/A", "R577", "天环广场")])[0]["opened"])
        self.assertEqual(len(opener.calls), 2)

    def test_max_tabs_per_wave_default_2(self):
        opener = FakeOpener()
        ca = make(opener=opener)
        hits = [
            hit("MK2P4CH/A", "R577", "天环广场"),
            hit("MK2Q4CH/A", "R577", "天环广场"),
            hit("MJYC4CH/A", "R577", "天环广场"),
            hit("MJYE4CH/A", "R577", "天环广场"),
        ]
        r = ca.on_stock_wave(hits)
        self.assertEqual(len(opener.calls), 2)
        self.assertEqual([x["opened"] for x in r], [True, True, False, False])
        self.assertEqual(r[2]["reason"], "wave_cap")
        self.assertEqual(r[3]["reason"], "wave_cap")

    def test_max_tabs_per_wave_configurable(self):
        opener = FakeOpener()
        ca = make(opener=opener, max_tabs_per_wave=1)
        r = ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场"), hit("MJYC4CH/A", "R577", "天环广场")])
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual([x["opened"] for x in r], [True, False])

    def test_auto_open_off_does_not_open(self):
        opener = FakeOpener()
        ca = make(opener=opener, auto_open_buy_page=False)
        r = ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])
        self.assertEqual(opener.calls, [])
        self.assertEqual(r[0]["reason"], "auto_open_disabled")

    def test_open_failure_does_not_consume_cooldown(self):
        opener = FakeOpener(ok=False)
        clock = FakeClock()
        ca = make(clock=clock, opener=opener)
        r = ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])
        self.assertFalse(r[0]["opened"])
        self.assertEqual(r[0]["reason"], "open_failed")
        opener.ok = True
        clock.advance(1)
        self.assertEqual(ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])[0]["reason"], "opened")

    def test_safari_browser_passed_to_opener(self):
        opener = FakeOpener()
        ca = make(opener=opener, browser="safari")
        ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])
        self.assertEqual(opener.calls[0][1], "safari")

    def test_legacy_on_stock_found_uses_same_rules(self):
        opener = FakeOpener()
        clock = FakeClock()
        ca = make(clock=clock, opener=opener)
        sku = {"name": "iPhone 18 Pro Max 512GB 银色", "capacity": "512GB", "color": "银色"}
        r = ca.on_stock_found("iphone18pm_512_silver", "MJYC4CH/A",
                              {"store_number": "R401", "store_name": "上海环贸 iapm"}, sku_info=sku)
        self.assertTrue(r[0]["opened"])
        self.assertIn("上海环贸 iapm(R401)", r[0]["message"])
        self.assertIn("MJYC4CH/A", r[0]["message"])
        clock.advance(10)
        r2 = ca.on_stock_found("iphone18pm_512_silver", "MJYC4CH/A",
                               {"store_number": "R390", "store_name": "香港广场"}, sku_info=sku)
        self.assertEqual(r2[0]["reason"], "cooldown")
        self.assertEqual(len(opener.calls), 1)


class FakePusher:
    def __init__(self, ok=True, raise_exc=False):
        self.ok = ok
        self.raise_exc = raise_exc
        self.payloads = []

    def __call__(self, payload):
        if self.raise_exc:
            raise RuntimeError("bark down")
        self.payloads.append(payload)
        return self.ok


BARK = {"enabled": True, "url": "https://api.day.app/TESTKEY/"}


class TestBarkPush(unittest.TestCase):
    def _make(self, bark=BARK, **kw):
        pusher = FakePusher()
        ca = CheckoutAssistant({"enabled": True, **NEUTRAL, **kw}, clock=FakeClock(), opener=FakeOpener(),
                               bark_config=bark, pusher=pusher)
        return ca, pusher

    def test_bark_disabled_by_default(self):
        ca = CheckoutAssistant({"enabled": True, **NEUTRAL}, opener=FakeOpener(), pusher=FakePusher())
        self.assertFalse(ca.bark_enabled())
        r = ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])
        self.assertFalse(r[0]["pushed"])

    def test_bark_needs_enabled_and_url(self):
        ca, _ = self._make(bark={"enabled": True, "url": ""})
        self.assertFalse(ca.bark_enabled())
        ca, _ = self._make(bark={"enabled": False, "url": "https://api.day.app/K"})
        self.assertFalse(ca.bark_enabled())
        ca, _ = self._make()
        self.assertTrue(ca.bark_enabled())

    def test_payload_contents_and_url_normalization(self):
        ca, pusher = self._make()
        r = ca.on_stock_wave([
            hit("MK2P4CH/A", "R577", "天环广场", name="iPhone Duo 512GB 星光白色", capacity="512GB", color="星光白色"),
            hit("MK2P4CH/A", "R639", "珠江新城", name="iPhone Duo 512GB 星光白色", capacity="512GB", color="星光白色"),
        ])
        self.assertTrue(r[0]["opened"])
        self.assertTrue(r[0]["pushed"])
        self.assertEqual(len(pusher.payloads), 1)
        p = pusher.payloads[0]
        self.assertEqual(p["bark_url"], "https://api.day.app/TESTKEY")  # 去掉末尾斜杠
        self.assertEqual(p["url"], "https://www.apple.com.cn/shop/product/MK2P4CH/A")
        self.assertEqual(p["group"], "iPhoneDuoMonitor")
        self.assertEqual(p["level"], "timeSensitive")
        self.assertIn("iPhone 有货", p["title"])
        for token in ("iPhone Duo 512GB 星光白色", "MK2P4CH/A", "天环广场(R577)", "珠江新城(R639)"):
            self.assertIn(token, p["body"])

    def test_push_also_sent_when_mac_open_is_suppressed_by_cooldown(self):
        clock = FakeClock()
        pusher = FakePusher()
        ca = CheckoutAssistant({"enabled": True, **NEUTRAL}, clock=clock, opener=FakeOpener(), bark_config=BARK, pusher=pusher)
        ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])
        clock.advance(60)
        r = ca.on_stock_wave([hit("MK2P4CH/A", "R639", "珠江新城")])
        self.assertEqual(r[0]["reason"], "cooldown")
        self.assertTrue(r[0]["pushed"])
        self.assertEqual(len(pusher.payloads), 2)
        self.assertIn("珠江新城(R639)", pusher.payloads[1]["body"])
        self.assertNotIn("已打开", pusher.payloads[1]["title"])

    def test_no_push_on_baseline(self):
        ca, pusher = self._make()
        r = ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")], initial_snapshot=True)
        self.assertEqual(r[0]["reason"], "baseline")
        self.assertFalse(r[0]["pushed"])
        self.assertEqual(pusher.payloads, [])

    def test_push_when_auto_open_disabled(self):
        ca, pusher = self._make(auto_open_buy_page=False)
        r = ca.on_stock_wave([hit("MJYC4CH/A", "R359", "南京东路")])
        self.assertEqual(r[0]["reason"], "auto_open_disabled")
        self.assertTrue(r[0]["pushed"])
        self.assertEqual(len(pusher.payloads), 1)

    def test_pusher_failure_does_not_break_open(self):
        pusher = FakePusher(raise_exc=True)
        opener = FakeOpener()
        ca = CheckoutAssistant({"enabled": True, **NEUTRAL}, opener=opener, bark_config=BARK, pusher=pusher)
        r = ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])
        self.assertTrue(r[0]["opened"])
        self.assertFalse(r[0]["pushed"])
        self.assertEqual(len(opener.calls), 1)
        self.assertIn("bark down", ca.last_push_error)

    def test_disabled_assistant_never_pushes(self):
        pusher = FakePusher()
        ca = CheckoutAssistant({"enabled": False}, opener=FakeOpener(), bark_config=BARK, pusher=pusher)
        self.assertEqual(ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")]), [])
        self.assertEqual(pusher.payloads, [])

    def test_set_bark_config_at_runtime(self):
        ca, pusher = self._make(bark={"enabled": False, "url": ""})
        ca.on_stock_wave([hit("MK2P4CH/A", "R577", "天环广场")])
        self.assertEqual(pusher.payloads, [])
        ca.set_bark_config(BARK)
        ca._last_open_by_part.clear()
        ca.on_stock_wave([hit("MK2Q4CH/A", "R577", "天环广场")])
        self.assertEqual(len(pusher.payloads), 1)


class TestPriorityStores(unittest.TestCase):
    """默认配置：深圳 R793/R484/R761 一级，广州 R577/R639 二级，只为重点门店开页，重点不受冷却"""

    def _ca(self, **cfg):
        pusher = FakePusher()
        opener = FakeOpener()
        # FakeClock 的时间落在本地 23:00-07:00 静音段内，重点门店测试默认关闭静音时段（静音逻辑单独测）
        ca = CheckoutAssistant({"enabled": True, "quiet_hours": "", **cfg}, clock=FakeClock(), opener=opener,
                               bark_config={"enabled": True, "url": "https://api.day.app/K"}, pusher=pusher)
        return ca, opener, pusher

    def test_defaults_and_parsing(self):
        ca, _, _ = self._ca()
        self.assertEqual(ca.priority_tier1, ["R793", "R484", "R761"])
        self.assertEqual(ca.priority_tier2, ["R577", "R639"])
        self.assertTrue(ca.open_only_priority and ca.priority_bypass_cooldown)
        self.assertEqual((ca.store_tier("r793"), ca.store_tier("R577"), ca.store_tier("R390")), (1, 2, 0))
        ca2, _, _ = self._ca(priority_stores_tier1="r401, R390 ,r401", priority_stores_tier2=[])
        self.assertEqual(ca2.priority_tier1, ["R401", "R390"])
        self.assertEqual(ca2.priority_tier2, [])
        cfg = ca.to_config()
        self.assertEqual(cfg["priority_stores_tier1"], ["R793", "R484", "R761"])
        self.assertEqual(CheckoutAssistant(cfg, opener=FakeOpener()).to_config(), cfg)

    def test_priority_ordering_and_open_only_priority(self):
        ca, opener, pusher = self._ca()
        r = ca.on_stock_wave([
            hit("MK2P4CH/A", "R390", "香港广场", city="上海"),
            hit("MK2Q4CH/A", "R577", "天环广场", city="广州"),
            hit("MJYC4CH/A", "R793", "前海壹方城", city="深圳"),
            hit("MJYC4CH/A", "R401", "上海环贸 iapm", city="上海"),
        ])
        self.assertEqual([x["part_number"] for x in r], ["MJYC4CH/A", "MK2Q4CH/A", "MK2P4CH/A"])
        self.assertEqual([x["reason"] for x in r], ["opened", "opened", "non_priority"])
        self.assertEqual([u for u, _ in opener.calls],
                         ["https://www.apple.com.cn/shop/product/MJYC4CH/A", "https://www.apple.com.cn/shop/product/MK2Q4CH/A"])
        self.assertTrue(r[0]["message"].startswith("【深圳】"))
        self.assertTrue(r[1]["message"].startswith("【广州】"))
        self.assertFalse(r[2]["message"].startswith("【"))
        # 组内门店：深圳排在上海前面
        self.assertEqual([st["store_number"] for st in r[0]["stores"]], ["R793", "R401"])
        # 非重点仍推送 Bark（普通等级），重点推送带前缀/等级/铃声
        self.assertEqual(len(pusher.payloads), 3)
        p1, p2, p3 = pusher.payloads
        self.assertTrue(p1["title"].startswith("【深圳】") and p1["level"] == "critical" and p1["sound"] == "alarm" and p1["volume"] == 10)
        self.assertTrue(p2["title"].startswith("【广州】") and p2["level"] == "timeSensitive" and p2["sound"] == "bell")
        self.assertFalse(p3["title"].startswith("【"))
        self.assertNotIn("sound", p3)

    def test_priority_bypasses_cooldown_but_wave_cap_and_gap_still_apply(self):
        clock = FakeClock()
        opener = FakeOpener()
        ca = CheckoutAssistant({"enabled": True, "quiet_hours": ""}, clock=clock, opener=opener)
        self.assertTrue(ca.on_stock_wave([hit("MK2P4CH/A", "R793", "前海壹方城", city="深圳")])[0]["opened"])
        clock.advance(60)
        r = ca.on_stock_wave([hit("MK2P4CH/A", "R484", "益田假日广场", city="深圳")])
        self.assertTrue(r[0]["opened"])  # 冷却内，但重点门店绕过
        clock.advance(5)
        r = ca.on_stock_wave([hit("MK2Q4CH/A", "R761", "万象城", city="深圳")])
        self.assertEqual(r[0]["reason"], "global_interval")  # 全局 20 秒间隔仍然生效
        clock.advance(30)
        r = ca.on_stock_wave([hit("MK2Q4CH/A", "R793", "a", city="深圳"), hit("MK2T4CH/A", "R484", "b", city="深圳"),
                              hit("MK2U4CH/A", "R761", "c", city="深圳")])
        self.assertEqual([x["reason"] for x in r], ["opened", "opened", "wave_cap"])  # 每轮上限仍然生效

    def test_quiet_hours_downgrade_critical(self):
        import time as _t
        ca, _, pusher = self._ca(quiet_hours="23:00-07:00")
        self.assertEqual(ca.quiet_hours, "23:00-07:00")
        # 构造本地时间 02:30（静音内）和 12:00（静音外）
        def at(h, m):
            lt = _t.localtime()
            return _t.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, m, 0, lt.tm_wday, lt.tm_yday, lt.tm_isdst))
        self.assertTrue(ca.in_quiet_hours(at(2, 30)))
        self.assertTrue(ca.in_quiet_hours(at(23, 30)))
        self.assertFalse(ca.in_quiet_hours(at(12, 0)))
        self.assertFalse(ca.in_quiet_hours(at(7, 0)))
        ca._clock = lambda: at(2, 30)
        ca.on_stock_wave([hit("MK2P4CH/A", "R793", "前海壹方城", city="深圳")])
        p = pusher.payloads[-1]
        self.assertTrue(p["title"].startswith("【深圳】"))
        self.assertEqual(p["level"], "timeSensitive")
        self.assertNotIn("sound", p)
        self.assertNotIn("volume", p)
        ca._clock = lambda: at(12, 0)
        ca._last_open_by_part.clear(); ca._last_open_global = 0
        ca.on_stock_wave([hit("MK2Q4CH/A", "R793", "前海壹方城", city="深圳")])
        self.assertEqual(pusher.payloads[-1]["level"], "critical")
        # 非法/留空 → 不静音
        self.assertEqual(CheckoutAssistant({"quiet_hours": "25:00-1"}).quiet_hours, "")
        self.assertEqual(CheckoutAssistant({"quiet_hours": ""}).quiet_hours, "")
        self.assertEqual(CheckoutAssistant({}).quiet_hours, "23:00-07:00")

    def test_wave_cap_prefers_priority_when_open_only_disabled(self):
        ca, opener, _ = self._ca(open_only_priority=False)
        r = ca.on_stock_wave([
            hit("MK2P4CH/A", "R390", "香港广场", city="上海"),
            hit("MK2Q4CH/A", "R577", "天环广场", city="广州"),
            hit("MJYC4CH/A", "R793", "前海壹方城", city="深圳"),
        ])
        self.assertEqual([(x["part_number"], x["reason"]) for x in r],
                         [("MJYC4CH/A", "opened"), ("MK2Q4CH/A", "opened"), ("MK2P4CH/A", "wave_cap")])


# ----------------------------------------------------------------------
# GUI 集成 smoke（需要 PySide6；离屏运行，不启动 Cloud/本地监控，不写用户消息历史）
# ----------------------------------------------------------------------

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication  # noqa: E402
    HAS_QT = True
except Exception:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 不可用，跳过 GUI 集成 smoke")
class TestGuiCloudIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        import gui_app
        cls.gui_app = gui_app

    def _window(self):
        from PySide6.QtCore import QTimer
        # 阻止 __init__ 中的 singleShot 启动 Cloud/本地监控
        orig_single = QTimer.singleShot
        QTimer.singleShot = staticmethod(lambda *a, **k: None)
        try:
            w = self.gui_app.MainWindow()
        finally:
            QTimer.singleShot = orig_single
        # 不污染真实消息历史 / 配置文件 / 系统通知 / 声音
        w._save_message_history = lambda: None
        w._persist_checkout_config = lambda: None
        w._send_macos_notification = lambda *a, **k: None
        w._play_alert_sound = lambda *a, **k: None
        w._legacy_opens = []
        w._open_buy_page = lambda sku_id: w._legacy_opens.append(sku_id)
        # 这组测试验证通用的边沿/冷却语义，关闭重点门店特权（重点门店行为在 TestPriorityStores 单独验证）
        w.checkout.open_only_priority = False
        w.checkout.priority_bypass_cooldown = False
        return w

    def _inventory(self, available, sku_id="duo_512_starlight", stores=("R577",)):
        inv = {}
        for s in stores:
            inv[f"{sku_id}|{s}"] = {"available": available, "detail": {"store_name": "x"}}
        return inv

    def test_disabled_behaviour_unchanged_and_no_opener_call(self):
        w = self._window()
        opener = FakeOpener()
        w.checkout._opener = opener
        w.checkout.enabled = False
        w.config.setdefault("notification", {})["auto_open_buy_page"] = False
        w._detect_cloud_inventory_changes(self._inventory(False))
        w._detect_cloud_inventory_changes(self._inventory(True))
        self.assertEqual(opener.calls, [])
        self.assertEqual(w._legacy_opens, [])
        self.assertEqual(w.checkout.state, CheckoutState.IDLE)
        # 旧开关打开时，关闭 Checkout 的行为与原来一致：仍走 _open_buy_page
        w.config["notification"]["auto_open_buy_page"] = True
        w._detect_cloud_inventory_changes(self._inventory(False))
        w._detect_cloud_inventory_changes(self._inventory(True))
        self.assertEqual(w._legacy_opens, ["duo_512_starlight"])
        self.assertEqual(opener.calls, [])

    def test_cloud_available_edge_triggers_local_open_once(self):
        w = self._window()
        opener = FakeOpener()
        w.checkout._opener = opener
        w.checkout.enabled = True
        w.config.setdefault("notification", {})["auto_open_buy_page"] = False
        # 第一次 snapshot：已有货也只建立 baseline
        w._detect_cloud_inventory_changes(self._inventory(True))
        self.assertEqual(opener.calls, [])
        self.assertTrue(w.checkout.baseline_established)
        # 掉为无货再变有货：触发一次
        w._detect_cloud_inventory_changes(self._inventory(False))
        w._detect_cloud_inventory_changes(self._inventory(True))
        self.assertEqual(opener.calls, [("https://www.apple.com.cn/shop/product/MK2P4CH/A", "default")])
        # 持续有货：不重复
        w._detect_cloud_inventory_changes(self._inventory(True))
        w._detect_cloud_inventory_changes(self._inventory(True))
        self.assertEqual(len(opener.calls), 1)
        # UNKNOWN → AVAILABLE：视为事件但被冷却吸收
        w._detect_cloud_inventory_changes(self._inventory(None))
        w._detect_cloud_inventory_changes(self._inventory(True))
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(w.checkout.last_results[0]["reason"], "cooldown")

    def test_cloud_same_sku_three_stores_one_tab(self):
        w = self._window()
        opener = FakeOpener()
        w.checkout._opener = opener
        w.checkout.enabled = True
        w.config.setdefault("notification", {})["auto_open_buy_page"] = True  # 与 Checkout 互斥，不应双开
        stores = ("R577", "R639", "R390")
        w._detect_cloud_inventory_changes(self._inventory(False, stores=stores))
        w._detect_cloud_inventory_changes(self._inventory(True, stores=stores))
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(w._legacy_opens, [])
        r = w.checkout.last_results[0]
        self.assertEqual([s["store_number"] for s in r["stores"]], list(stores))
        self.assertIn("天环广场(R577)", r["message"])
        self.assertIn("珠江新城(R639)", r["message"])
        self.assertIn("香港广场(R390)", r["message"])
        self.assertIn("MK2P4CH/A", r["message"])

    def test_legacy_open_buy_page_uses_product_url(self):
        w = self._window()
        # 还原真实 _open_buy_page，拦截 QDesktopServices.openUrl
        del w._open_buy_page
        from PySide6.QtGui import QDesktopServices
        opened = []
        orig = QDesktopServices.openUrl
        QDesktopServices.openUrl = staticmethod(lambda url: opened.append(url.toString()) or True)
        try:
            w._open_buy_page("iphone18pm_512_silver")
        finally:
            QDesktopServices.openUrl = orig
        self.assertEqual(opened, ["https://www.apple.com.cn/shop/product/MJYC4CH/A"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
