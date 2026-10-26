# iPhoneDuoMonitor 项目问题总结与排查记录

> 生成时间：2026-09-13
> 用途：交给 Claude Code 参考，了解项目历史中遇到的所有关键问题及已尝试的解决方案
> 项目目录：`/Users/liujingcheng/Doubao/chats/2026-09-11/new-chat/iphone-duo-monitor/`
> 服务器端目录：`/Users/liujingcheng/Doubao/chats/2026-09-11/new-chat/apple_pickup_linux_test/`

---

## 一、网络与 Pickup API 问题

### 1.1 澳洲本地网络频繁 541

**问题描述**：
用户人在澳大利亚阿德莱德，本地网络（Superloop / Telstra / Belong / QuickFox）访问 Apple 中国 Pickup API 时频繁返回 HTTP 541。

**Apple 中国 Pickup endpoint**：
```
https://www.apple.com.cn/shop/retail/pickup-message?pl=true&mts.0=regular&parts.0=MK2P4CH%2FA&location=200000
```

**已尝试的解决方案**：
- 切换不同澳洲网络运营商（Superloop → Telstra → Belong → QuickFox），均无法稳定解决
- 使用手机热点（Telstra），同样不稳定
- 确认不是单纯的"海外IP被限制"，因为同网络下 Product Locator 和 Apple 官网首页正常 200

**结论**：澳洲本地网络不适合作为长期监控入口，决定迁移到中国大陆云服务器。

---

### 1.2 `force_ipv4()` 全局 patch 导致 541

**问题描述**：
`apple_api.py` 中曾有一个 `force_ipv4()` 函数，全局 patch 了 `requests` 的 DNS 解析，强制使用 IPv4。这导致 Apple Pickup API 持续返回 541。

**根因**：
Apple 中国 CDN 对某些 IPv4 出口节点有差异化处理，强制 IPv4 绕过了正常的 IPv6/双栈路由，落到了被限制的边缘节点。

**解决方案**：
移除 `force_ipv4()` 全局 patch，恢复默认 DNS 解析后 Pickup 恢复正常。

**教训**：不要对网络层做全局 patch，除非完全理解后果。

---

### 1.3 腾讯云上海 IP 被 Apple Pickup 单独风控

**问题描述**：
购买腾讯云上海轻量服务器（公网 IP 49.235.136.61），部署初期 Pickup 正常 200。运行一段时间后（9月12日 12:43 起），Pickup 持续返回 541。

**诊断过程**：
1. 同一服务器上，Product Locator API 返回 200
2. 同一服务器上，Apple 中国官网首页返回 200
3. 只有 Pickup endpoint 返回 541
4. 朋友在天津电信网络测试同一 Pickup URL，返回 200
5. 确认不是 Apple Pickup endpoint 全局故障，而是腾讯云该出口 IP 被 Pickup 应用层单独风控

**关键证据**：
- Pickup = 541
- Product Locator = 200
- Apple 官网 = 200
- 其他大陆网络（天津电信）= Pickup 200

**最终处理**：
用户决定退款（5天无理由期内），腾讯云服务器已释放。

---

### 1.4 Tight Loop 事故：1 分钟 21000 次请求

**问题描述**：
腾讯云部署期间，`headless_monitor.py` 的 while 循环缺少 `sleep`，导致 1 分钟内产生约 21000 次 Pickup 请求。

**后果**：
- 极大概率触发了 Apple 端的风控/限流
- 这是腾讯云 IP 后续被持续 541 的重要诱因之一
- 暴露了缺少硬性速率保护的架构缺陷

**修复措施**：
1. 修复 while 循环，添加 sleep
2. 新增 `rate_limiter.py` 硬性速率限制器：
   - 单区域最小请求间隔：10 秒
   - 全局每分钟最多：12 次请求
   - 通过 monkey-patch `apple_api._request_with_retry` 注入
   - 即使外层 `run_once()` 被错误高频调用，实际 HTTP 请求仍受 limiter 限制
