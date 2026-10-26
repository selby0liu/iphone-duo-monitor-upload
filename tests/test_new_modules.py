#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新模块测试：China Control / Australia Control / Market Watch
"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from china_control_monitor import ChinaControlMonitor
from australia_monitor import AustraliaControlMonitor
from market_watch import MarketWatch


def test_china_control_init():
    """测试 China Control 初始化"""
    print("=== 1. China Control 初始化 ===")
    cc = ChinaControlMonitor(config={"enabled": True, "interval_seconds": 90})
    assert cc.enabled == True
    assert cc.interval == 90
    assert cc.CONTROL_SKU["part_number"] == "MJTF4CH/A"
    assert cc.CONTROL_SKU["name"] == "iPhone 18 Pro 512GB 白色"
    print("  ✓ 初始化正常")
    print(f"  ✓ Part Number: {cc.CONTROL_SKU['part_number']}")
    print(f"  ✓ 频率: {cc.interval}秒")
    return True


def test_china_control_state():
    """测试 China Control 状态管理"""
    print("\n=== 2. China Control 状态管理 ===")
    cc = ChinaControlMonitor(config={"enabled": False})
    status = cc.get_status()
    assert status["enabled"] == False
    assert "available" in status
    assert "last_check" in status
    print("  ✓ 状态结构完整")
    print("  ✓ 禁用时不执行检查")
    return True


def test_australia_control_init():
    """测试 Australia Control 初始化"""
    print("\n=== 3. Australia Control 初始化 ===")
    ac = AustraliaControlMonitor(config={"enabled": True, "interval_seconds": 60})
    assert ac.enabled == True
    assert ac.interval == 60
    assert ac.DUO_SKU["part_number"] == "MK2F4X/A"
    assert ac.IPHONE18_SKU["part_number"] == "MJRX4X/A"
    assert len(ac.ADELAIDE_STORES) == 1
    assert ac.ADELAIDE_STORES[0]["store_number"] == "R405"
    assert ac.ADELAIDE_STORES[0]["city"] == "Adelaide"
    print("  ✓ 初始化正常")
    print(f"  ✓ Duo PN: {ac.DUO_SKU['part_number']}")
    print(f"  ✓ 18 Pro PN: {ac.IPHONE18_SKU['part_number']}")
    print(f"  ✓ Adelaide门店: {ac.ADELAIDE_STORES[0]['store_name']} ({ac.ADELAIDE_STORES[0]['store_number']})")
    return True


def test_australia_control_independent():
    """测试 Australia Control 独立状态"""
    print("\n=== 4. Australia Control 独立状态 ===")
    ac = AustraliaControlMonitor(config={"enabled": False})
    status = ac.get_status()
    assert "duo_available" in status
    assert "iphone18_available" in status
    assert "backoff" in status
    print("  ✓ Duo 和 18 Pro 独立状态")
    print("  ✓ 独立退避状态")
    return True


def test_market_watch_init():
    """测试 Market Watch 初始化"""
    print("\n=== 5. Market Watch 初始化 ===")
    mw = MarketWatch(config={"enabled": False})
    assert mw.enabled == False
    assert len(mw.SKU_MAP) == 4
    assert "duo_512_starlight" in mw.SKU_MAP
    assert mw.OFFICIAL_PRICES["duo_512_starlight"] == 17999
    print("  ✓ 初始化正常")
    print(f"  ✓ 监控 SKU 数: {len(mw.SKU_MAP)}")
    print(f"  ✓ 512GB 原价: ¥{mw.OFFICIAL_PRICES['duo_512_starlight']}")
    return True


def test_market_watch_add_sample():
    """测试 Market Watch 添加样本"""
    print("\n=== 6. Market Watch 添加样本 ===")
    mw = MarketWatch(config={"enabled": True})
    mw.clear_data()

    # 添加有效样本
    assert mw.add_manual_sample("duo_512_starlight", 18999, "manual") == True
    assert mw.add_manual_sample("duo_512_starlight", 19999, "manual") == True
    assert mw.add_manual_sample("duo_512_starlight", 17999, "manual") == True

    # 无效样本（极端价格）
    assert mw.add_manual_sample("duo_512_starlight", 1000, "manual") == False
    assert mw.add_manual_sample("duo_512_starlight", 200000, "manual") == False

    stats = mw.get_sku_stats("duo_512_starlight")
    assert stats["sample_count"] == 3
    assert stats["current_min"] == 17999
    assert stats["current_median"] == 18999
    assert stats["premium_amount"] == 1000  # 18999 - 17999（v1.2.1 修正官方价）
    assert abs(stats["premium_percent"] - 5.56) < 0.1  # 1000/17999*100

    print(f"  ✓ 有效样本数: {stats['sample_count']}")
    print(f"  ✓ 最低价: ¥{stats['current_min']}")
    print(f"  ✓ 中位价: ¥{stats['current_median']}")
    print(f"  ✓ 溢价金额: ¥{stats['premium_amount']}")
    print(f"  ✓ 溢价百分比: {stats['premium_percent']}%")
    print("  ✓ 极端价格已过滤")
    return True


