#!/bin/bash
# iPhone Duo 库存监控 - 停止脚本
# 用法: ./stop.sh

PLIST_NAME="com.user.iphone-duo-monitor.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "停止 iPhone Duo 库存监控..."

# 通过 LaunchAgent 停止
if [ -f "$PLIST_DST" ]; then
    launchctl stop "$PLIST_NAME" 2>/dev/null || true
fi

# 直接 kill 进程
pkill -f "python3.*monitor.py" 2>/dev/null || true

# 停止 caffeinate
pkill -f "caffeinate -dimsu" 2>/dev/null || true

sleep 1

if pgrep -f "python3.*monitor.py" > /dev/null; then
    echo "警告：进程仍在运行，强制停止..."
    pkill -9 -f "python3.*monitor.py" 2>/dev/null || true
fi

echo "✓ 监控已停止"