3. 新增 tight-loop 防护测试：连续快速调用 1000 次调度函数，不会产生 1000 次 HTTP 请求

---

### 1.5 阿里云 Pickup 连续 541 与 Session Cookie 根因

**问题描述**：
购买阿里云轻量服务器（公网 IP x.x.x.x，杭州），部署初期 Pickup 有约 70% 的 200 率，随后也出现连续 541。

**根因发现（v2.3.1 关键修复）**：
`requests.Session()` 在收到 Apple 返回的 541 时，Apple 会设置一些风控相关的 cookie（如 `dude`、`dslang` 等）。这些 cookie 被 Session 保留后，后续所有请求都会携带这些"已被标记"的 cookie，导致持续 541，形成恶性循环。

**解决方案**：
在 `apple_api.py` 中新增 `_reset_session_cookies()` 方法：
- 每次收到 541 / 503 / 451 / 403 后，清除 Session 中所有 Apple 设置的 cookie
- 下一次请求使用干净的 Session
- 修复后阿里云 Pickup 三个区域全部恢复 200

**关键代码位置**：`apple_api.py:74` `_reset_session_cookies()`

**教训**：使用 `requests.Session()` 调用有风控的 API 时，必须在收到错误响应后清理 cookie，否则会被"标记"持续拦截。

---

### 1.6 开售期间 503 与数据中心 IP WAF 拦截

**问题描述**：
iPhone 18 系列预购当晚（9月12日 20:00 北京时间），Pickup API 出现大量 503。

**诊断**：
1. 朋友用阿里云杭州数据中心 IP 测试：Pickup 503、Product Locator 503、官网 200
2. 响应体固定 4828 字节，是 Apple/Akamai WAF 拦截特征
3. 朋友用天津电信家庭/机房网络测试：Pickup 200
4. 确认数据中心 IP 段被 Apple WAF 对 /shop/ 类接口做了更严格的拦截

**同时观察到**：
- 开售高峰期 Apple/CDN 本身在调整 Pickup 服务
- 503 不等于永久封禁，可能是临时风控或服务波动
- 阿里云 Pickup 在 503 后一段时间自动恢复 200

**当前状态**：
阿里云 Pickup 已恢复稳定 200，持续运行中。

---

### 1.7 服务器内存不足（OOM）

**问题描述**：
阿里云轻量服务器配置为 2 核 / ~894MB 内存 / 30GB 磁盘。运行 Playwright/Chromium 时频繁 OOM。

**影响**：
- Delivery ETA 的 Chromium 方案无法稳定运行（第2次测试就 OOM 超时）
- 服务器只能运行轻量级 Python requests 监控

**结论**：
不在服务器上运行任何需要浏览器的功能。Delivery ETA 的浏览器方案因此被放弃。

---

## 二、Delivery ETA（官网配送）问题

### 2.1 目标

监控 Apple 中国官网线上邮寄状态和预计送达时间，例如"预计送达 10 月 25 日"、"预计 2–3 周"、"暂不可配送"、"即将发售"等。

### 2.2 目标 API

```
https://www.apple.com.cn/shop/fulfillment-messages
```

已知成功的请求结构（曾通过 Chromium 完整页面流程拿到一次 200）：
```
GET /shop/fulfillment-messages?fae=true&geoLocated=false&state=安徽&city=合肥&district=蜀山区&parts.0=SKU&mts.0=expanded
```

ETA 字段路径：
```
body.content.deliveryMessage[SKU].expanded.deliveryOptions[0].date
```

### 2.3 已尝试的所有方案（全部失败或无法稳定复现）

#### 方案 A：裸 curl
- 各种 User-Agent、参数组合、地区
- 结果：全部 541

#### 方案 B：requests.Session() 模拟匿名购买流程
1. GET Apple 中国对应商品购买页，建立初始匿名 session
2. 使用同一 Session 调用 `/shop/address/location/update`，设置省/市/区
3. 确认响应正常并由 Session 自动保存 Apple 返回的 location/session cookies
4. 仍使用同一 Session 调用 `/shop/fulfillment-messages`
- 结果：仍然 541
- 结论：`requests.Session()` 不能完整复现真实 Chromium 页面上下文（缺少 JS 执行、TLS 指纹、浏览器特定 header 等）

