#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
供货趋势分析模块 - 纯读取，不产生任何 Apple 请求

数据来源：
- InventoryHistory（状态变化事件）
- 当前 Pickup 状态（由外部传入）
- Cloud 监控指标（由外部传入）

所有统计基于已有历史数据，不主动请求 Apple。
"""

import time
import logging
from typing import Dict, List, Optional
from collections import defaultdict

from inventory_history import InventoryHistory, STATUS_AVAILABLE, STATUS_UNAVAILABLE, STATUS_UNKNOWN

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """供货趋势分析器"""

    def __init__(self, history: InventoryHistory):
        self.history = history

    def _fmt_duration(self, seconds: float) -> str:
        """格式化持续时间"""
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            return f"{int(seconds // 60)}分{int(seconds % 60)}秒"
        else:
            return f"{int(seconds // 3600)}时{int((seconds % 3600) // 60)}分"

    def get_overview(self, current_states: Dict, sku_list: List[Dict],
                     store_list: List[Dict]) -> Dict:
        """
        当前供货概览

        Args:
            current_states: 当前 Pickup 状态 {"sku_id|store_number": {"available": bool/None, ...}}
            sku_list: SKU 列表 [{"id", "name", "part_number", ...}]
            store_list: 门店列表 [{"store_number", "name", "city", ...}]
        """
        total_stores = len(store_list)
        available_stores = 0
        available_store_set = set()

        for store in store_list:
            sn = store["store_number"]
            for sku in sku_list:
                key = f"{sku['id']}|{sn}"
                state = current_states.get(key, {})
                if state.get("available") is True:
                    available_store_set.add(sn)
                    break

        available_stores = len(available_store_set)

        # 最近补货信息
        restocks_1h = self.history.get_restock_events(hours=1)
        restocks_6h = self.history.get_restock_events(hours=6)
        restocks_24h = self.history.get_restock_events(hours=24)

        last_restock = restocks_24h[-1] if restocks_24h else None

        # 最近1/6/24小时出现过现货的门店数
        def stores_with_restock(hours):
            events = self.history.get_restock_events(hours=hours)
            return len(set(e["store_number"] for e in events))

        # 最活跃城市和SKU
        city_counts = defaultdict(int)
        sku_counts = defaultdict(int)
        for e in restocks_24h:
            city_counts[e.get("city", "未知")] += 1
            sku_counts[e.get("product_name", e["sku_id"])] += 1

        most_active_city = max(city_counts, key=city_counts.get) if city_counts else "-"
        most_active_sku = max(sku_counts, key=sku_counts.get) if sku_counts else "-"

        return {
            "current_available_stores": available_stores,
            "total_stores": total_stores,
            "last_restock_time": last_restock["timestamp"] if last_restock else None,
            "last_restock_store": last_restock.get("store_name", "-") if last_restock else "-",
            "last_restock_sku": last_restock.get("product_name", "-") if last_restock else "-",
            "restocks_1h": len(restocks_1h),
            "restocks_6h": len(restocks_6h),
            "restocks_24h": len(restocks_24h),
            "stores_with_restock_1h": stores_with_restock(1),
            "stores_with_restock_6h": stores_with_restock(6),
            "stores_with_restock_24h": stores_with_restock(24),
            "most_active_city": most_active_city,
            "most_active_sku": most_active_sku,
        }

    def get_sku_trends(self, current_states: Dict, sku_list: List[Dict],
                       store_list: List[Dict]) -> List[Dict]:
        """每个 SKU 的供货趋势"""
        results = []
        durations = self.history.get_available_durations(hours=24)

        for sku in sku_list:
            sku_id = sku["id"]
            sku_name = sku.get("name", sku_id)

            # 当前有货门店数
            current_available = 0
            for store in store_list:
                key = f"{sku_id}|{store['store_number']}"
                if current_states.get(key, {}).get("available") is True:
                    current_available += 1

            # 补货次数
            restocks_1h = [e for e in self.history.get_restock_events(hours=1) if e["sku_id"] == sku_id]
            restocks_6h = [e for e in self.history.get_restock_events(hours=6) if e["sku_id"] == sku_id]
            restocks_24h = [e for e in self.history.get_restock_events(hours=24) if e["sku_id"] == sku_id]

            last_restock = restocks_24h[-1] if restocks_24h else None

            # 连续无货时间（从最后一次有货结束到现在）
            sold_out_events = [e for e in self.history.get_sold_out_events(hours=24)
                              if e["sku_id"] == sku_id]
            consecutive_out_minutes = 0
            if sold_out_events and not last_restock:
                # 一直无货
                consecutive_out_minutes = int((time.time() - sold_out_events[-1]["timestamp"]) / 60)
            elif last_restock and sold_out_events and sold_out_events[-1]["timestamp"] > last_restock["timestamp"]:
                consecutive_out_minutes = int((time.time() - sold_out_events[-1]["timestamp"]) / 60)

            # 过去24小时出现过现货的门店数
            stores_with_stock = len(set(e["store_number"] for e in restocks_24h))

            # 平均现货持续时间
            sku_durations = [d for d in durations if d["sku_id"] == sku_id and d["complete"]]
            avg_duration = sum(d["duration_seconds"] for d in sku_durations) / len(sku_durations) if sku_durations else 0

            results.append({
                "sku_id": sku_id,
                "product_name": sku_name,
                "capacity": sku.get("capacity", ""),
                "color": sku.get("color", ""),
                "current_available_stores": current_available,
                "restocks_1h": len(restocks_1h),
                "restocks_6h": len(restocks_6h),
                "restocks_24h": len(restocks_24h),
                "last_restock_time": last_restock["timestamp"] if last_restock else None,
                "consecutive_out_minutes": consecutive_out_minutes,
                "stores_with_stock_24h": stores_with_stock,
                "avg_available_duration": self._fmt_duration(avg_duration) if avg_duration > 0 else "-",
            })

        return results

    def get_store_activity(self, store_list: List[Dict]) -> List[Dict]:
        """门店供货活跃度，按近24小时补货次数排序"""
        restocks_24h = self.history.get_restock_events(hours=24)
        restocks_6h = self.history.get_restock_events(hours=6)
        restocks_1h = self.history.get_restock_events(hours=1)
        durations = self.history.get_available_durations(hours=24)

        results = []
        for store in store_list:
            sn = store["store_number"]
            store_restocks_24h = [e for e in restocks_24h if e["store_number"] == sn]
            store_restocks_6h = [e for e in restocks_6h if e["store_number"] == sn]
            store_restocks_1h = [e for e in restocks_1h if e["store_number"] == sn]

            last_restock = store_restocks_24h[-1] if store_restocks_24h else None

            # 出现过的 SKU
            sku_counts = defaultdict(int)
            for e in store_restocks_24h:
                sku_counts[e.get("product_name", e["sku_id"])] += 1

            # 平均现货持续时间
            store_durations = [d for d in durations if d["store_number"] == sn and d["complete"]]
            avg_duration = sum(d["duration_seconds"] for d in store_durations) / len(store_durations) if store_durations else 0

            results.append({
                "store_number": sn,
                "store_name": store.get("name", sn),
                "city": store.get("city", ""),
                "restocks_1h": len(store_restocks_1h),
                "restocks_6h": len(store_restocks_6h),
                "restocks_24h": len(store_restocks_24h),
                "last_restock_time": last_restock["timestamp"] if last_restock else None,
                "sku_breakdown": dict(sku_counts),
                "avg_available_duration": self._fmt_duration(avg_duration) if avg_duration > 0 else "-",
            })

        results.sort(key=lambda x: x["restocks_24h"], reverse=True)
        return results

    def get_city_activity(self, store_list: List[Dict], current_states: Dict,
                          sku_list: List[Dict]) -> List[Dict]:
        """城市供货活跃度"""
        restocks_1h = self.history.get_restock_events(hours=1)
        restocks_6h = self.history.get_restock_events(hours=6)
        restocks_24h = self.history.get_restock_events(hours=24)

        # 按城市分组门店
        city_stores = defaultdict(list)
        for store in store_list:
            city_stores[store.get("city", "未知")].append(store)

        results = []
        for city, stores in city_stores.items():
            city_restocks_1h = [e for e in restocks_1h if e.get("city") == city]
            city_restocks_6h = [e for e in restocks_6h if e.get("city") == city]
            city_restocks_24h = [e for e in restocks_24h if e.get("city") == city]

            last_restock = city_restocks_24h[-1] if city_restocks_24h else None

            # 当前有货门店数
            current_available = 0
            for store in stores:
                for sku in sku_list:
                    key = f"{sku['id']}|{store['store_number']}"
                    if current_states.get(key, {}).get("available") is True:
                        current_available += 1
                        break

            # 活跃度评级
            count_24h = len(city_restocks_24h)
            if count_24h >= 20:
                level = "★★★★★"
            elif count_24h >= 10:
                level = "★★★★"
            elif count_24h >= 5:
                level = "★★★"
            elif count_24h >= 1:
                level = "★★"
            else:
                level = "★"

            results.append({
                "city": city,
                "current_available_stores": current_available,
                "total_stores": len(stores),
                "restocks_1h": len(city_restocks_1h),
                "restocks_6h": len(city_restocks_6h),
                "restocks_24h": count_24h,
                "last_restock_time": last_restock["timestamp"] if last_restock else None,
                "activity_level": level,
            })

        results.sort(key=lambda x: x["restocks_24h"], reverse=True)
        return results

    def get_restock_pulse(self) -> Dict:
        """补货脉冲 - 最近30分钟各城市/SKU补货次数"""
        restocks_30m = self.history.get_restock_events(hours=0.5)

        city_counts = defaultdict(int)
        sku_counts = defaultdict(int)
        for e in restocks_30m:
            city_counts[e.get("city", "未知")] += 1
            sku_counts[e.get("product_name", e["sku_id"])] += 1

        # 判断是否补货活跃（最近30分钟 > 过去3小时平均）
        restocks_3h = self.history.get_restock_events(hours=3)
        avg_per_30m = len(restocks_3h) / 6 if restocks_3h else 0
        is_active = len(restocks_30m) > avg_per_30m * 1.5 and len(restocks_30m) >= 3

        return {
            "restocks_30m": len(restocks_30m),
            "by_city": dict(city_counts),
            "by_sku": dict(sku_counts),
            "is_active": is_active,
            "avg_per_30m_recent": round(avg_per_30m, 1),
        }

    def get_available_duration_stats(self) -> Dict:
        """现货持续时间统计"""
        durations = self.history.get_available_durations(hours=24)
        complete_durations = [d for d in durations if d["complete"]]

        if not complete_durations:
            return {
                "last_duration": "-",
                "avg_duration": "-",
                "max_duration": "-",
                "min_duration": "-",
                "total_available_periods": 0,
                "incomplete_periods": len([d for d in durations if not d["complete"]]),
            }

        durations_sec = [d["duration_seconds"] for d in complete_durations]
        last_duration = durations[-1]["duration_seconds"] if durations else 0

        return {
            "last_duration": self._fmt_duration(last_duration),
            "avg_duration": self._fmt_duration(sum(durations_sec) / len(durations_sec)),
            "max_duration": self._fmt_duration(max(durations_sec)),
            "min_duration": self._fmt_duration(min(durations_sec)),
            "total_available_periods": len(complete_durations),
            "incomplete_periods": len([d for d in durations if not d["complete"]]),
        }

    def get_recent_events(self, limit: int = 20) -> List[Dict]:
        """最近库存事件（补货+售罄）"""
        events = self.history.get_events(limit=limit)
        # 只返回有意义的状态变化（排除 UNKNOWN <-> UNKNOWN）
        meaningful = [e for e in events
                     if e["old_status"] != STATUS_UNKNOWN or e["new_status"] != STATUS_UNKNOWN]
        return meaningful[-limit:]

    def get_health_status(self, pickup_api_available: bool, last_success_time: float,
                          last_http_status: int, cloud_online: bool,
                          control_sku_available: bool, last_check_time: float,
                          success_rate_1h: float) -> Dict:
        """监控健康度（纯读取现有指标）"""
        now = time.time()
        return {
            "pickup_status": "正常" if pickup_api_available else "异常",
            "last_success_time": last_success_time,
            "last_http_status": last_http_status,
            "last_check_seconds_ago": int(now - last_check_time) if last_check_time else None,
            "cloud_status": "在线" if cloud_online else "离线",
            "control_sku_status": "正常" if control_sku_available else "异常",
            "success_rate_1h": round(success_rate_1h * 100, 1) if success_rate_1h is not None else None,
        }

    def get_full_report(self, current_states: Dict, sku_list: List[Dict],
                        store_list: List[Dict], health_data: Dict = None) -> Dict:
        """生成完整趋势报告"""
        try:
            report = {
                "overview": self.get_overview(current_states, sku_list, store_list),
                "sku_trends": self.get_sku_trends(current_states, sku_list, store_list),
                "store_activity": self.get_store_activity(store_list),
                "city_activity": self.get_city_activity(store_list, current_states, sku_list),
                "restock_pulse": self.get_restock_pulse(),
                "duration_stats": self.get_available_duration_stats(),
                "recent_events": self.get_recent_events(20),
            }
            if health_data:
                report["health"] = self.get_health_status(**health_data)
            return report
        except Exception as e:
            logger.error("趋势分析失败: %s", e, exc_info=True)
            return {"error": str(e), "overview": {"current_available_stores": 0, "total_stores": len(store_list)}}
