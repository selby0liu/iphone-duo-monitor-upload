#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
门店助手（auto_select_store + 浏览器扩展）纯本地测试。
不联网、不打开浏览器、不访问 Apple、不产生任何 Apple 请求。

运行：
  python3 tests/test_store_selector.py
  或 python3 -m pytest tests/test_store_selector.py -v

扩展本身的 DOM 行为在真实浏览器里测：
  python3 browser_extension/apple_store_selector/test/serve.py
  打开 http://127.0.0.1:8799/test/run_tests.html
"""

import os
import re
import sys
import json
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from checkout_assistant import CheckoutAssistant, STORE_FRAGMENT_KEY, MAX_CANDIDATE_STORES  # noqa: E402

EXT_DIR = os.path.join(ROOT, "browser_extension", "apple_store_selector")
SZ1, SZ2, SZ3 = "R793", "R484", "R761"     # 深圳：前海壹方城 / 益田假日广场 / 万象城
GZ1, GZ2 = "R577", "R639"                   # 广州：天环广场 / 珠江新城
SH1 = "R390"                                # 上海：非重点


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

    @property
    def urls(self):
        return [u for u, _ in self.calls]


def hit(part, store_number, store_name="店", city="深圳"):
    return {"sku_id": part, "part_number": part, "sku_name": "", "capacity": "", "color": "",
            "store_number": store_number, "store_name": store_name, "city": city}


def make(opener=None, **cfg):
    config = {"enabled": True, "quiet_hours": "", "auto_select_store": True}
    config.update(cfg)
    return CheckoutAssistant(config, clock=FakeClock(), opener=opener or FakeOpener())


class TestFragmentFormat(unittest.TestCase):
    def test_fragment_shape(self):
        ca = make()
        self.assertEqual(ca.build_store_fragment([SZ3, SZ1, SZ2]),
                         "#duomonitor-stores=R761,R793,R484")
        self.assertEqual(STORE_FRAGMENT_KEY, "duomonitor-stores")

    def test_sanitize_rejects_everything_that_is_not_a_store_number(self):
        ca = make()
        dirty = ["R484", "r761", " R793 ", "R484",           # 合法（含小写/空格/重复）
                 "", None, "token=abc", "<script>", "R4",     # 非法
                 "DROP TABLE", "R4841234567", "apple.com.cn", "R577"]
        self.assertEqual(ca.sanitize_store_numbers(dirty), ["R484", "R761", "R793", "R577"])

    def test_sanitize_caps_candidate_count(self):
        ca = make()
        many = [f"R{n}" for n in range(100, 130)]
        self.assertEqual(len(ca.sanitize_store_numbers(many)), MAX_CANDIDATE_STORES)

    def test_fragment_contains_only_store_ids_no_secrets(self):
        """fragment 字符集硬性约束：除了 #key= 和门店号、逗号，不允许出现任何其它字符"""
        ca = make()
        frag = ca.build_store_fragment([SZ3, SZ1, SZ2, GZ1, SH1])
        self.assertRegex(frag, r"^#duomonitor-stores=R[0-9A-Z]+(,R[0-9A-Z]+)*$")
        for secret in ("token", "cookie", "apple", "id=", "@", "password", "session", "key"):
            self.assertNotIn(secret, frag.lower())

    def test_empty_or_invalid_candidates_produce_no_fragment(self):
        ca = make()
        self.assertEqual(ca.build_store_fragment([]), "")
        self.assertEqual(ca.build_store_fragment(["", None, "bad"]), "")


class TestBuyUrl(unittest.TestCase):
    BASE = "https://www.apple.com.cn/shop/product/MK2P4CH/A"

    def test_disabled_produces_exactly_the_old_url(self):
        ca = make(auto_select_store=False)
        self.assertEqual(ca.get_buy_url("MK2P4CH/A"), self.BASE)
        self.assertEqual(ca.get_buy_url("MK2P4CH/A", [SZ3, SZ1]), self.BASE)
        self.assertNotIn("#", ca.get_buy_url("MK2P4CH/A", [SZ3, SZ1]))

    def test_enabled_appends_fragment_in_candidate_order(self):
        ca = make()
        self.assertEqual(ca.get_buy_url("MK2P4CH/A", [SZ3, SZ1, SZ2]),
                         self.BASE + "#duomonitor-stores=R761,R793,R484")

    def test_enabled_without_candidates_is_still_the_plain_url(self):
        ca = make()
        self.assertEqual(ca.get_buy_url("MK2P4CH/A"), self.BASE)
        self.assertEqual(ca.get_buy_url("MK2P4CH/A", []), self.BASE)


