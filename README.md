# iPhone Duo 中国大陆库存监控工具

> 实时监控 Apple 中国大陆官网 iPhone Duo 的到店取货和官网配送库存，有货时立即通过 macOS 通知 + 提示音 + Bark 推送提醒你。

## 最快开始：直接用 .app（推荐）

1. 解压后找到 `dist/iPhoneDuoMonitor.app`
2. **双击打开**（第一次可能需要右键 → 打开，因为未签名）
3. 应用启动后自动开始监控，菜单栏会显示图标
4. 关闭窗口会最小化到菜单栏，继续后台监控
5. 菜单栏图标 → 退出程序 可完全关闭

**应用数据位置**：`~/Library/Application Support/iPhoneDuoMonitor/`
- `config/`：配置文件（可修改 SKU 开关、轮询间隔等）
- `logs/`：运行日志
- `state/`：库存状态持久化

## 这是什么

一个在 Apple Silicon macOS 上长期后台运行的小工具，每隔 5 秒自动查询 Apple 中国大陆官方库存接口，发现你关注的 iPhone Duo 型号有货时立刻通知你。

**现在有两种使用方式：**
- **GUI 应用**（推荐）：双击 .app，图形界面，菜单栏常驻，类似直播间库存面板
- **命令行**：终端运行，适合服务器或高级用户

**监控范围：**
- **到店取货**：广东省全部（广州 2 家 + 深圳 3 家）、南京全部（3 家）、上海全部（8 家），共 16 家 Apple Store 直营店
- **官网配送**：Apple 中国大陆官网能否下单配送到中国大陆地址

**默认监控四个 SKU（全部可开关）：**

| 容量 | 颜色 | Part Number | 默认启用 |
|------|------|-------------|----------|
| 512GB | 星光白色 | MK2P4CH/A | 是 |
| 512GB | 夜空色 | MK2Q4CH/A | 是 |
| 1TB | 星光白色 | MK2T4CH/A | 是 |
| 1TB | 夜空色 | MK2U4CH/A | 是 |

> 所有 Part Number 均通过 Apple 官方 `product-locator-meta` API 验证（2026-09-11）。
> iPhone Duo 预计 2026 年 10 月 16 日晚 8 点开始预购，10 月 23 日发售。发售前库存接口会显示"暂无供应"，属正常现象。

## 快速开始（零基础）

### 1. 解压项目

把下载的压缩包解压到你想放的位置，比如 `~/Documents/iphone-duo-monitor/`。

### 2. 打开终端

按 `Command + 空格`，输入 `终端`，回车打开。

### 3. 进入项目目录

```bash
cd ~/Documents/iphone-duo-monitor
```

（把路径换成你实际解压的位置）

### 4. 安装

```bash
chmod +x *.sh scripts/*.sh
./install.sh
```

这一步会：
- 安装 Python 依赖（只有 `requests` 一个包）
- 配置开机自启（LaunchAgent）
- 创建日志和状态目录

### 5. 启动

```bash
./start.sh
```

### 6. 查看状态

```bash
./status.sh
```

### 7. 停止

```bash
./stop.sh
```

### 8. 卸载

```bash
./uninstall.sh
```

## GUI 界面说明

打开 .app 后，你会看到三个标签页：

### 库存看板
- **顶部状态栏**：显示当前网络、Pickup API 状态、配送状态、最近刷新时间、轮询间隔、检查次数
- **SKU 开关**：四个 SKU 独立勾选，取消勾选即停止监控该型号（重启后生效）
- **门店库存表**：16 家 Apple Store × 4 个 SKU 的实时库存
  - 🟢 绿色"有货" = 可到店取货
  - ⚪ 灰色"无货" = 暂无库存
  - 🟡 橙色"未知" = API 不可用（541/403/超时），**绝不显示为无货**
- **官网配送**：每个 SKU 独立显示是否可配送及预计送达日期

