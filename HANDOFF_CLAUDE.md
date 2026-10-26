# iPhoneDuoMonitor - Claude Code 接手交接说明

> 生成时间：2026-09-13（阿德莱德时间）
> 基于当前真实源码和服务器运行状态，非凭记忆编写。

---

## 1. 项目当前版本

- **Mac App 版本号**：`2.1.0`（定义在 `gui_app.py:50` 的 `APP_VERSION`）
- **实际功能版本**：v2.5（新增供货趋势模块后，但 APP_VERSION 常量未更新）
- **技术栈**：Python 3 + PySide6 (GUI) + requests (HTTP) + paramiko (SSH 部署)
- **打包方式**：PyInstaller onefile，产物 `iPhoneDuoMonitor.app`（Apple Silicon arm64）

---

## 2. 目录结构

### 2.1 Mac 客户端项目（主开发目录）
```
/Users/liujingcheng/Doubao/chats/2026-09-11/new-chat/iphone-duo-monitor/
├── gui_app.py              # Mac 客户端入口（2262行，主窗口、Cloud模式、UI、消息栏）
├── monitor.py              # 核心监控调度器（IPhoneDuoMonitor 类）
├── apple_api.py            # Apple API 请求层（Pickup + Delivery + Session管理）
├── state_manager.py        # 状态持久化（UNKNOWN/last-known/历史记录）
├── notifier.py             # 通知模块（macOS通知 + 声音 + Bark + 购买页URL构造）
├── checkout_assistant.py   # Checkout Assistant（已存在，见第8节）
├── cloud_client.py         # Mac 端 Cloud 状态客户端（轮询云端API）
├── inventory_history.py    # 库存历史状态变化记录（v2.5新增）
├── trend_analyzer.py       # 供货趋势统计分析（v2.5新增）
├── china_control_monitor.py    # 中国对照组 SKU 监控
├── australia_control_monitor.py # 澳洲对照组 SKU 监控
├── product_locator_monitor.py  # Product Locator 辅助诊断
├── market_watch.py         # 市场观察
├── pickup_diagnostics.py   # Pickup 诊断模块（Sentinel A/B，当前未在headless启用）
├── playwright_delivery.py  # Playwright Delivery 备选（已禁用）
├── config.json             # 主配置文件
├── skus.json               # 7个 SKU 配置
├── stores.json             # 16家门店配置
├── config_loader.py        # 配置加载器
├── terminal_ui.py          # 终端 UI（备用）
├── build_app.sh            # PyInstaller 打包脚本
├── iPhoneDuoMonitor.spec   # PyInstaller spec
├── state/                  # 本地状态文件目录
│   └── monitor_state.json
├── tests/                  # 测试套件
│   ├── test_monitor.py
│   ├── test_e2e.py
│   └── test_new_modules.py
└── dist/iPhoneDuoMonitor.app  # 打包产物（已复制到 ~/Desktop/）
```

### 2.2 服务器端项目（Linux headless 部署目录）
```
/Users/liujingcheng/Doubao/chats/2026-09-11/new-chat/apple_pickup_linux_test/
├── headless_monitor.py     # 服务器端入口（systemd 启动此文件）
├── cloud_api.py            # Cloud Status API（HTTP 服务，Bearer Token认证）
├── rate_limiter.py         # 硬性速率限制器（全局+区域）
├── monitor.py              # 从 Mac 项目同步（核心调度）
├── apple_api.py            # 从 Mac 项目同步
├── state_manager.py        # 从 Mac 项目同步
├── notifier.py             # 从 Mac 项目同步
├── inventory_history.py    # 从 Mac 项目同步
├── trend_analyzer.py       # 从 Mac 项目同步
├── config.json             # 服务器端配置（Delivery已禁用）
└── test_*.py               # 测试脚本（可清理）
```

---

## 3. 入口文件

| 端 | 入口文件 | 启动方式 |
|---|---|---|
| **Mac 客户端** | `gui_app.py` | `python3 gui_app.py` 或双击 `.app` |
| **服务器端** | `headless_monitor.py` | systemd 服务 `iphone-duo-monitor` |

---

## 4. 核心模块代码位置

