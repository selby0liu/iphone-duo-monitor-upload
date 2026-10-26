#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Australia Control - 澳大利亚对照组监控
独立模块，只监控 Adelaide Apple Store。
不影响中国主 Monitor，独立状态、独立退避、独立频率。
"""

import os
import time
import json
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class AustraliaControlMonitor:
    """
    澳洲对照组监控
    - 只监控 South Australia / Adelaide
    - SKU：iPhone Duo 512GB Star White + iPhone 18 Pro 512GB Glacier
    - 门店：Apple Rundle Place（Adelaide，Store ID R405）
    - 默认频率：60 秒（可配置 60-120 秒）
    - 独立退避，不影响中国模块
    - 默认不发高优先级通知
    """

    # 经 Apple 澳洲官网确认的 Part Number
    DUO_SKU = {
        "id": "duo_512_starwhite_au",
        "name": "iPhone Duo 512GB Star White",
        "part_number": "MK2F4X/A",
        "capacity": "512GB",
        "color": "Star White",
        "verified": True,
        "verified_source": "Apple 澳洲官网购买页 https://www.apple.com/au/shop/buy-iphone/iphone-duo",
        "verified_date": "2026-09-11"
    }

    IPHONE18_SKU = {
        "id": "iphone18pro_512_glacier_au",
        "name": "iPhone 18 Pro 512GB Glacier",
        "part_number": "MJRX4X/A",
        "capacity": "512GB",
        "color": "Glacier",
        "verified": True,
        "verified_source": "Apple 澳洲官网购买页 https://www.apple.com/au/shop/buy-iphone/iphone-18-pro",
        "verified_date": "2026-09-11"
    }

    # Adelaide 直营店（经 Apple 澳洲官网确认）
    ADELAIDE_STORES = [
        {
            "store_number": "R405",
            "store_name": "Apple Rundle Place",
            "city": "Adelaide",
            "address": "Rundle Place, 91-99 Rundle Mall, Adelaide SA 5000",
        }
    ]

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.interval = self.config.get("interval_seconds", 300)  # v1.3.0: 60→300
        self.api_url = self.config.get("api_url",
            "https://www.apple.com/au/shop/retail/pickup-message")
        self.notify_on_change = self.config.get("notify_on_change", False)

        self.target_store_numbers = {s["store_number"] for s in self.ADELAIDE_STORES}

        # 独立状态（每个 SKU 独立）
        self.state = {
            "duo": {
                "available": None,
                "last_check": None,
                "last_success": None,
                "last_error": None,
                "last_http_status": None,
                "stores": {},
            },
            "iphone18": {
                "available": None,
                "last_check": None,
                "last_success": None,
                "last_error": None,
                "last_http_status": None,
                "stores": {},
            },
            "consecutive_success": 0,
            "consecutive_failure": 0,
        }

        # 独立退避
        self.backoff = 0
        self.next_check = time.time()

        self.state_file = os.path.expanduser(
            "~/Library/Application Support/iPhoneDuoMonitor/australia_control_state.json")
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
        """执行一次检查，独立于中国模块"""
        if not self.enabled:
            return self.state

        now = time.time()
        if now < self.next_check:
            return self.state

        try:
            # 一次请求批量查询两个 SKU
            stores = self._query_api()
            self.backoff = 0
            self.next_check = now + self.interval
            self.state["consecutive_success"] += 1
            self.state["consecutive_failure"] = 0

            # 解析 Duo
            self._parse_stores(stores, self.DUO_SKU, "duo")
            # 解析 iPhone 18 Pro
            self._parse_stores(stores, self.IPHONE18_SKU, "iphone18")

        except Exception as e:
            self.state["consecutive_failure"] += 1
            self.state["consecutive_success"] = 0
            self.state["duo"]["last_error"] = str(e)
            self.state["iphone18"]["last_error"] = str(e)
            # 退避 30 -> 60 -> 120
            current = self.backoff
            self.backoff = 30 if current == 0 else (60 if current == 30 else 120)
            self.next_check = now + self.backoff
            logger.warning("Australia Control 失败，退避 %d 秒: %s", self.backoff, e)
            # API 失败时明确标记为 UNKNOWN（None）
            self.state["duo"]["available"] = None
            self.state["iphone18"]["available"] = None
            for sn in self.state["duo"].get("stores", {}):
                self.state["duo"]["stores"][sn]["available"] = None
            for sn in self.state["iphone18"].get("stores", {}):
                self.state["iphone18"]["stores"][sn]["available"] = None

        self._save_state()
        return self.state

    def _parse_stores(self, stores: List[dict], sku: dict, state_key: str):
        """解析门店库存"""
        any_available = False
        for store in stores:
            sn = store.get("store_number")
            if sn not in self.target_store_numbers:
                continue

            parts = store.get("partsAvailability", store.get("parts", {}))
            part_info = parts.get(sku["part_number"], {})
            available = (
                part_info.get("storeSelectionEnabled", False) or
                part_info.get("pickupDisplay") == "available" or
                part_info.get("pickupSearchQuote") == "Available today"
            )
            if available:
                any_available = True

            self.state[state_key]["stores"][sn] = {
                "available": available,
                "store_name": store.get("storeName", store.get("store_name", "")),
                "pickup_search_quote": part_info.get("pickupSearchQuote",
                                                     part_info.get("pickup_search_quote", "")),
            }

        self.state[state_key]["available"] = any_available
        self.state[state_key]["last_check"] = time.time()
        self.state[state_key]["last_success"] = time.time()
        self.state[state_key]["last_http_status"] = 200

    def _query_api(self) -> List[dict]:
        """查询 Apple 澳洲 pickup API，批量查询两个 SKU"""
        import urllib.request
        import urllib.parse

        params = {
            "pl": "true",
            "mts.0": "regular",
            "mts.1": "regular",
            "parts.0": self.DUO_SKU["part_number"],
            "parts.1": self.IPHONE18_SKU["part_number"],
            "location": "5000",  # Adelaide 邮编
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
                logger.info("HTTP_REQUEST | module=australia_control | endpoint=/shop/retail/pickup-message | location=Adelaide-5000 | status=%d | latency=%.2fs",
                            resp.status, latency)
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
            logger.info("HTTP_REQUEST | module=australia_control | endpoint=/shop/retail/pickup-message | location=Adelaide-5000 | status=%s | latency=%.2fs | error=%s",
                        status_str, latency, error_msg[:100])
            raise

    def get_status(self) -> Dict:
        """获取当前状态（用于 GUI 显示）"""
        return {
            "enabled": self.enabled,
            "duo_sku": self.DUO_SKU,
            "iphone18_sku": self.IPHONE18_SKU,
            "stores": self.ADELAIDE_STORES,
            "duo_available": self.state["duo"]["available"],
            "iphone18_available": self.state["iphone18"]["available"],
            "last_check": self.state["duo"]["last_check"],
            "last_success": self.state["duo"]["last_success"],
            "last_error": self.state["duo"]["last_error"],
            "consecutive_success": self.state["consecutive_success"],
            "consecutive_failure": self.state["consecutive_failure"],
            "interval": self.interval,
            "backoff": self.backoff,
        }

    def reset_backoff(self):
        """网络切换时重置退避（v1.3.0）"""
        self.backoff = 0
        self.state["consecutive_failure"] = 0
        self.state["duo"]["last_error"] = None
        self.state["iphone18"]["last_error"] = None