#### 方案 C：Chromium 简化流程（页面内 fetch）
- 在 Chromium 页面上下文中直接 fetch fulfillment API
- 结果：541

#### 方案 D：Chromium 完整 14 步页面流程
严格复现正常用户购买流程：
1. 打开 Apple 中国 iPhone 17 购买页
2. 选择颜色（薰衣草紫色）
3. 选择容量（256GB）
4. 选择"不折抵换购"
5. 选择"不加 AppleCare+"
6. 滚动到底部，确认"添加到购物袋"按钮启用
7. 页面右侧出现"预计发货日期：3-5 个工作日"
8. 点击"查看送货日期"
9. 选择安徽 / 合肥 / 蜀山区
10. 点击"显示选项"
11. 页面显示"标准送货 2026/09/18 – 2026/09/20 免费"
12. 监听页面自身发出的 Network 请求
13. 找到 `/shop/fulfillment-messages`
14. 记录 HTTP 状态和响应内容

- 第 1 次：成功拿到 200 + ETA（2026/09/18 – 2026/09/20）
- 第 2 次：541
- 第 3 次：超时（服务器 OOM）
- 结论：无法稳定复现，且服务器内存不足以支撑 Chromium

#### 方案 E：同 Session 多 SKU 批量查询
- 验证 fulfillment 是否支持 `parts.0=SKU1&parts.1=SKU2&parts.2=SKU3`
- 因方案 D 无法稳定复现，未能完成验证

### 2.4 关键矛盾

同一台服务器、同一个 IP：
- Pickup API：稳定 200
- fulfillment-messages：持续 541

说明 Apple 对这两个 endpoint 有不同的风控策略，fulfillment 对数据中心 IP / 非浏览器客户端更严格。

### 2.5 最终决定

**放弃 Delivery ETA 功能**，原因：
1. 所有技术方案均无法稳定获取 ETA
2. 服务器内存不足以运行 Chromium
3. 用户在澳洲，无法使用国内家庭宽带运行监控
4. 投入产出比过低

**替代方案**：
新增"供货趋势"纯展示模块（`trend_analyzer.py` + `inventory_history.py`），基于现有 Pickup 历史数据统计：
- 当前有货门店数
- 近 1h/6h/24h 补货次数
- 最近补货时间和门店
- 门店/城市/SKU 供货活跃度
- 现货持续时间
- 补货脉冲（最近30分钟集中补货判断）

**Delivery 配置**：服务器端 `config.json` 中 `delivery.enabled=false`，Mac 端原"官网配送"区域已替换为"供货趋势"。

---

## 三、加购购物车显示英文界面问题

### 3.1 问题描述

用户在 Apple 中国官网（apple.com.cn）选择 iPhone 型号、加入购物车时，页面显示英文界面。**经后续分析确认：这不是地区跳转，而是购买页的"非 JS 回退提交"失败后，Apple 渲染了英文的通用错误页。**

关键证据：URL 域名仍然是 `apple.com.cn`，路径仍是中国站购买页，只是多了一串参数。如果真的被重定向到美国/澳洲站，域名会变成 `apple.com`。

### 3.2 用户提供的实际 URL

用户手动选择型号、加入购物车后跳转到：
```
https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/mjtd4ch/a?product=MJTD4CH%2FA&purchaseOption=fullPrice&step=select&acpart=none&atbtoken=495ad3c397b159814ddf589d802172b93e2db9ce&igt=true&add-to-cart=add-to-cart
```

用户描述："加入到购物车的时候，它直接跳转到美国的网站了。我也不知道是美国的网站还是澳洲的网站，反正是英语。"

### 3.3 根因分析（已确认）