### 4.1 Pickup 请求
- **请求构造与发送**：`apple_api.py:193` `check_pickup_availability()`
- **API URL**：`https://www.apple.com.cn/shop/retail/pickup-message`
- **Session 管理**：`apple_api.py:38` `self.session = requests.Session()`
- **541/503 后 cookie 重置**：`apple_api.py:74` `_reset_session_cookies()`（v2.3.1 关键修复）
- **请求头**：`apple_api.py:45` `_apply_browser_headers()`

### 4.2 Scheduler（调度器）
- **主调度循环**：`monitor.py:420` `run_once()`
- **Pickup 检查核心**：`monitor.py:220` `_check_pickup()`
- **三区错峰**：`monitor.py:220-340`，邮编 `510000`(广东) / `200000`(南京) / `210000`(上海)
- **交替 payload**：`monitor.py:129-132` `pickup_payload_toggle`
  - True = 7个SKU（Duo 4 + 18PM 3）
  - False = 仅 Duo 4个SKU
- **Duo 实际频率**：每区域约 90 秒一次（`pickup_region_interval`）
- **18PM 实际频率**：每区域约 180 秒一次（交替 payload 自然降频）

### 4.3 Rate Limiter（硬性速率限制）
- **实现文件**：服务器端 `rate_limiter.py`
- **全局单例**：`rate_limiter.py:142` `_global_rate_limiter`
- **区域最小间隔**：10 秒
- **全局每分钟上限**：12 次
- **注入方式**：`headless_monitor.py:117` `patch_api_with_rate_limiter()`  monkey-patch `apple_api._request_with_retry`
- **tight-loop 防护**：即使 `run_once()` 被错误高频调用，实际 HTTP 请求仍受 limiter 限制

### 4.4 Backoff（退避）
- **实现位置**：`monitor.py:120` `self.pickup_backoff = {}`
- **退避逻辑**：`monitor.py:315-326`
  - 连续失败 1-2 次：正常间隔 90 秒
  - 连续失败 3 次：600 秒（10分钟）
  - 连续失败更多：1200 秒（20分钟）→ 1800 秒（30分钟）
- **退避重置**：请求成功后 `monitor.py:260` 归零

### 4.5 UNKNOWN / last-known
- **实现位置**：`state_manager.py:75` `update_pickup()`
- **三态**：`available=True`(有货) / `available=False`(无货) / `available=None`(未知)
- **last-known 保留**：`state_manager.py:85-95`，状态更新时保留 `last_available`
- **API 失败标记 UNKNOWN**：`monitor.py:328-340`，本轮实际查询的 SKU 标记 UNKNOWN，未查询的保持不变
- **Duo-only 轮次失败**：只标记 Duo 为 UNKNOWN，18PM 不动
- **7-SKU 轮次失败**：Duo + 18PM 全部标记 UNKNOWN

### 4.6 Control SKU（对照组）
- **中国对照组**：`china_control_monitor.py`，每 1800 秒（30分钟）一次
- **澳洲对照组**：`australia_control_monitor.py`，服务器端已禁用（`enabled=false`）
- **用途**：辅助判断是 Duo 真实无货还是监控链路异常

### 4.7 Cloud API
- **服务器端实现**：`cloud_api.py` `CloudStatusAPI` 类
- **监听地址**：服务器 Tailscale IP `100.122.114.47:8765`（不监听公网）
- **认证方式**：Bearer Token（从 EnvironmentFile 读取）
- **端点**：`GET /status`
- **返回字段**：`service`, `version`, `online`, `server_time`, `monitor`, `pickup`, `delivery`, `inventory`, `rate_limiter`, `skus`, `store_count`, `trends`, `china_control`
- **Mac 端客户端**：`cloud_client.py` `CloudClient` 类，每 10 秒轮询一次

---

## 5. 配置文件

### 5.1 7 个监控 SKU（`skus.json`）