class TestSafariOpenPath(unittest.TestCase):
    """browser="safari" + auto_select_store 时，必须走普通的 open -a Safari，不碰 AppleScript"""

    def test_safari_open_command_carries_the_fragment(self):
        opener = FakeOpener()
        ca = make(opener=opener, browser="safari", priority_stores_tier1=[SZ3, SZ1, SZ2])
        r = ca.on_stock_wave([hit("MK2P4CH/A", SZ1), hit("MK2P4CH/A", SZ3)])
        self.assertTrue(r[0]["opened"])
        url, browser = opener.calls[0]
        self.assertEqual(browser, "safari")
        self.assertEqual(url, "https://www.apple.com.cn/shop/product/MK2P4CH/A"
                              "#duomonitor-stores=R761,R793")
        self.assertEqual(ca.build_open_command(url), ["open", "-a", "Safari", url])

    def test_default_browser_command_unchanged(self):
        ca = make(browser="default")
        self.assertEqual(ca.build_open_command("https://x#y"), ["open", "https://x#y"])

    def test_both_browsers_are_still_supported(self):
        from checkout_assistant import SUPPORTED_BROWSERS
        self.assertEqual(tuple(SUPPORTED_BROWSERS), ("default", "safari"))
        self.assertEqual(CheckoutAssistant({"browser": "safari"}).browser, "safari")
        self.assertEqual(CheckoutAssistant({"browser": "default"}).browser, "default")

    def test_no_applescript_anywhere_in_the_open_path(self):
        """打开购买页这条路径上不允许有 osascript / AppleScript / TCC 自动化"""
        import inspect
        import checkout_assistant as mod
        for fn in (mod.CheckoutAssistant.build_open_command,
                   mod.CheckoutAssistant._open_url,
                   mod.CheckoutAssistant.get_buy_url):
            src = inspect.getsource(fn)
            for banned in ("osascript", "AppleScript", "tell application"):
                self.assertNotIn(banned, src, f"{fn.__name__} 不应出现 {banned}")


