# HANDOFF - 项目交接文档

## 项目概述
iPhone Duo 中国大陆库存监控工具，Apple Silicon macOS 应用。
监控广东/南京/上海 16 家 Apple Store 到店取货 + 官网配送，有货时通知。

## 当前版本
v1.2.0 (2026-09-11)

## 项目结构
```
iphone-duo-monitor/
├── monitor.py              # 主监控逻辑（错峰+退避+三态）
├── apple_api.py            # Apple API 封装（未改动）
├── state_manager.py        # 状态持久化（未改动）
├── notifier.py             # 通知（未改动）
├── config_loader.py        # 配置加载（未改动）
├── terminal_ui.py          # 终端 UI（未改动）
├── gui_app.py              # PySide6 GUI（8个标签页）
├── checkout_assistant.py   # 结账助手（独立模块，默认关闭，未改动）
├── china_control_monitor.py  # 中国对照组（v1.2.0 新增）
├── australia_monitor.py    # 澳洲对照组（v1.2.0 新增）
├── market_watch.py         # 二级市场行情（v1.2.0 新增）
├── config.json             # 主配置
├── skus.json               # 四个 SKU 配置
├── stores.json             # 16 家门店白名单
├── requirements.txt        # 依赖
├── build_app.sh            # .app 打包脚本
├── install.sh / start.sh / stop.sh / status.sh / uninstall.sh
├── scripts/com.user.iphone-duo-monitor.plist  # LaunchAgent
├── tests/                  # 测试套件（74 + 28 + 9 = 111 项）
├── dist/iPhoneDuoMonitor.app  # 打包好的 macOS 应用
├── CHANGELOG.md
├── HANDOFF.md
├── README.md
├── LICENSE (MIT)
└── ATTRIBUTION.md (上游署名)
```

## 核心模块说明

### monitor.py
- IPhoneDuoMonitor 类，主监控逻辑
- 错峰查询：3 个邮编间隔 5 秒
- 541 退避：30s → 60s → 120s，恢复 200 后重置
- Delivery 独立频率 30 秒
- Pickup 三态：AVAILABLE / UNAVAILABLE / UNKNOWN
- signal 仅在 CLI 主线程注册（GUI 传 register_signals=False）

### gui_app.py
- PySide6 主窗口，5 个标签页：库存看板 / API 统计 / 日志 / 设置 / Checkout Assistant
- QThread 分离监控线程，不阻塞 UI
- 菜单栏常驻，关闭窗口后台运行
- 网络/API 健康面板、最后已知库存、历史统计
- Test Mode、手动测试按钮、诊断报告导出

### checkout_assistant.py
- 独立模块，默认关闭
- 使用 Safari AppleScript 自动化
- 状态机，遇到验证立即暂停
- 永久禁止自动提交订单和付款
- 用户资料本机保存（权限 600），可一键清除

## 四个 SKU（全部经 Apple 官方验证）
- MK2P4CH/A = 512GB 星光白
- MK2Q4CH/A = 512GB 夜空色
- MK2T4CH/A = 1TB 星光白
- MK2U4CH/A = 1TB 夜空色

## 16 家目标门店
广东 5 家：R577 天环广场、R639 珠江新城、R793 前海壹方城、R484 深圳益田假日广场、R761 深圳万象城
南京 3 家：R703 玄武湖、R493 新街口、R643 虹悦城
上海 8 家：R390 香港广场、R401 环贸iapm、R359 南京东路、R389 浦东、R678 静安、R683 环球港、R581 五角场、R705 七宝

## 网络环境注意事项
- 澳大利亚 Superloop 固网：Apple CN pickup API 返回 541
- 澳大利亚 Telstra/Belong 手机热点：低频稳定 200
- 程序已实现 541 → UNKNOWN，绝不误报无货
- API 恢复后自动恢复精确库存监控

## 测试
- 运行：python3 tests/test_monitor.py && python3 tests/test_e2e.py
- 当前：102 tests passed, 0 failed
- 新增功能必须保持 102 项不下降

## 打包 .app
```bash
./build_app.sh
# 或手动：
pyinstaller --name "iPhoneDuoMonitor" --windowed --onefile --clean \
  --add-data "config.json:." --add-data "skus.json:." --add-data "stores.json:." \
  --add-data "LICENSE:." --add-data "ATTRIBUTION.md:." \
  --hidden-import "PySide6.QtWidgets" --hidden-import "PySide6.QtCore" \
  --hidden-import "PySide6.QtGui" --collect-submodules "PySide6" gui_app.py
```

## 新增模块说明（v1.2.0）

### China Control（中国对照组）
- 文件：china_control_monitor.py
- 产品：iPhone 18 Pro 512GB 白色（Glacier）
- Part Number：MJTF4CH/A
- 验证来源：Apple 中国官网购买页 https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro
- 验证日期：2026-09-11
- 门店：广东/南京/上海（与 Duo 相同 16 家）
- 频率：90 秒（可配置 60-120 秒）
- 退避：独立 30→60→120 秒
- 通知：默认关闭

### Australia Control（澳洲对照组）
- 文件：australia_monitor.py
- Duo SKU：MK2F4X/A（iPhone Duo 512GB Star White）
- 18 Pro SKU：MJRX4X/A（iPhone 18 Pro 512GB Glacier）
- 验证来源：Apple 澳洲官网购买页
- 验证日期：2026-09-11
- 门店：Apple Rundle Place，Store ID R405（Adelaide 唯一直营店）
- Endpoint：https://www.apple.com/au/shop/retail/pickup-message
- 频率：60 秒（可配置 60-120 秒）
- 退避：独立 30→60→120 秒
- 批量查询：一次请求带 parts.0 和 parts.1

### Market Watch（二级市场行情）
- 文件：market_watch.py
- 监控 SKU：四个 Duo 型号
- 原价：512GB ¥15999，1TB ¥17999
- 数据源：手动输入（闲鱼/淘宝需登录，标记不可用）
- 频率：60 分钟（默认关闭）
- 数据清洗：排除定金、回收价、租赁、配件、分期、极端价格
- 本地保存：~/Library/Application Support/iPhoneDuoMonitor/market_data.json

## 已知问题
- iPhone USB tethering 在用户环境下 DHCP 持续失败，双网络分流方案暂未实现
- Superloop 下 pickup API 541，需连 Telstra/Belong 热点才能精确查询门店库存
- Checkout Assistant 的 Safari 自动化依赖页面结构，Apple 页面变化可能导致按钮找不到（安全失败，不拖垮 monitor）

## 上游项目
基于 https://github.com/wpddmcmc/ApplestoreMonitor (MIT License) 重构
保留 LICENSE 和 ATTRIBUTION.md

## 下一阶段待办
- 实现双网络分流（Superloop 上网 + iPhone 热点走 Apple 请求）
- Checkout Assistant 更完善的 Safari 自动化
- 更多 GUI 视觉优化
- 菜单栏图标显示库存状态