| ID | Part Number | 产品 | 容量 | 颜色 | 分组 |
|---|---|---|---|---|---|
| duo_512_starlight | MK2P4CH/A | iPhone Duo | 512GB | 星光白色 | duo |
| duo_512_midnight | MK2Q4CH/A | iPhone Duo | 512GB | 夜空色 | duo |
| duo_1tb_starlight | MK2T4CH/A | iPhone Duo | 1TB | 星光白色 | duo |
| duo_1tb_midnight | MK2U4CH/A | iPhone Duo | 1TB | 夜空色 | duo |
| iphone18pm_512_silver | MJYC4CH/A | iPhone 18 Pro Max | 512GB | 银色 | iphone18promax |
| iphone18pm_512_glacier | MJYE4CH/A | iPhone 18 Pro Max | 512GB | 冰川色 | iphone18promax |
| iphone18pm_512_burgundy | MJYD4CH/A | iPhone 18 Pro Max | 512GB | 酒红色 | iphone18promax |

### 5.2 16 家目标门店（`stores.json`）

- **广东 5 家**：R577 天环广场(广州)、R639 珠江新城(广州)、R793 前海壹方城(深圳)、R484 深圳益田假日广场(深圳)、R761 深圳万象城(深圳)
- **南京 3 家**：R703 玄武湖、R493 新街口、R643 虹悦城
- **上海 8 家**：R390 香港广场、R401 环贸iapm、R359 南京东路、R389 浦东、R678 静安、R683 环球港、R581 五角场、R705 七宝

### 5.3 主配置（`config.json`）
- Pickup 区域：`510000`, `200000`, `210000`
- Delivery：Mac 端 `enabled=true`，服务器端 `enabled=false`
- China Control：`enabled=true`, `interval_seconds=1800`
- Australia Control：`enabled=false`
- Bark：`enabled=false`（当前关闭）
- Cloud：`enabled=true`, `server_url=http://100.102.13.35:8765`（注意：此为旧腾讯云IP，需更新为阿里云 Tailscale IP）

---

## 6. Cloud 与 Mac 的数据流

```
阿里云服务器 (headless_monitor.py)
  │
  ├─ monitor.py → apple_api.py → Apple Pickup API (每90秒/区域)
  │                                    │
  │                                    ▼
  │                              state_manager.py (三态 + last-known)
  │                                    │
  │                                    ▼
  │                              inventory_history.py (状态变化记录)
  │                                    │
  │                                    ▼
  │                              trend_analyzer.py (供货趋势统计)
  │                                    │
  │                                    ▼
  └─ cloud_api.py → HTTP :8765 (Tailscale私网, Bearer Token)
                       │
                       ▼
Mac App (gui_app.py)
  ├─ cloud_client.py → 每10秒轮询 /status
  │                       │
  │                       ▼
  ├─ _on_cloud_status_update() → 更新顶部状态卡片
  ├─ _detect_cloud_inventory_changes() → 检测库存变化 → 通知/声音/消息栏
  ├─ _update_store_table_from_cloud() → 更新门店库存表
  ├─ _update_trends_from_cloud() → 更新供货趋势显示
  └─ (待实现) checkout_assistant.on_stock_found() → 自动打开购买页
```

---

## 7. 事件/通知链路

### 7.1 Cloud 模式下（当前主用模式）
1. `cloud_client.py` 每 10 秒从云端获取状态
2. `gui_app.py:1293` `_on_cloud_status_update()` 接收状态
3. `gui_app.py:1419` `_detect_cloud_inventory_changes()` 检测 `available` 从非 True → True
4. 触发：
   - `_add_inventory_message()` → 底部消息通知栏
   - `_send_macos_notification()` → macOS 系统通知
   - `_play_alert_sound()` → 提示音
   - `_open_buy_page()` → 自动打开购买页（如果 `auto_open_buy_page=true`）
5. **注意**：Cloud 模式下**没有调用** `checkout_assistant.on_stock_found()`，而是直接调用 `_open_buy_page()`

### 7.2 本地模式下（备用）
1. `monitor.py` 检测到有货 → 返回 alerts 列表
2. `gui_app.py:1973` 调用 `self.checkout.on_stock_found()`
3. Checkout Assistant 根据配置执行：打开购买页 → 加入购物袋 → 填写信息 → 进入结账

### 7.3 Bark 通知
- `notifier.py:133` `send_bark()`
- 当前 `enabled=false`，未启用
- 服务器端 Bark 也未启用

---

## 8. 现有 Checkout Assistant 状态

### 8.1 文件
`checkout_assistant.py`（327行，已存在）

