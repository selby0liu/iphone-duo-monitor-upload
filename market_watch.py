#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Market Watch - 二级市场溢价趋势监控
独立模块，监控 iPhone Duo 上市初期黄牛加价变化。
数据仅保存在本机，不影响 Apple 库存 monitor。
"""

import os
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from statistics import median, mean

logger = logging.getLogger(__name__)


class MarketWatch:
    """
    二级市场行情监控
    - 重点 SKU：四个 iPhone Duo 型号
    - 数据展示：原价、最低/中位/平均报价、溢价金额/百分比、24h/7d变化、最高/最低溢价
    - 本地历史数据保存
    - 数据源模块化，默认标记不可用的来源
    - 自动清洗无效报价
    """

    # Apple 官网原价（人民币，2026-09-12 经 Apple 中国官网确认）
    # 256GB: ¥15999, 512GB: ¥17999, 1TB: ¥21499, 2TB: ¥26499
    OFFICIAL_PRICES = {
        "duo_512_starlight": 17999,  # 512GB 星光白
        "duo_512_midnight": 17999,   # 512GB 夜空色
        "duo_1tb_starlight": 21499,  # 1TB 星光白
        "duo_1tb_midnight": 21499,   # 1TB 夜空色
    }

    SKU_MAP = {
        "duo_512_starlight": {"name": "512GB 星光白", "part_number": "MK2P4CH/A"},
        "duo_512_midnight": {"name": "512GB 夜空色", "part_number": "MK2Q4CH/A"},
        "duo_1tb_starlight": {"name": "1TB 星光白", "part_number": "MK2T4CH/A"},
        "duo_1tb_midnight": {"name": "1TB 夜空色", "part_number": "MK2U4CH/A"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", False)  # 默认关闭
        self.interval_minutes = self.config.get("interval_minutes", 60)
        self.data_file = os.path.expanduser(
            "~/Library/Application Support/iPhoneDuoMonitor/market_data.json")
        self.samples = self._load_data()

        # 数据源状态
        self.data_sources = {
            "manual": {"available": True, "name": "手动输入"},
            "xianyu": {"available": False, "name": "闲鱼", "reason": "需登录，反爬限制"},
            "taobao": {"available": False, "name": "淘宝", "reason": "需登录，反爬限制"},
        }
        self.last_fetch = None
        self.last_error = None

    def _load_data(self) -> List[dict]:
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save_data(self):
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.samples, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("保存行情数据失败: %s", e)

    def add_manual_sample(self, sku_id: str, price: float, source: str = "manual",
                          sample_type: str = "listing") -> bool:
        """手动添加报价样本"""
        if sku_id not in self.SKU_MAP:
            return False
        official = self.OFFICIAL_PRICES.get(sku_id, 15999)
        # 极端价格直接拒绝（低于原价50%或高于原价300%或超过10万）
        if price <= 0 or price < official * 0.5 or price > official * 3 or price > 100000:
            return False

        sample = {
            "timestamp": time.time(),
            "sku_id": sku_id,
            "price": price,
            "source": source,
            "sample_type": sample_type,
            "excluded": False,
            "exclude_reason": None,
        }
        self.samples.append(sample)
        self._save_data()
        return True

    def _is_valid_sample(self, sample: dict) -> bool:
        """数据清洗：判断样本是否有效"""
        if sample.get("excluded"):
            return False

        sku_id = sample.get("sku_id")
        price = sample.get("price", 0)
        sample_type = sample.get("sample_type", "")

        # 排除非目标类型
        if sample_type in ["deposit", "recycle", "rental", "accessory",
                           "installment", "wanted", "overseas"]:
            return False

        # 极端价格排除（低于原价50%或高于原价300%）
        official = self.OFFICIAL_PRICES.get(sku_id, 15999)
        if price < official * 0.5 or price > official * 3:
            return False

        return True

    def get_sku_stats(self, sku_id: str, hours: int = None) -> Dict:
        """获取指定 SKU 的统计数据"""
        if sku_id not in self.SKU_MAP:
            return {}

        official = self.OFFICIAL_PRICES.get(sku_id, 15999)
        cutoff = time.time() - hours * 3600 if hours else 0
        valid_samples = [s for s in self.samples
                        if s["sku_id"] == sku_id
                        and s["timestamp"] >= cutoff
                        and self._is_valid_sample(s)]

        if not valid_samples:
            return {
                "sku_id": sku_id,
                "name": self.SKU_MAP[sku_id]["name"],
                "official_price": official,
                "current_min": None,
                "current_median": None,
                "current_avg": None,
                "premium_amount": None,
                "premium_percent": None,
                "sample_count": 0,
                "change_24h": None,
                "change_7d": None,
                "all_time_high": None,
                "all_time_low": None,
                "last_updated": None,
            }

        prices = [s["price"] for s in valid_samples]
        current_min = min(prices)
        current_median = median(prices)
        current_avg = mean(prices)

        # 24h 变化
        samples_24h = [s for s in valid_samples
                      if s["timestamp"] >= time.time() - 86400]
        change_24h = None
        if len(samples_24h) >= 2:
            change_24h = samples_24h[-1]["price"] - samples_24h[0]["price"]

        # 7d 变化
        samples_7d = [s for s in valid_samples
                     if s["timestamp"] >= time.time() - 7 * 86400]
        change_7d = None
        if len(samples_7d) >= 2:
            change_7d = samples_7d[-1]["price"] - samples_7d[0]["price"]

        # 历史最高最低
        all_valid = [s for s in self.samples
                    if s["sku_id"] == sku_id and self._is_valid_sample(s)]
        all_prices = [s["price"] for s in all_valid]

        return {
            "sku_id": sku_id,
            "name": self.SKU_MAP[sku_id]["name"],
            "part_number": self.SKU_MAP[sku_id]["part_number"],
            "official_price": official,
            "current_min": current_min,
            "current_median": current_median,
            "current_avg": round(current_avg, 2),
            "premium_amount": round(current_median - official, 2),
            "premium_percent": round((current_median - official) / official * 100, 2),
            "sample_count": len(valid_samples),
            "change_24h": change_24h,
            "change_7d": change_7d,
            "all_time_high": max(all_prices) if all_prices else None,
            "all_time_low": min(all_prices) if all_prices else None,
            "last_updated": valid_samples[-1]["timestamp"] if valid_samples else None,
            "data_sources": list(set(s["source"] for s in valid_samples)),
        }

    def get_all_stats(self, hours: int = None) -> Dict[str, Dict]:
        """获取所有 SKU 的统计"""
        return {sku_id: self.get_sku_stats(sku_id, hours)
                for sku_id in self.SKU_MAP}

    def get_trend_data(self, sku_id: str, days: int = 7) -> List[dict]:
        """获取趋势图数据（按天聚合）"""
        if sku_id not in self.SKU_MAP:
            return []

        cutoff = time.time() - days * 86400
        valid_samples = [s for s in self.samples
                        if s["sku_id"] == sku_id
                        and s["timestamp"] >= cutoff
                        and self._is_valid_sample(s)]

        # 按天聚合
        daily = {}
        for s in valid_samples:
            day = datetime.fromtimestamp(s["timestamp"]).strftime("%Y-%m-%d")
            if day not in daily:
                daily[day] = []
            daily[day].append(s["price"])

        trend = []
        for day in sorted(daily.keys()):
            prices = daily[day]
            trend.append({
                "date": day,
                "median": median(prices),
                "avg": round(mean(prices), 2),
                "min": min(prices),
                "max": max(prices),
                "count": len(prices),
            })
        return trend

    def fetch_market_data(self) -> bool:
        """
        尝试从公开数据源获取行情数据。
        当前大多数二级市场源需要登录或有反爬，默认标记不可用。
        不使用 CAPTCHA 绕过、代理池、Cookie 伪造等手段。
        """
        if not self.enabled:
            return False

        self.last_fetch = time.time()

        # 尝试公开数据源（如果可访问）
        # 由于合规性限制，当前仅支持手动输入
        # 未来可扩展无需登录的公开价格比较源
        available_sources = [k for k, v in self.data_sources.items()
                           if v.get("available")]

        if not available_sources or available_sources == ["manual"]:
            self.last_error = "无可用自动数据源，仅支持手动输入"
            return False

        return False

    def get_status(self) -> Dict:
        """获取模块状态（用于 GUI）"""
        all_stats = self.get_all_stats()
        total_samples = sum(s["sample_count"] for s in all_stats.values())
        return {
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "total_samples": total_samples,
            "last_fetch": self.last_fetch,
            "last_error": self.last_error,
            "data_sources": self.data_sources,
            "stats": all_stats,
        }

    def clear_data(self):
        """清除所有行情数据"""
        self.samples = []
        self._save_data()
