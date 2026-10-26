# CHANGELOG

## v1.3.0 (2026-09-12)

### 新增

1. **Product Locator 辅助诊断模块**：新增 `product_locator_monitor.py`，使用 Apple 官方 `product-locator-meta?family=iphoneduo` 接口判断 SKU 是否存在、商品状态、官方价格。仅用于诊断，**不替代** pickup-message 的门店级库存。
2. **GUI Product Locator Health**：顶部状态栏新增 Product Locator 状态显示（HTTP、SKU 数量）。
3. **诊断结论**：根据 Pickup + Product Locator + Delivery 状态自动显示诊断文案（"Pickup通道异常，商品与官网服务正常"等）。
4. **网络切换自动重置退避**：检测到公网 IP 变化时，自动重置所有模块的退避状态并立即重新 probe。不继承上一个网络出口的连续失败计数。
5. **API 统计按网络会话区分**：新增 `network_session_id`，GUI 同时显示"当前网络成功率"和"全局成功率"。切换 Telstra 后不会还显示 Superloop 的 541 历史。

### 频率优化（核心变更）

6. **中国主 Pickup**：每区域 15秒 → **30秒**，错峰 5秒 → **10秒**。调度：00广东 10上海 20南京 30广东...
7. **Delivery**：30秒 → **60秒**
8. **China Control**：90秒 → **300秒（5分钟）**
9. **Australia Control**：60秒 → **300秒（5分钟）**
10. **Product Locator**：300秒（5分钟）
11. 总体 Apple 请求从 12-15次/分钟 降到 **7-8次/分钟以内**

### 退避优化

12. **541 退避更保守**：30秒 → 60秒 → 120秒 → **300秒（最大5分钟）**
13. HTTP 200 后立即清零退避，恢复正常频率。

### 未修改

- 核心 Monitor 逻辑（apple_api.py / state_manager.py / notifier.py）
- Pickup 三态（AVAILABLE / UNAVAILABLE / UNKNOWN）
- Checkout Assistant
- 门店白名单和 Part Number
- 通知架构
- Market Watch（默认关闭）

### 测试

- Baseline: 117 passed
- Final: **122 passed** (新增 5 个 v1.3.0 测试)
- 0 failed

## v1.2.1 (2026-09-12)

### Bugfix

1. **China Control 541 三态修复**：HTTP 541 时顶部状态从"无货"改为"未知"，门店级状态也标记为未知，与主 Monitor 三态一致。
2. **Market Watch 官方价格修正**：512GB 从 ¥15999 改为 ¥17999，1TB 从 ¥17999 改为 ¥21499。所有溢价计算自动使用正确基准。
3. **版本号统一**：APP_VERSION 从 1.1.0 更新为 1.2.1，窗口标题和诊断报告统一读取。
4. **Delivery 顶部状态修复**：所有 SKU 暂无时顶部显示"暂不可购买"，comingSoon 显示"即将发售"，API失败显示"不可用"，不再永久显示"检测中"。
5. **Pickup 区域轮询间隔修复**：成功后下次查询从 5 秒改为 15 秒（错峰间隔 × 区域数），避免每区域每 5 秒请求。541 退避 30→60→120 秒保持不变。
6. **GUI 频率文案修正**：顶部显示"区域轮询: 15秒 | 错峰: 5秒"，退避时显示当前退避秒数。设置页标签改为"地区错峰间隔"。
7. **ISP 显示**：新增 ISP 查询（ip-api.com），失败显示"未知"，不影响监控。
8. **Bark Key 密码框**：改为密码显示模式，增加"显示/隐藏"按钮。

### 未修改
- 核心 Monitor 逻辑（apple_api.py / state_manager.py / notifier.py）
- Checkout Assistant
- 门店白名单和 Part Number
- 通知架构

### 测试
- Baseline: 114 passed
- Final: 117 passed (新增 3 个 bugfix 测试)

## v1.2.0 (2026-09-11)

### 新增模块

#### China Control（中国大陆对照组）
- 独立模块 `china_control_monitor.py`
- 监控：iPhone 18 Pro 512GB 白色（Glacier）
- Part Number：MJTF4CH/A（经 Apple 中国官网购买页确认）
- 门店范围：广东/南京/上海（与 Duo 相同 16 家）
- 默认频率：90 秒（可配置 60-120 秒）
- 独立退避（30→60→120秒），不影响主 Monitor
- 默认不发高优先级通知
- GUI 独立标签页，显示状态、HTTP、最近检查、门店库存表

#### Australia Control（澳大利亚对照组）
- 独立模块 `australia_monitor.py`
- 只监控 Adelaide Apple Store
- SKU：iPhone Duo 512GB Star White (MK2F4X/A) + iPhone 18 Pro 512GB Glacier (MJRX4X/A)
- 门店：Apple Rundle Place（Store ID R405，Adelaide 唯一直营店）
- Endpoint：https://www.apple.com/au/shop/retail/pickup-message
- 默认频率：60 秒（可配置 60-120 秒）
- 独立退避，批量查询两个 SKU
- 失败不影响中国模块
- GUI 独立标签页

#### Market Watch（二级市场溢价趋势）
- 独立模块 `market_watch.py`
- 监控四个 Duo SKU 的二级市场溢价
- 数据展示：原价、最低/中位/平均报价、溢价金额/百分比、24h/7d变化、历史最高最低
- 本地历史数据保存（含时间戳、SKU、来源、价格、溢价）
- 数据清洗：自动排除定金、回收价、租赁、配件、分期、极端诈骗价、非目标容量/颜色
- 数据源：手动输入（闲鱼/淘宝需登录，标记不可用，不使用反爬绕过）
- 默认频率：60 分钟（可配置 30-60 分钟），默认关闭
- GUI 独立标签页，支持手动添加报价和统计表格

