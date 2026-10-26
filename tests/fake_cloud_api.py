#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地假 Cloud API（仅用于验证 Mac 端 Checkout Assistant 整条链路）

- 只监听 127.0.0.1，纯标准库，不访问 Apple，不访问真实服务器
- 返回与真实 cloud_api /status 相同结构的 JSON，inventory 用项目自带的 skus.json / stores.json 生成
- 时间线从 App 第一次请求 /status 开始计时，按脚本翻转库存，用来验证：
    baseline → 无货变有货 → 同 SKU 多店只开 1 个标签 → 冷却不重复 → 不同 SKU 每轮最多 2 个标签 → 冷却过期后再次打开

用法：
    python3 tests/fake_cloud_api.py            # 默认 127.0.0.1:8766
    python3 tests/fake_cloud_api.py --port 8766

然后在 Test.app 设置里把 Cloud 服务器地址临时改为 http://127.0.0.1:8766，保存后完全退出并重新启动 App。
测试结束后务必改回真实地址并重启 App，再 Ctrl+C 停掉本脚本。
"""

import os
import sys
import json
import time
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

A = "duo_512_starlight"        # MK2P4CH/A
B = "iphone18pm_512_silver"    # MJYC4CH/A
C = "duo_1tb_midnight"         # MK2U4CH/A
D = "iphone18pm_512_glacier"   # MJYE4CH/A
E = "duo_512_midnight"         # MK2Q4CH/A

# (开始秒数, 有货集合 {sku_id: [store_number...]}, App 预期表现)
TIMELINE = [
    (0,   {},                                                  "全部无货：第一次 snapshot 建立 baseline，不弹页面"),
    (30,  {A: ["R577", "R639", "R390"]},                       "A 三店同时有货：弹 1 个标签页（MK2P4CH/A），消息栏合并显示 3 家门店"),
    (60,  {A: ["R577", "R639", "R390", "R401"]},               "A 新增第 4 店：日志 [Checkout] 冷却中，不弹"),
    (90,  {A: ["R577", "R639", "R390", "R401"], B: ["R359"]},  "B 有货：弹第 2 个标签页（MJYC4CH/A，18 Pro Max 页面）"),
    (120, {B: ["R359"]},                                       "A 全部转无货：消息栏出现无货记录，不弹"),
    (150, {A: ["R577"], B: ["R359"]},                          "A 再次有货：仍在 600 秒冷却内，日志 [Checkout] 冷却中，不弹"),
    (180, {A: ["R577"], B: ["R359"], C: ["R577"], D: ["R577"], E: ["R577"]},
                                                               "C/D/E 同一轮有货：弹 2 个标签页 + 1 条 [Checkout] 本轮已达标签页上限"),
    (660, {B: ["R359"], C: ["R577"], D: ["R577"], E: ["R577"]}, "A 转无货（为冷却过期后的再次触发做准备）"),
    (690, {A: ["R639"], B: ["R359"], C: ["R577"], D: ["R577"], E: ["R577"]},
                                                               "A 再次有货且冷却已过（690-30 > 600）：再弹 1 个标签页"),
    (720, {A: ["R639"], B: ["R359"], C: ["R577"], D: ["R577"], E: ["R577"]}, "保持不变，测试结束，可改回真实服务器地址"),
]


ALL_STORES = ["R577", "R639", "R793", "R484", "R761", "R703", "R493", "R643",
              "R390", "R401", "R359", "R389", "R678", "R683", "R581", "R705"]
SZ = ["R793", "R484", "R761"]
GZ = ["R577", "R639"]
OTHER = [x for x in ALL_STORES if x not in SZ + GZ]
DUO = [A, E, "duo_1tb_starlight", C]

# 开售彩排：模拟 10 月 16 日 20:00 预购开放 → 名额被抢 → 零星补货
TIMELINE_LAUNCH = [
    (0,   {},                                                        "全部无货：baseline"),
    (30,  {k: list(ALL_STORES) for k in DUO},                         "开售！4 个 Duo × 16 店同时有货：预期 1 条合并通知【深圳】64 条、Mac 开 2 页（一级优先）、Bark 4 条（critical）"),
    (90,  {A: GZ + OTHER, E: list(ALL_STORES), "duo_1tb_starlight": OTHER, C: OTHER},
                                                                     "深圳的 512 星光白 / 1TB 售罄，其它城市还在：不弹页（已开过）"),
    (150, {A: ["R390"], E: ["R577"]},                                "基本抢空，只剩上海 1 店 / 广州 1 店"),
    (210, {A: ["R390"], E: ["R577"], C: ["R793"]},                   "深圳前海壹方城补货 1TB 夜空：应立即弹页 + 【深圳】critical 推送（不受冷却）"),
    (270, {A: ["R390", "R401"], E: ["R577"], C: ["R793"]},           "上海环贸补货 512 星光白：只通知不开页（非重点）"),
    (330, {A: ["R390", "R401", "R484", "R761"], E: ["R577"], C: ["R793"]},
                                                                     "深圳两店同时补货同一 SKU：只开 1 页，推送里合并两店"),
    (390, {}, "全部售罄，彩排结束，改回真实服务器地址"),
]


# 门店助手彩排：用 iPhone 18 Pro Max（已开售，购买页有真实取货门店列表），
# 全部命中深圳一级重点门店，验证 Mac 打开页面 → 扩展自动点开供货情况 → 选中最高优先门店。
# 只安排 2 次开页，避免多余的 Apple 页面访问。
S18 = "iphone18pm_512_silver"     # MJYC4CH/A
G18 = "iphone18pm_512_glacier"    # MJYE4CH/A

TIMELINE_REHEARSAL18 = [
    (0,  {},                                  "全部无货：建立基线，不开页"),
    (25, {S18: ["R761", "R484", "R793"]},     "18PM 银色 深圳三店同时有货：应开 1 个标签页，"
                                              "fragment 候选顺序 R793,R484,R761"),
    (55, {S18: ["R761", "R484", "R793"],
          G18: ["R793", "R577"]},             "18PM 冰川色 前海壹方城+天环广场：应开第 2 个标签页，"
                                              "候选 R793,R577"),
    (85, {},                                  "全部转无货，彩排结束"),
]

# iPhone 17 彩排：17 已开售、购买页有真实取货门店列表，最适合验证扩展能不能真的选中门店。
# 依赖 skus.json 里一条临时条目 iphone17_rehearsal（跑完会删掉），只开 1 个标签页。
I17 = "iphone17_rehearsal"        # MG704CH/A

TIMELINE_REHEARSAL17 = [
    (0,  {},                                  "全部无货：建立基线，不开页"),
    (25, {I17: ["R761", "R484", "R793"]},     "iPhone 17 深圳三店同时有货：应开 1 个标签页，"
                                              "fragment 候选顺序 R793,R484,R761，"
                                              "扩展应自动点开供货情况并选中其中仍可取货的最高优先门店"),
    (75, {},                                  "转无货，彩排结束"),
]


def load_json(name):
    with open(os.path.join(ROOT, name), "r", encoding="utf-8") as f:
        return json.load(f)


SKUS = [s for s in load_json("skus.json")["skus"] if s.get("enabled", True)]
STORES = []
for _region, _data in load_json("stores.json")["regions"].items():
    for _s in _data["stores"]:
        STORES.append(_s)


def phase_for(elapsed):
    idx = 0
    for i, (start, _, _) in enumerate(TIMELINE):
        if elapsed >= start:
            idx = i
    return idx


def build_inventory(available_map, now):
    inv = {}
    for sku in SKUS:
        for st in STORES:
            avail = st["store_number"] in available_map.get(sku["id"], [])
            inv[f"{sku['id']}|{st['store_number']}"] = {
                "available": avail,
                "last_checked": now,
                "last_available": now if avail else None,
                "first_detected": now if avail else None,
                "detail": {
                    "store_name": st["name"],
                    "city": st["city"],
                    "address": st["address"],
                    "product_title": sku["name"],
                    "pickup_search_quote": "今天可取货" if avail else "暂无供应",
                    "store_pickup_quote": "今天可取货" if avail else "目前暂不提供 Apple Store 零售店取货服务",
                    "pickup_display": "available" if avail else "unavailable",
                },
            }
    return inv


def build_status(elapsed, start_time, check_count):
    now = time.time()
    idx = phase_for(elapsed)
    available_map = TIMELINE[idx][1]
    inventory = build_inventory(available_map, now)
    available_stores = {s for stores in available_map.values() for s in stores}
    return {
        "service": "iphone-duo-monitor",
        "version": "FAKE-LOCAL-TEST",
        "online": True,
        "server_time": now,
        "monitor": {
            "running": True,
            "uptime_seconds": now - start_time,
            "check_count": check_count,
            "last_check": now,
            "last_error": "",
        },
        "pickup": {
            "api_available": True,
            "last_http_status": 200,
            "last_success_time": now,
            "consecutive_success": check_count,
            "consecutive_failures": 0,
        },
        "delivery": {"api_available": None, "last_http_status": None},
        "inventory": inventory,
        "rate_limiter": {"global_requests_last_60s": 0},
        "skus": [s["part_number"] for s in SKUS],
        "store_count": len(STORES),
        "api_stats": {"success_rate": 100.0},
        "trends": {
            "overview": {
                "current_available_stores": len(available_stores),
                "total_stores": len(STORES),
                "restocks_1h": 0, "restocks_6h": 0, "restocks_24h": 0,
                "last_restock_time": None,
                "most_active_city": "-",
            },
            "restock_pulse": {"restocks_30m": 0, "is_active": False, "by_city": {}},
            "recent_events": [],
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--scenario",
                        choices=["default", "launch", "rehearsal18", "rehearsal17"], default="default",
                        help="default=去重/冷却验证；launch=开售彩排（大波次 + 深圳优先）；"
                             "rehearsal18=门店助手彩排（18 Pro Max，只开 2 页）；"
                             "rehearsal17=门店助手彩排（iPhone 17，有真实取货门店，只开 1 页）")
    args = parser.parse_args()
    global TIMELINE
    if args.scenario == "launch":
        TIMELINE = TIMELINE_LAUNCH
    elif args.scenario == "rehearsal18":
        TIMELINE = TIMELINE_REHEARSAL18
    elif args.scenario == "rehearsal17":
        TIMELINE = TIMELINE_REHEARSAL17
    if args.host != "127.0.0.1":
        print("拒绝监听非 127.0.0.1 地址：此脚本只用于本机测试", file=sys.stderr)
        sys.exit(2)

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    state = {"first_request": None, "count": 0, "last_phase": -1}
    start_time = time.time()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/status", "/", "/health"):
                self.send_response(404)
                self.end_headers()
                return
            if self.path == "/health":
                body = json.dumps({"status": "ok"})
            else:
                if state["first_request"] is None:
                    state["first_request"] = time.time()
                    print(f"[{time.strftime('%H:%M:%S')}] App 首次请求，时间线开始计时")
                state["count"] += 1
                elapsed = time.time() - state["first_request"]
                idx = phase_for(elapsed)
                if idx != state["last_phase"]:
                    state["last_phase"] = idx
                    print(f"[{time.strftime('%H:%M:%S')}] t={int(elapsed)}s 进入阶段 {idx}: {TIMELINE[idx][2]}")
                body = json.dumps(build_status(elapsed, start_time, state["count"]), ensure_ascii=False)
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *a):
            pass

    print("=" * 64)
    print(f"假 Cloud API 已启动: http://{args.host}:{args.port}/status  （仅本机，不访问 Apple / 真实服务器）")
    print(f"SKU {len(SKUS)} 个，门店 {len(STORES)} 家；时间线从 App 第一次请求开始：")
    for start, _, desc in TIMELINE:
        print(f"  t={start:>4}s  {desc}")
    print("在 Test.app 设置里把 Cloud 服务器地址改为上面的地址，保存后完全退出并重新启动 App。")
    print("测试结束后：改回 http://100.122.114.47:8765 → 保存 → 退出并重启 App → 再 Ctrl+C 停掉本脚本。")
    print("=" * 64)
    server = HTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。请确认 App 的 Cloud 地址已改回真实服务器。")


if __name__ == "__main__":
    main()
