#!/bin/bash
# iPhone Duo 库存监控 - 安装脚本
# 用法: ./install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.user.iphone-duo-monitor.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_SRC="$SCRIPT_DIR/scripts/$PLIST_NAME"
PLIST_DST="$LAUNCH_AGENTS_DIR/$PLIST_NAME"
LOG_DIR="$SCRIPT_DIR/logs"
STATE_DIR="$SCRIPT_DIR/state"

echo "=========================================="
echo "  iPhone Duo 库存监控 - 安装"
echo "=========================================="
echo ""

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo "错误：未找到 python3，请先安装 Python 3"
    exit 1
fi
echo "✓ Python3: $(python3 --version)"

# 安装依赖
echo ""
echo "安装 Python 依赖..."
pip3 install -r "$SCRIPT_DIR/requirements.txt" --quiet
echo "✓ 依赖安装完成"

# 创建目录
mkdir -p "$LOG_DIR" "$STATE_DIR"
echo "✓ 日志/状态目录已创建"

# 复制 LaunchAgent
mkdir -p "$LAUNCH_AGENTS_DIR"
cp "$PLIST_SRC" "$PLIST_DST"

# 替换 plist 中的路径为实际路径
sed -i '' "s|__PROJECT_DIR__|$SCRIPT_DIR|g" "$PLIST_DST"
sed -i '' "s|__USER__|$USER|g" "$PLIST_DST"

echo "✓ LaunchAgent 已安装: $PLIST_DST"

# 加载 LaunchAgent（先卸载旧的）
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo "✓ LaunchAgent 已加载（登录时自动启动）"

echo ""
echo "=========================================="
echo "  安装完成！"
echo "=========================================="
echo ""
echo "常用命令："
echo "  启动:  $SCRIPT_DIR/start.sh"
echo "  停止:  $SCRIPT_DIR/stop.sh"
echo "  状态:  $SCRIPT_DIR/status.sh"
echo "  卸载:  $SCRIPT_DIR/uninstall.sh"
echo "  日志:  tail -f $LOG_DIR/monitor.log"
echo ""
echo "监控将在登录时自动启动。"
echo "如需立即启动，请运行: $SCRIPT_DIR/start.sh"
