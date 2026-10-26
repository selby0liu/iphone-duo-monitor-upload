#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
取货日期标签测试（纯本地，不联网，不访问 Apple）

背景：2026-09-14 10:32 天环广场冰川色"有货"，其实是 Apple 放出的一个
「星期六 2026/09/19」取货名额，消息栏只写了「有货 ✓」，看起来像能马上抢的现货。
现在把取货日期带进消息栏、Mac 通知和 Bark。只显示，不过滤。

运行：
  python3 tests/test_pickup_date_label.py
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from checkout_assistant import CheckoutAssistant, pickup_date_label  # noqa: E402


class TestPickupDateLabel(unittest.TestCase):
    def test_real_sample_from_2026_09_14(self):
        """服务器当时抓到的原话"""
        self.assertEqual(pickup_date_label("星期六 2026/09/19；Apple 天环广场"), "周六 09/19 可取")

    def test_today_and_tomorrow(self):
        self.assertEqual(pickup_date_label("今天可取货"), "今天可取")
        self.assertEqual(pickup_date_label("今日可取"), "今天可取")
        self.assertEqual(pickup_date_label("明天可取货"), "明天可取")

    def test_weekday_variants(self):
        self.assertEqual(pickup_date_label("星期日 2026/10/18"), "周日 10/18 可取")
        self.assertEqual(pickup_date_label("星期天 2026/10/18"), "周日 10/18 可取")
        self.assertEqual(pickup_date_label("星期五 2026/10/16"), "周五 10/16 可取")

    def test_date_without_weekday(self):
        self.assertEqual(pickup_date_label("2026/10/16"), "10/16 可取")
        self.assertEqual(pickup_date_label("10月16日可取货"), "10/16 可取")
        self.assertEqual(pickup_date_label("10月16日 星期五"), "周五 10/16 可取")

    def test_html_is_stripped(self):
        quote = ('<button type="button" class="rf-pickup-quote-overlay-trigger">'
                 'Apple 天环广场</button> 星期五 2026/10/16')
        self.assertEqual(pickup_date_label(quote), "周五 10/16 可取")

    def test_unavailable_wording_yields_nothing(self):
        for q in ("暂无供应", "Apple 天环广场 目前无货",
                  "目前暂不提供 Apple 天环广场 零售店取货服务",
                  '<button type="button">Apple 天环广场</button> 目前无货'):
            self.assertEqual(pickup_date_label(q), "", q)

    def test_never_invents_a_label(self):
        for q in ("", None, "Apple 天环广场", "可取货", "店内取货"):
            self.assertEqual(pickup_date_label(q), "", repr(q))
        self.assertEqual(pickup_date_label(), "")

    def test_scans_both_fields(self):
        """pickup_search_quote 和 store_pickup_quote 哪个里有日期都要认出来"""
        self.assertEqual(pickup_date_label("暂无供应", "星期六 2026/09/19；Apple 天环广场"),
                         "周六 09/19 可取")
        self.assertEqual(pickup_date_label("今天可取货", "Apple 天环广场"), "今天可取")


def hit(part, store_number, store_name, pickup_label="", city="广州"):
    return {"sku_id": part, "part_number": part, "sku_name": "", "capacity": "", "color": "",
            "store_number": store_number, "store_name": store_name, "city": city,
            "pickup_label": pickup_label}


