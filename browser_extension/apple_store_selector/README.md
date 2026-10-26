# 取货门店助手（Chrome / Edge 扩展 · 权威源）

这个目录是**唯一一份**门店选择逻辑。Safari 版在 `../safari/`，它的扩展资源由构建脚本
从这里复制，并用 sha256 校验逐字节一致，所以两边不可能出现行为分叉。

- `store_selector_core.js` 共享核心，所有逻辑都在这里
- `content.js` 极薄启动器，只负责调用核心
- `manifest.json` MV3 清单，Chrome/Edge 和 Safari 共用同一份


Mac 端 Checkout Assistant 检测到有货、打开购买页时，会把**这一轮这个 SKU 所有有货门店**
按你设定的优先级写进 URL 的 `#` 片段。这个扩展读到它之后，自动点开“查看供货情况”，
等 Apple 自己把取货门店列表加载出来，选中**当前仍然可取货的最高优先门店**，然后停下。

- URL 片段（fragment）按 HTTP 规范**永远不会发送给 Apple 服务器**，只有本机浏览器读得到。
- 扩展**自己不发任何网络请求**，不调用 Apple 任何库存接口。它点“查看供货情况”之后，
  是**页面自己**去查供货，和你手点那一下完全一样，不会多出第二次。监控服务器的
  Pickup 轮询预算一次都没有增加。
- 扩展**不点“继续”、不加入购物袋、不结账、不下单、不付款**。选中门店就结束。
- 扩展**不读写 Cookie / localStorage / sessionStorage**，不碰 Apple ID、密码、验证码、付款信息。
- 扩展只允许点两类元素：供货情况触发器、取货门店单选框。全文件只有一处 `.click()`，
  且必须先过白名单校验，这一点有静态测试守着。

## 用哪个浏览器

- 打开方式选 **系统默认浏览器**（你的默认是 Chrome）→ 装这个目录的未打包扩展。
- 打开方式选 **Safari** → 装 `../safari/` 里构建出来的扩展 App，见那边的 README。

两边效果一致，因为跑的是同一份 `store_selector_core.js`。

## 安装（全部鼠标操作，不用终端）

1. 打开 Chrome，点右上角 **⋮** → **扩展程序** → **管理扩展程序**。
   （Edge 是 **…** → **扩展** → **管理扩展**。）
2. 打开右上角的 **开发者模式** 开关。
3. 点左上角 **加载已解压的扩展程序**。
4. 在弹出的文件选择窗口里按 **⌘ + ⇧ + G**，粘贴下面这行，回车：

   ```
   ~/Doubao/chats/2026-09-11/new-chat/iphone-duo-monitor/browser_extension/apple_store_selector
   ```

   选中 `apple_store_selector` **这个文件夹本身**（不要进去选里面的文件），点 **选择**。
5. 列表里出现「iPhone Duo Monitor 取货门店助手」，确认右下角开关是**蓝色（已启用）**。

装好后 Chrome 每次启动可能提示“请停用以开发者模式运行的扩展程序”，点 **取消** 即可，
扩展会继续工作。不要点“停用”。

## 在 Mac App 里打开开关

Checkout Assistant 标签页 → 勾选 **自动选中候选取货门店**。
默认是关闭的；关闭时购买页 URL 不带 `#` 片段，扩展完全不动作，行为和以前一模一样。

## 它会做什么、不会做什么

打开购买页后：

1. 立刻用 `history.replaceState` 把自定义片段从地址栏抹掉，不刷新页面。
2. 先安静 1.2 秒。如果页面自己就把取货门店列表渲染出来了，就直接跳到第 4 步，
   连“查看供货情况”都不用点，也就少让页面查一次供货。
3. 列表还没出现就自动点一次“查看供货情况”。只认安全的触发器：
   `<button type="button">`、`<a href="#">`、带 `role="button"` 的元素。
   没写 `type` 的 `<button>` 在表单里默认是提交按钮，点下去可能等于加入购物袋，一律拒绝；
   会跳走的链接、文字里带“继续/加入购物袋/结账/付款”这类词的元素，也一律拒绝。
   弹窗一开就不再点，最多点 3 次。
4. 按候选顺序逐个检查：最高优先的那家如果不存在或不可选，**立刻**看第二家，再第三家。
   选中第一个当前仍可选的门店，用普通 DOM click / change / input 事件。
5. 确认 `checked` 之后**停止一切动作**，右下角显示一个小角标：
   `已选中：深圳万象城 R761，请人工继续`。点角标可关掉。
6. 之后的“继续、加入购物袋、结账、付款”**全部由你本人手动完成**。

失败时显示 `候选门店当前均无法自动选择，请手动操作`，然后彻底停止，不刷新、不重试。
门店列表根本没出现时会多一句“（门店列表未出现）”，那通常意味着弹窗要你先选省市区。

几个可以自己改的数字都在 `content.js` 顶部：`PANEL_TIMEOUT_MS` 是等门店列表的 15 秒上限，
`TRIGGER_INITIAL_DELAY_MS` 是开局安静的 1.2 秒，`AUTO_OPEN_PICKUP_PANEL` 改成 `false`
就只被动等、不主动点。改完回扩展页面点一下刷新图标。

## 权限

`manifest.json` 里**没有** `permissions`、没有 `host_permissions`、没有后台脚本，
只有一条内容脚本规则：

```
matches: ["https://www.apple.com.cn/shop/*"]
```

Chrome 因此只会显示“读取和更改 www.apple.com.cn 上的数据”。
没有申请 cookies、webRequest、history、downloads、tabs、storage 中的任何一个。

## 自测

```
python3 browser_extension/apple_store_selector/test/serve.py
```

然后浏览器打开 <http://127.0.0.1:8799/apple_store_selector/test/run_tests.html>。
21 个场景会跑两遍：一遍用这个目录的权威源，一遍用 Safari 扩展包里的副本，
最后比对两边结果。标题显示 `ALL PASS 42/42 parity 21/21` 即正常。
测试页面是本地假的 Apple 取货面板，不联网、不访问 Apple。
Mac 端对应的测试是 `tests/test_store_selector.py`。
