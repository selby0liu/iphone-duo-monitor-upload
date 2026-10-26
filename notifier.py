#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通知模块
- macOS 系统通知（osascript）
- 本地提示音（afplay）
- Bark 推送（可选）
- 自动打开购买页（可选）
"""

import subprocess
import logging
import time
from typing import List, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


class Notifier:
    """多渠道通知"""

    def __init__(self, config: dict, skus: list, stores: dict):
        self.config = config
        self.notif_cfg = config.get("notification", {})
        self.skus = {s["id"]: s for s in skus}
        self.stores = stores
        self._last_notify_time = 0
        self._notify_cooldown = 2  # 通知冷却时间（秒），防止瞬间重复

    def _get_sku_info(self, sku_id: str) -> dict:
        return self.skus.get(sku_id, {})

    def _get_store_info(self, store_number: str) -> dict:
        for region in self.stores.get("regions", {}).values():
            for s in region.get("stores", []):
                if s["store_number"] == store_number:
                    return s
        return {"name": store_number, "city": "", "address": ""}

    def _build_buy_url(self, part_number: str) -> str:
        """构建 Apple 官方购买页 URL（根据 SKU 类型选择对应产品页）"""
        if part_number.startswith("MJY"):
            product_slug = "iphone-18-pro"
        else:
            product_slug = "iphone-duo"
        return f"https://www.apple.com.cn/shop/buy-iphone/{product_slug}/{part_number}"

    def _format_message(self, alert: dict) -> dict:
        """格式化通知内容"""
        sku_id = alert.get("sku_id", "")
        sku = self._get_sku_info(sku_id)
        part_number = sku.get("part_number", "")
        capacity = sku.get("capacity", "")
        color = sku.get("color", "")
        name = sku.get("name", f"iPhone Duo {capacity} {color}")
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        buy_url = self._build_buy_url(part_number)

        if alert["type"] == "pickup":
            store_number = alert.get("store_number", "")
            store = self._get_store_info(store_number)
            detail = alert.get("detail", {})
            pickup_quote = detail.get("store_pickup_quote", "")
            title = "iPhone Duo 到店取货有货！"
            body = (
                f"产品：{name}\n"
                f"型号：{part_number}\n"
                f"容量：{capacity}\n"
                f"颜色：{color}\n"
                f"库存类型：到店取货\n"
                f"门店：{store.get('name', '')}（{store.get('city', '')}）\n"
                f"地址：{store.get('address', '')}\n"
                f"取货信息：{pickup_quote}\n"
                f"时间：{now}\n"
                f"购买入口：{buy_url}"
            )
        else:  # delivery
            detail = alert.get("detail", {})
            delivery_date = detail.get("delivery_date", "")
            message = detail.get("message", "")
            title = "iPhone Duo 官网配送有货！"
            body = (
                f"产品：{name}\n"
                f"型号：{part_number}\n"
                f"容量：{capacity}\n"
                f"颜色：{color}\n"
                f"库存类型：官网配送\n"
                f"配送信息：{message}\n"
                f"预计送达：{delivery_date or '见官网'}\n"
                f"时间：{now}\n"
                f"购买入口：{buy_url}"
            )

        return {
            "title": title,
            "body": body,
            "buy_url": buy_url,
            "part_number": part_number,
            "sku_name": name,
        }

    def send_macos_notification(self, title: str, body: str):
        """发送 macOS 系统通知"""
        if not self.notif_cfg.get("macos_notification", True):
            return
        try:
            # 替换 body 中的换行符，osascript 需要转义
            body_escaped = body.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            script = f'display notification "{body_escaped}" with title "{title}" sound name "Glass"'
            subprocess.run(["osascript", "-e", script],
                         capture_output=True, timeout=5)
            logger.info("macOS 通知已发送")
        except Exception as e:
            logger.error("macOS 通知失败: %s", e)

    def play_sound(self):
        """播放本地提示音"""
        if not self.notif_cfg.get("sound", True):
            return
        sound_file = self.notif_cfg.get("sound_file",
            "/System/Library/Sounds/Glass.aiff")
        try:
            subprocess.Popen(["afplay", sound_file],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            logger.info("提示音已播放")
        except Exception as e:
            logger.error("播放提示音失败: %s", e)

    def send_bark(self, title: str, body: str, url: str = ""):
        """发送 Bark 推送"""
        bark_cfg = self.notif_cfg.get("bark", {})
        if not bark_cfg.get("enabled", False):
            return
        bark_url = bark_cfg.get("url", "").strip()
        if not bark_url:
            logger.warning("Bark 已启用但未配置 URL")
            return
        try:
            # Bark URL 格式: https://api.day.app/key/title/body
            full_url = f"{bark_url.rstrip('/')}/{quote(title)}/{quote(body)}"
            params = {}
            if url:
                params["url"] = url
            resp = requests.get(full_url, params=params, timeout=10)
            logger.info("Bark 推送状态码: %s", resp.status_code)
        except Exception as e:
            logger.error("Bark 推送失败: %s", e)

    def open_buy_page(self, url: str):
        """在浏览器中打开购买页"""
        if not self.notif_cfg.get("auto_open_buy_page", False):
            return
        try:
            subprocess.Popen(["open", url])
            logger.info("已打开购买页: %s", url)
        except Exception as e:
            logger.error("打开购买页失败: %s", e)

    def notify(self, alerts: List[dict]):
        """
        发送一组报警通知
        alerts: 状态变化报警列表
        """
        if not alerts:
            return

        # 冷却检查
        now = time.time()
        if now - self._last_notify_time < self._notify_cooldown:
            logger.info("通知冷却中，跳过")
            return
        self._last_notify_time = now

        for alert in alerts:
            formatted = self._format_message(alert)
            title = formatted["title"]
            body = formatted["body"]
            buy_url = formatted["buy_url"]

            logger.info("=" * 60)
            logger.info("有货报警！%s", title)
            logger.info(body)
            logger.info("=" * 60)

            # 各渠道独立发送
            self.send_macos_notification(title, body)
            self.play_sound()
            self.send_bark(title, body, buy_url)
            self.open_buy_page(buy_url)

            # 多个报警之间稍作间隔
            time.sleep(0.5)

    def send_startup_notification(self, enabled_skus: list, store_count: int,
                                   interval: int, delivery_enabled: bool):
        """启动通知"""
        sku_names = [s.get("name", s.get("part_number", "")) for s in enabled_skus]
        title = "苹果库存监控-柳景盛开发已启动"
        body = (
            f"监控 SKU：{len(enabled_skus)} 个\n"
            f"{chr(10).join(sku_names)}\n"
            f"目标门店：{store_count} 家\n"
            f"官网配送：{'启用' if delivery_enabled else '禁用'}\n"
            f"检查间隔：{interval} 秒\n"
            f"启动时间：{time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.send_macos_notification(title, body)
        logger.info("启动通知已发送")
