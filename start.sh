#!/bin/bash
# iPhone Duo 库存监控 - 启动脚本
# 用法: ./start.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.user.iphone-duo-monitor.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "启动 iPhone Duo 库存监控..."

# 检查是否已在运行
if pgrep -f "python3.*monitor.py" > /dev/null; then
    echo "监控已在运行中 (PID: $(pgrep -f 'python3.*monitor.py'))"
    exit 0
fi

# 通过 LaunchAgent 启动
if [ -f "$PLIST_DST" ]; then
    launchctl start "$PLIST_NAME" 2>/dev/null || true
    sleep 1
fi

# 如果 LaunchAgent 启动失败，直接后台启动
if ! pgrep -f "python3.*monitor.py" > /dev/null; then
    cd "$SCRIPT_DIR"
    nohup python3 monitor.py run >> logs/monitor.log 2>&1 &
    echo "已后台启动 (PID: $!)"
else
    echo "已启动 (PID: $(pgrep -f 'python3.*monitor.py'))"
fi

echo ""
echo "查看日志: tail -f $SCRIPT_DIR/logs/monitor.log"
echo "停止监控: $SCRIPT_DIR/stop.sh"