class TestCandidateOrdering(unittest.TestCase):
    def test_same_sku_many_stores_one_tab_full_candidate_list(self):
        """同一个 SKU 多店同时有货：只开 1 个页面，整条候选列表按优先级进 fragment"""
        opener = FakeOpener()
        ca = make(opener=opener, priority_stores_tier1=[SZ3, SZ1, SZ2], priority_stores_tier2=[GZ1, GZ2])
        r = ca.on_stock_wave([
            hit("MK2P4CH/A", GZ1, city="广州"),   # 命中顺序故意打乱
            hit("MK2P4CH/A", SZ2),
            hit("MK2P4CH/A", SZ3),
            hit("MK2P4CH/A", SZ1),
            hit("MK2P4CH/A", SZ2),                # 重复门店
        ])
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["candidate_stores"], [SZ3, SZ1, SZ2, GZ1])
        self.assertEqual(opener.urls[0],
                         "https://www.apple.com.cn/shop/product/MK2P4CH/A#duomonitor-stores=R761,R793,R484,R577")
        self.assertIn("R761 → R793 → R484 → R577", r[0]["message"])

    def test_tier_order_beats_hit_order_and_tier1_beats_tier2(self):
        opener = FakeOpener()
        ca = make(opener=opener, priority_stores_tier1=[SZ1, SZ2, SZ3], priority_stores_tier2=[GZ2, GZ1],
                  open_only_priority=False)
        r = ca.on_stock_wave([hit("MK2P4CH/A", SH1, city="上海"), hit("MK2P4CH/A", GZ1, city="广州"),
                              hit("MK2P4CH/A", GZ2, city="广州"), hit("MK2P4CH/A", SZ3)])
        # 一级(R761) > 二级按配置顺序(R639, R577) > 普通(R390)
        self.assertEqual(r[0]["candidate_stores"], [SZ3, GZ2, GZ1, SH1])

    def test_candidates_come_only_from_this_wave(self):
        """候选门店只能来自本轮真实 AVAILABLE，不能把优先级矩阵里其它门店塞进来"""
        opener = FakeOpener()
        ca = make(opener=opener, priority_stores_tier1=[SZ1, SZ2, SZ3], priority_stores_tier2=[GZ1, GZ2])
        r = ca.on_stock_wave([hit("MK2P4CH/A", SZ2)])
        self.assertEqual(r[0]["candidate_stores"], [SZ2])
        self.assertEqual(opener.urls[0].split("#")[1], "duomonitor-stores=R484")
        for absent in (SZ1, SZ3, GZ1, GZ2):
            self.assertNotIn(absent, opener.urls[0])

    def test_two_skus_two_tabs_each_with_its_own_candidate_list(self):
        """用户给的例子：512 星光白 R761/R793/R484，512 夜空黑 R793/R577 → 只开 2 页，各自独立候选"""
        opener = FakeOpener()
        ca = make(opener=opener, priority_stores_tier1=[SZ3, SZ1, SZ2], priority_stores_tier2=[GZ1, GZ2])
        r = ca.on_stock_wave([
            hit("MK2P4CH/A", SZ2), hit("MK2P4CH/A", SZ3), hit("MK2P4CH/A", SZ1),
            hit("MK2Q4CH/A", GZ1, city="广州"), hit("MK2Q4CH/A", SZ1),
        ])
        self.assertEqual(len(opener.calls), 2)
        self.assertEqual(sorted(opener.urls), sorted([
            "https://www.apple.com.cn/shop/product/MK2P4CH/A#duomonitor-stores=R761,R793,R484",
            "https://www.apple.com.cn/shop/product/MK2Q4CH/A#duomonitor-stores=R793,R577",
        ]))
        self.assertEqual([x["opened"] for x in r], [True, True])

    def test_three_skus_still_capped_at_max_tabs_per_wave(self):
        opener = FakeOpener()
        ca = make(opener=opener, priority_stores_tier1=[SZ1, SZ2, SZ3])
        r = ca.on_stock_wave([hit("MK2P4CH/A", SZ1), hit("MK2Q4CH/A", SZ2), hit("MK2U4CH/A", SZ3)])
        self.assertEqual(len(opener.calls), 2)
        self.assertEqual([x["reason"] for x in r], ["opened", "opened", "wave_cap"])
        self.assertTrue(all("#duomonitor-stores=" in u for u in opener.urls))

    def test_multi_store_does_not_increase_tab_count(self):
        """8 家门店 × 1 个 SKU 仍然只有 1 个标签页"""
        opener = FakeOpener()
        ca = make(opener=opener, priority_stores_tier1=[SZ1, SZ2, SZ3], priority_stores_tier2=[GZ1, GZ2],
                  open_only_priority=False)
        stores = [SZ1, SZ2, SZ3, GZ1, GZ2, SH1, "R401", "R359"]
        r = ca.on_stock_wave([hit("MK2P4CH/A", s) for s in stores])
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(len(r[0]["candidate_stores"]), 8)


class TestDisabledBehaviourUnchanged(unittest.TestCase):
    def test_default_is_off(self):
        self.assertFalse(CheckoutAssistant({}).auto_select_store)
        self.assertFalse(CheckoutAssistant({"enabled": True}).auto_select_store)

    def test_off_means_urls_and_messages_identical_to_before(self):
        opener_off = FakeOpener()
        off = make(opener=opener_off, auto_select_store=False,
                   priority_stores_tier1=[SZ1, SZ2, SZ3])
        r_off = off.on_stock_wave([hit("MK2P4CH/A", SZ1), hit("MK2P4CH/A", SZ2)])
        self.assertEqual(opener_off.urls, ["https://www.apple.com.cn/shop/product/MK2P4CH/A"])
        self.assertNotIn("候选门店顺序", r_off[0]["message"])
        self.assertNotIn("#", r_off[0]["url"])

    def test_config_roundtrip_includes_flag(self):
        ca = make(auto_select_store=True)
        cfg = ca.to_config()
        self.assertTrue(cfg["auto_select_store"])
        self.assertEqual(CheckoutAssistant(cfg).to_config(), cfg)
        self.assertFalse(CheckoutAssistant({}).to_config()["auto_select_store"])


def _strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