### 日志
显示最近的请求和状态变化，例如：
```
21:30:05 上海查询成功 HTTP 200
21:30:10 广东查询成功 HTTP 200
21:30:15 南京 HTTP 541 → UNKNOWN
21:31:02 pickup API 恢复
```

### 设置
- **轮询间隔**：3-300 秒可调，实时生效
- **macOS 系统通知**：有货时弹出系统通知
- **播放提示音**：有货时播放 Glass.aiff 提示音
- **自动打开购买页面**：有货时自动在浏览器打开 Apple 官方购买页（不会下单/登录/付款）
- **Bark 推送**：填写你的 Bark Key，有货时推送到 iPhone

### 菜单栏常驻
- 关闭窗口 = 最小化到菜单栏，继续后台监控
- 菜单栏图标 → 显示窗口 / 退出程序
- 有货时菜单栏会弹出系统通知

## 配置说明

### 开关 SKU（不改源码）

编辑 `skus.json`，把想监控的型号 `"enabled": true`，不想监控的改成 `"enabled": false`。

例如只监控 512GB 两个型号：

```json
{
  "skus": [
    {"id": "duo_512_starlight", "part_number": "MK2P4CH/A", "enabled": true, ...},
    {"id": "duo_512_midnight", "part_number": "MK2Q4CH/A", "enabled": true, ...},
    {"id": "duo_1tb_starlight", "part_number": "MK2T4CH/A", "enabled": false, ...},
    {"id": "duo_1tb_midnight", "part_number": "MK2U4CH/A", "enabled": false, ...}
  ]
}
```

改完后重启监控：`./stop.sh && ./start.sh`

### 修改检查间隔

编辑 `config.json`，找到：

```json
"monitor": {
  "interval_seconds": 5
}
```

改成你想要的秒数（不建议低于 3 秒，可能触发限流）。

### 配置 Bark 推送（可选）

Bark 是一个 iOS 推送工具，可以把有货通知推到你的 iPhone 上。

1. 在 App Store 下载「Bark」App
2. 打开 App，复制你的推送地址（类似 `https://api.day.app/xxxxxxxxxx`）
3. 编辑 `config.json`，找到 `notification.bark`：

```json
"bark": {
  "enabled": true,
  "url": "https://api.day.app/你的Key"
}
```

### 自动打开购买页（可选）

有货时自动在浏览器打开对应 SKU 的 Apple 官方购买页（不会下单、不会登录、不会付款）：

```json
"notification": {
  "auto_open_buy_page": true
}
```

### 防系统睡眠

默认启用 `caffeinate` 防止系统睡眠（屏幕可以关闭）。副作用是系统不会自动进入睡眠，可能增加功耗。

关闭方法：编辑 `config.json`，把 `power.prevent_sleep` 改成 `false`。

## 通知内容

有货时通知会包含：
- 产品名称（iPhone Duo + 容量 + 颜色）
- Part Number
- 库存类型（到店取货 / 官网配送）
- 具体门店名称和地址（到店取货时）
- 取货/配送信息（Apple 返回时）
- 当前时间
- Apple 中国大陆官方购买入口链接

## 智能去重

- **只在"无货→有货"时报警**，持续有货不会反复打扰
- 有货消失后再次出现，会重新报警
- 重启后状态自动恢复，不会因为重启而重复报警或漏报
- 网络失败、超时、403/429 时保持上次已知状态，**不会误报**

## 目标门店列表（16 家）

### 广东省（5 家）
| Store ID | 名称 | 城市 |
|----------|------|------|
| R577 | 天环广场 | 广州 |
| R639 | 珠江新城 | 广州 |
| R793 | 前海壹方城 | 深圳 |
| R484 | 深圳益田假日广场 | 深圳 |
| R761 | 深圳万象城 | 深圳 |

### 南京（3 家）
| Store ID | 名称 |
|----------|------|
| R703 | 玄武湖 |
| R493 | 新街口 |
| R643 | 虹悦城 |