class TestLabelFlowsIntoMessagesAndBark(unittest.TestCase):
    def _ca(self):
        pushed = []
        ca = CheckoutAssistant(
            {"enabled": True, "quiet_hours": "", "open_only_priority": False},
            opener=lambda url, browser: True,
            bark_config={"enabled": True, "url": "https://api.day.app/K"},
            pusher=lambda p: pushed.append(p) or True)
        return ca, pushed

    def test_label_appears_next_to_its_store(self):
        ca, pushed = self._ca()
        r = ca.on_stock_wave([hit("MJYE4CH/A", "R577", "天环广场", "周六 09/19 可取")])
        self.assertIn("天环广场(R577) 周六 09/19 可取", r[0]["stores_label"])
        self.assertIn("周六 09/19 可取", r[0]["message"])
        self.assertIn("周六 09/19 可取", pushed[0]["body"])

    def test_each_store_keeps_its_own_label(self):
        ca, _ = self._ca()
        r = ca.on_stock_wave([
            hit("MJYE4CH/A", "R577", "天环广场", "今天可取"),
            hit("MJYE4CH/A", "R639", "珠江新城", "周六 09/19 可取"),
        ])
        self.assertIn("天环广场(R577) 今天可取", r[0]["stores_label"])
        self.assertIn("珠江新城(R639) 周六 09/19 可取", r[0]["stores_label"])

    def test_no_label_keeps_old_text_exactly(self):
        ca, _ = self._ca()
        r = ca.on_stock_wave([hit("MJYE4CH/A", "R577", "天环广场")])
        self.assertEqual(r[0]["stores_label"], "天环广场(R577)")

    def test_label_never_leaks_into_the_url(self):
        ca, _ = self._ca()
        ca.auto_select_store = True
        r = ca.on_stock_wave([hit("MJYE4CH/A", "R577", "天环广场", "周六 09/19 可取")])
        self.assertEqual(r[0]["url"],
                         "https://www.apple.com.cn/shop/product/MJYE4CH/A#duomonitor-stores=R577")


try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication  # noqa: E402
    HAS_QT = True
except Exception:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 不可用，跳过 GUI 集成测试")
class TestGuiShowsPickupDate(unittest.TestCase):
    """复刻 2026-09-14 10:32 那一幕：消息栏、Mac 通知、Checkout 结果都要带上取货日期"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        import gui_app
        cls.gui_app = gui_app

    def _window(self):
        from PySide6.QtCore import QTimer
        orig = QTimer.singleShot
        QTimer.singleShot = staticmethod(lambda *a, **k: None)
        try:
            w = self.gui_app.MainWindow()
        finally:
            QTimer.singleShot = orig
        w._save_message_history = lambda: None
        w._persist_checkout_config = lambda: None
        w._persist_launch_check = lambda: None
        w._send_macos_notification = lambda *a, **k: None
        w._play_alert_sound = lambda *a, **k: None
        w._open_buy_page = lambda sku_id: None
        w._message_history = []
        c = w.checkout
        c.enabled = True
        c.auto_open_page = True
        c.quiet_hours = ""
        c.priority_tier1 = ["R793", "R484", "R761"]
        c.priority_tier2 = ["R577", "R639"]
        c.open_only_priority = True
        c.set_bark_config({"enabled": False, "url": ""})
        c._opener = lambda url, browser: True
        return w

    @staticmethod
    def _inv(available, quote):
        return {"iphone18pm_512_glacier|R577": {
            "available": available,
            "detail": {"store_name": "天环广场",
                       "pickup_search_quote": quote if available else "暂无供应",
                       "store_pickup_quote": quote}}}

    def test_message_bar_notification_and_checkout_all_show_the_date(self):
        w = self._window()
        w._detect_cloud_inventory_changes(self._inv(False, "Apple 天环广场 目前无货"))
        w._detect_cloud_inventory_changes(self._inv(True, "星期六 2026/09/19；Apple 天环广场"))
        statuses = [m["status"] for m in w._message_history]
        self.assertIn("有货 ✓ · 周六 09/19 可取", statuses)
        self.assertIn("周六 09/19 可取", w._last_wave_notification["body"])
        r = w.checkout.last_results[0]
        self.assertTrue(r["opened"], "带日期不能影响开页")
        self.assertIn("天环广场(R577) 周六 09/19 可取", r["stores_label"])

    def test_unrecognised_quote_keeps_the_old_wording(self):
        w = self._window()
        w._detect_cloud_inventory_changes(self._inv(False, "Apple 天环广场 目前无货"))
        w._detect_cloud_inventory_changes(self._inv(True, "Apple 天环广场"))
        statuses = [m["status"] for m in w._message_history]
        self.assertIn("有货 ✓", statuses)
        self.assertFalse(any("可取" in s for s in statuses))
        self.assertTrue(w.checkout.last_results[0]["opened"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