**正常流程**：点"加入购物袋"会被页面 JS 拦截，走 XHR 调 `/shop/api/...` 的购物袋接口，然后跳到 `/shop/bag`，用户永远不会看到带 `add-to-cart=add-to-cart` 的 URL。

**实际发生的流程**：
1. JS 路径失败（见下方原因）
2. 浏览器退化成原生表单 GET 提交（页面里有 `method="get"` 的表单，隐藏字段正好是 `product` / `purchaseOption` / `step`，`add-to-cart=add-to-cart` 是提交按钮的 name/value，`atbtoken` 是一次性令牌）
3. 服务端拒绝这次回退提交（令牌无效或请求被拦）
4. 渲染 Apple 的通用错误模板——**那个模板本身就是英文的 "Page Not Found"，哪怕在 cn 域名下也是英文**

**JS 路径失败的原因（按可能性排序）**：
1. **澳洲 IP 在 `/shop/api/...` 上被 Apple WAF 拦（541/403）**——最可能。这和 §1.1 是同一类问题：同一网络下官网首页 200、`/shop/retail/pickup-message` 却 541。购物袋接口同样在 `/shop/` 下，接口一失败，前端就退化成表单提交，再被拦一次就是错误页。这最能解释"时好时坏、换网络表现不同"。
2. **页面 JS 还没绑定完就点了按钮**——抢购时页面刚弹出立刻点，最容易发生。
3. **Safari 扩展 / 内容拦截器 / "阻止跨站跟踪"破坏了 Apple 的脚本或 Cookie**。
4. **页面开太久，atbtoken 过期**。

**已排除的原因**：
- Apple ID 区域（未必登录，且不会换域名）
- `country=CN` / `locale` 参数（本来就在 CN 域，这个流程也没有这种参数）
- `X-Apple-Store-Front`（那是 iTunes/App Store 的头，网页商店不用，浏览器导航也加不了自定义头）

### 3.4 当前 Checkout Assistant 的处理方式

Checkout Assistant 不使用带 `add-to-cart` 参数的 URL，而是使用更简单的商品页格式：
```
https://www.apple.com.cn/shop/product/<part_number>
```

例如：
- iPhone Duo：`https://www.apple.com.cn/shop/product/MK2P4CH/A`
- iPhone 18 Pro Max：`https://www.apple.com.cn/shop/product/MJYC4CH/A`

**注意**：`/shop/product/<SKU>` 打开时容量和颜色已经预选好了，用户只需处理折抵/AppleCare 那几步和加购。Checkout Assistant 只负责打开正确的商品页，不自动提交。

### 3.5 验证方法（只观察，不改任何东西）

Safari → 开发 → 显示网页检查器 → "网络"标签，先打开再点"加入购物袋"，看三样：
1. 有没有发往 `www.apple.com.cn/shop/api/…` 的请求，状态码是多少：541/403/503 → 原因 1
2. 如果根本没有这个请求、页面直接跳到 `?add-to-cart=` 的 URL → 原因 2 或 3
3. 那个 `?add-to-cart=` 文档请求本身的状态码（541 还是 404）

再用无痕窗口、关掉所有扩展重试一次，可以直接排除原因 3。

### 3.6 在现有规则内能做的缓解

- **抢购动作**：等页面完全加载、按钮变为可点后，临点前刷新一次，只开一个购买页标签，不用内容拦截器，点一次就等结果。
- **出错误页后**：立刻手动打开 `https://www.apple.com.cn/shop/bag`，有时商品其实已经加进去了。
- **如果原因 1 被确认**：根本解法只有"让加购请求从 Apple 认为正常的网络发出"（中国大陆住宅网络、托国内的人下单、或者用户自己浏览器的网络选择）。软件层面不做代理/IP 轮换这条不变；用户个人浏览器走什么网络是用户的决定，不是代码问题。
- **也可以试 Apple Store iOS App + 中国大陆区 Apple ID**，是另一套客户端路径。

**这也再次说明：现在不做"自动加入购物袋"是对的——JS 路径失败时，自动点按钮只会撞同一堵墙，还会把失败藏起来。**

