#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
China Control - 中国大陆对照组监控
独立模块，监控 iPhone 18 Pro 512GB 白色，用于诊断对照。
不影响主 Duo Monitor，独立状态、独立退避、独立频率。
"""

import os
import time
import json
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class ChinaControlMonitor:
    """
    中国对照组监控
    - 产品：iPhone 18 Pro 512GB 白色（Glacier）
    - Part Number：MJTF4CH/A（经 Apple 中国官网购买页确认 2026-09-11）
    - 门店范围：广东/南京/上海（与 Duo 相同）
    - 默认频率：90 秒（可配置 60-120 秒）
    - 独立退避，不影响主 Monitor
    - 默认不发高优先级通知
    """

    # 经 Apple 中国官网购买页确认的 Part Number
    CONTROL_SKU = {
        "id": "iphone18pro_512_glacier",
        "name": "iPhone 18 Pro 512GB 白色",
        "part_number": "MJTF4CH/A",
        "capacity": "512GB",
        "color": "Glacier（白色）",
        "verified": True,
        "verified_source": "Apple 中国官网购买页 https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro",
        "verified_date": "2026-09-11"
    }

    def __init__(self, config: dict = None, stores = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.interval = self.config.get("interval_seconds", 300)  # v1.3.0: 90→300
        self.api_url = self.config.get("api_url",
            "https://www.apple.com.cn/shop/retail/pickup-message")
        self.postcodes = self.config.get("search_postcodes",
            ["510000", "200000", "210000"])
        self.notify_on_change = self.config.get("notify_on_change", False)

        # 目标门店（支持字典格式{regions:{...}}或列表格式）
        self.target_stores = []
        if isinstance(stores, dict):
            # 从 regions 字典展平
            for region in stores.get("regions", {}).values():
                self.target_stores.extend(region.get("stores", []))
        elif isinstance(stores, list):
            self.target_stores = stores
        self.target_store_numbers = {s["store_number"] for s in self.target_stores}

        # 独立状态
        self.state = {
            "available": None,  # True/False/None
            "last_check": None,
            "last_success": None,
            "last_error": None,
            "last_http_status": None,
            "stores": {},  # store_number -> {available, detail}
            "consecutive_success": 0,
            "consecutive_failure": 0,
        }

        # 独立退避（每个邮编）
        self.backoff = {pc: 0 for pc in self.postcodes}
        self.next_check = {pc: time.time() for pc in self.postcodes}

        # 状态文件
        self.state_file = os.path.expanduser(
            "~/Library/Application Support/iPhoneDuoMonitor/china_control_state.json")
        self._load_state()

    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.state.update(saved)
            except:
                pass

    def _save_state(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except:
            pass

    def check_once(self) -> Dict:
        """
        执行一次检查。返回状态字典。
        独立于主 Monitor，失败不影响主 Monitor。
        """
        if not self.enabled:
            return self.state

        now = time.time()
        any_success = False
        any_attempted = False
        all_stores = {}

        for postcode in self.postcodes:
            # 错峰 + 退避
            if now < self.next_check.get(postcode, 0):
                continue

            any_attempted = True
            try:
                stores = self._query_api(postcode)
                any_success = True
                self.backoff[postcode] = 0
                self.next_check[postcode] = now + self.interval

                for store in stores:
                    sn = store.get("store_number")
                    if sn in self.target_store_numbers:
                        all_stores[sn] = store

            except Exception as e:
                self.state["last_error"] = str(e)
                # 退避 30 -> 60 -> 120
                current = self.backoff.get(postcode, 0)
                new_backoff = 30 if current == 0 else (60 if current == 30 else 120)
                self.backoff[postcode] = new_backoff
                self.next_check[postcode] = now + new_backoff
                logger.warning("China Control 邮编 %s 失败，退避 %d 秒: %s",
                             postcode, new_backoff, e)

        if not any_attempted:
            return self.state

        # 更新状态
        self.state["last_check"] = now
        if any_success:
            self.state["last_success"] = now
            self.state["consecutive_success"] += 1
            self.state["consecutive_failure"] = 0
            self.state["last_http_status"] = 200

            # 解析门店库存
            any_available = False
            for sn in self.target_store_numbers:
                store = all_stores.get(sn)
                if store:
                    parts = store.get("parts", {})
                    part_info = parts.get(self.CONTROL_SKU["part_number"], {})
                    available = (
                        part_info.get("store_selection_enabled", False) or
                        part_info.get("pickup_display") == "available" or
                        part_info.get("pickup_search_quote") == "今天可取货"
                    )
                    if available:
                        any_available = True
                    self.state["stores"][sn] = {
                        "available": available,
                        "store_name": store.get("store_name", ""),
                        "city": store.get("city", ""),
                        "pickup_search_quote": part_info.get("pickup_search_quote", ""),
                    }

            prev_available = self.state["available"]
            self.state["available"] = any_available

            # 状态变化通知（如果启用）
            if self.notify_on_change and prev_available is not None and prev_available != any_available:
                logger.info("China Control 状态变化: %s -> %s", prev_available, any_available)
        else:
            self.state["consecutive_failure"] += 1
            self.state["consecutive_success"] = 0
            self.state["last_http_status"] = 541  # 或其他错误
            # API 失败时明确标记为 UNKNOWN（None），不保持过时的无货状态
            # 门店级状态也标记为未知
            self.state["available"] = None
            for sn in self.state.get("stores", {}):
                self.state["stores"][sn]["available"] = None

        self._save_state()
        return self.state

    def _query_api(self, postcode: str) -> List[dict]:
        """查询 Apple pickup API"""
        import urllib.request
        import urllib.parse

        params = {
            "pl": "true",
            "mts.0": "regular",
            "parts.0": self.CONTROL_SKU["part_number"],
            "location": postcode,
        }
        url = f"{self.api_url}?{urllib.parse.urlencode(params)}"

        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

        start_time = time.time()
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                latency = time.time() - start_time
                # v1.4.0: 请求审计日志
                logger.info("HTTP_REQUEST | module=china_control | endpoint=/shop/retail/pickup-message | location=%s | status=%d | latency=%.2fs",
                            postcode, resp.status, latency)
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("body", {}).get("stores", [])
        except Exception as e:
            latency = time.time() - start_time
            # 提取 HTTP 状态码
            status_str = "NETWORK_ERROR"
            error_msg = str(e)
            if "HTTP Error" in error_msg:
                try:
                    status_str = error_msg.split("HTTP Error ")[1].split(":")[0].strip()
                except:
                    pass
            logger.info("HTTP_REQUEST | module=china_control | endpoint=/shop/retail/pickup-message | location=%s | status=%s | latency=%.2fs | error=%s",
                        postcode, status_str, latency, error_msg[:100])
            raise

    def get_status(self) -> Dict:
        """获取当前状态（用于 GUI 显示）"""
        return {
            "enabled": self.enabled,
            "sku": self.CONTROL_SKU,
            "available": self.state["available"],
            "last_check": self.state["last_check"],
            "last_success": self.state["last_success"],
            "last_error": self.state["last_error"],
            "last_http_status": self.state["last_http_status"],
            "consecutive_success": self.state["consecutive_success"],
            "consecutive_failure": self.state["consecutive_failure"],
            "interval": self.interval,
            "stores_with_stock": [sn for sn, s in self.state["stores"].items()
                                  if s.get("available")],
        }

    def reset_backoff(self):
        """网络切换时重置退避（v1.3.0）"""
        self.state["consecutive_failure"] = 0
        self.state["last_error"] = None
        self._next_check = 0