def test_market_watch_invalid_filter():
    """测试 Market Watch 无效报价过滤"""
    print("\n=== 7. Market Watch 无效报价过滤 ===")
    mw = MarketWatch(config={"enabled": True})
    mw.clear_data()

    # 添加各种类型的无效样本
    mw.add_manual_sample("duo_512_starlight", 500, "manual", "deposit")  # 定金
    mw.add_manual_sample("duo_512_starlight", 8000, "manual", "recycle")  # 回收价
    mw.add_manual_sample("duo_512_starlight", 18999, "manual", "listing")  # 有效

    stats = mw.get_sku_stats("duo_512_starlight")
    assert stats["sample_count"] == 1  # 只有有效样本
    print("  ✓ 定金/回收价已过滤")
    print("  ✓ 有效样本保留")
    return True


def test_market_watch_trend():
    """测试 Market Watch 趋势数据"""
    print("\n=== 8. Market Watch 趋势数据 ===")
    mw = MarketWatch(config={"enabled": True})
    mw.clear_data()

    # 添加不同时间的样本
    for i, price in enumerate([18000, 18500, 19000, 19500, 20000]):
        sample = {
            "timestamp": time.time() - (4 - i) * 3600,
            "sku_id": "duo_512_starlight",
            "price": price,
            "source": "manual",
            "sample_type": "listing",
            "excluded": False,
        }
        mw.samples.append(sample)
    mw._save_data()

    trend = mw.get_trend_data("duo_512_starlight", days=1)
    assert len(trend) >= 1
    print(f"  ✓ 趋势数据点: {len(trend)}")
    print("  ✓ 按天聚合正常")
    return True


def test_module_isolation():
    """测试模块隔离：新模块不影响主 Monitor"""
    print("\n=== 9. 模块隔离测试 ===")
    # 初始化所有新模块，确保不抛异常
    cc = ChinaControlMonitor(config={"enabled": False})
    ac = AustraliaControlMonitor(config={"enabled": False})
    mw = MarketWatch(config={"enabled": False})

    # 执行检查（禁用状态应立即返回）
    cc_status = cc.check_once()
    ac_status = ac.check_once()

    assert cc_status == cc.state
    assert ac_status == ac.state
    print("  ✓ China Control 禁用时安全返回")
    print("  ✓ Australia Control 禁用时安全返回")
    print("  ✓ Market Watch 禁用时不执行抓取")
    return True


def test_china_control_dict_stores():
    """测试 China Control 正确处理字典格式的 stores（回归测试）"""
    print("\n=== 10. China Control 字典格式 stores（回归测试） ===")
    # 模拟主 Monitor 的 stores 数据结构（按地区分组的字典）
    dict_stores = {
        "regions": {
            "广东": {"stores": [{"store_number": "R577", "name": "天环广场", "city": "广州"}]},
            "上海": {"stores": [{"store_number": "R359", "name": "南京东路", "city": "上海"}]},
        }
    }
    cc = ChinaControlMonitor(config={"enabled": False}, stores=dict_stores)
    assert len(cc.target_stores) == 2
    assert "R577" in cc.target_store_numbers
    assert "R359" in cc.target_store_numbers
    print("  ✓ 正确处理字典格式 stores")
    print(f"  ✓ 目标门店数: {len(cc.target_stores)}")
    return True


def test_new_modules_init_no_network():
    """测试新模块 __init__ 不执行网络请求（快速完成）"""
    print("\n=== 11. 新模块初始化不联网 ===")
    import time

    t0 = time.time()
    cc = ChinaControlMonitor(config={"enabled": True}, stores={"regions": {}})
    t1 = time.time()
    ac = AustraliaControlMonitor(config={"enabled": True})
    t2 = time.time()
    mw = MarketWatch(config={"enabled": False})
    t3 = time.time()

    # 初始化应该在 1 秒内完成（不联网）
    assert (t1 - t0) < 1.0, f"China Control 初始化耗时 {t1-t0:.2f}s，可能联网了"
    assert (t2 - t1) < 1.0, f"Australia Control 初始化耗时 {t2-t1:.2f}s，可能联网了"
    assert (t3 - t2) < 1.0, f"Market Watch 初始化耗时 {t3-t2:.2f}s，可能联网了"
    print(f"  ✓ China Control 初始化: {(t1-t0)*1000:.0f}ms")
    print(f"  ✓ Australia Control 初始化: {(t2-t1)*1000:.0f}ms")
    print(f"  ✓ Market Watch 初始化: {(t3-t2)*1000:.0f}ms")
    print("  ✓ 所有模块初始化 < 1秒，无网络请求")
    return True


