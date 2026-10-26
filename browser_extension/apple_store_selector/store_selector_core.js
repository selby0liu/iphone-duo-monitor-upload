/*
 * iPhone Duo Monitor - 取货门店助手 · 共享核心 v1.2
 *
 * 这是 Chrome/Edge 版和 Safari 版唯一的一份门店选择逻辑。两边加载的是同一个文件，
 * Safari 扩展包里的副本由构建脚本从这里复制，并有 sha256 测试保证逐字节一致。
 * 本文件只定义 globalThis.DuoMonitorStoreSelector，不自己执行；由各自的 content.js 调 run()。
 *
 * 流程：读 URL 片段里的候选门店 → 自动点一次“查看供货情况” → 等 Apple 自己把取货门店列表
 * 渲染出来 → 选中当前仍然可选的最高优先门店 → 停下，等你人工继续。
 *
 * 永久禁止（本文件不包含、也不允许添加任何这些能力）：
 *   - 不发任何网络请求：没有 fetch / XMLHttpRequest / sendBeacon / WebSocket / EventSource
 *   - 不调用 fulfillment-messages、pickup-message 或任何 Apple 库存接口（只让页面自己去调）
 *   - 不读写 cookie / localStorage / sessionStorage / IndexedDB
 *   - 不读取 Apple ID、密码、验证码、付款信息，不导出任何东西
 *   - 不操作 Apple 的 Redux / React 内部状态（content script 在隔离世界，本来也碰不到页面 JS）
 *   - 不点“继续”、不加入购物袋、不结账、不下单、不付款
 *   - 不刷新页面、不无限重试：一次页面加载只跑一轮，超时就停
 *
 * 只允许点两类元素，且都要过 safeClick 的白名单校验：
 *   1) 取货门店单选框 input[type=radio][name^="store-"]
 *   2) 打开供货情况弹窗的那个触发器（必须是 button[type=button] / 锚点 href="#" / role=button）
 * 其它任何元素一律拒绝点击。
 */
