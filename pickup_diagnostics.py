#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pickup Diagnostics 诊断模块（v1.5.0）
- 独立 Sentinel A（Python requests）和 Sentinel B（curl）
- DIVERGENCE EVENT 自动捕获
- 网络会话管理
- 晨间摘要生成
- 完全旁路，不影响主库存 Monitor
"""

import os
import sys
import json
import time
import socket
import subprocess
import threading
import logging
import uuid
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List, Optional, Tuple
from logging.handlers import RotatingFileHandler

import requests

logger = logging.getLogger(__name__)

# 日志目录
DATA_DIR = os.path.expanduser("~/Library/Application Support/iPhoneDuoMonitor")
LOG_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def setup_diagnostics_logging():
    """配置诊断模块独立日志"""
    diag_logger = logging.getLogger("pickup_diagnostics")
    diag_logger.setLevel(logging.INFO)

    # 避免重复添加 handler
    if diag_logger.handlers:
        return diag_logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Sentinel 请求日志
    sentinel_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "sentinel_requests.log"),
        maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    sentinel_handler.setFormatter(formatter)
    diag_logger.addHandler(sentinel_handler)

    return diag_logger


diag_logger = setup_diagnostics_logging()


class NetworkSessionManager:
    """网络会话管理器：检测网络变化，创建新 session_id"""

    def __init__(self):
        self.current_session_id = str(uuid.uuid4())[:8]
        self.current_public_ip = None
        self.current_isp = "unknown"
        self.current_interface = "unknown"
        self.session_start_time = time.time()
        self.session_history = []  # [(session_id, ip, start_time, end_time)]
        self._lock = threading.Lock()
        # v1.5.1: 网络信息缓存（30秒）和独立 session
        self._network_info_cache = None
        self._network_info_cache_time = 0
        self._network_info_session = requests.Session()  # 独立客户端，不共享主 Pickup 或 Sentinel Session
        self._network_info_session.headers.update({
            "User-Agent": "iPhoneDuoMonitor-NetworkCheck/1.0"
        })

    def get_network_info(self) -> Dict:
        """获取当前网络信息（公网IP、ISP、接口），v1.5.1 增加30秒缓存"""
        # 检查缓存
        now = time.time()
        if self._network_info_cache and (now - self._network_info_cache_time) < 30:
            return dict(self._network_info_cache)

        info = {
            "public_ip": "unknown",
            "isp": "unknown",
            "interface": "unknown",
            "remote_ip": "unknown",
            "ip_version": "unknown",
        }

        # 获取公网 IP（使用独立 session）
        try:
            resp = self._network_info_session.get("https://api.ipify.org", timeout=5)
            info["public_ip"] = resp.text.strip()
        except Exception:
            pass

        # 获取 ISP（通过 ip-api，不记录敏感信息，使用独立 session）
        if info["public_ip"] != "unknown":
            try:
                resp = self._network_info_session.get(
                    f"http://ip-api.com/json/{info['public_ip']}", timeout=5)
                data = resp.json()
                info["isp"] = data.get("isp", "unknown")
            except Exception:
                pass

        # 获取默认网络接口
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            info["interface"] = s.getsockname()[0]
            s.close()
        except Exception:
            pass

        # v1.5.1: 保存缓存（30秒）
        self._network_info_cache = dict(info)
        self._network_info_cache_time = time.time()

        return info

    def check_network_change(self) -> Optional[Dict]:
        """检测网络是否变化，返回变化信息或 None"""
        with self._lock:
            info = self.get_network_info()
            old_ip = self.current_public_ip

            if info["public_ip"] != old_ip and info["public_ip"] != "unknown":
                # 网络变化
                old_session = self.current_session_id
                self.session_history.append({
                    "session_id": old_session,
                    "public_ip": old_ip,
                    "isp": self.current_isp,
                    "start_time": self.session_start_time,
                    "end_time": time.time(),
                })

                self.current_session_id = str(uuid.uuid4())[:8]
                self.current_public_ip = info["public_ip"]
                self.current_isp = info["isp"]
                self.current_interface = info["interface"]
                self.session_start_time = time.time()

                logger.info("网络切换: %s -> %s, 新 session_id=%s",
                            old_ip, info["public_ip"], self.current_session_id)

                return {
                    "old_session": old_session,
                    "new_session": self.current_session_id,
                    "old_ip": old_ip,
                    "new_ip": info["public_ip"],
                    "new_isp": info["isp"],
                }

            # 更新当前信息
            if info["public_ip"] != "unknown":
                self.current_public_ip = info["public_ip"]
                self.current_isp = info["isp"]
                self.current_interface = info["interface"]

            return None

    def get_current_session(self) -> Dict:
        """获取当前会话信息"""
        with self._lock:
            return {
                "session_id": self.current_session_id,
                "public_ip": self.current_public_ip,
                "isp": self.current_isp,
                "interface": self.current_interface,
                "start_time": self.session_start_time,
            }


class AuditLogger:
    """Pickup 请求审计日志记录器"""

    def __init__(self, log_file: str = "pickup_audit.log"):
        self.log_path = os.path.join(LOG_DIR, log_file)
        self.audit_logger = logging.getLogger("pickup_audit")
        self.audit_logger.setLevel(logging.INFO)

        if not self.audit_logger.handlers:
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler = RotatingFileHandler(
                self.log_path, maxBytes=10 * 1024 * 1024,
                backupCount=5, encoding="utf-8"
            )
            handler.setFormatter(formatter)
            self.audit_logger.addHandler(handler)

    def log_request(self, module: str, endpoint: str, location: str,
                    http_status: str, latency: float,
                    session_mgr: NetworkSessionManager,
                    remote_ip: str = "unknown",
                    ip_version: str = "unknown",
                    http_version: str = "unknown",
                    tls_version: str = "unknown",
                    alpn: str = "unknown",
                    request_id: str = None,
                    extra: Dict = None):
        """记录一次请求审计日志（不记录 Cookie/Token 等敏感信息）"""
        if request_id is None:
            request_id = str(uuid.uuid4())[:8]

        session = session_mgr.get_current_session()

        log_entry = (
            f"PICKUP_AUDIT | request_id={request_id} | module={module} | "
            f"endpoint={endpoint} | location={location} | "
            f"status={http_status} | latency={latency:.2f}s | "
            f"public_ip={session['public_ip']} | isp={session['isp']} | "
            f"interface={session['interface']} | "
            f"network_session_id={session['session_id']} | "
            f"remote_ip={remote_ip} | ip_version={ip_version} | "
            f"http_version={http_version} | tls_version={tls_version} | "
            f"alpn={alpn}"
        )

        if extra:
            for k, v in extra.items():
                log_entry += f" | {k}={v}"

        self.audit_logger.info(log_entry)
        return request_id


class SentinelA:
    """独立 Sentinel A：Python requests，每30秒一次"""

    def __init__(self, session_mgr: NetworkSessionManager, audit_logger: AuditLogger):
        self.session_mgr = session_mgr
        self.audit_logger = audit_logger
        self.running = False
        self.thread = None
        self.interval = 30  # 秒
        self.history = deque(maxlen=500)
        self.stats = {"200": 0, "541": 0, "other": 0, "timeout": 0, "error": 0}
        self.consecutive_541 = 0
        self.consecutive_200 = 0
        self.max_consecutive_541 = 0
        self.max_consecutive_200 = 0
        self._lock = threading.Lock()

        # 独立 session，不共享主 App
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        })

    def _make_request(self) -> Dict:
        """发起一次请求，返回诊断结果"""
        url = "https://www.apple.com.cn/shop/retail/pickup-message"
        params = {
            "pl": "true",
            "location": "200000",
            "parts.0": "MK2P4CH/A",
        }

        start_time = time.time()
        result = {
            "timestamp": datetime.now().isoformat(),
            "module": "sentinel_a",
            "endpoint": "/shop/retail/pickup-message",
            "location": "200000",
            "status": "ERROR",
            "latency": 0,
            "remote_ip": "unknown",
            "ip_version": "unknown",
            "http_version": "unknown",
            "tls_version": "unknown",
            "alpn": "unknown",
        }

        try:
            # 获取 remote IP
            try:
                hostname = "www.apple.com.cn"
                addr_info = socket.getaddrinfo(hostname, 443)
                if addr_info:
                    result["remote_ip"] = addr_info[0][4][0]
                    result["ip_version"] = "IPv4" if addr_info[0][0] == socket.AF_INET else "IPv6"
            except Exception:
                pass

            resp = self.session.get(url, params=params, timeout=10)
            result["latency"] = time.time() - start_time
            result["status"] = str(resp.status_code)

            # 获取 TLS/HTTP 版本（通过 raw response）
            try:
                if hasattr(resp, 'raw') and hasattr(resp.raw, '_connection'):
                    conn = resp.raw._connection
                    if hasattr(conn, 'sock'):
                        sock = conn.sock
                        if hasattr(sock, 'version'):
                            result["tls_version"] = sock.version()
                        if hasattr(sock, 'selected_alpn_protocol'):
                            alpn = sock.selected_alpn_protocol()
                            if alpn:
                                result["alpn"] = alpn
                                result["http_version"] = "HTTP/2" if alpn == "h2" else "HTTP/1.1"
            except Exception:
                pass

        except requests.exceptions.Timeout:
            result["latency"] = time.time() - start_time
            result["status"] = "TIMEOUT"
        except requests.exceptions.RequestException as e:
            result["latency"] = time.time() - start_time
            result["status"] = "NETWORK_ERROR"
            result["error"] = str(e)[:100]

        return result

    def _run_loop(self):
        """主循环"""
        while self.running:
            try:
                result = self._make_request()

                # 记录审计日志
                self.audit_logger.log_request(
                    module="sentinel_a",
                    endpoint=result["endpoint"],
                    location=result["location"],
                    http_status=result["status"],
                    latency=result["latency"],
                    session_mgr=self.session_mgr,
                    remote_ip=result["remote_ip"],
                    ip_version=result["ip_version"],
                    http_version=result["http_version"],
                    tls_version=result["tls_version"],
                    alpn=result["alpn"],
                )

                # 更新统计
                with self._lock:
                    self.history.append(result)
                    status = result["status"]
                    if status == "200":
                        self.stats["200"] += 1
                        self.consecutive_200 += 1
                        self.consecutive_541 = 0
                        self.max_consecutive_200 = max(self.max_consecutive_200, self.consecutive_200)
                    elif status == "541":
                        self.stats["541"] += 1
                        self.consecutive_541 += 1
                        self.consecutive_200 = 0
                        self.max_consecutive_541 = max(self.max_consecutive_541, self.consecutive_541)
                    elif status == "TIMEOUT":
                        self.stats["timeout"] += 1
                    else:
                        self.stats["other"] += 1

                diag_logger.info("Sentinel A: status=%s latency=%.2fs", result["status"], result["latency"])

            except Exception as e:
                logger.error("Sentinel A 异常: %s", e)

            # 等待下一次
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)

    def start(self):
        """启动 Sentinel A"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Sentinel A 已启动（每30秒）")

    def stop(self):
        """停止 Sentinel A"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Sentinel A 已停止")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            total = sum(self.stats.values())
            success_rate = (self.stats["200"] / total * 100) if total > 0 else 0
            return {
                "stats": dict(self.stats),
                "total": total,
                "success_rate": round(success_rate, 1),
                "consecutive_541": self.consecutive_541,
                "consecutive_200": self.consecutive_200,
                "max_consecutive_541": self.max_consecutive_541,
                "max_consecutive_200": self.max_consecutive_200,
                "last_result": self.history[-1] if self.history else None,
            }


class SentinelB:
    """独立 Sentinel B：curl，每30秒，与 Sentinel A 错开15秒"""

    def __init__(self, session_mgr: NetworkSessionManager, audit_logger: AuditLogger):
        self.session_mgr = session_mgr
        self.audit_logger = audit_logger
        self.running = False
        self.thread = None
        self.interval = 30  # 秒
        self.initial_delay = 15  # 与 Sentinel A 错开15秒
        self.history = deque(maxlen=500)
        self.stats = {"200": 0, "541": 0, "other": 0, "timeout": 0, "error": 0}
        self.consecutive_541 = 0
        self.consecutive_200 = 0
        self.max_consecutive_541 = 0
        self.max_consecutive_200 = 0
        self._lock = threading.Lock()

    def _make_request(self) -> Dict:
        """使用 curl 发起请求"""
        url = "https://www.apple.com.cn/shop/retail/pickup-message?pl=true&parts.0=MK2P4CH%2FA&location=200000"

        start_time = time.time()
        result = {
            "timestamp": datetime.now().isoformat(),
            "module": "sentinel_b",
            "endpoint": "/shop/retail/pickup-message",
            "location": "200000",
            "status": "ERROR",
            "latency": 0,
            "remote_ip": "unknown",
            "ip_version": "unknown",
            "http_version": "unknown",
            "tls_version": "unknown",
            "alpn": "unknown",
        }

        try:
            # curl 请求，获取详细信息
            cmd = [
                "curl", "-sS", "-o", "/dev/null",
                "-w", "%{http_code} %{time_total} %{remote_ip} %{http_version} %{ssl_verify_result}",
                "--max-time", "10",
                url
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            result["latency"] = time.time() - start_time

            parts = proc.stdout.strip().split()
            if len(parts) >= 2:
                result["status"] = parts[0]
                try:
                    result["latency"] = float(parts[1])
                except ValueError:
                    pass
            if len(parts) >= 3:
                result["remote_ip"] = parts[2]
            if len(parts) >= 4:
                http_ver = parts[3]
                result["http_version"] = f"HTTP/{http_ver}" if http_ver != "0" else "unknown"

            # 判断 IPv4/IPv6
            if ":" in result["remote_ip"]:
                result["ip_version"] = "IPv6"
            elif result["remote_ip"] != "unknown":
                result["ip_version"] = "IPv4"

        except subprocess.TimeoutExpired:
            result["latency"] = time.time() - start_time
            result["status"] = "TIMEOUT"
        except Exception as e:
            result["latency"] = time.time() - start_time
            result["status"] = "NETWORK_ERROR"
            result["error"] = str(e)[:100]

        return result

    def _run_loop(self):
        """主循环"""
        # 初始延迟15秒，与 Sentinel A 错开
        for _ in range(self.initial_delay):
            if not self.running:
                return
            time.sleep(1)

        while self.running:
            try:
                result = self._make_request()

                # 记录审计日志
                self.audit_logger.log_request(
                    module="sentinel_b",
                    endpoint=result["endpoint"],
                    location=result["location"],
                    http_status=result["status"],
                    latency=result["latency"],
                    session_mgr=self.session_mgr,
                    remote_ip=result["remote_ip"],
                    ip_version=result["ip_version"],
                    http_version=result["http_version"],
                    tls_version=result["tls_version"],
                    alpn=result["alpn"],
                )

                # 更新统计
                with self._lock:
                    self.history.append(result)
                    status = result["status"]
                    if status == "200":
                        self.stats["200"] += 1
                        self.consecutive_200 += 1
                        self.consecutive_541 = 0
                        self.max_consecutive_200 = max(self.max_consecutive_200, self.consecutive_200)
                    elif status == "541":
                        self.stats["541"] += 1
                        self.consecutive_541 += 1
                        self.consecutive_200 = 0
                        self.max_consecutive_541 = max(self.max_consecutive_541, self.consecutive_541)
                    elif status == "TIMEOUT":
                        self.stats["timeout"] += 1
                    else:
                        self.stats["other"] += 1

                diag_logger.info("Sentinel B: status=%s latency=%.2fs", result["status"], result["latency"])

            except Exception as e:
                logger.error("Sentinel B 异常: %s", e)

            # 等待下一次
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)

    def start(self):
        """启动 Sentinel B"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Sentinel B 已启动（每30秒，错开15秒）")

    def stop(self):
        """停止 Sentinel B"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Sentinel B 已停止")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            total = sum(self.stats.values())
            success_rate = (self.stats["200"] / total * 100) if total > 0 else 0
            return {
                "stats": dict(self.stats),
                "total": total,
                "success_rate": round(success_rate, 1),
                "consecutive_541": self.consecutive_541,
                "consecutive_200": self.consecutive_200,
                "max_consecutive_541": self.max_consecutive_541,
                "max_consecutive_200": self.max_consecutive_200,
                "last_result": self.history[-1] if self.history else None,
            }


class DivergenceDetector:
    """分叉事件检测器：App=541 而 Sentinel=200 时标记 DIVERGENCE EVENT"""

    def __init__(self):
        self.divergence_events = deque(maxlen=100)
        self.app_last_status = None
        self.sentinel_a_last_status = None
        self.sentinel_b_last_status = None
        self._lock = threading.Lock()

    def update(self, module: str, status: str, timestamp: float = None):
        """更新状态，检测分叉事件"""
        if timestamp is None:
            timestamp = time.time()

        with self._lock:
            if module == "app_pickup":
                self.app_last_status = status
            elif module == "sentinel_a":
                self.sentinel_a_last_status = status
            elif module == "sentinel_b":
                self.sentinel_b_last_status = status

            # 检测分叉：App=541，Sentinel=200
            if (self.app_last_status == "541" and
                    (self.sentinel_a_last_status == "200" or self.sentinel_b_last_status == "200")):
                event = {
                    "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                    "type": "APP_541_SENTINEL_200",
                    "app_status": self.app_last_status,
                    "sentinel_a_status": self.sentinel_a_last_status,
                    "sentinel_b_status": self.sentinel_b_last_status,
                    "description": "App 返回 541 但 Sentinel 返回 200，可能是 App 请求行为特有问题",
                }
                self.divergence_events.append(event)
                logger.warning("DIVERGENCE EVENT: %s", event["description"])
                diag_logger.warning("DIVERGENCE_EVENT | %s", json.dumps(event, ensure_ascii=False))

            # 反向分叉：App=200，Sentinel=541
            elif (self.app_last_status == "200" and
                  (self.sentinel_a_last_status == "541" or self.sentinel_b_last_status == "541")):
                event = {
                    "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                    "type": "APP_200_SENTINEL_541",
                    "app_status": self.app_last_status,
                    "sentinel_a_status": self.sentinel_a_last_status,
                    "sentinel_b_status": self.sentinel_b_last_status,
                    "description": "App 返回 200 但 Sentinel 返回 541",
                }
                self.divergence_events.append(event)
                diag_logger.warning("DIVERGENCE_EVENT | %s", json.dumps(event, ensure_ascii=False))

    def get_events(self) -> List[Dict]:
        """获取所有分叉事件"""
        with self._lock:
            return list(self.divergence_events)


class MorningSummaryGenerator:
    """晨间摘要生成器"""

    def __init__(self, session_mgr: NetworkSessionManager):
        self.session_mgr = session_mgr

    def generate_summary(self, app_stats: Dict, sentinel_a_stats: Dict,
                         sentinel_b_stats: Dict, divergence_events: List[Dict]) -> str:
        """生成晨间摘要"""
        summary_lines = []
        summary_lines.append("=" * 60)
        summary_lines.append("Pickup Diagnostics 晨间摘要")
        summary_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        summary_lines.append("=" * 60)

        # 当前网络会话
        session = self.session_mgr.get_current_session()
        summary_lines.append(f"\n【当前网络会话】")
        summary_lines.append(f"  Session ID: {session['session_id']}")
        summary_lines.append(f"  公网 IP: {session['public_ip']}")
        summary_lines.append(f"  ISP: {session['isp']}")
        summary_lines.append(f"  会话时长: {int(time.time() - session['start_time'])} 秒")

        # 各模块统计
        summary_lines.append(f"\n【请求统计】")
        for name, stats in [("App Pickup", app_stats),
                            ("Sentinel A (requests)", sentinel_a_stats),
                            ("Sentinel B (curl)", sentinel_b_stats)]:
            if stats and stats.get("total", 0) > 0:
                summary_lines.append(f"\n  {name}:")
                summary_lines.append(f"    总请求: {stats['total']}")
                summary_lines.append(f"    HTTP 200: {stats['stats'].get('200', 0)}")
                summary_lines.append(f"    HTTP 541: {stats['stats'].get('541', 0)}")
                summary_lines.append(f"    成功率: {stats['success_rate']}%")
                summary_lines.append(f"    最长连续 541: {stats['max_consecutive_541']}")
                summary_lines.append(f"    最长连续 200: {stats['max_consecutive_200']}")

        # 分叉事件
        summary_lines.append(f"\n【DIVERGENCE EVENTS】")
        if divergence_events:
            summary_lines.append(f"  共 {len(divergence_events)} 次分叉事件")
            for i, event in enumerate(divergence_events[-10:]):  # 最近10次
                summary_lines.append(f"  {i+1}. [{event['timestamp']}] {event['type']}")
                summary_lines.append(f"     App={event['app_status']}, "
                                     f"SentinelA={event['sentinel_a_status']}, "
                                     f"SentinelB={event['sentinel_b_status']}")
        else:
            summary_lines.append("  无分叉事件")

        # 诊断倾向
        summary_lines.append(f"\n【诊断倾向】")
        app_541 = app_stats.get("stats", {}).get("541", 0) if app_stats else 0
        sa_541 = sentinel_a_stats.get("stats", {}).get("541", 0) if sentinel_a_stats else 0
        sb_541 = sentinel_b_stats.get("stats", {}).get("541", 0) if sentinel_b_stats else 0
        app_200 = app_stats.get("stats", {}).get("200", 0) if app_stats else 0
        sa_200 = sentinel_a_stats.get("stats", {}).get("200", 0) if sentinel_a_stats else 0

        if app_541 > 0 and sa_541 > 0 and sb_541 > 0:
            summary_lines.append("  情况 A: App 和所有 Sentinel 都有 541")
            summary_lines.append("  倾向: 网络 / Apple Pickup endpoint 共同问题")
        elif app_541 > 0 and (sa_200 > 0 or sb_200 > 0):
            summary_lines.append("  情况 B: App 541 但 Sentinel 200")
            summary_lines.append("  倾向: App 请求行为存在特有问题，需要进一步 diff")
        elif app_200 > 0 and (sa_541 > 0 or sb_541 > 0):
            summary_lines.append("  情况 C: App 200 但 Sentinel 541")
            summary_lines.append("  倾向: 检查 HTTP 栈 / TLS / 连接复用 / IPv4-IPv6")
        elif app_200 > 0 and sa_200 > 0 and sb_200 > 0:
            summary_lines.append("  情况 D: 所有都 200")
            summary_lines.append("  记录为正常窗口")
        else:
            summary_lines.append("  数据不足，无法判断")

        summary_lines.append("\n" + "=" * 60)

        summary_text = "\n".join(summary_lines)

        # 写入文件
        summary_path = os.path.join(LOG_DIR, "diagnostics_summary.log")
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(summary_text + "\n\n")
        except Exception as e:
            logger.error("写入摘要失败: %s", e)

        return summary_text


class PickupDiagnostics:
    """Pickup Diagnostics 主类：整合所有诊断组件"""

    def __init__(self):
        self.session_mgr = NetworkSessionManager()
        self.audit_logger = AuditLogger()
        self.sentinel_a = SentinelA(self.session_mgr, self.audit_logger)
        self.sentinel_b = SentinelB(self.session_mgr, self.audit_logger)
        self.divergence_detector = DivergenceDetector()
        self.summary_generator = MorningSummaryGenerator(self.session_mgr)
        self.app_stats = {"stats": {"200": 0, "541": 0, "other": 0, "timeout": 0, "error": 0},
                          "total": 0, "success_rate": 0,
                          "consecutive_541": 0, "consecutive_200": 0,
                          "max_consecutive_541": 0, "max_consecutive_200": 0}
        self._app_stats_lock = threading.Lock()
        self.running = False

    def start(self):
        """启动所有诊断组件"""
        if self.running:
            return
        self.running = True
        self.sentinel_a.start()
        self.sentinel_b.start()
        logger.info("Pickup Diagnostics 已启动")

    def stop(self):
        """停止所有诊断组件"""
        self.running = False
        self.sentinel_a.stop()
        self.sentinel_b.stop()
        logger.info("Pickup Diagnostics 已停止")

    def log_app_pickup_request(self, status: str, latency: float,
                                remote_ip: str = "unknown",
                                ip_version: str = "unknown",
                                http_version: str = "unknown",
                                tls_version: str = "unknown",
                                alpn: str = "unknown"):
        """记录主 App Pickup 请求（供主 Monitor 调用）"""
        request_id = self.audit_logger.log_request(
            module="app_pickup",
            endpoint="/shop/retail/pickup-message",
            location="multi",
            http_status=status,
            latency=latency,
            session_mgr=self.session_mgr,
            remote_ip=remote_ip,
            ip_version=ip_version,
            http_version=http_version,
            tls_version=tls_version,
            alpn=alpn,
        )

        # 更新 App 统计
        with self._app_stats_lock:
            self.app_stats["total"] += 1
            if status == "200":
                self.app_stats["stats"]["200"] += 1
                self.app_stats["consecutive_200"] += 1
                self.app_stats["consecutive_541"] = 0
                self.app_stats["max_consecutive_200"] = max(
                    self.app_stats["max_consecutive_200"],
                    self.app_stats["consecutive_200"])
            elif status == "541":
                self.app_stats["stats"]["541"] += 1
                self.app_stats["consecutive_541"] += 1
                self.app_stats["consecutive_200"] = 0
                self.app_stats["max_consecutive_541"] = max(
                    self.app_stats["max_consecutive_541"],
                    self.app_stats["consecutive_541"])
            elif status == "TIMEOUT":
                self.app_stats["stats"]["timeout"] += 1
            else:
                self.app_stats["stats"]["other"] += 1

            total = self.app_stats["total"]
            self.app_stats["success_rate"] = round(
                self.app_stats["stats"]["200"] / total * 100, 1) if total > 0 else 0

        # 更新分叉检测器
        self.divergence_detector.update("app_pickup", status)

        return request_id

    def check_network_change(self) -> Optional[Dict]:
        """检测网络变化（供主 Monitor 调用）"""
        change = self.session_mgr.check_network_change()
        if change:
            # 网络变化时重置 App 统计的连续计数
            with self._app_stats_lock:
                self.app_stats["consecutive_541"] = 0
                self.app_stats["consecutive_200"] = 0
            diag_logger.info("NETWORK_CHANGE | %s", json.dumps(change, ensure_ascii=False))
        return change

    def get_current_session(self) -> Dict:
        """获取当前网络会话"""
        return self.session_mgr.get_current_session()

    def get_dashboard_data(self) -> Dict:
        """获取 GUI 显示用的数据"""
        return {
            "session": self.get_current_session(),
            "app_stats": self.app_stats,
            "sentinel_a": self.sentinel_a.get_stats(),
            "sentinel_b": self.sentinel_b.get_stats(),
            "divergence_events": self.divergence_detector.get_events()[-5:],
            "running": self.running,
        }

    def generate_morning_summary(self) -> str:
        """生成晨间摘要"""
        return self.summary_generator.generate_summary(
            self.app_stats,
            self.sentinel_a.get_stats(),
            self.sentinel_b.get_stats(),
            self.divergence_detector.get_events(),
        )