### 8.2 当前实现到哪一步

| 功能 | 实现状态 | 位置 |
|---|---|---|
| 状态机 (IDLE → STOCK_FOUND → OPENING → CART_ADDED → CHECKOUT → PAYMENT) | ✅ 完整 | `CheckoutState` 枚举 |
| 默认关闭 | ✅ | `enabled=false` |
| 有货触发入口 `on_stock_found()` | ✅ | 111行 |
| 打开购买页 (Safari AppleScript) | ✅ | `_open_product_page()` 134行 |
| 回退到默认浏览器 | ✅ | `webbrowser.open()` 154行 |
| 自动加入购物袋 (Safari JS点击) | ⚠️ 实验性 | `_add_to_cart()` 156行 |
| 自动进入结账 | ⚠️ 实验性 | `_start_checkout()` 206行 |
| 登录/验证码检测暂停 | ✅ | `_check_auth_required()` 244行 |
| 自动填写收货信息 | ⚠️ 框架已搭，未实际实现 | `_fill_details()` 277行 |
| 不保存密码/CVV/Cookie | ✅ | 安全边界已实现 |
| 不自动提交订单/付款 | ✅ | 安全边界已实现 |

### 8.3 已知问题
1. **`get_buy_url()` 硬编码 `iphone-duo`**（107-109行）：不支持 iPhone 18 Pro Max。而 `notifier.py:43` 的 `_build_buy_url()` 已正确根据 part_number 前缀判断。
2. **`gui_app.py:1516` `_open_buy_page()` 也硬编码 `iphone-duo`**：Cloud 模式下有货时打开的 URL 对 18PM 是错误的。
3. **Cloud 模式未接入 Checkout Assistant**：直接调用 `_open_buy_page()`，绕过了 Checkout Assistant 的状态机和配置。
4. **Safari AppleScript 方式可能不稳定**：Apple 页面结构变化后 JS 选择器可能失效。

---

## 9. 稳定且禁止随意修改的文件

以下文件当前运行正常，修改风险高，**非必要不动**：

| 文件 | 原因 |
|---|---|
| `monitor.py` | 核心调度，交替payload/退避/错峰逻辑复杂，已多轮验证 |
| `apple_api.py` | Session/cookie 管理是 541 问题的关键修复点，改动易复发 |
| `state_manager.py` | 三态/last-known 逻辑，改错会导致 UNKNOWN 显示为无货 |
| `rate_limiter.py` | 硬性限速，防止 tight-loop 事故的安全底线 |
| `headless_monitor.py` | 服务器入口，改错影响云端 24h 运行 |
| `cloud_api.py` | Cloud 通信层，改错导致 Mac 无法读取状态 |
| `config.json` / `skus.json` / `stores.json` | 配置文件，SKU和门店已验证 |
| `notifier.py` | 通知链路，`_build_buy_url()` 是正确的 URL 构造参考 |

---

## 10. 已废弃或禁用的功能

### 10.1 Delivery ETA / fulfillment-messages（已禁用）
- **API**：`https://www.apple.com.cn/shop/fulfillment-messages`
- **状态**：服务器端 `config.json` 中 `delivery.enabled=false`
- **原因**：阿里云 IP 上 fulfillment API 持续返回 541，requests.Session 和 Chromium 页面流程均无法稳定复现 200
- **残留文件**：`playwright_delivery.py`（未使用）、`apple_api.py` 中的 `check_delivery_availability()`（未被 headless 调用）
- **Mac 端 UI**：原"官网配送"区域已替换为"供货趋势"（v2.5）

### 10.2 Pickup Diagnostics / Sentinel A/B（未启用）
- **文件**：`pickup_diagnostics.py`
- **状态**：代码存在，但 headless_monitor.py 未导入和启用
- **原因**：阿里云 Pickup 稳定 200 后不再需要 Sentinel 对照

### 10.3 腾讯云服务器（已退款释放）
- 原公网 IP `49.235.136.61` 已释放
- `config.json` 中 `cloud.server_url` 仍指向旧 IP `100.102.13.35`（腾讯云 Tailscale IP），**需更新为阿里云 Tailscale IP `100.122.114.47`**

---

## 11. 服务器部署架构

