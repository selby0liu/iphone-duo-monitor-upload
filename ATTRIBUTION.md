# 上游项目署名 / Upstream Attribution

本项目基于以下开源项目进行修改和扩展：

## 上游项目 / Upstream Project

- **名称**: ApplestoreMonitor
- **作者**: LennonChin (wpddmcmc)
- **仓库**: https://github.com/wpddmcmc/ApplestoreMonitor
- **许可证**: MIT License
- **克隆时间**: 2026-09-11
- **Commit**: main 分支最新提交

### 上游项目贡献 / Upstream Contributions

- Apple Store 到店取货库存 API 调用思路
- Bark 推送通知实现
- 钉钉、Telegram 通知框架
- 多商品配置思路

### 本项目主要改动 / Major Modifications

1. 重构为模块化架构（apple_api / state_manager / notifier / config_loader / terminal_ui）
2. 新增状态持久化（JSON 文件），支持重启后状态恢复、去重、消失后再报
3. 新增 macOS 系统通知（osascript）和本地提示音（afplay）
4. 新增官网配送监控（fulfillment API + pickup-message availability 回退）
5. 新增广东/南京/上海门店白名单，严格过滤异地门店
6. 新增 JSON 配置系统，支持四 SKU 任意组合开关，无需改源码
7. 新增终端实时状态面板
8. 新增 LaunchAgent 开机自启、异常退出重启
9. 新增安装/卸载/启停脚本
10. 新增防系统睡眠（caffeinate）
11. 新增退避重试机制（403/429/5xx/超时）
12. 固定产品为 iPhone Duo，四个 SKU 经 Apple 官方 API 验证
13. 新增完整测试套件

## 参考项目 / Reference Projects

- **iphone_stock_alert** (haggqvist459): https://github.com/haggqvist459/iphone_stock_alert
  - 参考了 pickup-message API 端点和响应解析方式
