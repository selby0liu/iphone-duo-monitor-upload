#!/bin/bash
#
# 构建 Safari Web Extension App（不需要 Xcode，只需要 Command Line Tools）
#
# Apple 官方的 safari-web-extension-converter 随 Xcode.app 发行；这台 Mac 只装了
# Command Line Tools，所以这里直接用同一套官方工具链（clang + macOS SDK + codesign）
# 按 Safari Web Extension 的标准 bundle 结构手工组装，产物结构与 Xcode 模板一致。
#
# 关键点：appex 里的 Resources 是从 ../apple_store_selector/ 复制过来的，
# 复制完会做 sha256 比对，保证 Safari 版和 Chrome 版跑的是逐字节相同的同一份逻辑。

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/src"
CANON="$HERE/../apple_store_selector"
BUILD="$HERE/build"

APP_NAME="DuoMonitorStoreSelector"
EXT_NAME="DuoMonitorStoreSelectorExtension"
APP="$BUILD/$APP_NAME.app"
APPEX="$APP/Contents/PlugIns/$EXT_NAME.appex"

SDK="$(xcrun --show-sdk-path)"
ARCH="$(uname -m)"
MIN_OS="13.0"

# 只有这三个文件构成 Web Extension；权威副本在 apple_store_selector/
SHARED_FILES=(manifest.json store_selector_core.js content.js)

echo "=========================================="
echo "构建 Safari 取货门店助手"
echo "  SDK    : $SDK"
echo "  架构   : $ARCH"
echo "  输出   : $APP"
echo "=========================================="

rm -rf "$BUILD"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
mkdir -p "$APPEX/Contents/MacOS" "$APPEX/Contents/Resources"

# ---------------------------------------------------------------- 容器 App
echo "[1/5] 编译容器 App..."
clang -fobjc-arc -fmodules \
  -isysroot "$SDK" -arch "$ARCH" -mmacosx-version-min="$MIN_OS" \
  -framework Cocoa -framework SafariServices \
  -o "$APP/Contents/MacOS/$APP_NAME" \
  "$SRC/main.m"
cp "$SRC/App-Info.plist" "$APP/Contents/Info.plist"

# ---------------------------------------------------------------- appex
# -e _NSExtensionMain：app extension 没有 main()，入口由 Foundation 提供
# -fapplication-extension：禁用扩展里不允许调用的 API
echo "[2/5] 编译扩展 appex..."
clang -fobjc-arc -fmodules -fapplication-extension \
  -isysroot "$SDK" -arch "$ARCH" -mmacosx-version-min="$MIN_OS" \
  -framework Foundation \
  -Xlinker -e -Xlinker _NSExtensionMain \
  -o "$APPEX/Contents/MacOS/$EXT_NAME" \
  "$SRC/SafariWebExtensionHandler.m"
cp "$SRC/Extension-Info.plist" "$APPEX/Contents/Info.plist"

# ---------------------------------------------------------------- 共享资源
echo "[3/5] 从权威源复制 Web Extension 资源并校验一致性..."
for f in "${SHARED_FILES[@]}"; do
  cp "$CANON/$f" "$APPEX/Contents/Resources/$f"
  a="$(shasum -a 256 "$CANON/$f" | awk '{print $1}')"
  b="$(shasum -a 256 "$APPEX/Contents/Resources/$f" | awk '{print $1}')"
  if [ "$a" != "$b" ]; then
    echo "复制后 sha256 不一致: $f" >&2
    exit 1
  fi
  echo "      $f  $a"
done

# ---------------------------------------------------------------- 签名
# 这台 Mac 没有 Apple Developer 签名身份，只能 ad-hoc 签名（-s -）。
# Safari 会把 ad-hoc 签名的扩展当作“未签名”，需要在 开发 菜单里打开
# “允许未签名的扩展”。有正式 Developer ID 时把 IDENTITY 换成证书名即可。
IDENTITY="${CODESIGN_IDENTITY:--}"
echo "[4/5] 代码签名（身份: $IDENTITY）..."
codesign --force --timestamp=none \
  --sign "$IDENTITY" --entitlements "$SRC/Extension.entitlements" \
  "$APPEX"
codesign --force --timestamp=none \
  --sign "$IDENTITY" --entitlements "$SRC/App.entitlements" \
  "$APP"

echo "[5/5] 校验签名..."
codesign --verify --deep --strict --verbose=1 "$APP"

echo ""
echo "=========================================="
echo "构建完成: $APP"
echo "=========================================="