### 11.1 基本信息
- **云厂商**：阿里云轻量应用服务器
- **公网 IP**：`x.x.x.x`
- **Tailscale IP**：`100.122.114.47`（hostname: iphone-duo-monitor-aliyun）
- **系统**：Ubuntu 24.04.2 LTS
- **配置**：2核，~894MB 内存，30GB 磁盘
- **部署目录**：`/home/ubuntu/iphone_duo_monitor/`
- **Python venv**：`/home/ubuntu/iphone_duo_monitor/venv/`

### 11.2 systemd 服务
- **服务名**：`iphone-duo-monitor`
- **状态**：active (running) + enabled (开机自启)
- **EnvironmentFile**：`/etc/iphone-duo-monitor.env`（权限 600，存 Cloud API Token 和 Bark Key）
- **工作目录**：`/home/ubuntu/iphone_duo_monitor/`
- **启动命令**：`venv/bin/python headless_monitor.py`

### 11.3 网络架构
```
Mac (Tailscale IP: 100.96.165.115)
  │ Tailscale 私网
  ▼
阿里云 (Tailscale IP: 100.122.114.47:8765)
  │ Cloud API (Bearer Token)
  ├─ 不监听公网 0.0.0.0:8765
  └─ 安全组不开放 8765
  │
  └─ Apple Pickup API (公网出站)
```

### 11.4 安全组
- SSH (22)：公网开放（密码登录，后续可改为密钥）
- 8765：**不开放公网**，仅 Tailscale 私网访问

### 11.5 日志
- `journalctl -u iphone-duo-monitor -f` 实时查看
- 应用日志：`~/Library/Application Support/iPhoneDuoMonitor/logs/`（Mac 端）
- 服务器端日志：systemd journal

---

## 12. 当前已知正常状态（2026-09-13 验证）

| 项目 | 状态 |
|---|---|
| systemd 服务 | active + enabled |
| Pickup HTTP | 200（三区全部正常，延迟 0.4-0.8s） |
| Cloud API | 正常返回，包含 trends 字段 |
| 8765 监听 | 仅 Tailscale IP，不监听公网 |
| 7 个 SKU | 全部加载 |
| 16 家门店 | 全部加载 |
| 供货趋势模块 | 已部署，历史数据从空开始积累 |
| Delivery | 已禁用 |
| Bark | 已关闭 |
| 累计检查 | 27000+ 次 |
| Mac App | 已重新打包 v2.5，位于 ~/Desktop/ |

---

## 13. 待实现目标

> **Pickup AVAILABLE 后，Mac 本地自动打开正确 SKU 的 Apple 中国商品/购买页，并显示对应有货门店。Apple ID 由用户自己提前登录，最终门店确认和付款由用户手动完成。**

具体要求：
1. Cloud 模式下检测到某 SKU 某门店从非 AVAILABLE → AVAILABLE 时触发
2. 自动打开浏览器，URL 带正确的 partNumber 和 product-family（iphone-duo 或 iphone-18-pro）
3. 在消息通知栏显示有货的具体门店名称
4. 不自动提交订单、不自动付款、不自动输入 Apple ID 密码/验证码/CVV
5. 不做 Cookie 伪造、代理/IP 轮换、TLS 指纹修改或绕过风控
6. Checkout Assistant 必须是独立模块，默认关闭，只在本地 Mac 运行，Cloud 不能自动下单

---

## 14. 实现目标的最小修改文件清单

### 需要修改（2个文件）

| 文件 | 修改内容 |
|---|---|
| `gui_app.py` | 1. 修复 `_open_buy_page()` (1505行)：根据 SKU group 判断 product-family（iphone-duo / iphone-18-pro），不再硬编码<br>2. 在 `_detect_cloud_inventory_changes()` (1419行) 中，有货时调用 `self.checkout.on_stock_found()` 替代直接调用 `_open_buy_page()`，或在 `_open_buy_page` 中修复 URL 后保留直接调用<br>3. 确保打开页面时在消息栏显示具体门店名称（已有此功能） |
| `checkout_assistant.py` | 1. 修复 `get_buy_url()` (107行)：根据 part_number 前缀或 SKU group 判断 product-family，参考 `notifier.py:43` 的 `_build_buy_url()` 实现<br>2. 可选：增加"仅打开购买页，不执行后续自动化"的轻量模式（当前 `auto_open_page=true, auto_add_to_cart=false` 已可实现） |

