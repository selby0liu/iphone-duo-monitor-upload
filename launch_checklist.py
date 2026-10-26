#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开售前检查清单（纯本地、纯逻辑，不联网）

边界（永久）：
- 不访问 Apple 商品页、不调用 Pickup / fulfillment-messages / 任何 Apple 接口
- 不读取浏览器 Cookie、登录态、密码、扩展内部数据、浏览器配置目录
- 浏览器"存在与否"只用 os.path.exists 看 .app 包在不在，仅此而已
- 凡是涉及"浏览器里是否登录"和"扩展是否已启用"的，一律只能由用户手动勾选确认，
  程序不做、也不许假装做自动检测
- 清单只是提示，不阻断 Pickup 监控，也不改变 Checkout 的打开行为
"""

import os
import time

# 手动确认项：程序无法诚实自动检测，必须用户自己勾
SAFARI_MANUAL = (
    ("safari_extension_enabled", "Safari 门店助手已启用",
     "Safari → 设置 → 扩展，勾选「iPhone Duo Monitor 取货门店助手」，"
     "并在「编辑网站」里把 www.apple.com.cn 设为允许"),
    ("safari_unsigned_allowed", "开发 → 允许未签名的扩展 已开启",
     "Safari 菜单栏 → 开发 → 勾选「允许未签名的扩展」。"
     "没有 Apple 开发者证书，这个开关每次重启 Safari 都会自动关掉"),
    ("apple_id_signed_in", "Apple ID 已登录",
     "在 Safari 里打开 apple.com.cn，确认右上角是你自己的账号"),
)

CHROME_MANUAL = (
    ("chrome_extension_enabled", "Apple Store Selector 扩展已启用",
     "Chrome → 扩展程序 → 管理扩展程序，确认「iPhone Duo Monitor 取货门店助手」开关是打开的"),
    ("apple_id_signed_in", "Apple ID 已登录",
     "在 Chrome 里打开 apple.com.cn，确认右上角是你自己的账号"),
)

SAFARI_RESTART_WARNING = "Safari 重启后未签名扩展可能失效，开售前请重新确认"

# 手动确认超过这么久就提示重新确认（Safari 重启、换浏览器、退出登录都会让旧确认失效）
MANUAL_STALE_SECONDS = 6 * 3600

# 只看 .app 包在不在，不读任何浏览器数据
BROWSER_APP_PATHS = {
    "safari": ("/Applications/Safari.app", "/System/Applications/Safari.app"),
    "chrome": ("/Applications/Google Chrome.app",
               os.path.expanduser("~/Applications/Google Chrome.app")),
    "edge": ("/Applications/Microsoft Edge.app",
             os.path.expanduser("~/Applications/Microsoft Edge.app")),
}
SAFARI_HELPER_APP = os.path.expanduser("~/Applications/DuoMonitorStoreSelector.app")
CHROME_EXT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "browser_extension", "apple_store_selector")

PICKUP_FRESH_SECONDS = 300   # 最近一次成功 Pickup 超过 5 分钟就算不新鲜

STATUS_ICON = {
    "ok": "✓", "warn": "!", "fail": "✗", "info": "·",
    "manual_ok": "✓", "manual_stale": "!", "manual_pending": "☐",
}
STATUS_COLOR = {
    "ok": "#27ae60", "manual_ok": "#27ae60",
    "warn": "#f39c12", "manual_stale": "#f39c12", "manual_pending": "#f39c12",
    "fail": "#e74c3c", "info": "#7f8c8d",
}


def target_browser(browser):
    """Checkout 的 browser 配置 → 实际要检查的浏览器。default 按用户环境等同 Chrome。"""
    return "safari" if str(browser or "").lower() == "safari" else "chrome"


def manual_items(browser):
    return SAFARI_MANUAL if target_browser(browser) == "safari" else CHROME_MANUAL


def manual_keys(browser):
    return [k for k, _label, _hint in manual_items(browser)]


def find_browser(target, exists=os.path.exists):
    """只判断 .app 是否存在，返回 (present, path)。不启动浏览器、不读任何数据。"""
    for path in BROWSER_APP_PATHS.get(target, ()):
        if exists(path):
            return True, path
    return False, ""


def manual_status(record, now=None, stale_seconds=MANUAL_STALE_SECONDS):
    """手动确认项的状态：未勾 / 已勾 / 勾过但太久需要重新确认"""
    now = time.time() if now is None else now
    if not record or not record.get("confirmed"):
        return "manual_pending"
    at = record.get("at")
    try:
        at = float(at)
    except (TypeError, ValueError):
        return "manual_ok"
    return "manual_stale" if (now - at) > stale_seconds else "manual_ok"


def _confirm_detail(record, status, now):
    if status == "manual_pending":
        return ""
    at = record.get("at")
    try:
        stamp = time.strftime("%m-%d %H:%M", time.localtime(float(at)))
    except (TypeError, ValueError):
        return ""
    if status == "manual_stale":
        hours = int((now - float(at)) // 3600)
        return f"上次确认 {stamp}（{hours} 小时前，建议重新确认）"
    return f"已确认 {stamp}"


def build_checklist(state, now=None, exists=os.path.exists):
    """
    state 里全部是 Mac 本地已有的信息，不为了自检去请求任何东西：
      cloud_online / cloud_healthy : 服务器卡片已经算好的在线与健康
      pickup_ok                    : 任一数据源 api_available
      pickup_ok_age                : 最近一次成功 Pickup 距今多少秒（None = 不知道）
      checkout_enabled / auto_open_buy_page / auto_select_store / browser
      prevent_sleep                : caffeinate 是否在跑
      sound_enabled / bark_enabled
      manual                       : {key: {"confirmed": bool, "at": epoch}}
    返回 [{key, label, status, detail, manual, hint}, ...]
    """
    now = time.time() if now is None else now
    manual = state.get("manual") or {}
    browser = state.get("browser")
    target = target_browser(browser)
    items = []

    # 1 Cloud 在线
    if state.get("cloud_healthy"):
        items.append(dict(key="cloud_online", label="Cloud 在线", status="ok",
                          detail="至少一台服务器在线且 Pickup 正常", manual=False, hint=""))
    elif state.get("cloud_online"):
        items.append(dict(key="cloud_online", label="Cloud 在线", status="warn",
                          detail="服务器连得上，但 Pickup 当前不正常", manual=False, hint=""))
    else:
        items.append(dict(key="cloud_online", label="Cloud 在线", status="fail",
                          detail="主备服务器都连不上", manual=False, hint=""))

    # 2 最近 Pickup 200
    age = state.get("pickup_ok_age")
    if state.get("pickup_ok") and age is not None and age <= PICKUP_FRESH_SECONDS:
        items.append(dict(key="pickup_recent", label="最近 Pickup 200", status="ok",
                          detail=f"{int(age)} 秒前有成功返回", manual=False, hint=""))
    elif age is not None:
        items.append(dict(key="pickup_recent", label="最近 Pickup 200", status="warn",
                          detail=f"最近一次成功在 {int(age)} 秒前，可能正在限流",
                          manual=False, hint=""))
    else:
        items.append(dict(key="pickup_recent", label="最近 Pickup 200", status="warn",
                          detail="还没拿到成功记录", manual=False, hint=""))

    # 3 Checkout 已开启
    if not state.get("checkout_enabled"):
        items.append(dict(key="checkout_enabled", label="Checkout 已开启", status="fail",
                          detail="Checkout Assistant 未启用，有货不会自动开页",
                          manual=False, hint=""))
    elif not state.get("auto_open_buy_page"):
        items.append(dict(key="checkout_enabled", label="Checkout 已开启", status="warn",
                          detail="已启用，但「自动打开购买页」是关的", manual=False, hint=""))
    else:
        extra = "，门店助手已开" if state.get("auto_select_store") else "，门店助手未开"
        items.append(dict(key="checkout_enabled", label="Checkout 已开启", status="ok",
                          detail=f"有货会自动打开购买页{extra}", manual=False, hint=""))

    # 4 目标浏览器存在（只看 .app 在不在）
    present, path = find_browser(target, exists=exists)
    label = "目标浏览器存在（Safari）" if target == "safari" else "目标浏览器存在（Chrome）"
    if present:
        detail = path
        if target == "chrome" and str(browser or "").lower() != "safari":
            detail += "（打开方式=系统默认浏览器）"
        items.append(dict(key="browser_present", label=label, status="ok",
                          detail=detail, manual=False, hint=""))
    else:
        edge_present, edge_path = find_browser("edge", exists=exists)
        hint = f"检测到 Microsoft Edge：{edge_path}" if edge_present else ""
        items.append(dict(key="browser_present", label=label, status="fail",
                          detail="没找到这个浏览器的 .app", manual=False, hint=hint))

    # 5/6 门店助手 + Apple ID：全部人工确认，程序不猜
    for key, text, hint in manual_items(browser):
        record = manual.get(key) or {}
        status = manual_status(record, now=now)
        detail = _confirm_detail(record, status, now)
        if key == "safari_extension_enabled":
            installed = exists(SAFARI_HELPER_APP)
            hint += ("；扩展 App 已安装：" + SAFARI_HELPER_APP) if installed \
                else "；注意：没找到 " + SAFARI_HELPER_APP
        elif key == "chrome_extension_enabled":
            # 打包成 .app 之后 __file__ 在临时解包目录里，源目录多半定位不到；
            # 这种情况下不要报一个不存在的路径去误导人，直接不提。
            ext_dir = state.get("chrome_ext_dir") or CHROME_EXT_DIR
            hint += ("；扩展源目录在：" + ext_dir) if exists(ext_dir) \
                else "；（未定位到扩展源目录，不影响这一项的确认）"
        items.append(dict(key=key, label=text, status=status, detail=detail,
                          manual=True, hint=hint))

    # 7 防睡眠
    if state.get("prevent_sleep"):
        items.append(dict(key="prevent_sleep", label="防睡眠已生效", status="ok",
                          detail="caffeinate 正在运行，系统不会睡", manual=False, hint=""))
    else:
        items.append(dict(key="prevent_sleep", label="防睡眠已生效", status="warn",
                          detail="caffeinate 没在跑，Mac 可能睡过去", manual=False, hint=""))

    # 8 声音 / Bark
    sound = bool(state.get("sound_enabled"))
    bark = bool(state.get("bark_enabled"))
    if sound and bark:
        status, detail = "ok", "本机提示音开，Bark 推送开"
    elif bark:
        status, detail = "warn", "Bark 开，本机提示音关"
    elif sound:
        status, detail = "warn", "本机提示音开，Bark 关（手机收不到）"
    else:
        status, detail = "fail", "提示音和 Bark 都关着，有货你不会被叫醒"
    items.append(dict(key="alerting", label="声音 / Bark", status=status,
                      detail=detail, manual=False, hint=""))

    return items


def browser_env_ready(state, now=None, exists=os.path.exists):
    """浏览器环境是否就绪：目标浏览器在 + 该浏览器的人工确认项全部勾上且未过期"""
    now = time.time() if now is None else now
    browser = state.get("browser")
    present, _ = find_browser(target_browser(browser), exists=exists)
    if not present:
        return False
    manual = state.get("manual") or {}
    for key in manual_keys(browser):
        if manual_status(manual.get(key) or {}, now=now) != "manual_ok":
            return False
    return True


def pending_manual_labels(state, now=None):
    """还没确认（或需要重新确认）的人工项名称，用于横幅提示"""
    now = time.time() if now is None else now
    manual = state.get("manual") or {}
    out = []
    for key, label, _hint in manual_items(state.get("browser")):
        if manual_status(manual.get(key) or {}, now=now) != "manual_ok":
            out.append(label)
    return out


def banner_text(state, now=None, exists=os.path.exists):
    """(文案, 颜色, 是否就绪)；首发模式下未就绪要显眼"""
    now = time.time() if now is None else now
    ready = browser_env_ready(state, now=now, exists=exists)
    launch_mode = bool(state.get("launch_mode"))
    if ready:
        return ("浏览器环境已就绪", "#27ae60", True)
    pending = pending_manual_labels(state, now=now)
    tail = ("：待确认 " + "、".join(pending)) if pending else ""
    color = "#e74c3c" if launch_mode else "#f39c12"
    return ("浏览器环境未就绪" + tail, color, False)


def normalize_manual(raw):
    """读配置时清洗：只保留 {confirmed: bool, at: float}，丢掉任何其它字段"""
    out = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            at = float(value.get("at") or 0)
        except (TypeError, ValueError):
            at = 0.0
        out[str(key)] = {"confirmed": bool(value.get("confirmed")), "at": at}
    return out
