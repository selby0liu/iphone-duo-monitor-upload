"""
Product Locator 辅助诊断模块
使用 Apple 官方 product-locator-meta 接口判断 SKU 是否存在、商品状态。
仅用于诊断，不替代 pickup-message 的门店级库存。
"""
import json
import time
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

PRODUCT_LOCATOR_URL = "https://www.apple.com.cn/shop/product-locator-meta?family=iphoneduo"
DEFAULT_TIMEOUT = (5, 10)


class ProductLocatorMonitor:
    def __init__(self, config=None):
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.interval = config.get("interval_seconds", 300)
        self.timeout = config.get("timeout", DEFAULT_TIMEOUT)
        self.last_check = None
        self.last_success = None
        self.last_error = None
        self.http_status = None
        self.latency = None
        self.products = {}
        self.consecutive_failures = 0
        self.backoff_seconds = 0
        self.next_check = 0

    def check(self):
        """查询 product-locator-meta，返回诊断结果"""
        if not self.enabled:
            return {"status": "disabled"}

        now = time.time()
        if now < self.next_check:
            return {"status": "backoff", "next_check": self.next_check}

        start = time.time()
        try:
            req = urllib.request.Request(
                PRODUCT_LOCATOR_URL,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout[1]) as resp:
                self.http_status = resp.status
                body = resp.read().decode("utf-8")
            self.latency = round(time.time() - start, 3)
            self.last_check = now

            # v1.4.0: 请求审计日志
            logger.info("HTTP_REQUEST | module=product_locator | endpoint=/shop/product-locator-meta | location=iphoneduo | status=%d | latency=%.2fs",
                        self.http_status, self.latency)

            if self.http_status != 200:
                self._record_failure(f"HTTP {self.http_status}")
                return self._result("error", f"HTTP {self.http_status}")

            data = json.loads(body)
            self._parse_products(data)
            self._record_success()
            return self._result("ok")

        except urllib.error.HTTPError as e:
            self.http_status = e.code
            self.latency = round(time.time() - start, 3)
            self.last_check = now
            logger.info("HTTP_REQUEST | module=product_locator | endpoint=/shop/product-locator-meta | location=iphoneduo | status=%d | latency=%.2fs | error=HTTPError",
                        e.code, self.latency)
            self._record_failure(f"HTTP Error {e.code}")
            return self._result("error", f"HTTP Error {e.code}")
        except Exception as e:
            self.latency = round(time.time() - start, 3)
            self.last_check = now
            logger.info("HTTP_REQUEST | module=product_locator | endpoint=/shop/product-locator-meta | location=iphoneduo | status=NETWORK_ERROR | latency=%.2fs | error=%s",
                        self.latency, str(e)[:100])
            self._record_failure(str(e))
            return self._result("error", str(e))

    def _parse_products(self, data):
        """解析 product-locator 返回的产品列表"""
        try:
            meta = data["body"]["productLocatorOverlayData"]["productLocatorMeta"]
            products_list = meta.get("products", [])
            prices = meta.get("prices", {})

            self.products = {}
            for p in products_list:
                pn = p.get("partNumber", "")
                if not pn:
                    continue
                price_key = p.get("price", "")
                price_info = prices.get(price_key, {})
                self.products[pn] = {
                    "part_number": pn,
                    "product_title": p.get("productTitle", ""),
                    "capacity": p.get("dimensionCapacity", ""),
                    "color": p.get("dimensionColor", ""),
                    "price": price_info.get("fullPrice", ""),
                    "product_url": p.get("productLink", ""),
                    "base_part_number": p.get("basePartNumber", ""),
                    "exists": True,
                }
        except Exception as e:
            logger.warning(f"Product Locator 解析失败: {e}")

    def sku_exists(self, part_number):
        """检查 SKU 是否在 product-locator 中存在"""
        return part_number in self.products

    def get_sku_info(self, part_number):
        """获取 SKU 信息"""
        return self.products.get(part_number, {"exists": False})

    def _record_success(self):
        self.consecutive_failures = 0
        self.backoff_seconds = 0
        self.last_success = self.last_check
        self.last_error = None
        self.next_check = time.time() + self.interval

    def _record_failure(self, error_msg):
        self.consecutive_failures += 1
        self.last_error = error_msg
        # 退避: 30, 60, 120, 300
        backoff_map = {1: 30, 2: 60, 3: 120}
        self.backoff_seconds = backoff_map.get(self.consecutive_failures, 300)
        self.next_check = time.time() + self.backoff_seconds

    def _result(self, status, error=None):
        return {
            "status": status,
            "http_status": self.http_status,
            "latency": self.latency,
            "last_check": self.last_check,
            "last_success": self.last_success,
            "last_error": error or self.last_error,
            "products_count": len(self.products),
            "consecutive_failures": self.consecutive_failures,
            "backoff_seconds": self.backoff_seconds,
        }

    def reset_backoff(self):
        """网络切换时重置退避"""
        self.consecutive_failures = 0
        self.backoff_seconds = 0
        self.next_check = 0
        logger.info("Product Locator 退避已重置（网络切换）")

    def get_diagnostic_summary(self, skus=None):
        """获取诊断摘要"""
        if not self.products:
            return "Product Locator: 无数据"

        skus = skus or []
        existing = [pn for pn in skus if self.sku_exists(pn)]
        missing = [pn for pn in skus if not self.sku_exists(pn)]

        parts = [f"Product Locator: HTTP {self.http_status}, {len(self.products)}个SKU"]
        if existing:
            parts.append(f"有效: {', '.join(existing)}")
        if missing:
            parts.append(f"未找到: {', '.join(missing)}")
        return " | ".join(parts)
