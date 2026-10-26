#!/bin/bash
# iPhone Duo 库存监控 - 状态查看
# 用法: ./status.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "  iPhone Duo 库存监控 - 状态"
echo "=========================================="
echo ""

# 进程状态
if pgrep -f "python3.*monitor.py" > /dev/null; then
    PID=$(pgrep -f "python3.*monitor.py")
    echo "运行状态: ✓ 运行中 (PID: $PID)"
else
    echo "运行状态: ✗ 未运行"
fi

# LaunchAgent 状态
PLIST_DST="$HOME/Library/LaunchAgents/com.user.iphone-duo-monitor.plist"
if [ -f "$PLIST_DST" ]; then
    echo "开机自启: ✓ 已配置"
else
    echo "开机自启: ✗ 未配置"
fi

# caffeinate 状态
if pgrep -f "caffeinate -dimsu" > /dev/null; then
    echo "防睡眠: ✓ 已启用"
else
    echo "防睡眠: ✗ 未启用"
fi

echo ""

# 最近日志
LOG_FILE="$SCRIPT_DIR/logs/monitor.log"
if [ -f "$LOG_FILE" ]; then
    echo "最近日志（最后 10 行）："
    echo "------------------------------------------"
    tail -10 "$LOG_FILE"
    echo "------------------------------------------"
fi

# 状态文件
STATE_FILE="$SCRIPT_DIR/state/monitor_state.json"
if [ -f "$STATE_FILE" ]; then
    echo ""
    echo "状态统计："
    python3 -c "
import json
with open('$STATE_FILE') as f:
    s = json.load(f)
pickup_avail = sum(1 for v in s.get('pickup',{}).values() if v.get('available'))
delivery_avail = sum(1 for v in s.get('delivery',{}).values() if v.get('available'))
print(f'  到店取货有货: {pickup_avail} 项')
print(f'  官网配送有货: {delivery_avail} 项')
print(f'  检查次数: {s.get(\"meta\",{}).get(\"check_count\",0)}')
meta = s.get('meta',{})
if meta.get('last_check'):
    import time
    print(f'  最近检查: {time.strftime(\"%Y-%m-%d %H:%M:%S\", time.localtime(meta[\"last_check\"]))}')
" 2>/dev/null || true
fi
