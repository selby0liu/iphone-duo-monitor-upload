#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
库存历史记录模块 - 纯记录，不影响 Pickup 核心逻辑

只在状态真正变化时写入事件：
- UNAVAILABLE -> AVAILABLE (补货)
- AVAILABLE -> UNAVAILABLE (售罄)
- UNKNOWN -> AVAILABLE (恢复有货)
- AVAILABLE -> UNKNOWN (有货变未知)
- UNAVAILABLE -> UNKNOWN
- UNKNOWN -> UNAVAILABLE

相同状态连续轮询不重复写入。
UNKNOWN 不等于无货，统计时需区分。
"""

import json
import os
import time
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# 状态常量
STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"
STATUS_UNKNOWN = "unknown"

# 历史记录上限：最多 50000 条事件（约7天高频变化）
MAX_EVENTS = 50000


class InventoryHistory:
    """库存状态变化历史记录"""

    def __init__(self, history_file: str):
        self.history_file = history_file
        self.events: List[Dict] = []
        self._load()

    def _load(self):
        """从文件加载历史记录"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.events = data
                        logger.info("历史记录已加载: %d 条事件", len(self.events))
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("加载历史记录失败，使用空记录: %s", e)
                self.events = []

    def _save(self):
        """保存历史记录到文件"""
        try:
            os.makedirs(os.path.dirname(self.history_file) or ".", exist_ok=True)
            # 只保留最近 MAX_EVENTS 条
            if len(self.events) > MAX_EVENTS:
                self.events = self.events[-MAX_EVENTS:]
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.events, f, ensure_ascii=False)
        except IOError as e:
            logger.error("保存历史记录失败: %s", e)

    @staticmethod
    def _normalize_status(available) -> str:
        """将 available (True/False/None) 转换为状态字符串"""
        if available is True:
            return STATUS_AVAILABLE
        elif available is False:
            return STATUS_UNAVAILABLE
        else:
            return STATUS_UNKNOWN

    def record_change(self, sku_id: str, product_name: str,
                      store_number: str, store_name: str, city: str,
                      old_available, new_available):
        """
        记录一次状态变化。只有状态真正变化时才写入。

        Args:
            sku_id: SKU ID
            product_name: 产品名称
            store_number: 门店编号
            store_name: 门店名称
            city: 城市
            old_available: 旧状态 (True/False/None)
            new_available: 新状态 (True/False/None)
        """
        old_status = self._normalize_status(old_available)
        new_status = self._normalize_status(new_available)

        # 状态未变化，不记录
        if old_status == new_status:
            return

        event = {
            "timestamp": time.time(),
            "sku_id": sku_id,
            "product_name": product_name,
            "store_number": store_number,
            "store_name": store_name,
            "city": city,
            "old_status": old_status,
            "new_status": new_status,
            "is_restock": (old_status != STATUS_AVAILABLE and new_status == STATUS_AVAILABLE),
            "is_sold_out": (old_status == STATUS_AVAILABLE and new_status != STATUS_AVAILABLE),
        }
        self.events.append(event)
        self._save()

    def get_events(self, hours: float = None, limit: int = None) -> List[Dict]:
        """
        获取历史事件

        Args:
            hours: 只返回最近 N 小时的事件，None 表示全部
            limit: 最多返回 N 条，None 表示全部
        """
        result = self.events
        if hours is not None:
            cutoff = time.time() - hours * 3600
            result = [e for e in result if e["timestamp"] >= cutoff]
        if limit is not None:
            result = result[-limit:]
        return result

    def get_restock_events(self, hours: float = None) -> List[Dict]:
        """获取补货事件（非有货 -> 有货）"""
        events = self.get_events(hours=hours)
        return [e for e in events if e.get("is_restock")]

    def get_sold_out_events(self, hours: float = None) -> List[Dict]:
        """获取售罄事件（有货 -> 非有货）"""
        events = self.get_events(hours=hours)
        return [e for e in events if e.get("is_sold_out")]

    def get_available_durations(self, hours: float = None) -> List[Dict]:
        """
        计算每次 AVAILABLE 状态的持续时间。

        返回列表，每个元素包含：
        - sku_id, store_number, start_time, end_time, duration_seconds, complete
        - complete=False 表示因为 UNKNOWN 导致结束时间不确定
        """
        events = self.get_events(hours=hours)
        durations = []
        # 按 sku + store 分组
        from collections import defaultdict
        groups = defaultdict(list)
        for e in events:
            key = (e["sku_id"], e["store_number"])
            groups[key].append(e)

        for key, group_events in groups.items():
            group_events.sort(key=lambda x: x["timestamp"])
            available_start = None
            for e in group_events:
                if e["new_status"] == STATUS_AVAILABLE:
                    available_start = e["timestamp"]
                elif available_start is not None and e["old_status"] == STATUS_AVAILABLE:
                    duration = e["timestamp"] - available_start
                    complete = (e["new_status"] == STATUS_UNAVAILABLE)
                    durations.append({
                        "sku_id": key[0],
                        "store_number": key[1],
                        "start_time": available_start,
                        "end_time": e["timestamp"],
                        "duration_seconds": duration,
                        "complete": complete,
                    })
                    available_start = None
        return durations

    def clear(self):
        """清空历史记录（测试用）"""
        self.events = []
        self._save()