---

## 四、其他已解决的问题

### 4.1 Cloud API Token 泄露

- 问题：Cloud API Token 曾完整出现在聊天输出中
- 处理：立即废弃旧 Token，生成新的 256-bit 随机 Token，更新服务器 EnvironmentFile，重启服务
- 后续：所有报告只显示 `Token: configured (****a468)` 或最后4位掩码

### 4.2 公网明文 HTTP + 0.0.0.0/0 开放端口

- 问题：初期 Cloud API 建议 `http://49.235.136.61:8765` 公网直接访问
- 处理：改为 Tailscale 私网架构，Cloud API 只监听 Tailscale IP，腾讯云/阿里云安全组不开放 8765
- 当前：8765 仅通过 Tailscale 私网访问 + Bearer Token 双重保护

### 4.3 UI 多次修改引入的 bug

- 门店库存显示异常（18PM 未显示、型号名称缺失）
- "官网配送"全部显示"云端同步中"
- 连续成功/连续失败计数异常
- 处理：多轮代码审查和修复，当前 v2.5 UI 基本稳定

### 4.4 Diagnostics 页面 bug

- 问题：`'MainWindow' object has no attribute 'worker'`
- 状态：用户说"不用修改"，暂未修复

### 4.5 18 Pro Max UNKNOWN 状态逻辑漏洞

- 问题：Duo-only 轮次失败时，18PM 状态保持不变；但 7-SKU 轮次失败时，18PM 也应该标记为 UNKNOWN
- 修复：7-SKU 轮次失败时，Duo + 18PM 全部 SKU 当前状态设为 UNKNOWN，同时保留各自 last-known
- Duo-only 轮次失败时，只标记 Duo 为 UNKNOWN，18PM 完全不动

---

## 五、当前系统架构

### 5.1 服务器端（阿里云）

- **公网 IP**：x.x.x.x
- **Tailscale IP**：100.122.114.47
- **系统**：Ubuntu 24.04.2 LTS，2核，~894MB 内存
- **部署目录**：`/home/ubuntu/iphone_duo_monitor/`
- **systemd 服务**：`iphone-duo-monitor`（active + enabled）
- **EnvironmentFile**：`/etc/iphone-duo-monitor.env`（权限 600）
- **Cloud API**：仅监听 Tailscale IP:8765，Bearer Token 认证
- **Pickup 频率**：Duo 每区域约 90 秒，18PM 每区域约 180 秒（交替 payload）
- **硬性限速**：区域最小间隔 10 秒，全局每分钟最多 12 次
- **Delivery**：已禁用

### 5.2 Mac 客户端

- **Test.app**：`~/Desktop/iPhoneDuoMonitor-Test.app`（含 Checkout Assistant，当前正在验收）
- **旧 App**：`~/Desktop/iPhoneDuoMonitor.app`（v2.5）
- **Cloud 模式**：默认开启，通过 Tailscale 读取云端状态
- **本地 Monitor**：默认关闭
- **Checkout Assistant**：默认关闭，启用后有货时自动打开购买页

### 5.3 7 个监控 SKU

| Part Number | 产品 | 容量 | 颜色 |
|---|---|---|---|
| MK2P4CH/A | iPhone Duo | 512GB | 星光白色 |
| MK2Q4CH/A | iPhone Duo | 512GB | 夜空色 |
| MK2T4CH/A | iPhone Duo | 1TB | 星光白色 |
| MK2U4CH/A | iPhone Duo | 1TB | 夜空色 |
| MJYC4CH/A | iPhone 18 Pro Max | 512GB | 银色 |
| MJYE4CH/A | iPhone 18 Pro Max | 512GB | 冰川色 |
| MJYD4CH/A | iPhone 18 Pro Max | 512GB | 酒红色 |

### 5.4 16 家目标门店

广东 5 家、南京 3 家、上海 8 家（详见 `stores.json`）

---