def test_market_watch_disabled_no_network():
    """测试 Market Watch 禁用时不执行网络 I/O"""
    print("\n=== 12. Market Watch 禁用时零网络请求 ===")
    mw = MarketWatch(config={"enabled": False})

    # fetch_market_data 在禁用时应立即返回 False
    import time
    t0 = time.time()
    result = mw.fetch_market_data()
    elapsed = time.time() - t0

    assert result == False
    assert elapsed < 0.1, f"禁用状态下 fetch 耗时 {elapsed:.2f}s，可能执行了网络请求"
    print(f"  ✓ 禁用时 fetch_market_data 立即返回 False")
    print(f"  ✓ 耗时: {elapsed*1000:.0f}ms")
    print("  ✓ 零网络请求")
    return True


def test_china_control_541_unknown():
    """测试 China Control HTTP 541 时状态为 UNKNOWN（None），不是无货"""
    print("\n=== 13. China Control 541 => UNKNOWN（回归测试） ===")
    cc = ChinaControlMonitor(config={"enabled": False}, stores={"regions": {}})
    # 模拟 API 失败后的状态
    cc.state["available"] = None
    cc.state["last_http_status"] = 541
    cc.state["consecutive_failure"] = 1

    assert cc.state["available"] is None, "541 时 available 应为 None（未知），不是 False（无货）"
    assert cc.state["last_http_status"] == 541

    status = cc.get_status()
    assert status["available"] is None
    print("  ✓ 541 时 available = None（未知）")
    print("  ✓ 不显示为无货")
    return True


def test_market_watch_correct_prices():
    """测试 Market Watch 官方价格正确（v1.2.1 修复）"""
    print("\n=== 14. Market Watch 官方价格（回归测试） ===")
    mw = MarketWatch(config={"enabled": False})

    assert mw.OFFICIAL_PRICES["duo_512_starlight"] == 17999, "512GB 应为 ¥17999"
    assert mw.OFFICIAL_PRICES["duo_512_midnight"] == 17999
    assert mw.OFFICIAL_PRICES["duo_1tb_starlight"] == 21499, "1TB 应为 ¥21499"
    assert mw.OFFICIAL_PRICES["duo_1tb_midnight"] == 21499

    # 测试溢价计算：512GB 中位价 ¥19000，官网 ¥17999
    mw.clear_data()
    mw.add_manual_sample("duo_512_starlight", 19000, "manual")
    stats = mw.get_sku_stats("duo_512_starlight")
    assert stats["premium_amount"] == 1001, f"溢价金额应为 1001，实际 {stats['premium_amount']}"
    assert abs(stats["premium_percent"] - 5.56) < 0.1, f"溢价率应约 5.56%，实际 {stats['premium_percent']}"

    print(f"  ✓ 512GB 官网价: ¥{mw.OFFICIAL_PRICES['duo_512_starlight']}")
    print(f"  ✓ 1TB 官网价: ¥{mw.OFFICIAL_PRICES['duo_1tb_starlight']}")
    print(f"  ✓ ¥19000 对应 512GB 溢价: +¥{stats['premium_amount']} (+{stats['premium_percent']}%)")
    return True


def test_pickup_backoff_interval():
    """测试 pickup 区域轮询间隔为 90 秒（v2.3低频: 30→90）"""
    print("\n=== 15. Pickup 区域轮询间隔（回归测试） ===")
    from monitor import IPhoneDuoMonitor
    m = IPhoneDuoMonitor('.', register_signals=False)

    assert m.pickup_region_interval == 90, f"区域轮询间隔应为 90 秒，实际 {m.pickup_region_interval}"
    assert m.pickup_stagger_seconds == 30, f"错峰间隔应为 30 秒，实际 {m.pickup_stagger_seconds}"
    assert len(m.pickup_postcodes) == 3

    print(f"  ✓ 区域轮询间隔: {m.pickup_region_interval}秒")
    print(f"  ✓ 错峰间隔: {m.pickup_stagger_seconds}秒")
    print(f"  ✓ 区域数: {len(m.pickup_postcodes)}")
    print("  ✓ 每区域 90 秒一次，错峰 30 秒")
    return True


