#!/bin/bash
# iPhone Duo 库存监控 - 卸载脚本
# 用法: ./uninstall.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.user.iphone-duo-monitor.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_DST="$LAUNCH_AGENTS_DIR/$PLIST_NAME"

echo "=========================================="
echo "  iPhone Duo 库存监控 - 卸载"
echo "=========================================="
echo ""

# 停止监控
echo "停止监控..."
launchctl unload "$PLIST_DST" 2>/dev/null || true
pkill -f "python3.*monitor.py" 2>/dev/null || true
echo "✓ 监控已停止"

# 删除 LaunchAgent
if [ -f "$PLIST_DST" ]; then
    rm "$PLIST_DST"
    echo "✓ LaunchAgent 已删除"
fi

# 停止 caffeinate
pkill -f "caffeinate -dimsu" 2>/dev/null || true

echo ""
echo "=========================================="
echo "  卸载完成"
echo "=========================================="
echo ""
echo "注意：项目文件、日志和状态数据保留在："
echo "  $SCRIPT_DIR"
echo "如需彻底删除，请手动删除该目录。"