class TestExtensionIsMinimalAndOffline(unittest.TestCase):
    """对扩展源码做静态检查：权限最小、零网络、不碰 Cookie/存储、不点结账类按钮"""

    def setUp(self):
        with open(os.path.join(EXT_DIR, "manifest.json"), "r", encoding="utf-8") as f:
            self.manifest = json.load(f)
        with open(os.path.join(EXT_DIR, "store_selector_core.js"), "r", encoding="utf-8") as f:
            self.js_raw = f.read()
        self.js = _strip_js_comments(self.js_raw)
        with open(os.path.join(EXT_DIR, "content.js"), "r", encoding="utf-8") as f:
            self.bootstrap = _strip_js_comments(f.read())

    def test_manifest_loads_core_before_bootstrap(self):
        self.assertEqual(self.manifest["content_scripts"][0]["js"],
                         ["store_selector_core.js", "content.js"])

    def test_bootstrap_holds_no_logic_of_its_own(self):
        """content.js 只负责调用共享核心，不能自己长出第二套行为"""
        self.assertIn("globalThis.DuoMonitorStoreSelector", self.bootstrap)
        self.assertIn("core.run()", self.bootstrap)
        self.assertNotIn(".click()", self.bootstrap)
        self.assertNotIn("querySelector", self.bootstrap)
        self.assertNotIn("setInterval", self.bootstrap)
        self.assertLess(len(self.bootstrap.strip().splitlines()), 12)

    def test_manifest_requests_no_permissions_at_all(self):
        for key in ("permissions", "host_permissions", "optional_permissions",
                    "optional_host_permissions", "background", "web_accessible_resources"):
            self.assertNotIn(key, self.manifest, f"manifest 不应包含 {key}")
        self.assertEqual(self.manifest["manifest_version"], 3)

    def test_manifest_only_matches_apple_cn_shop(self):
        cs = self.manifest["content_scripts"]
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0]["matches"], ["https://www.apple.com.cn/shop/*"])
        self.assertEqual(cs[0]["js"], ["store_selector_core.js", "content.js"])
        self.assertEqual(cs[0]["run_at"], "document_start")
        self.assertFalse(cs[0]["all_frames"])

    def test_content_script_makes_no_network_calls(self):
        for banned in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket",
                       "EventSource", "importScripts", "http://", "https://"):
            self.assertNotIn(banned, self.js, f"共享核心不应出现 {banned}")
            self.assertNotIn(banned, self.bootstrap, f"content.js 不应出现 {banned}")

    def test_content_script_touches_no_cookies_or_storage(self):
        for banned in ("document.cookie", "localStorage", "sessionStorage", "indexedDB",
                       "chrome.cookies", "chrome.storage", "chrome.tabs",
                       "browser.cookies", "browser.storage", "browser.tabs"):
            self.assertNotIn(banned, self.js, f"共享核心不应出现 {banned}")
            self.assertNotIn(banned, self.bootstrap, f"content.js 不应出现 {banned}")

    def test_checkout_controls_appear_only_inside_the_blacklists(self):
        """结账类关键词只能出现在 FORBIDDEN_* 黑名单里，不能作为点击目标"""
        head = self.js[:self.js.index("function parseCandidates")]
        for term in ("continuePickUp", "add-to-cart", "addToBag", "checkout", "proceed", "buy"):
            self.assertIn(term, head, f"{term} 应在黑名单常量里")
            body = self.js[self.js.index("function parseCandidates"):]
            self.assertNotIn('"' + term + '"', body, f"{term} 不应出现在黑名单之外")
        for banned in ("atbtoken", "submit()", "location.reload", "location.href ="):
            self.assertNotIn(banned, self.js, f"content.js 不应出现 {banned}")

    def test_single_click_site_guarded_by_a_two_item_whitelist(self):
        """全文件只有一处 .click()，且必须先通过 safeClick 的白名单校验"""
        self.assertEqual(self.js.count(".click()"), 1)
        start = self.js.index("function safeClick")
        end = self.js.index(".click()")
        self.assertLess(start, end, ".click() 必须在 safeClick 内部")
        guard = self.js[start:end]
        self.assertIn('if (kind === "store-radio")', guard)
        self.assertIn("if (!isStoreRadio(el)) { return false; }", guard)
        self.assertIn('} else if (kind === "pickup-trigger") {', guard)
        self.assertIn("if (!isPickupTrigger(el)) { return false; }", guard)
        self.assertIn("} else {\n      return false;", guard)   # 任何其它 kind 一律拒绝
        self.assertIn("if (isForbidden(el)) { return false; }", guard)

    def test_store_radio_selector_is_exact(self):
        self.assertIn('input[type="radio"][name^="store-"]', self.js)

    def test_pickup_trigger_cannot_submit_a_form_or_navigate(self):
        fn = self.js[self.js.index("function isPickupTrigger"):self.js.index("function findPickupTrigger")]
        # <button> 必须显式 type="button"；不写 type 的 button 默认是 submit
        self.assertIn('if (tag === "BUTTON") {', fn)
        self.assertIn('if (el.type !== "button") { return false; }', fn)
        # <a> 只允许锚点，不允许跳走
        self.assertIn('if (href && href.charAt(0) !== "#") { return false; }', fn)
        # 其它元素必须带 role="button"
        self.assertIn('el.getAttribute("role") !== "button"', fn)
        # 红线校验放在最前面
        self.assertIn("if (isForbidden(el) || insideForbiddenAncestor(el)) { return false; }", fn)

    def test_trigger_clicks_are_bounded(self):
        self.assertIn("MAX_TRIGGER_CLICKS = 3", self.js)
        self.assertIn("AUTO_OPEN_PICKUP_PANEL = true", self.js)
        # 安静期留给用户自己选 AppleCare / 折抵，之后扩展才接管
        self.assertIn("TRIGGER_INITIAL_DELAY_MS = 8000", self.js)
        # 弹窗已经打开就不再点，列表已经出现就根本不去找触发器
        self.assertIn("if (overlayOpen(trigger)) { return; }", self.js)
        self.assertIn("if (!present) { tryOpenPickupPanel(now); }", self.js)

    def test_bounded_retry_no_refresh(self):
        # 超时必须大于安静期，否则还没轮到扩展动手就放弃了
        self.assertIn("PANEL_TIMEOUT_MS = 60000", self.js)
        self.assertGreater(60000, 8000)
        self.assertNotIn("location.reload", self.js)
        # 两个定时器：主轮询 + 待命角标倒计时；两个都必须在 stop() 里被清掉
        self.assertEqual(self.js.count("setInterval"), 2)
        self.assertEqual(self.js.count("clearInterval"), 2)
        stop_fn = self.js[self.js.index("function stop()"):self.js.index("function succeed(")]
        self.assertIn("clearInterval(timer)", stop_fn)
        self.assertIn("clearStandby()", stop_fn)
        clear_standby = self.js[self.js.index("function clearStandby()"):self.js.index("function standbyText()")]
        self.assertIn("clearInterval(standbyTimer)", clear_standby)
        self.assertIn("standby.remove()", clear_standby)

    def test_fragment_key_matches_python_side(self):
        self.assertIn('FRAGMENT_KEY = "%s"' % STORE_FRAGMENT_KEY, self.js)
        self.assertIn("MAX_CANDIDATES = %d" % MAX_CANDIDATE_STORES, self.js)

    def test_fragment_is_removed_without_reloading(self):
        self.assertIn("history.replaceState", self.js)


