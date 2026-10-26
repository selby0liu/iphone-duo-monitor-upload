#!/bin/bash
# iPhone Duo 库存监控 - macOS .app 打包脚本
# 使用 PyInstaller 打包为 Apple Silicon 原生应用

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "iPhone Duo 库存监控 - 打包为 macOS .app"
echo "=========================================="

# 检查 PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "安装 PyInstaller..."
    pip3 install pyinstaller
fi

# 清理旧的构建
rm -rf build dist
rm -f iphone_duo_monitor.spec

echo ""
echo "开始打包..."
echo ""

# 每个发布版本用不同的 bundle identifier，否则 macOS 会把新旧两个 .app 当成同一个 App，
# 导致"退出新版、双击回退到旧版"时只是把已经在跑的那个激活到前台。
APP_BUNDLE_ID="${APP_BUNDLE_ID:-com.duomonitor.iphone.final}"

# bundle 文件名必须保持 ASCII：PyInstaller 的 --name 会同时用作可执行文件名，
# 中文文件名在 codesign 和某些 shell 环节会出问题。
# 用户看到的中文名在打包后用 PlistBuddy 写进 Info.plist，两者互不影响。
BUNDLE_NAME="AppleStockMonitor"
DISPLAY_NAME="苹果库存监控-柳景盛开发"

pyinstaller \
    --name "$BUNDLE_NAME" \
    --windowed \
    --onefile \
    --clean \
    --noconfirm \
    --osx-bundle-identifier "$APP_BUNDLE_ID" \
    --icon "appicon.icns" \
    --add-data "config.json:." \
    --add-data "skus.json:." \
    --add-data "stores.json:." \
    --add-data "LICENSE:." \
    --add-data "ATTRIBUTION.md:." \
    --hidden-import "PySide6.QtWidgets" \
    --hidden-import "PySide6.QtCore" \
    --hidden-import "PySide6.QtGui" \
    --collect-submodules "PySide6" \
    gui_app.py

APP="dist/$BUNDLE_NAME.app"

# 写入中文显示名：Finder、Dock、菜单栏看到的都是这个
if [ -d "$APP" ]; then
    for KEY in CFBundleName CFBundleDisplayName; do
        /usr/libexec/PlistBuddy -c "Set :$KEY $DISPLAY_NAME" "$APP/Contents/Info.plist" 2>/dev/null \
            || /usr/libexec/PlistBuddy -c "Add :$KEY string $DISPLAY_NAME" "$APP/Contents/Info.plist"
    done
    # 改过 Info.plist 后签名会失效，必须重新 ad-hoc 签名
    codesign --force --deep -s - "$APP" >/dev/null 2>&1 || true
fi

echo ""
echo "=========================================="
echo "打包完成！"
echo "应用位置: $APP"
echo "显示名称: $DISPLAY_NAME"
echo "Bundle ID: $APP_BUNDLE_ID"
echo "=========================================="

# 显示应用信息
if [ -d "$APP" ]; then
    echo ""
    echo "应用信息:"
    ls -lh "$APP/Contents/MacOS/"
    echo ""
    echo "架构:"
    file "$APP/Contents/MacOS/$BUNDLE_NAME"
    echo ""
    echo "签名:"
    codesign -dv "$APP" 2>&1 | head -3
fi