### 上海（8 家）
| Store ID | 名称 |
|----------|------|
| R390 | 香港广场 |
| R401 | 上海环贸 iapm |
| R359 | 南京东路 |
| R389 | 浦东 |
| R678 | 静安 |
| R683 | 环球港 |
| R581 | 五角场 |
| R705 | 七宝 |

> 严格排除北京、成都、杭州、重庆、天津、苏州、武汉、西安及其他地区。

## 文件结构

```
iphone-duo-monitor/
├── monitor.py              # 主程序
├── apple_api.py            # Apple API 封装
├── state_manager.py        # 状态持久化
├── notifier.py             # 通知模块
├── config_loader.py        # 配置加载
├── terminal_ui.py          # 终端状态面板
├── config.json             # 主配置
├── skus.json               # SKU 配置（开关在这里）
├── stores.json             # 门店白名单
├── requirements.txt        # Python 依赖
├── install.sh              # 安装
├── uninstall.sh            # 卸载
├── start.sh                # 启动
├── stop.sh                 # 停止
├── status.sh               # 查看状态
├── scripts/
│   └── com.user.iphone-duo-monitor.plist  # 开机自启配置
├── logs/                   # 日志目录
├── state/                  # 状态文件目录
├── tests/
│   ├── test_monitor.py     # 测试套件
│   └── test_output.txt     # 测试输出
├── LICENSE                 # MIT 许可证
├── ATTRIBUTION.md          # 上游项目署名
└── README.md               # 本文件
```

## 常用命令

```bash
# 前台运行（可以看到实时状态面板）
python3 monitor.py run

# 验证 SKU 和门店配置
python3 monitor.py verify

# 测试通知（会发一条测试通知）
python3 monitor.py test-notify

# 查看实时日志
tail -f logs/monitor.log

# 查看状态
./status.sh
```

## 常见问题

**Q: 为什么一直显示"暂无供应"？**
A: iPhone Duo 预计 2026 年 10 月 23 日才发售，发售前官方库存接口会显示"暂无供应"。这是正常的，工具会在有货时第一时间通知你。

**Q: 会被 Apple 封 IP 吗？**
A: 5 秒间隔是合理的查询频率，工具内置了 403/429 退避重试机制。不建议把间隔改到 3 秒以下。

**Q: 通知没声音？**
A: 检查 macOS 系统设置 → 通知 → 脚本编辑器（或终端），确保允许通知和声音。

**Q: 怎么确认监控在正常运行？**
A: 运行 `./status.sh`，或者 `tail -f logs/monitor.log` 看日志。

**Q: 可以监控其他 iPhone 型号吗？**
A: 可以。编辑 `skus.json` 添加新的 SKU，填写正确的 Part Number 即可。Part Number 可以通过 `python3 monitor.py verify-skus` 或 Apple 官网查询。

## 技术细节

- **到店取货 API**：`https://www.apple.com.cn/shop/retail/pickup-message`
- **Part Number 验证 API**：`https://www.apple.com.cn/shop/product-locator-meta?family=iphoneduo`
- **官网配送 API**：`https://www.apple.com.cn/shop/fulfillment-messages?fae=true`（回退到 pickup-message 的 availability 字段）
- **仅依赖**：`requests`（Python HTTP 库）
- **无浏览器自动化**：纯 API 调用，不需要 Chrome/Selenium
- **不绕验证码/风控**：合理频率 + 退避重试

## 免责声明

本工具仅供个人学习和使用，通过 Apple 官方公开接口查询库存信息。不会下单、不会登录、不会付款、不会绕过任何验证机制。请合理使用，遵守 Apple 服务条款。

## 许可证

MIT License。基于 [ApplestoreMonitor](https://github.com/wpddmcmc/ApplestoreMonitor) (LennonChin) 修改扩展，详见 `ATTRIBUTION.md`。