(function (global) {
  "use strict";

  var CORE_VERSION = "1.2.0";

  // ---------------------------------------------------------------- 常量
  var FRAGMENT_KEY = "duomonitor-stores";
  var STORE_RE = /^R[0-9A-Z]{2,7}$/;
  var MAX_CANDIDATES = 8;
  var RADIO_SELECTOR = 'input[type="radio"][name^="store-"]';

  // 改成 false 就只被动等门店列表、不主动点“查看供货情况”
  var AUTO_OPEN_PICKUP_PANEL = true;
  // 开局先安静这么久，留给你自己选 AppleCare 和折抵。这段时间里扩展一个字都不动，
  // 页面完全是 Apple 原样。注意计时从浏览器开始解析页面算起，不是从你看到页面算起。
  // 这期间你如果自己点开了“查看供货情况”，门店列表一出来扩展就立刻替你选，不会等满。
  // 等满了还没有门店列表，扩展才自己去点那个按钮。
  var TRIGGER_INITIAL_DELAY_MS = 8000;
  // 触发器最多点这么多次，且两次之间至少隔 TRIGGER_RETRY_MS；弹窗一旦打开就不再点
  var MAX_TRIGGER_CLICKS = 3;
  var TRIGGER_RETRY_MS = 1500;

  // 等门店列表出现的上限（毫秒）。超过就显示“请手动操作”并彻底停止。
  // 要大于上面的安静期加上弹窗加载时间，否则会没等到门店列表就放弃。
  var PANEL_TIMEOUT_MS = 60000;
  // 门店列表首次出现后，再给它这么久把剩下的门店渲染完，然后才判定“候选都不可选”
  var PANEL_SETTLE_MS = 1500;
  var POLL_MS = 200;

  // 供货情况弹窗的触发器：先按选择器找，找不到再按按钮文字找
  var TRIGGER_SELECTORS = [
    ".rf-pickup-quote-overlay-trigger",
    '[data-autom="pickup-quote-overlay-trigger"]',
    '[data-autom="availabilityButton"]'
  ];
  var TRIGGER_TEXT = ["查看供货情况", "查看门店供货情况", "检查供货情况"];
  var TRIGGER_TEXT_MAX = 40;

  // 红线：文字或 data-autom 命中任意一条的元素，永远不点
  var FORBIDDEN_TEXT = ["继续", "加入购物袋", "加入购物车", "立即购买", "结账", "去结账",
    "付款", "支付", "下单", "提交订单", "Continue", "Add to Bag", "Add to Cart",
    "Check Out", "Checkout", "Buy", "Place Order", "Pay"];
  var FORBIDDEN_AUTOM = ["continuePickUp", "add-to-cart", "addToBag", "checkout",
    "proceed", "buy", "placeOrder"];

  // ---------------------------------------------------------------- fragment
  function parseCandidates(hash) {
    var out = [];
    var raw = String(hash || "");
    if (raw.charAt(0) === "#") { raw = raw.slice(1); }
    if (!raw) { return out; }
    var value = null;
    var pairs = raw.split("&");
    for (var i = 0; i < pairs.length; i++) {
      var eq = pairs[i].indexOf("=");
      if (eq > 0 && pairs[i].slice(0, eq) === FRAGMENT_KEY) {
        value = pairs[i].slice(eq + 1);
        break;
      }
    }
    if (value === null) { return out; }
    var parts = decodeURIComponent(value).split(",");
    for (var j = 0; j < parts.length && out.length < MAX_CANDIDATES; j++) {
      var sn = parts[j].trim().toUpperCase();
      if (STORE_RE.test(sn) && out.indexOf(sn) === -1) { out.push(sn); }
    }
    return out;
  }

  // 立即抹掉自定义 fragment，保留 fragment 里可能存在的其它内容；不刷新页面
  function stripFragment() {
    var raw = String(location.hash || "");
    if (raw.charAt(0) === "#") { raw = raw.slice(1); }
    var kept = [];
    var pairs = raw.split("&");
    for (var i = 0; i < pairs.length; i++) {
      if (!pairs[i]) { continue; }
      var eq = pairs[i].indexOf("=");
      var key = eq > 0 ? pairs[i].slice(0, eq) : pairs[i];
      if (key !== FRAGMENT_KEY) { kept.push(pairs[i]); }
    }
    var url = location.pathname + location.search + (kept.length ? "#" + kept.join("&") : "");
    try {
      history.replaceState(history.state, "", url);
    } catch (e) {
      /* 极端情况下拿不到 history：不影响后面的门店选择，也不做别的补救 */
    }
  }

  // ---------------------------------------------------------------- 通用判定
  function ownText(el) {
    return String((el && el.textContent) || "").replace(/\s+/g, " ").trim();
  }

  function visible(el) {
    if (!el) { return false; }
    var box = el.getBoundingClientRect();
    return box.width > 0 || box.height > 0;
  }

  // 红线校验：任何要点的元素都必须先过这一关
  function isForbidden(el) {
    if (!el) { return true; }
    var autom = String(el.getAttribute && el.getAttribute("data-autom") || "");
    for (var i = 0; i < FORBIDDEN_AUTOM.length; i++) {
      if (autom.toLowerCase().indexOf(FORBIDDEN_AUTOM[i].toLowerCase()) >= 0) { return true; }
    }
    var text = ownText(el);
    if (text.length <= TRIGGER_TEXT_MAX) {
      for (var j = 0; j < FORBIDDEN_TEXT.length; j++) {
        if (text.toLowerCase().indexOf(FORBIDDEN_TEXT[j].toLowerCase()) >= 0) { return true; }
      }
    }
    return false;
  }

  // 祖先里带结账类 data-autom 的元素也不点。只对触发器做这层检查：
  // 门店 radio 由 isStoreRadio 精确锁定，再查祖先只会带来误伤（查不中就整个功能失效）。
  function insideForbiddenAncestor(el) {
    if (!el || !el.closest) { return false; }
    for (var k = 0; k < FORBIDDEN_AUTOM.length; k++) {
      if (el.closest('[data-autom="' + FORBIDDEN_AUTOM[k] + '"]')) { return true; }
    }
    return false;
  }

  // ---------------------------------------------------------------- 门店 radio
  function isStoreRadio(el) {
    return !!el && el.tagName === "INPUT" && el.type === "radio" &&
      typeof el.name === "string" && el.name.indexOf("store-") === 0;
  }

  function labelFor(el) {
    if (el.id) {
      try {
        var l = document.querySelector('label[for="' + (global.CSS && global.CSS.escape ? global.CSS.escape(el.id) : el.id) + '"]');
        if (l) { return l; }
      } catch (e) { /* 选择器异常时退回 closest */ }
    }
    return el.closest ? el.closest("label") : null;
  }

  function selectable(el) {
    if (!isStoreRadio(el)) { return false; }
    if (el.disabled) { return false; }
    if (el.getAttribute("aria-disabled") === "true") { return false; }
    if (el.closest && el.closest('[aria-disabled="true"]')) { return false; }
    // Apple 常把真正的 input 视觉隐藏、由 label 显示，所以 input 或它的 label 可见即算可见
    var l = labelFor(el);
    if (!visible(el) && !visible(l)) { return false; }
    return true;
  }

  function findRadio(store) {
    var nodes = document.querySelectorAll(RADIO_SELECTOR);
    for (var i = 0; i < nodes.length; i++) {
      if (String(nodes[i].value || "").trim().toUpperCase() === store) { return nodes[i]; }
    }
    return null;
  }

  function panelPresent() {
    return document.querySelector(RADIO_SELECTOR) !== null;
  }

  function storeNameOf(el) {
    var container = labelFor(el) || el.parentElement;
    if (!container) { return ""; }
    var text = ownText(container);
    return text.length > 24 ? text.slice(0, 24) + "…" : text;
  }

  // ---------------------------------------------------------------- 供货情况触发器
  /*
   * 只认“安全可点”的触发器：
   *   - <button> 必须显式 type="button"。没写 type 的 button 在表单里默认是 submit，
   *     点下去可能直接提交配置器表单（等于加入购物袋），所以一律拒绝。
   *   - <a> 只允许没有 href、href="#" 或 href 以 "#" 开头的锚点，避免跳走。
   *   - 其它元素必须带 role="button"。
   */
  function isPickupTrigger(el) {
    if (!el || !el.tagName) { return false; }
    if (isForbidden(el) || insideForbiddenAncestor(el)) { return false; }
    if (el.disabled) { return false; }
    if (el.getAttribute("aria-disabled") === "true") { return false; }
    if (!visible(el)) { return false; }

    var tag = el.tagName;
    if (tag === "BUTTON") {
      if (el.type !== "button") { return false; }
    } else if (tag === "A") {
      var href = String(el.getAttribute("href") || "");
      if (href && href.charAt(0) !== "#") { return false; }
    } else if (el.getAttribute("role") !== "button") {
      return false;
    }

    // 身份确认：要么命中已知选择器，要么按钮文字就是“查看供货情况”这一类
    for (var i = 0; i < TRIGGER_SELECTORS.length; i++) {
      try {
        if (el.matches && el.matches(TRIGGER_SELECTORS[i])) { return true; }
      } catch (e) { /* 选择器不被支持时忽略 */ }
    }
    var text = ownText(el);
    if (text.length > TRIGGER_TEXT_MAX) { return false; }
    for (var j = 0; j < TRIGGER_TEXT.length; j++) {
      if (text.indexOf(TRIGGER_TEXT[j]) >= 0) { return true; }
    }
    return false;
  }

  function findPickupTrigger() {
    var i, nodes;
    for (i = 0; i < TRIGGER_SELECTORS.length; i++) {
      try {
        nodes = document.querySelectorAll(TRIGGER_SELECTORS[i]);
      } catch (e) { continue; }
      for (var j = 0; j < nodes.length; j++) {
        if (isPickupTrigger(nodes[j])) { return nodes[j]; }
      }
    }
    nodes = document.querySelectorAll('button, a, [role="button"]');
    var limit = Math.min(nodes.length, 400);
    for (i = 0; i < limit; i++) {
      if (isPickupTrigger(nodes[i])) { return nodes[i]; }
    }
    return null;
  }

  function overlayOpen(trigger) {
    if (document.querySelector('[role="dialog"], [aria-modal="true"]')) { return true; }
    if (trigger && trigger.getAttribute("aria-expanded") === "true") { return true; }
    return false;
  }

  // ---------------------------------------------------------------- 唯一的点击出口
  function safeClick(el, kind) {
    if (kind === "store-radio") {
      if (!isStoreRadio(el)) { return false; }
    } else if (kind === "pickup-trigger") {
      if (!isPickupTrigger(el)) { return false; }
    } else {
      return false;
    }
    if (isForbidden(el)) { return false; }
    try {
      if (el.focus) { el.focus({ preventScroll: true }); }
      el.click();
    } catch (e) {
      return false;
    }
    return true;
  }

  // 普通 DOM 点击；必要时再补 input/change 事件
  function selectRadio(el) {
    if (!safeClick(el, "store-radio")) { return false; }
    if (!el.checked) {
      try {
        el.checked = true;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } catch (e) { return false; }
    }
    return el.checked === true;
  }

  // ---------------------------------------------------------------- 角标
  // ok: true=成功(绿) / false=失败(橙) / null=待命(灰)
  function badge(ok, text) {
    var host = document.createElement("div");
    host.style.cssText = "all:initial;position:fixed;z-index:2147483647;right:16px;bottom:16px;";
    var root = host.attachShadow ? host.attachShadow({ mode: "closed" }) : null;
    var box = document.createElement("div");
    box.setAttribute("role", "status");
    box.textContent = text;
    var style = document.createElement("style");
    style.textContent =
      ":host{all:initial}" +
      "div{font:500 12px/1.45 -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;" +
      "max-width:300px;padding:8px 12px;border-radius:8px;color:#fff;" +
      "box-shadow:0 2px 10px rgba(0,0,0,.28);" +
      "background:" + (ok === null ? "#4a4a4f" : (ok ? "#1d7a46" : "#8a5a00")) + ";}";
    if (root) {
      root.appendChild(style);
      root.appendChild(box);
    } else {
      host.appendChild(box);
    }
    host.addEventListener("click", function () {
      if (host.parentNode) { host.parentNode.removeChild(host); }
    });
    (document.documentElement || document.body).appendChild(host);
    // 返回一个更新/移除的句柄，供静默期倒计时用
    return {
      host: host,
      setText: function (t) { box.textContent = t; },
      remove: function () { if (host.parentNode) { host.parentNode.removeChild(host); } }
    };
  }

  // ---------------------------------------------------------------- 配置
  function num(value, fallback) {
    return typeof value === "number" ? value : fallback;
  }

  /*
   * 测试注入点。content script 运行在隔离世界（Chrome 和 Safari 都是），
   * apple.com.cn 的页面脚本写不进这个对象，所以线上永远取不到 override；
   * 只有本地测试页直接 <script src="store_selector_core.js"> 时才生效。
   */
  function resolveOptions(overrides) {
    var T = overrides || (global.__DUOMONITOR_TEST__) || {};
    return {
      autoOpenPanel: typeof T.autoOpenPanel === "boolean" ? T.autoOpenPanel : AUTO_OPEN_PICKUP_PANEL,
      triggerInitialDelayMs: num(T.triggerInitialDelayMs, TRIGGER_INITIAL_DELAY_MS),
      triggerRetryMs: num(T.triggerRetryMs, TRIGGER_RETRY_MS),
      panelTimeoutMs: num(T.panelTimeoutMs, PANEL_TIMEOUT_MS),
      settleMs: num(T.settleMs, PANEL_SETTLE_MS),
      pollMs: num(T.pollMs, POLL_MS),
      onDone: typeof T.onDone === "function" ? T.onDone : null
    };
  }

  // ---------------------------------------------------------------- 主流程
  var alreadyRan = false;

  function run(overrides) {
    if (alreadyRan) { return false; }
    alreadyRan = true;
    var opts = resolveOptions(overrides);

    var candidates = parseCandidates(location.hash);
    if (candidates.length) { stripFragment(); }

    if (!candidates.length) {
      // Mac 端没开门店助手，或这不是我们打开的页面：
      // 什么都不做，不点任何东西、不插角标、不起定时器
      if (opts.onDone) { opts.onDone({ status: "inactive", core: CORE_VERSION }); }
      return false;
    }

    var started = Date.now();
    var panelSeenAt = 0;
    var finished = false;
    var timer = null;
    var observer = null;
    var trigger = null;
    var triggerClicks = 0;
    var lastTriggerClickAt = 0;

    // 待命角标：静默期里让你一眼看到扩展是活的，还剩几秒接管。
    // 没有它的话，页面打开后好几秒毫无动静，看起来就像扩展没工作。
    var standby = null;
    var standbyTimer = null;

    function clearStandby() {
      if (standbyTimer) { clearInterval(standbyTimer); standbyTimer = null; }
      if (standby) { standby.remove(); standby = null; }
    }

    function standbyText() {
      var left = Math.ceil((opts.triggerInitialDelayMs - (Date.now() - started)) / 1000);
      if (!opts.autoOpenPanel) {
        return "门店助手待命中 · 请自己点开“查看供货情况”，列表出来就替你选";
      }
      if (left > 0) {
        return "门店助手待命中 · " + left + " 秒后自动打开供货情况，你也可以现在自己点";
      }
      return "门店助手工作中 · 正在等取货门店列表";
    }

    function showStandby() {
      standby = badge(null, standbyText());
      standbyTimer = setInterval(function () {
        if (finished || !standby) { return; }
        standby.setText(standbyText());
      }, 500);
    }

    function stop() {
      finished = true;
      if (timer) { clearInterval(timer); timer = null; }
      if (observer) { observer.disconnect(); observer = null; }
      clearStandby();
    }

    function succeed(store, el) {
      stop();
      var name = storeNameOf(el);
      badge(true, "已选中：" + (name ? name + " " : "") + store + "，请人工继续");
      if (opts.onDone) {
        opts.onDone({ status: "selected", store: store, name: name, core: CORE_VERSION,
          candidates: candidates, triggerClicks: triggerClicks });
      }
    }

    function fail(reason) {
      stop();
      var text = "候选门店当前均无法自动选择，请手动操作";
      if (reason === "panel_timeout") { text += "（门店列表未出现）"; }
      badge(false, text);
      if (opts.onDone) {
        opts.onDone({ status: "failed", reason: reason, core: CORE_VERSION,
          candidates: candidates, triggerClicks: triggerClicks });
      }
    }

    // 门店列表还没出来时，尝试点一次“查看供货情况”。弹窗已开或次数用完就不再点。
    function tryOpenPickupPanel(now) {
      if (!opts.autoOpenPanel) { return; }
      if (now - started < opts.triggerInitialDelayMs) { return; }
      if (triggerClicks >= MAX_TRIGGER_CLICKS) { return; }
      if (now - lastTriggerClickAt < opts.triggerRetryMs) { return; }
      if (overlayOpen(trigger)) { return; }
      var el = findPickupTrigger();
      if (!el) { return; }
      trigger = el;
      if (safeClick(el, "pickup-trigger")) {
        triggerClicks += 1;
        lastTriggerClickAt = now;
      } else {
        // 找到了但不安全（例如 type=submit）：记为已用完，绝不降级去点别的东西
        triggerClicks = MAX_TRIGGER_CLICKS;
      }
    }

    function tick() {
      if (finished) { return; }
      var now = Date.now();
      var present = panelPresent();
      if (present && !panelSeenAt) { panelSeenAt = Date.now(); }
      if (!present) { tryOpenPickupPanel(now); }

      // 按候选顺序逐个试：最高优先的不存在或不可选，立刻看下一个
      for (var i = 0; i < candidates.length; i++) {
        var el = findRadio(candidates[i]);
        if (!el || !selectable(el)) { continue; }
        if (el.checked === true) { succeed(candidates[i], el); return; }
        if (selectRadio(el)) { succeed(candidates[i], el); return; }
        // 点了没生效：不纠缠，直接看下一个候选
      }

      if (panelSeenAt && now - panelSeenAt >= opts.settleMs) { fail("no_selectable_candidate"); return; }
      if (now - started >= opts.panelTimeoutMs) { fail(panelSeenAt ? "no_selectable_candidate" : "panel_timeout"); }
    }

    showStandby();
    timer = setInterval(tick, opts.pollMs);
    try {
      observer = new MutationObserver(tick);
      observer.observe(document.documentElement || document, {
        childList: true, subtree: true,
        attributes: true, attributeFilter: ["disabled", "aria-disabled", "value", "checked", "aria-expanded"]
      });
    } catch (e) {
      observer = null; // 只靠轮询也能工作
    }
    tick();
    return true;
  }

  global.DuoMonitorStoreSelector = {
    CORE_VERSION: CORE_VERSION,
    FRAGMENT_KEY: FRAGMENT_KEY,
    MAX_CANDIDATES: MAX_CANDIDATES,
    RADIO_SELECTOR: RADIO_SELECTOR,
    parseCandidates: parseCandidates,
    isStoreRadio: isStoreRadio,
    isPickupTrigger: isPickupTrigger,
    safeClick: safeClick,
    run: run
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
