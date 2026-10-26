#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright Delivery 备选模块 v2
当 fulfillment API 返回 541 时，用 Playwright 浏览器渲染页面提取配送时间。
优化：一次浏览器实例批量查询所有SKU，按产品页面分组，减少内存占用和启动次数。
完全独立，失败不影响主程序。
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# SKU 前缀到购买页面的映射
PRODUCT_PAGES = {
    "MK2": "https://www.apple.com.cn/shop/buy-iphone/iphone-duo",      # iPhone Duo
    "MJY": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro",   # iPhone 18 Pro Max
    "MJT": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro",   # iPhone 18 Pro
}

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")


def get_product_page(part_number: str) -> Optional[str]:
    """根据 SKU 前缀获取购买页面 URL"""
    for prefix, url in PRODUCT_PAGES.items():
        if part_number.startswith(prefix):
            return url
    return None


def group_by_product_page(part_numbers: List[str]) -> Dict[str, List[str]]:
    """按产品页面分组SKU"""
    groups = {}
    for pn in part_numbers:
        url = get_product_page(pn)
        if url:
            groups.setdefault(url, []).append(pn)
    return groups


class PlaywrightDeliveryChecker:
    """用 Playwright 从 Apple 购买页面提取配送时间"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.enabled = self.config.get("playwright_fallback", False)
        self.timeout = self.config.get("playwright_timeout", 45)

    async def get_delivery_info_batch(self, part_numbers: List[str],
                                       location: str = "510000") -> Dict[str, dict]:
        """
        批量获取多个SKU的配送信息。
        一次浏览器实例，按产品页面分组，每个页面只访问一次。
        返回: {part_number: {available, message, delivery_date, source, is_coming_soon}}
        """
        results = {}
        if not self.enabled or not part_numbers:
            for pn in part_numbers:
                results[pn] = {"available": None, "message": "", "delivery_date": "",
                               "source": "disabled", "is_coming_soon": None}
            return results

        groups = group_by_product_page(part_numbers)
        if not groups:
            for pn in part_numbers:
                results[pn] = {"available": None, "message": "", "delivery_date": "",
                               "source": "playwright-unknown-sku", "is_coming_soon": None}
            return results

        browser = None
        playwright = None
        try:
            from playwright.async_api import async_playwright
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT, locale="zh-CN")

            total_start = time.time()

            for url, skus in groups.items():
                try:
                    page = await context.new_page()
                    logger.info("Playwright: 访问 %s (SKU: %s)", url, ",".join(skus))
                    start = time.time()

                    await page.goto(url, wait_until="domcontentloaded",
                                    timeout=self.timeout * 1000)
                    await page.wait_for_timeout(5000)  # 等待JS渲染

                    # 滚动触发懒加载
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2000)
                    await page.evaluate("window.scrollTo(0, 0)")
                    await page.wait_for_timeout(1000)

                    full_text = await page.inner_text("body")
                    load_time = time.time() - start

                    # 同一个页面的所有SKU共享相同的配送信息
                    parsed = self._parse_delivery_text(full_text)
                    for pn in skus:
                        results[pn] = {
                            "available": parsed.get("available"),
                            "message": parsed.get("message", ""),
                            "delivery_date": parsed.get("delivery_date", ""),
                            "source": "playwright",
                            "is_coming_soon": parsed.get("is_coming_soon"),
                        }

                    logger.info("Playwright: %s 加载完成 %.1fs, 配送: %s",
                                ",".join(skus), load_time,
                                parsed.get("message", "")[:60])
                    await page.close()

                except Exception as e:
                    logger.warning("Playwright 页面 %s 失败: %s", url, e)
                    for pn in skus:
                        if pn not in results:
                            results[pn] = {"available": None, "message": "",
                                           "delivery_date": "", "source": "playwright-error",
                                           "is_coming_soon": None, "error": str(e)[:80]}

            total_time = time.time() - total_start
            logger.info("Playwright 批量查询完成: %d个SKU, %.1fs", len(results), total_time)

        except Exception as e:
            logger.warning("Playwright 批量查询异常: %s", e)
            for pn in part_numbers:
                if pn not in results:
                    results[pn] = {"available": None, "message": "", "delivery_date": "",
                                   "source": "playwright-error", "is_coming_soon": None,
                                   "error": str(e)[:80]}
        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()

        # 填充未处理的SKU
        for pn in part_numbers:
            if pn not in results:
                results[pn] = {"available": None, "message": "", "delivery_date": "",
                               "source": "playwright-error", "is_coming_soon": None}
        return results

    def _parse_delivery_text(self, text: str) -> Dict:
        """从页面文本中解析配送信息"""
        result = {
            "available": None,
            "message": "",
            "delivery_date": "",
            "is_coming_soon": None,
        }

        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # 检测是否即将发售（优先匹配）
        for line in lines:
            if ("预购" in line or "发售" in line) and any(
                kw in line for kw in ["月", "日", "点", "晚", "即将"]
            ):
                result["is_coming_soon"] = True
                result["message"] = line[:120]
                break

        # 查找具体配送时间
        import re
        for line in lines:
            if any(kw in line for kw in ["送达", "配送", "送货", "发货", "到货"]):
                if any(kw in line for kw in ["了解", "更多", "方式", "说明", "当商品", "为预计"]):
                    continue
                if len(line) < 200:
                    dates = re.findall(r'\d{1,2}月\d{1,2}日|周[一二三四五六日]|[\d.]+[-至到][\d.]+', line)
                    if dates:
                        result["delivery_date"] = dates[0]
                        if not result["message"]:
                            result["message"] = line[:120]
                        result["available"] = True
                        break

        # 如果没找到即将发售也没找到配送时间，检查"有货/无货"
        if not result["message"]:
            for line in lines:
                if "暂无" in line or "无货" in line or "不可购买" in line:
                    result["available"] = False
                    result["message"] = line[:120]
                    break
                if "有货" in line or "可取" in line:
                    result["available"] = True
                    result["message"] = line[:120]
                    break

        return result


# 同步包装器
def get_delivery_batch_sync(part_numbers: List[str], location: str = "510000",
                            config: dict = None) -> Dict[str, dict]:
    """同步批量获取配送信息"""
    checker = PlaywrightDeliveryChecker(config)
    return asyncio.run(checker.get_delivery_info_batch(part_numbers, location))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = {"playwright_fallback": True}

    print("=== 批量测试 7个SKU ===")
    skus = ["MK2P4CH/A", "MK2Q4CH/A", "MK2T4CH/A", "MK2U4CH/A",
            "MJYC4CH/A", "MJYE4CH/A", "MJYD4CH/A"]
    results = get_delivery_batch_sync(skus, "510000", config)
    for pn, r in results.items():
        print(f"  {pn}: {r.get('message', '')[:60]} (source={r.get('source')})")
