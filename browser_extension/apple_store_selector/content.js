/*
 * iPhone Duo Monitor - 取货门店助手 · 启动器（content script）
 *
 * 这个文件故意保持极薄：所有门店选择逻辑都在 store_selector_core.js 里，
 * Chrome/Edge 版和 Safari 版加载的是同一份核心，行为不可能分叉。
 * manifest 里的加载顺序必须是 ["store_selector_core.js", "content.js"]。
 */
(function () {
  "use strict";
  var core = (typeof globalThis !== "undefined") && globalThis.DuoMonitorStoreSelector;
  if (!core || typeof core.run !== "function") { return; }
  core.run();
})();
