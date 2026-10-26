# 取货门店助手（Safari 版）

和 Chrome/Edge 版是**同一套逻辑**：扩展资源由 `build_safari_extension.sh` 从
`../apple_store_selector/` 复制，复制后做 sha256 校验，`tests/test_store_selector.py`
里还有一条测试盯着这三个文件在两边逐字节一致。改逻辑只改权威源，然后重新构建这里。

## 已经构建好了

```
~/Applications/DuoMonitorStoreSelector.app
```

构建产物同时保留在 `browser_extension/safari/build/DuoMonitorStoreSelector.app`。
macOS 已经把里面的扩展登记为 Safari Web Extension，`pluginkit` 能查到
`com.duomonitor.storeselector.Extension`。

## 在 Safari 里启用（只有这几步，全是鼠标操作）

1. 双击 `~/Applications/DuoMonitorStoreSelector.app`，窗口里也写着同样的步骤。
2. Safari → 设置 → **高级** → 勾选「显示网页开发者功能」。
3. Safari 菜单栏 → **开发** → 勾选「允许未签名的扩展」。
4. Safari → 设置 → **扩展** → 勾选「iPhone Duo Monitor 取货门店助手」。
5. 同一页点「编辑网站」，把 `www.apple.com.cn` 设为**允许**。

### 第 3 步每次重启 Safari 都要重做

这台 Mac 上没有 Apple Developer 签名证书（`security find-identity` 查到 0 个），
所以扩展只能 ad-hoc 签名，Safari 把它当作「未签名扩展」。
「允许未签名的扩展」这个开关在 Safari 退出后会自动关掉。

抢购当天如果重启过 Safari，**先把第 3 步和第 4 步重做一遍再开抢**，
否则扩展是静默不工作的，你只会看到购买页正常打开、门店没有被自动选中。

想彻底免掉这一步，只有两条路：拿到 Apple Developer 证书（付费账号）后
把 `CODESIGN_IDENTITY` 设成证书名重新构建；或者改用 Chrome 版，
Chrome 的未打包扩展不会因为重启而失效。

## 权限

扩展资源里的 `manifest.json` 和 Chrome 版是同一份文件：没有 `permissions`、
没有 `host_permissions`、没有后台脚本，只有一条内容脚本规则

```
matches: ["https://www.apple.com.cn/shop/*"]
```

Safari 因此只会要求 `www.apple.com.cn` 一个站点的访问权。
没有申请 cookies、history、webRequest、downloads、tabs、storage 中的任何一个。

原生部分 `src/SafariWebExtensionHandler.m` 只有一个方法，收到请求就立刻结束，
不发网络请求、不读 Cookie、不读钥匙串、不启动子进程。这一点有静态测试守着。

## 目录

```
src/SafariWebExtensionHandler.m   appex 的原生处理器，什么都不做
src/main.m                        容器 App，显示启用步骤 + 一个跳转按钮
src/App-Info.plist                容器 App 的 Info.plist
src/Extension-Info.plist          appex 的 Info.plist，声明 Safari web-extension 扩展点
src/*.entitlements                App Sandbox
build_safari_extension.sh         构建脚本
build/                            构建产物
```

## 关于 safari-web-extension-converter

Apple 官方的 `safari-web-extension-converter` 随 Xcode.app 发行，这台 Mac 只装了
Command Line Tools，所以那个命令不存在。构建脚本用的是同一套官方工具链
（`clang` + macOS SDK + `codesign`），按 Safari Web Extension 的标准 bundle 结构组装，
产物结构和 Xcode 模板一致：容器 App 里放一个 `.appex`，appex 的 Info.plist 声明
`NSExtensionPointIdentifier = com.apple.Safari.web-extension`，Resources 里放 Web Extension 文件。

以后如果装了 Xcode，直接对 `../apple_store_selector/` 跑一次 converter 也能得到等价工程，
逻辑来源仍然是同一个目录。

## 重新构建

改完 `../apple_store_selector/store_selector_core.js` 之后：

```
bash browser_extension/safari/build_safari_extension.sh
cp -R browser_extension/safari/build/DuoMonitorStoreSelector.app ~/Applications/
```

然后在 Safari 的扩展设置里关掉再打开一次，让它重新加载。