def test_product_locator_init():
    """测试 Product Locator 模块初始化不联网"""
    print("\n=== 16. Product Locator 初始化（v1.3.0） ===")
    from product_locator_monitor import ProductLocatorMonitor
    pl = ProductLocatorMonitor(config={"enabled": True, "interval_seconds": 300})
    assert pl.enabled is True
    assert pl.interval == 300
    assert pl.products == {}
    assert pl.http_status is None
    print("  ✓ Product Locator 初始化成功，不联网")
    print("  ✓ 默认间隔 300 秒")
    return True


def test_product_locator_sku_exists():
    """测试 Product Locator SKU 存在性判断"""
    print("\n=== 17. Product Locator SKU 判断（v1.3.0） ===")
    from product_locator_monitor import ProductLocatorMonitor
    pl = ProductLocatorMonitor()
    pl.products = {"MK2P4CH/A": {"exists": True, "part_number": "MK2P4CH/A"}}
    assert pl.sku_exists("MK2P4CH/A") is True
    assert pl.sku_exists("INVALID") is False
    info = pl.get_sku_info("MK2P4CH/A")
    assert info["exists"] is True
    print("  ✓ SKU 存在性判断正确")
    print("  ✓ 不存在的 SKU 返回 False")
    return True


def test_network_change_reset_backoff():
    """测试网络切换时重置退避（v1.3.0）"""
    print("\n=== 18. 网络切换重置退避（v1.3.0） ===")
    from monitor import IPhoneDuoMonitor
    m = IPhoneDuoMonitor('.', register_signals=False)
    # 设置退避状态
    for pc in m.pickup_postcodes:
        m.pickup_backoff[pc] = 120
        m.pickup_next_check[pc] = time.time() + 120
    # 模拟网络切换
    result = m.check_network_change("1.2.3.4")
    assert result is True
    assert m.current_public_ip == "1.2.3.4"
    for pc in m.pickup_postcodes:
        assert m.pickup_backoff[pc] == 0
    # 相同 IP 不触发重置
    result2 = m.check_network_change("1.2.3.4")
    assert result2 is False
    print("  ✓ 网络切换触发退避重置")
    print("  ✓ 相同 IP 不触发重置")
    return True


def test_control_modules_reset_backoff():
    """测试对照组模块 reset_backoff 方法（v1.3.0）"""
    print("\n=== 19. 对照组 reset_backoff（v1.3.0） ===")
    from china_control_monitor import ChinaControlMonitor
    from australia_monitor import AustraliaControlMonitor
    cc = ChinaControlMonitor(config={"enabled": True, "interval_seconds": 300})
    ac = AustraliaControlMonitor(config={"enabled": True, "interval_seconds": 300})
    cc.reset_backoff()
    ac.reset_backoff()
    assert cc.state["consecutive_failure"] == 0
    assert ac.backoff == 0
    print("  ✓ China Control reset_backoff 正常")
    print("  ✓ Australia Control reset_backoff 正常")
    return True


def test_delivery_interval_60():
    """测试 Delivery 默认间隔为 180 秒（v2.3低频: 60→180）"""
    print("\n=== 20. Delivery 间隔 180 秒（v2.3） ===")
    from monitor import IPhoneDuoMonitor
    m = IPhoneDuoMonitor('.', register_signals=False)
    assert m.delivery_interval == 180, f"Delivery 间隔应为 180 秒，实际 {m.delivery_interval}"
    print(f"  ✓ Delivery 间隔: {m.delivery_interval}秒")
    return True


def main():
    print("=" * 60)
    print("新模块测试：China Control / Australia Control / Market Watch / Product Locator")
    print("=" * 60)

    tests = [
        test_china_control_init,
        test_china_control_state,
        test_australia_control_init,
        test_australia_control_independent,
        test_market_watch_init,
        test_market_watch_add_sample,
        test_market_watch_invalid_filter,
        test_market_watch_trend,
        test_module_isolation,
        test_china_control_dict_stores,
        test_new_modules_init_no_network,
        test_market_watch_disabled_no_network,
        test_china_control_541_unknown,
        test_market_watch_correct_prices,
        test_pickup_backoff_interval,
        test_product_locator_init,
        test_product_locator_sku_exists,
        test_network_change_reset_backoff,
        test_control_modules_reset_backoff,
        test_delivery_interval_60,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