### GUI 扩展
- 从 5 个标签页扩展为 8 个：库存看板 / China Control / Australia Control / Market Watch / API 统计 / 日志 / 设置 / Checkout Assistant
- 新模块状态实时更新
- 新模块失败不影响主 Monitor 和 GUI

### 模块隔离
- 三个新模块完全独立，各自状态、退避、频率
- 新模块崩溃不影响主 Monitor
- Pickup 失败不影响 Delivery，反之亦然
- Checkout Assistant 保持不变

### 未修改的核心模块
- apple_api.py / state_manager.py / notifier.py / checkout_assistant.py
- monitor.py 仅最小调度修改（错峰+退避已在 v1.1.0 完成）

### 测试
- Baseline: 102 passed
- 新增: 9 tests（新模块）
- Final: 111 passed, 0 failed

## v1.1.0 (2026-09-11)

### 新增功能

#### GUI 完善（第一阶段）
- 主界面增加"柳景盛开发"署名（右上角，低调显示）
- 顶部增加网络/API 健康状态面板：
  - 当前网络、公网 IP、ISP
  - Pickup API 状态（正常/不可用/恢复中）
  - Pickup HTTP 状态码（200/541/403/timeout）
  - Delivery 状态
  - 最近成功/错误时间
  - 连续成功/失败次数
  - 成功率统计
  - 累计检查次数
  - 当前轮询间隔
- 门店库存表增加"最后已知状态"列：
  - API 541 时显示"未知"，但保留最后已知有货/无货状态
  - UNKNOWN 绝不触发有货通知
- API 历史统计（内存中最近 500 次请求）：
  - 最近 1 小时/24 小时 HTTP 200/541 比例
  - 平均响应时间
  - 仅记录技术信息，不记录敏感数据
- 设置页增加手动测试按钮：
  - 测试 Pickup API
  - 测试 Delivery
  - 测试 macOS 通知
  - 测试声音
  - 测试 Bark
  - 手动测试不改变真实库存状态机
- Developer / Test Mode：
  - 默认关闭
  - 可模拟 512GB 星光白 @ 上海南京东路 有货
  - 用于测试 GUI、通知、Bark、声音
  - 醒目标注 TEST MODE
  - 模拟结果不写入真实库存数据库
- 日志工具：
  - 打开日志目录
  - 导出诊断报告（含软件版本、macOS 版本、网络、HTTP 统计、SKU/门店配置）
  - 诊断报告不包含 Bark Key、Apple ID、Cookie、Token、地址、电话

#### 轮询策略优化（第二阶段）
- 各地区错峰查询（广东/上海/南京间隔 5 秒），不再瞬间同时打 3 个请求
- HTTP 541 时自动退避：30 秒 → 60 秒 → 120 秒
- API 恢复 200 后自动重置退避，恢复正常轮询
- Delivery 独立频率（默认 30 秒）
- 主循环改为 1 秒粒度睡眠，支持错峰
- 不加入代理、VPN、IP 伪装、UA 轮换、Cookie 伪造

#### macOS App 打包（第三阶段）
- PySide6 GUI 打包为 Apple Silicon 原生 .app
- 双击启动，不需要 Terminal
- 菜单栏常驻
- 关闭窗口最小化到后台继续监控
- 配置/日志/状态保存在 ~/Library/Application Support/iPhoneDuoMonitor/

#### Checkout Assistant（第四阶段，独立模块，默认关闭）
- 新建独立模块 checkout_assistant.py，不修改 monitor 核心
- 状态机：IDLE → STOCK_FOUND → CART_ADDED → CHECKOUT_STARTED → DETAILS_FILLED → WAITING_FOR_AUTH → WAITING_FOR_PAYMENT
- 可配置开关：
  - 自动打开购买页
  - 自动加入购物袋
  - 自动填写收货信息
  - 自动进入结账
- 使用用户已登录的本地 Safari（AppleScript 控制）
- 遇到登录/2FA/CAPTCHA 立即暂停，等待用户处理
- 永久禁止：
  - 自动提交订单
  - 自动付款
  - 保存 Apple ID 密码
  - 保存 2FA/短信验证码
  - 保存 CVV/支付密码
  - 导出 Cookie/session token
- 用户资料仅本机保存，文件权限 600，不写日志，可一键清除
- GUI 增加独立标签页，含开关、状态显示、资料配置、安全声明

### 修改的文件
- gui_app.py（GUI 全面完善）
- monitor.py（错峰+退避+独立 delivery 频率+signal 线程安全）
- 新增 checkout_assistant.py
- 新增 CHANGELOG.md
- 新增 HANDOFF.md
- requirements.txt（增加 PySide6, pyinstaller）
- README.md（更新使用说明）

### 未修改的核心模块
- apple_api.py（Apple API 封装，未改动）
- state_manager.py（状态持久化，未改动）
- notifier.py（通知，未改动）
- config_loader.py（配置加载，未改动）
- terminal_ui.py（终端 UI，未改动）
- skus.json / stores.json / config.json（配置未改动）

### 测试
- Baseline: 102 tests passed (74 + 28)
- Final: 102 tests passed (74 + 28)
- 新增功能未导致任何回归

## v1.0.0 (2026-09-11)

### 初始版本
- 四个 iPhone Duo SKU 监控
- 广东/南京/上海 16 家 Apple Store 到店取货监控
- 官网配送监控
- Pickup 三态（AVAILABLE/UNAVAILABLE/UNKNOWN）
- 541 正确处理，API 自动恢复
- macOS 通知 + 声音 + Bark
- 防重复报警，恢复再报
- 状态持久化
- LaunchAgent 长期运行
- 命令行界面
