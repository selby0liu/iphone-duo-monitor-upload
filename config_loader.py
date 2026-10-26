#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置加载器
- 加载主配置、SKU 配置、门店白名单
- 验证配置完整性
"""

import json
import os
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """配置错误"""
    pass


def load_config(config_dir: str = None) -> Tuple[dict, list, dict]:
    """
    加载所有配置文件
    返回: (config, skus, stores)
    """
    if config_dir is None:
        config_dir = os.path.dirname(os.path.abspath(__file__))

    config_path = os.path.join(config_dir, "config.json")
    skus_path = os.path.join(config_dir, "skus.json")
    stores_path = os.path.join(config_dir, "stores.json")

    # 加载主配置
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 加载 SKU 配置
    with open(skus_path, "r", encoding="utf-8") as f:
        skus_data = json.load(f)
    skus = skus_data.get("skus", [])

    # 加载门店白名单
    with open(stores_path, "r", encoding="utf-8") as f:
        stores = json.load(f)

    # 验证
    _validate(config, skus, stores)

    return config, skus, stores


def _validate(config: dict, skus: list, stores: dict):
    """验证配置完整性"""
    # 检查 SKU
    if not skus:
        raise ConfigError("SKU 配置为空")
    for sku in skus:
        if not sku.get("part_number"):
            raise ConfigError(f"SKU 缺少 part_number: {sku}")
        if not sku.get("id"):
            raise ConfigError(f"SKU 缺少 id: {sku}")

    # 检查门店
    regions = stores.get("regions", {})
    if not regions:
        raise ConfigError("门店白名单为空")
    total = 0
    for region_name, region in regions.items():
        for store in region.get("stores", []):
            if not store.get("store_number"):
                raise ConfigError(f"门店缺少 store_number: {store}")
            total += 1
    logger.info("配置验证通过：%d 个 SKU，%d 家门店", len(skus), total)


def get_enabled_skus(skus: list) -> list:
    """获取启用的 SKU 列表"""
    return [s for s in skus if s.get("enabled", False)]


def get_all_store_numbers(stores: dict) -> list:
    """获取所有目标门店的 store_number 列表"""
    numbers = []
    for region in stores.get("regions", {}).values():
        for store in region.get("stores", []):
            numbers.append(store["store_number"])
    return numbers


def get_store_map(stores: dict) -> dict:
    """获取 store_number -> store_info 的映射"""
    store_map = {}
    for region in stores.get("regions", {}).values():
        for store in region.get("stores", []):
            store_map[store["store_number"]] = store
    return store_map