SAFARI_DIR = os.path.join(ROOT, "browser_extension", "safari")
SAFARI_APP = os.path.join(SAFARI_DIR, "build", "DuoMonitorStoreSelector.app")
SAFARI_APPEX = os.path.join(SAFARI_APP, "Contents", "PlugIns",
                            "DuoMonitorStoreSelectorExtension.appex")
SAFARI_RES = os.path.join(SAFARI_APPEX, "Contents", "Resources")
SHARED_FILES = ("manifest.json", "store_selector_core.js", "content.js")


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@unittest.skipUnless(os.path.isdir(SAFARI_APPEX), "Safari 扩展尚未构建，跳过")
class TestSafariBundleSharesTheSameLogic(unittest.TestCase):
    """Safari 版和 Chrome 版必须是逐字节相同的同一套逻辑，且权限同样为零"""

    def test_shared_files_are_byte_identical(self):
        for name in SHARED_FILES:
            canon = os.path.join(EXT_DIR, name)
            shipped = os.path.join(SAFARI_RES, name)
            self.assertTrue(os.path.isfile(shipped), f"Safari 包里缺少 {name}")
            self.assertEqual(_sha256(canon), _sha256(shipped),
                             f"{name} 在 Safari 包里和权威源不一致，请重新运行 build_safari_extension.sh")

    def test_safari_bundle_ships_nothing_else_executable(self):
        extra = sorted(set(os.listdir(SAFARI_RES)) - set(SHARED_FILES))
        self.assertEqual(extra, [], f"Safari 包的 Resources 里有计划外的文件: {extra}")

    def test_safari_manifest_permissions_are_still_empty(self):
        with open(os.path.join(SAFARI_RES, "manifest.json"), "r", encoding="utf-8") as f:
            m = json.load(f)
        for key in ("permissions", "host_permissions", "optional_permissions",
                    "optional_host_permissions", "background", "web_accessible_resources"):
            self.assertNotIn(key, m, f"Safari manifest 不应包含 {key}")
        self.assertEqual(m["content_scripts"][0]["matches"], ["https://www.apple.com.cn/shop/*"])

    def test_extension_plist_declares_safari_web_extension_point(self):
        import plistlib
        with open(os.path.join(SAFARI_APPEX, "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
        self.assertEqual(info["NSExtension"]["NSExtensionPointIdentifier"],
                         "com.apple.Safari.web-extension")
        self.assertEqual(info["NSExtension"]["NSExtensionPrincipalClass"],
                         "SafariWebExtensionHandler")
        self.assertEqual(info["CFBundleIdentifier"], "com.duomonitor.storeselector.Extension")

    def test_native_handler_does_nothing_but_close_the_request(self):
        with open(os.path.join(SAFARI_DIR, "src", "SafariWebExtensionHandler.m"),
                  "r", encoding="utf-8") as f:
            src = _strip_js_comments(f.read())   # ObjC 用的是同一套 // 和 /* */ 注释
        self.assertIn("completeRequestReturningItems:@[]", src)
        for banned in ("NSURLSession", "NSURLConnection", "http://", "https://",
                       "cookie", "Cookie", "keychain", "Keychain", "NSTask"):
            self.assertNotIn(banned, src, f"原生处理器不应出现 {banned}")


# ----------------------------------------------------------------------
# GUI 集成（需要 PySide6；离屏运行，不启动 Cloud/本地监控，不写用户配置）
# ----------------------------------------------------------------------

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication  # noqa: E402
    HAS_QT = True
except Exception:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 不可用，跳过 GUI 集成测试")
class TestGuiIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        import gui_app
        cls.gui_app = gui_app

    def _window(self, auto_select_store):
        from PySide6.QtCore import QTimer
        orig = QTimer.singleShot
        QTimer.singleShot = staticmethod(lambda *a, **k: None)
        try:
            w = self.gui_app.MainWindow()
        finally:
            QTimer.singleShot = orig
        w._save_message_history = lambda: None
        w._persist_checkout_config = lambda: None
        w._send_macos_notification = lambda *a, **k: None
        w._play_alert_sound = lambda *a, **k: None
        w._open_buy_page = lambda sku_id: None
        c = w.checkout
        c.enabled = True
        c.auto_select_store = auto_select_store
        c.priority_tier1 = [SZ3, SZ1, SZ2]
        c.priority_tier2 = [GZ1, GZ2]
        c.open_only_priority = True
        c.quiet_hours = ""
        return w

    def _inv(self, available, sku_id="duo_512_starlight", stores=(SZ2,)):
        return {f"{sku_id}|{s}": {"available": available, "detail": {"store_name": "x"}} for s in stores}

    def test_wave_passes_full_candidate_list_in_one_tab(self):
        w = self._window(auto_select_store=True)
        opener = FakeOpener()
        w.checkout._opener = opener
        stores = (SZ2, SZ3, SZ1)  # 益田、万象城、前海：命中顺序与优先级顺序不同
        w._detect_cloud_inventory_changes(self._inv(False, stores=stores))
        w._detect_cloud_inventory_changes(self._inv(True, stores=stores))
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(opener.urls[0],
                         "https://www.apple.com.cn/shop/product/MK2P4CH/A#duomonitor-stores=R761,R793,R484")
        r = w.checkout.last_results[0]
        self.assertEqual(r["candidate_stores"], [SZ3, SZ1, SZ2])

    def test_flag_off_gives_the_old_url_byte_for_byte(self):
        w = self._window(auto_select_store=False)
        opener = FakeOpener()
        w.checkout._opener = opener
        stores = (SZ2, SZ3, SZ1)
        w._detect_cloud_inventory_changes(self._inv(False, stores=stores))
        w._detect_cloud_inventory_changes(self._inv(True, stores=stores))
        self.assertEqual(opener.urls, ["https://www.apple.com.cn/shop/product/MK2P4CH/A"])

    def test_checkbox_reflects_and_updates_the_flag(self):
        w = self._window(auto_select_store=False)
        self.assertFalse(w.checkout.auto_select_store)
        w.checkout_auto_select_cb.setChecked(True)
        w._on_checkout_option_changed()
        self.assertTrue(w.checkout.auto_select_store)
        self.assertIn("门店助手 开", w.armed_label.text())
        w.checkout_auto_select_cb.setChecked(False)
        w._on_checkout_option_changed()
        self.assertFalse(w.checkout.auto_select_store)
        self.assertIn("门店助手 关", w.armed_label.text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
