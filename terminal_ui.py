#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
终端状态面板
- 运行状态、启用 SKU、最近检查时间、间隔、请求延迟
- 配送状态、目标门店、最近发现库存时间、最近错误
"""

import time
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class TerminalUI:
    """终端状态显示"""

    def __init__(self, config: dict, skus: list, stores: dict):
        self.config = config
        self.skus = skus
        self.stores = stores
        self.store_count = sum(
            len(r.get("stores", []))
            for r in stores.get("regions", {}).values()
        )
        self.enabled_skus = [s for s in skus if s.get("enabled", False)]
        self.last_check_time = None
        self.last_check_duration = 0
        self.check_count = 0
        self.last_error = None
        self.last_inventory_time = None
        self.pickup_status = {}  # store_number|sku_id -> True/False/None
        self.delivery_status = {}  # sku_id -> True/False/None
        self.pickup_api_ok = None  # None=未检测, True=可用, False=不可用

    def set_pickup_api_status(self, ok):
        """设置 pickup API 实时状态"""
        self.pickup_api_ok = ok

    def update_check_result(self, duration: float, error: str = None):
        """更新检查结果"""
        self.last_check_time = time.time()
        self.last_check_duration = duration
        self.check_count += 1
        if error:
            self.last_error = error
        else:
            self.last_error = None

    def update_pickup_status(self, store_number: str, sku_id: str, available):
        """更新到店取货状态，available: True/False/None(未知)"""
        key = f"{store_number}|{sku_id}"
        self.pickup_status[key] = available
        if available is True:
            self.last_inventory_time = time.time()

    def update_delivery_status(self, sku_id: str, available):
        """更新配送状态，available: True/False/None(未知)"""
        self.delivery_status[sku_id] = available
        if available is True:
            self.last_inventory_time = time.time()

    def _fmt_status(self, available) -> str:
        """格式化状态显示"""
        if available is True:
            return "有货"
        elif available is False:
            return "无货"
        else:
            return "未知"

    def _fmt_time(self, ts: float) -> str:
        if ts is None:
            return "从未"
        return time.strftime("%H:%M:%S", time.localtime(ts))

    def _fmt_ago(self, ts: float) -> str:
        if ts is None:
            return "—"
        ago = int(time.time() - ts)
        if ago < 60:
            return f"{ago}秒前"
        elif ago < 3600:
            return f"{ago // 60}分前"
        else:
            return f"{ago // 3600}时{ago % 3600 // 60}分前"

    def render(self):
        """渲染终端状态面板"""
        # 清屏
        print("\033[2J\033[H", end="")

        width = 70
        print("=" * width)
        print("  iPhone Duo 中国大陆库存监控".center(width))
        print("=" * width)

        # 运行状态
        interval = self.config.get("monitor", {}).get("interval_seconds", 5)
        if self.pickup_api_ok is True:
            api_text = "门店API:正常"
        elif self.pickup_api_ok is False:
            api_text = "门店API:不可用(状态未知)"
        else:
            api_text = "门店API:检测中"
        print(f"\n  运行状态：运行中（{api_text}）")
        print(f"  检查次数：{self.check_count}")
        print(f"  检查间隔：{interval} 秒")
        print(f"  最近检查：{self._fmt_time(self.last_check_time)}（耗时 {self.last_check_duration:.1f}s）")
        print(f"  最近有货：{self._fmt_ago(self.last_inventory_time)}")
        if self.last_error:
            print(f"  最近错误：{self.last_error}")

        # 启用 SKU
        print(f"\n  启用 SKU（{len(self.enabled_skus)}/4）：")
        for sku in self.enabled_skus:
            if sku["id"] in self.delivery_status:
                delivery_avail = self.delivery_status[sku["id"]]
                delivery_icon = self._fmt_status(delivery_avail)
            else:
                delivery_icon = "未检查"
            print(f"    [{sku['part_number']}] {sku['name']}  配送:{delivery_icon}")

        # 目标门店
        print(f"\n  目标门店：{self.store_count} 家（广东+南京+上海）")

        # 到店取货状态（如果有数据）
        if self.pickup_status:
            available_count = sum(1 for v in self.pickup_status.values() if v is True)
            unknown_count = sum(1 for v in self.pickup_status.values() if v is None)
            print(f"\n  到店取货状态：{available_count} 有货 / {len(self.pickup_status)} 总 / {unknown_count} 未知")
            if available_count > 0:
                print("  有货门店：")
                for key, avail in self.pickup_status.items():
                    if avail is True:
                        store_num, sku_id = key.split("|", 1)
                        sku_name = next((s["name"] for s in self.skus if s["id"] == sku_id), sku_id)
                        print(f"    - {store_num}: {sku_name}")
            elif unknown_count > 0:
                print("  ⚠ 门店库存接口当前不可用，状态为未知（不代表无货）")

        print(f"\n  按 Ctrl+C 停止监控")
        print("=" * width)