### 绝对不需要修改的文件

- `monitor.py` — 调度逻辑不动
- `apple_api.py` — Pickup 请求不动
- `state_manager.py` — 状态逻辑不动
- `cloud_api.py` — Cloud API 不动
- `cloud_client.py` — 客户端不动
- `rate_limiter.py` — 限速不动
- `headless_monitor.py` — 服务器入口不动
- `notifier.py` — 通知不动（其 `_build_buy_url()` 是正确参考）
- `inventory_history.py` / `trend_analyzer.py` — 趋势不动
- `config.json` / `skus.json` / `stores.json` — 配置不动
- `china_control_monitor.py` / `australia_control_monitor.py` — 对照组不动
- `playwright_delivery.py` — 已禁用，不动

### 部署注意
- 修改 `gui_app.py` 和 `checkout_assistant.py` 后只需**重新打包 Mac App**，不需要部署到服务器
- 服务器端代码完全不需要改动
- Mac App 打包命令：`cd iphone-duo-monitor && bash build_app.sh`，产物复制到 `~/Desktop/`

---

## 15. 关键 URL 参考

### Apple 中国购买页 URL 格式
- iPhone Duo：`https://www.apple.com.cn/shop/buy-iphone/iphone-duo/{PART_NUMBER}`
- iPhone 18 Pro：`https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/{PART_NUMBER}`
- 购物袋：`https://www.apple.com.cn/shop/bag`

### Part Number 前缀判断
- `MK2*` → iPhone Duo（product-family: iphone-duo）
- `MJY*` → iPhone 18 Pro Max（product-family: iphone-18-pro）

### 正确的 URL 构造参考（已验证）
`notifier.py:43-49` `_build_buy_url()`：
```python
def _build_buy_url(self, part_number: str) -> str:
    if part_number.startswith("MJY"):
        product_slug = "iphone-18-pro"
    else:
        product_slug = "iphone-duo"
    return f"https://www.apple.com.cn/shop/buy-iphone/{product_slug}/{part_number}"
```

---

## 16. 测试命令

```bash
# 运行测试套件
cd /Users/liujingcheng/Doubao/chats/2026-09-11/new-chat/iphone-duo-monitor
python3 -m pytest tests/test_monitor.py tests/test_new_modules.py -v

# 语法检查
python3 -c "import py_compile; py_compile.compile('gui_app.py', doraise=True); py_compile.compile('checkout_assistant.py', doraise=True)"

# 重新打包
bash build_app.sh
cp -R dist/iPhoneDuoMonitor.app ~/Desktop/

# 服务器状态检查
ssh root@100.122.114.47 "systemctl is-active iphone-duo-monitor"
ssh root@100.122.114.47 "journalctl -u iphone-duo-monitor --no-pager -n 20 | grep HTTP_REQUEST"
```

---

## 17. 常见坑位提醒

1. **config.json 中 cloud.server_url 是旧腾讯云 IP**：`100.102.13.35`，需确认 Mac App 设置中已更新为阿里云 Tailscale IP `100.122.114.47`
2. **`_open_buy_page()` 硬编码 iphone-duo**：这是当前最直接的 bug，18PM 有货时会打开错误 URL
3. **Cloud 模式绕过了 Checkout Assistant**：直接调用 `_open_buy_page()`，如果要使用 Checkout Assistant 的完整功能需要接入
4. **服务器内存仅 894MB**：不要在服务器端跑 Playwright/Chromium，会 OOM
5. **541 后必须重置 session cookie**：`apple_api.py:_reset_session_cookies()` 是关键修复，不要移除
6. **UNKNOWN ≠ 无货**：任何修改都不能把 UNKNOWN 显示或解释为无货
7. **趋势模块历史数据从现在开始积累**：刚部署时补货次数全 0 是正常的

---

*文档结束。接手后请先阅读 `gui_app.py` 的 `_detect_cloud_inventory_changes()` 和 `_open_buy_page()`，以及 `checkout_assistant.py` 的 `get_buy_url()`，这三处是实现目标的核心切入点。*