## 六、交给 Claude Code 的核心待解决问题

### 优先级 P0：加购购物车显示英文界面（根因已定位，待验证）

**根因已确认**：这不是地区跳转，而是 JS 加购路径失败后退化为原生表单 GET 提交，被服务端拒绝后渲染了英文通用错误页。详见 §3.3。

**最可能的原因**：澳洲 IP 在 `/shop/api/...` 购物袋接口上被 Apple WAF 拦（541/403），导致 JS 路径失败。

**值得做的验证**：
1. 用 Safari 网页检查器确认 `/shop/api/...` 请求的状态码（541/403/503 则确认原因 1）
2. 用无痕窗口 + 关闭所有扩展重试，排除扩展/内容拦截器干扰
3. 确认 `?add-to-cart=` 文档请求本身的状态码

**不值得做的方向（已排除）**：
- ~~URL 中添加 `country=CN` / `locale=zh_CN`~~（本来就在 CN 域，无此参数）
- ~~`/shop/address/location/update` 先设地区~~（那是配送地址流程，和加购无关，且同样是可能被拦的 /shop/ 接口）
- ~~`atbtoken` 生成机制分析~~（只在回退路径有用，真正要的是让 JS 路径成功，且伪造令牌违反规则）
- ~~`X-Apple-Store-Front` header~~（那是 iTunes/App Store 的头，网页商店不用）

**如果确认是原因 1（WAF 拦截）**：
- 软件层面无解（不做代理/IP 轮换）
- 根本解法：让加购请求从 Apple 认为正常的网络发出（中国大陆住宅网络、托国内的人下单、Apple Store iOS App + 中国区 Apple ID）
- Checkout Assistant 保持"只打开购买页，不自动加购"的设计是正确的

### 优先级 P1：Delivery ETA 稳定获取

fulfillment-messages 持续 541，所有方案均失败或无法稳定复现（详见 §2）。如果 P0 验证确认是 WAF 对 `/shop/` 接口的统一拦截，那么 fulfillment 也属于同一类问题，软件层面同样无解。

**可选方向**：
1. 在 Mac 本地运行 Delivery ETA 检查（Mac 内存充足，可运行 Chromium），结果通过 Cloud API 同步——但 Mac 在澳洲，同样可能被 WAF 拦
2. 等待用户有中国大陆住宅网络环境时再验证
3. 接受"供货趋势"作为替代，不再追求 ETA

### 优先级 P2：网络稳定性持续优化

当前阿里云 Pickup 稳定 200，但需要持续关注：
- 开售高峰期是否再次出现 503
- 长期运行是否再次触发风控
- 是否需要进一步降频或增加随机抖动

---

## 七、关键文件索引

| 文件 | 位置 | 说明 |
|---|---|---|
| 核心监控 | `monitor.py` | Pickup 调度、交替 payload、退避逻辑 |
| API 请求层 | `apple_api.py` | Pickup/Delivery 请求、Session 管理、`_reset_session_cookies()` |
| 状态管理 | `state_manager.py` | 三态逻辑、last-known、历史记录 |
| 速率限制 | `rate_limiter.py` | 硬性限速（服务器端） |
| Cloud API | `cloud_api.py` | 只读状态 API（服务器端） |
| Cloud 客户端 | `cloud_client.py` | Mac 端轮询 |
| Checkout | `checkout_assistant.py` | 有货自动打开购买页 |
| 供货趋势 | `trend_analyzer.py` | 纯展示趋势统计 |
| 库存历史 | `inventory_history.py` | 状态变化事件记录 |
| 服务器入口 | `headless_monitor.py` | systemd 启动入口 |
| Mac 入口 | `gui_app.py` | PySide6 GUI |
| 配置 | `config.json` / `skus.json` / `stores.json` | 主配置 |
| 交接说明 | `HANDOFF_CLAUDE.md` | 完整项目交接文档 |

---

*文档结束。如有疑问，参考 `HANDOFF_CLAUDE.md` 获取更详细的代码级交接信息。*
