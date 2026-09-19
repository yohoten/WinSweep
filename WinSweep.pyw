#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WinSweep v3.4 - 系统垃圾清理工具 (.pyw)
图形界面版本，双击运行无控制台窗口。
需要管理员权限，如未提权会自动请求。

v3.4 更新（UI 与显示全面重构）：
  * 修复布局缺陷：旧版日志区 expand 抢占全部空间，窗口高度不足时「系统」按钮组与
    状态栏被挤出可视区（显示不全）。改为 grid 分区 + Panedwindow 可拖拽分隔，
    头部 / 导航 / 内容 / 日志 / 状态栏各自保底高度，缩到最小也不会丢控件
  * 单窗口多视图：概览 / 缓存清理 / 预装清理 / 系统优化 / 系统工具 / 关于，
    原「自定义清理 / 系统优化 / 预装清理 / 系统工具」4 个弹窗全部内嵌为视图，
    不再出现弹窗遮挡主窗、关闭后主窗口滚轮失效的问题
  * 滚轮改为指针命中测试：只在鼠标所在的滚动区内滚动，视图之间互不干扰
  * 头部信息条重构：磁盘胶囊条随窗口伸缩 + 可用/总量 + Windows.old / 上次清理状态标签
  * 深色标题栏（DWM immersive dark mode）+ Win11 圆角与边框配色，窗口不再上白下黑
  * 日志区升级：级别过滤（全部/信息/成功/警告/错误，带计数）、关键词搜索、
    自动滚动开关与「跳到最新」、等宽时间戳+级别列对齐、分区标题行底色、导出日志文件
  * 进度反馈升级：长耗时外部任务（DISM / sfc / 还原点 / 预装清理）改用跑马灯 +
    已用时计时 + 旋转指示器，不再停在 0% 让人误以为卡死；可量化任务保留百分比
  * 按钮改用内容自适应宽度 + 自动换行容器（旧版 width 按字符计，中文/emoji 混排会截断）
  * 字体集中为命名字体管理，Ctrl+= / Ctrl+- 全局缩放字号；字号、视图、布局、窗口尺寸
    记忆到 data/settings.json
  * 系统优化 / 预装清理视图直接显示资源文件是否存在（缺失标灰提示），风险分级与二次确认不变
  * 任务执行中关闭窗口会二次确认；关闭时保存布局
  * 高 DPI：优先 Per-Monitor V2，逐级回退，缩放屏不再模糊

v3.3 更新（UI 细节优化）：
  * 颜色系统扩充、ToolTip 延迟出现、按钮禁用态灰化、品牌栏快捷键徽标
  * 信息栏圆点管理员状态、磁盘条圆角胶囊、日志 timestamp 分段渲染、状态栏闪烁反馈
v3.1 / v3.0：集成 Win11Debloat 与 Neon 优化包、全新深色 UI、清理提速与高 DPI 适配
"""

import os
import sys
import glob
import json
import math
import shutil
import stat
import subprocess
import threading
import time
import ctypes
import tempfile
from queue import Queue, Empty
from tkinter import filedialog
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont

APP_NAME    = "WinSweep"
APP_VERSION = "3.4"
APP_TAGLINE = "系统垃圾清理 · 一站式优化"

# ────────────── 项目路径（统一基础常量：资源与运行时数据分层） ──────────────
APP_DIR  = os.path.dirname(os.path.abspath(__file__))
RES_DIR  = os.path.join(APP_DIR, "resources")     # 资源目录（Optimization / Win11Debloat）
DATA_DIR = os.path.join(APP_DIR, "data")          # 运行时数据（自动生成）
os.makedirs(DATA_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
LOG_DIR       = os.path.join(DATA_DIR, "logs")

# ────────────── Win11Debloat 系统预装清理路径 ──────────────
# 已内置到 resources/Win11Debloat/ 子目录（自包含，可整体移动）
WIN11DEBLOAT_DIR  = os.path.join(RES_DIR, "Win11Debloat")
WIN11DEBLOAT_PS1  = os.path.join(WIN11DEBLOAT_DIR, "Win11Debloat.ps1")
WIN11DEBLOAT_GUI  = os.path.join(WIN11DEBLOAT_DIR, "Win11DebloatGUI.ps1")
W11D_LAST_FILE    = os.path.join(DATA_DIR, "w11d_last.txt")

# 系统预装清理快速预设（params 直接传给 Win11Debloat.ps1，追加 -Silent 静默执行）
W11D_PRESETS = [
    {"name": "仅移除默认预装应用", "color": "#F5B942", "tag": "轻度",
     "params": "-RemoveApps",
     "desc": "移除 Appslist.txt 中列出的默认预装应用（winget / Remove-AppxPackage）"},
    {"name": "禁用遥测、必应、广告与建议", "color": "#F5B942", "tag": "中度",
     "params": "-DisableTelemetry -DisableBing -DisableLockscreenTips -DisableSuggestions",
     "desc": "禁用遥测诊断数据、必应搜索/Cortana、锁屏提示、系统建议与广告"},
    {"name": "默认模式（常用组合）", "color": "#3B82F6", "tag": "推荐",
     "params": ("-RemoveApps -DisableTelemetry -DisableBing -DisableLockscreenTips "
                "-DisableSuggestions -ShowKnownFileExt -DisableWidgets -HideChat -DisableCopilot"),
     "desc": "Win11Debloat 官方默认模式：移除预装应用 + 常用隐私/任务栏/资源管理器优化"},
]

# ────────────── Windows 高 DPI 适配（优先 Per-Monitor V2，逐级回退） ──────────────
def _enable_dpi_awareness():
    """返回实际生效的 DPI 感知模式，用于日志说明。"""
    try:  # Win10 1703+ : PER_MONITOR_AWARE_V2
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "PerMonitorV2"
    except Exception:
        pass
    try:  # Win8.1+ : PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "PerMonitor"
    except Exception:
        pass
    try:  # Win7+ : SYSTEM_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return "System"
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return "System(legacy)"
    except Exception:
        return "none"

DPI_MODE = _enable_dpi_awareness()


def _dpi_scale():
    """系统缩放倍率（1.0 = 100%），取不到时按 1.0 处理。"""
    try:
        dc = ctypes.windll.user32.GetDC(0)
        logpix = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)   # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, dc)
        if logpix:
            return logpix / 96.0
    except Exception:
        pass
    return 1.0


# ────────────── 主题配色（与项目 index.html 落地页同一色阶） ──────────────
BG      = "#0B0E14"   # 主背景（窗口）
BG1     = "#10141D"   # 头部 / 状态栏 / 面板
BG2     = "#161B26"   # 卡片背景
BG3     = "#1C2230"   # 控件 / 次级卡片
BG4     = "#262E3F"   # hover 亮色
LINE    = "#232B39"   # 1px 分隔线 / 卡片描边
LINE_HI = "#33405A"   # hover 描边

FG      = "#E8ECF4"   # 主文字
FG_DIM  = "#A3ADC0"   # 次要文字
FG_MUTE = "#6B7689"   # 辅助文字（timestamp、说明）

ACCENT   = "#37D67A"  # 主色 薄荷绿（清理 / 成功）
ACCENT_D = "#2FB96A"  # 主色按压态
ACCENT2  = "#3B82F6"  # 蓝（深度清理 / 链接）
CYAN     = "#39C5E0"  # 青（系统优化入口）
AMBER    = "#F5B942"  # 警告黄 / 中危
ORANGE   = "#F59E0B"  # 系统工具
PURPLE   = "#A78BFA"  # 自定义
VIOLET   = "#8B5CF6"  # 预装清理
RED      = "#FF6B6B"  # 危险红
SLATE    = "#3A4356"  # 中性按钮底

SUCCESS_BG = "#0E2119"  # 成功行底色
ERROR_BG   = "#241318"  # 错误行底色
WARN_BG    = "#221C10"  # 警告行底色
SECTION_BG = "#131A26"  # 分区标题行底色

# 日志级别 → (显示代号, 前景色, 行底色, 是否加粗)
LEVEL_STYLE = {
    "title":   ("--", ACCENT2,  SECTION_BG, True),
    "cyan":    ("==", ACCENT2,  SECTION_BG, True),
    "info":    ("..", FG,       "",         False),
    "gray":    ("..", FG_MUTE,  "",         False),
    "bold":    ("..", FG,       "",         True),
    "success": ("OK", ACCENT,   SUCCESS_BG, True),
    "warning": ("!!", AMBER,    WARN_BG,    False),
    "error":   ("XX", RED,      ERROR_BG,   True),
}
LEVEL_ORDER = ["all", "info", "success", "warning", "error"]
LEVEL_LABEL = {"all": "全部", "info": "信息", "success": "成功", "warning": "警告", "error": "错误"}
# 过滤分组 → 归入该组的原始 tag
LEVEL_GROUP = {
    "info":    ("info", "gray", "bold", "title", "cyan"),
    "success": ("success",),
    "warning": ("warning",),
    "error":   ("error",),
}

# 字体族候选（Windows 自带，优先 UI 版雅黑，缺失时逐级回退）
UI_FAMILY_CANDIDATES  = ("Microsoft YaHei UI", "微软雅黑", "Microsoft YaHei", "Segoe UI", "TkDefaultFont")
MONO_FAMILY_CANDIDATES = ("Cascadia Mono", "Consolas", "Microsoft YaHei Mono", "Courier New")

# 命名字体：基准字号（pt），运行时按 scale 缩放
FONT_SPECS = {
    "brand":  (17, "bold"),
    "h1":     (13, "bold"),
    "h2":     (11, "bold"),
    "ui":     (10, "normal"),
    "ui_b":   (10, "bold"),
    "small":  (9,  "normal"),
    "small_b": (9, "bold"),
    "tiny":   (8,  "normal"),
    "mono":   (10, "normal"),
    "mono_s": (9,  "normal"),
    "num":    (16, "bold"),
}

PROGRESSBAR_THICKNESS = 10      # 进度条厚度（px）
DISK_BAR_H            = 12      # 磁盘胶囊条高度（px）
TOOLTIP_DELAY_MS      = 380     # ToolTip 延迟出现（ms）
MAX_LOG_LINES  = 1200           # 日志区最多渲染行数（超出截断前半）
MAX_LOG_RECORDS = 4000          # 内存中保留的日志记录上限
QUEUE_POLL_MS  = 60             # 消息队列轮询间隔
TICK_MS        = 1000           # 时钟/计时刷新间隔
DISK_EVERY     = 4              # 每 N 个 tick 刷新一次磁盘信息

NAV_WIDTH   = 200               # 侧边导航宽度
LOG_MIN_H   = 96                # 日志区最小高度
LOG_DEF_H   = 250               # 日志区默认高度

# 视图定义：(key, 图标, 名称, 视图副标题, 导航短标题)
VIEWS = [
    ("overview", "◈", "概览",     "磁盘状态 · 一键清理",                 "磁盘与快捷入口"),
    ("clean",    "▣", "缓存清理", "14 项清理 · 快速 / 深度 / 自定义",     "快速 / 深度 / 自定义"),
    ("debloat",  "◉", "预装清理", "Win11Debloat 预设与图形界面",         "预设与图形界面"),
    ("optimize", "⚙", "系统优化", "Neon 优化包 · 危险分级",             "10 项 · 危险分级"),
    ("tools",    "✦", "系统工具", "还原点 · DISM · sfc · chkdsk",       "还原点 / DISM / sfc"),
    ("about",    "ⓘ", "关于",     "版本 · 快捷键 · 免责声明",           "版本与说明"),
]
VIEW_BY_KEY = {v[0]: v for v in VIEWS}


# ────────────── 设置持久化（字号 / 布局 / 上次视图） ──────────────
def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_settings(data):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_FILE)
        return True
    except Exception:
        return False

# ══════════════ 通用小工具 ══════════════

# 运行时命名字体表（由 build_fonts 填充）：key → tkinter.font.Font
FONT = {}


def format_size(n):
    """字节数转可读字符串"""
    try:
        n = int(n)
    except Exception:
        return "0 B"
    if n >= 1 << 30:
        return f"{n / (1 << 30):.2f} GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.0f} KB"
    return f"{n} B"


def fmt_elapsed(seconds):
    """秒数 → mm:ss（超过 1 小时显示 h:mm:ss）"""
    try:
        s = max(0, int(seconds))
    except Exception:
        return "00:00"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def _split_rgb(color):
    c = str(color).lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        return (128, 128, 128)
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (128, 128, 128)


def _join_rgb(rgb):
    return "#{:02x}{:02x}{:02x}".format(*[max(0, min(255, int(v))) for v in rgb])


def lighten(color, amount=0.18):
    """颜色加亮，用于按钮 hover 效果"""
    r, g, b = _split_rgb(color)
    return _join_rgb((r + (255 - r) * amount, g + (255 - g) * amount, b + (255 - b) * amount))


def darken(color, amount=0.35):
    """颜色压暗，用于禁用态背景"""
    r, g, b = _split_rgb(color)
    return _join_rgb((r * (1 - amount), g * (1 - amount), b * (1 - amount)))


def mix(c1, c2, amount=0.5):
    """两色线性混合"""
    a, b = _split_rgb(c1), _split_rgb(c2)
    return _join_rgb((x + (y - x) * amount for x, y in zip(a, b)))


def luminance(color):
    """相对亮度 0~1，用于自动选择按钮文字颜色"""
    r, g, b = _split_rgb(color)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def best_fg(bg_color, light="#FFFFFF", dark="#08120C"):
    """按背景亮度自动挑选前景色（薄荷绿/琥珀黄用深色字，保证对比度）"""
    return dark if luminance(bg_color) > 0.60 else light


def to_colorref(color):
    """#RRGGBB → Windows COLORREF (0x00BBGGRR)"""
    r, g, b = _split_rgb(color)
    return (b << 16) | (g << 8) | r


def resolve_family(candidates, default=None):
    """在已安装字体中挑选第一个可用字族"""
    try:
        fams = {f.lower() for f in tkfont.families()}
    except Exception:
        fams = set()
    for name in candidates:
        if name.lower() in fams:
            return name
    return default or candidates[-1]


def build_fonts(root, scale=1.0, ui_family=None, mono_family=None):
    """创建/更新命名字体（缩放时只改 size，控件自动跟随，无需重建界面）"""
    ui = ui_family or resolve_family(UI_FAMILY_CANDIDATES, "TkDefaultFont")
    mono = mono_family or resolve_family(MONO_FAMILY_CANDIDATES, "TkFixedFont")
    for name, (base, weight) in FONT_SPECS.items():
        family = mono if name.startswith("mono") else ui
        size = max(7, int(round(base * scale)))
        fname = "ws_" + name
        f = FONT.get(name)
        if f is None:
            f = FONT[name] = tkfont.Font(root=root, name=fname, family=family,
                                         size=size, weight=weight)
        else:
            f.configure(family=family, size=size, weight=weight)
    FONT["_ui_family"], FONT["_mono_family"] = ui, mono
    return FONT


def apply_dark_titlebar(win, caption=BG1, border=LINE, text=FG):
    """Win10 2004+/Win11：标题栏深色 + 圆角 + 边框配色；失败静默忽略"""
    try:
        hwnd = ctypes.c_void_p(ctypes.windll.user32.GetParent(win.winfo_id()))
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        for attr in (20, 19):        # DWMWA_USE_IMMERSIVE_DARK_MODE（新旧编号）
            try:
                if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), 4) == 0:
                    break
            except Exception:
                break
        for attr, val in ((33, ctypes.c_int(2)),          # 圆角优先
                          (34, ctypes.c_uint(to_colorref(border))),   # 边框色
                          (35, ctypes.c_uint(to_colorref(caption))),  # 标题栏底色
                          (36, ctypes.c_uint(to_colorref(text)))):    # 标题文字色
            try:
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4)
            except Exception:
                pass
        return True
    except Exception:
        return False


def center(win, w, h):
    """使窗口在屏幕居中"""
    try:
        win.update_idletasks()
        x = max(0, (win.winfo_screenwidth() - w) // 2)
        y = max(0, (win.winfo_screenheight() - h) // 2)
        win.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass


class ToolTip:
    """悬停提示：延迟出现、屏幕边缘自动翻转，避免快速划过时乱弹"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text   = str(text)
        self.tip    = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, e=None):
        self._cancel_timer()
        self._after_id = self.widget.after(TOOLTIP_DELAY_MS, self._show)

    def _cancel_timer(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _hide(self, e=None):
        self._cancel_timer()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None

    def _show(self):
        self._after_id = None
        if self.tip is not None or not self.text:
            return
        try:
            if not self.widget.winfo_exists():
                return
        except Exception:
            return
        sw, sh = self.widget.winfo_screenwidth(), self.widget.winfo_screenheight()
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_attributes("-topmost", True)
        border = tk.Frame(self.tip, bg=LINE_HI, padx=1, pady=1)
        border.pack()
        lbl = tk.Label(border, text=self.text, bg="#1B2231", fg=FG,
                       font=FONT.get("small"), justify="left", anchor="w",
                       padx=10, pady=5, wraplength=min(420, max(200, sw - x - 20)))
        lbl.pack()
        self.tip.update_idletasks()
        w, h = self.tip.winfo_reqwidth(), self.tip.winfo_reqheight()
        if x + w > sw - 8:
            x = max(4, sw - w - 8)
        if y + h > sh - 8:                      # 底部放不下就翻到上方
            y = max(4, self.widget.winfo_rooty() - h - 6)
        self.tip.wm_geometry(f"+{x}+{y}")


class Card(tk.Frame):
    """1px 描边卡片：hover 时描边亮起，返回 body 作为内容父容器"""
    def __init__(self, parent, bg=BG2, border=LINE, hover=True,
                 padx=14, pady=12, hover_border=LINE_HI, **kw):
        super().__init__(parent, bg=border, padx=1, pady=1, **kw)
        self.body = tk.Frame(self, bg=bg, padx=padx, pady=pady)
        self.body.pack(fill="both", expand=True)
        self._border, self._hover_border, self._hover = border, hover_border, hover
        if hover:
            self.bind("<Enter>", lambda e: self._set(hover_border), add="+")
            self.bind("<Leave>", lambda e: self._set(border), add="+")

    def _set(self, color):
        try:
            self.configure(bg=color)
        except Exception:
            pass


class FlowFrame(tk.Frame):
    """子控件按可用宽度自动换行：替代旧的固定 width 按钮（中文/emoji 混排会截断）"""
    def __init__(self, parent, bg=BG, spacing=6, **kw):
        super().__init__(parent, bg=bg, **kw)
        self._items = []
        self.spacing = spacing
        self.bind("<Configure>", self._relayout)

    def add(self, widget, padx=None, pady=None):
        self._items.append([widget, self.spacing if padx is None else padx,
                            self.spacing if pady is None else pady])
        widget.bind("<Configure>", lambda e: self._relayout(), add="+")
        self._relayout()
        return widget

    def clear(self):
        for w, _, _ in self._items:
            try:
                w.destroy()
            except Exception:
                pass
        self._items = []
        self.configure(height=1)

    def _relayout(self, e=None):
        avail = max(self.winfo_width(), 40)
        x = y = rowh = 0
        for w, px, py in list(self._items):
            try:
                if not w.winfo_ismapped() and not w.winfo_exists():
                    continue
                w.update_idletasks()
                cw, ch = w.winfo_reqwidth() + px * 2, w.winfo_reqheight() + py * 2
            except Exception:
                continue
            if x + cw > avail and x > 0:
                x, y, rowh = 0, y + rowh, 0
            w.place(x=x + px, y=y + py)
            x += cw
            rowh = max(rowh, ch)
        try:
            self.configure(height=y + rowh)
        except Exception:
            pass


def make_button(parent, text, command=None, color=BG3, size="md", style="solid",
                tooltip=None, takefocus=False):
    """统一扁平按钮：内容自适应宽度（不再按字符数截断）
    style: solid 实色 / soft 深底彩字 / ghost 透明描边
    size : sm / md / lg
    """
    pad = {"sm": (10, 3), "md": (14, 6), "lg": (20, 9)}[size]
    fname = {"sm": "small_b", "md": "ui_b", "lg": "h2"}[size]
    if style == "solid":
        bg, fg = color, best_fg(color)
    elif style == "soft":
        bg, fg = mix(BG3, color, 0.16), color
    else:  # ghost
        bg, fg = BG1, color
    btn = tk.Button(
        parent, text=text, command=command, bg=bg, fg=fg,
        activebackground=lighten(bg, 0.14), activeforeground=fg,
        disabledforeground="#5A6472",
        relief="flat", bd=0, highlightthickness=0, takefocus=1 if takefocus else 0,
        cursor="hand2", font=FONT.get(fname), padx=pad[0], pady=pad[1],
    )
    btn._ws_base = (bg, fg, lighten(bg, 0.14))
    btn.bind("<Enter>", lambda e: _btn_hover(btn, True))
    btn.bind("<Leave>", lambda e: _btn_hover(btn, False))
    if tooltip:
        ToolTip(btn, tooltip)
    return btn


def _btn_hover(btn, on):
    try:
        if str(btn["state"]) == "disabled":
            return
        bg, _fg, act = btn._ws_base
        btn.configure(bg=lighten(bg) if on else bg,
                      activebackground=lighten(bg, 0.14) if on else act)
    except Exception:
        pass


def set_button_enabled(btn, enabled):
    """启用/禁用按钮并同步视觉（禁用态压暗 + 取消手型）"""
    try:
        bg, fg, act = btn._ws_base
        if enabled:
            btn.configure(state=tk.NORMAL, bg=bg, fg=fg, activebackground=act, cursor="hand2")
        else:
            btn.configure(state=tk.DISABLED, bg=darken(bg, 0.55), fg="#5A6472",
                          activebackground=darken(bg, 0.55), cursor="arrow")
    except Exception:
        try:
            btn.configure(state=tk.NORMAL if enabled else tk.DISABLED)
        except Exception:
            pass


def chip(parent, text, fg=FG_DIM, bg=BG3, border=None, font=None, padx=8, pady=3):
    """小圆角胶囊标签（用 1px 边框 Frame 模拟）"""
    outer = tk.Frame(parent, bg=border or bg, padx=1, pady=1)
    lbl = tk.Label(outer, text=text, bg=bg, fg=fg, font=font or FONT.get("small"),
                   padx=padx, pady=pady)
    lbl.pack()
    outer.label = lbl
    return outer


class Spinner(tk.Canvas):
    """16px 旋转指示器：任务运行中给出不依赖字体的活动反馈"""
    FRAMES = 8

    def __init__(self, parent, size=16, color=ACCENT, **kw):
        super().__init__(parent, width=size, height=size, bg=kw.pop("bg", BG1),
                         highlightthickness=0, **kw)
        self.size, self.color = size, color
        self._bgcolor = str(self["bg"])
        self._angle = 0
        self._id = None

    def draw(self):
        self.delete("all")
        s, r = self.size, self.size / 2 - 2
        cx = cy = s / 2
        for i in range(self.FRAMES):
            ang = i * (360.0 / self.FRAMES) + self._angle
            alpha = 0.18 + 0.82 * (i / float(self.FRAMES - 1))
            col = mix(self._bgcolor, self.color, alpha)
            x = cx + r * 0.72 * math.cos(math.radians(ang))
            y = cy + r * 0.72 * math.sin(math.radians(ang))
            rad = s * 0.055 + (s * 0.075) * (i / float(self.FRAMES - 1))
            self.create_oval(x - rad, y - rad, x + rad, y + rad, fill=col, outline="")

    def start(self):
        if self._id is not None:
            return
        self._tick()

    def stop(self):
        if self._id is not None:
            try:
                self.after_cancel(self._id)
            except Exception:
                pass
            self._id = None
        self._angle = 0
        try:
            self.delete("all")      # 空闲时不占位、不显示静态圈点
        except Exception:
            pass

    def _tick(self):
        self._angle = (self._angle + 45) % 360
        self.draw()
        self._id = self.after(90, self._tick)

# ────────────── 管理员权限检测与提权 ──────────────
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def run_as_admin():
    """以管理员权限重新启动当前脚本"""
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{__file__}"', None, 1
        )
        sys.exit(0)

# ────────────── 磁盘信息 ──────────────
def get_drive():
    return os.environ.get("SystemDrive", "C:") + "\\"


def get_free_bytes():
    """当前磁盘可用字节数"""
    try:
        return shutil.disk_usage(get_drive()).free
    except Exception:
        return 0


def get_disk_usage(drive=None):
    """返回 {drive,total,used,free,pct_used,pct_free}；失败返回 None"""
    drive = drive or get_drive()
    try:
        total, used, free = shutil.disk_usage(drive)
        if total <= 0:
            return None
        return {
            "drive": drive, "total": total, "used": used, "free": free,
            "pct_used": used * 100.0 / total, "pct_free": free * 100.0 / total,
        }
    except Exception:
        return None


def usage_color(pct_used):
    """使用率 → 颜色（<80% 绿 / <92% 黄 / ≥92% 红）"""
    if pct_used >= 92:
        return RED
    if pct_used >= 80:
        return AMBER
    return ACCENT


def windows_old_path():
    """存在则返回 Windows.old 路径，否则 None"""
    p = os.path.join(get_drive(), "Windows.old")
    return p if os.path.exists(p) else None


def get_disk_summary():
    """一行磁盘摘要，用于信息栏常驻显示"""
    u = get_disk_usage()
    if not u:
        return "磁盘信息不可用"
    return (f"{u['drive'][:-1]}  可用 {format_size(u['free'])} / {format_size(u['total'])}"
            f"   已用 {u['pct_used']:.1f}%")


def format_disk_report():
    """磁盘详情（等宽对齐，供日志区显示；不再依赖空格伪表格）"""
    u = get_disk_usage()
    if not u:
        return ["无法获取磁盘信息"]
    gb = 1024 ** 3
    lines = [
        f"驱动器   {u['drive']}",
        f"总容量   {u['total'] / gb:8.1f} GB",
        f"已  用   {u['used'] / gb:8.1f} GB  ({u['pct_used']:.1f}%)",
        f"可  用   {u['free'] / gb:8.1f} GB  ({u['pct_free']:.1f}%)",
    ]
    old = windows_old_path()
    if old:
        lines.append("提示     发现 Windows.old 备份目录（可能占 10-30GB）")
        lines.append("         请用「磁盘清理 → 清理系统文件」删除")
    return lines


# ────────────── 浏览器安装检测（只读，供概览显示） ──────────────
def installed_browser_names():
    try:
        return sorted({name for name, _p in _get_installed_browsers()})
    except Exception:
        return []
# ══════════════ 清理功能实现 ══════════════
# 均需管理员权限（程序启动时已提权）。

def _clear_dir(path):
    """清空目录内容后重建（保留目录本身）"""
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)


def clean_temp_files(log):
    """清理系统根目录下散落的临时文件（仅扫描根目录，不递归，避免全盘遍历）"""
    drive = get_drive()
    exts = (".tmp", "._mp", ".gid", ".chk", ".old", ".bak")
    removed = 0
    try:
        for f in os.listdir(drive):
            fp = os.path.join(drive, f)
            if os.path.isfile(fp) and f.lower().endswith(exts):
                try:
                    os.chmod(fp, stat.S_IWRITE)   # 清除只读属性
                    os.remove(fp)
                    removed += 1
                except Exception:
                    pass
    except Exception:
        pass
    log("info", f"[清理] 系统根目录临时文件完成（删除 {removed} 个文件）")


def clean_windows_temp(log):
    """清理 Windows 临时目录"""
    windir = os.environ.get("WINDIR", "C:\\Windows")
    _clear_dir(os.path.join(windir, "temp"))
    log("info", "[清理] Windows 临时目录完成")


def clean_user_temp(log):
    """清理用户临时文件"""
    _clear_dir(tempfile.gettempdir())
    log("info", "[清理] 用户临时文件完成")


def clean_recycle_bin(log):
    """清空回收站"""
    try:
        subprocess.run(
            ["powershell", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
            capture_output=True, check=False
        )
        log("success", "  回收站已清空")
    except Exception:
        system_drive = get_drive()
        recycle_path = os.path.join(system_drive, "$Recycle.Bin")
        try:
            if os.path.exists(recycle_path):
                shutil.rmtree(recycle_path, ignore_errors=True)
                log("success", "  回收站已清空（备用方法）")
        except Exception:
            log("warning", "  回收站清理失败")


def clean_thumb_cache(log):
    """清理缩略图缓存"""
    userprofile = os.environ.get("USERPROFILE", "")
    cache_path = os.path.join(
        userprofile, "AppData", "Local", "Microsoft", "Windows", "Explorer"
    )
    removed = 0
    try:
        for file in os.listdir(cache_path):
            if file.endswith(".db"):
                fp = os.path.join(cache_path, file)
                try:
                    os.remove(fp)
                    removed += 1
                except Exception:
                    pass
    except Exception:
        pass
    log("info", f"[清理] 缩略图缓存完成（删除 {removed} 个缓存文件）")


def clean_dns_cache(log):
    """刷新 DNS 缓存（直接传参，不经 shell）"""
    subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
    log("info", "[清理] DNS 缓存已刷新")


def clean_error_reports(log):
    """清理 Windows 错误报告"""
    paths = [
        os.path.join(get_drive(), "ProgramData", "Microsoft", "Windows", "WER", "ReportArchive"),
        os.path.join(get_drive(), "ProgramData", "Microsoft", "Windows", "WER", "ReportQueue"),
        os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Microsoft", "Windows", "WER"),
    ]
    for p in paths:
        if os.path.exists(p):
            shutil.rmtree(p, ignore_errors=True)
    log("info", "[清理] Windows 错误报告完成")


def clean_memory_dump(log):
    """清理内存转储文件 —— 只清理已知固定位置，不再全盘遍历（原 v2 全盘 os.walk 极慢）"""
    system_drive = get_drive()
    targets = [
        os.path.join(system_drive, "Windows", "MEMORY.DMP"),
        os.path.join(system_drive, "Windows", "Minidump"),
        os.path.join(system_drive, "Windows", "LiveKernelReports"),
    ]
    cleared = 0
    for t in targets:
        try:
            if os.path.isfile(t):
                os.chmod(t, stat.S_IWRITE)
                os.remove(t)
                cleared += 1
            elif os.path.isdir(t):
                shutil.rmtree(t, ignore_errors=True)
                cleared += 1
        except Exception:
            pass
    log("info", f"[清理] 内存转储文件完成（清理 {cleared} 项）")


def check_old_windows(log):
    """检查 Windows.old 目录"""
    old_path = os.path.join(get_drive(), "Windows.old")
    if os.path.exists(old_path):
        log("warning", "  发现 Windows.old 目录（约 10-30GB），如需删除请使用“磁盘清理”工具")
    else:
        log("info", "  未发现 Windows.old 目录")


def clean_software_dist(log):
    """清理 Windows 更新缓存（合并 stop/start 为各一次子进程调用）"""
    windir = os.environ.get("WINDIR", "C:\\Windows")
    download_dir = os.path.join(windir, "SoftwareDistribution", "Download")
    try:
        subprocess.run("net stop wuauserv & net stop bits", shell=True, capture_output=True)
        try:
            if os.path.exists(download_dir):
                shutil.rmtree(download_dir, ignore_errors=True)
        finally:
            subprocess.run("net start wuauserv & net start bits", shell=True, capture_output=True)
    except Exception:
        pass
    log("info", "[清理] Windows 更新缓存完成")


# ────────────── 浏览器候选列表（自动扫描已安装，动态清理） ──────────────
# 每项：(显示名称, 相对 %LOCALAPPDATA% 或 %APPDATA% 的路径, 根环境变量)
# 路径支持 glob 通配符（Firefox 多 Profile 场景）
_BROWSER_CACHE_PATHS = [
    ("Microsoft Edge",   r"Microsoft\Edge\User Data\Default\Cache",              "LOCALAPPDATA"),
    ("Microsoft Edge",   r"Microsoft\Edge\User Data\Default\Code Cache",         "LOCALAPPDATA"),
    ("Google Chrome",    r"Google\Chrome\User Data\Default\Cache",               "LOCALAPPDATA"),
    ("Google Chrome",    r"Google\Chrome\User Data\Default\Code Cache",          "LOCALAPPDATA"),
    ("Brave",            r"BraveSoftware\Brave-Browser\User Data\Default\Cache", "LOCALAPPDATA"),
    ("Brave",            r"BraveSoftware\Brave-Browser\User Data\Default\Code Cache", "LOCALAPPDATA"),
    ("Opera",            r"Opera Software\Opera Stable\Cache",                   "APPDATA"),
    ("Opera GX",         r"Opera Software\Opera GX Stable\Cache",               "APPDATA"),
    ("Vivaldi",          r"Vivaldi\User Data\Default\Cache",                     "LOCALAPPDATA"),
    ("IE / INetCache",   r"Microsoft\Windows\INetCache",                         "LOCALAPPDATA"),
    ("IE Legacy",        r"Microsoft\Internet Explorer",                         "LOCALAPPDATA"),
]


def _get_installed_browsers():
    """扫描候选列表，返回实际存在的 (名称, 路径) 列表（去重路径）"""
    found = []
    seen = set()
    local = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    for name, rel, env in _BROWSER_CACHE_PATHS:
        base = local if env == "LOCALAPPDATA" else appdata
        full = os.path.join(base, rel)
        if full in seen:
            continue
        if os.path.exists(full):
            seen.add(full)
            found.append((name, full))
    return found


def clean_browser_cache(log):
    """动态扫描并清理已安装浏览器的缓存目录"""
    targets = _get_installed_browsers()
    if not targets:
        log("warning", "  未检测到已安装浏览器的缓存目录，跳过")
        return
    cleared, skipped = 0, 0
    shown_names = set()
    for name, path in targets:
        if name not in shown_names:
            log("info", f"    检测到浏览器：{name}")
            shown_names.add(name)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.isfile(path):
                os.remove(path)
            cleared += 1
        except Exception:
            skipped += 1
    log("info", f"[清理] 浏览器缓存完成（清理 {cleared} 个目录"
               + (f"，{skipped} 个跳过（浏览器可能正在运行）" if skipped else "") + "）")


def clean_prefetch(log):
    """清理预读取文件"""
    windir = os.environ.get("WINDIR", "C:\\Windows")
    prefetch_path = os.path.join(windir, "prefetch")
    removed = 0
    try:
        if os.path.exists(prefetch_path):
            for f in os.listdir(prefetch_path):
                fp = os.path.join(prefetch_path, f)
                if os.path.isfile(fp):
                    try:
                        os.remove(fp)
                        removed += 1
                    except Exception:
                        pass
    except Exception:
        pass
    log("info", f"[清理] 预读取文件完成（删除 {removed} 个文件）")


def clean_recent_docs(log):
    """清理最近文档记录"""
    userprofile = os.environ.get("USERPROFILE", "")
    paths = [
        os.path.join(userprofile, "AppData", "Roaming", "Microsoft", "Windows", "Recent"),
        os.path.join(userprofile, "Recent"),
    ]
    for p in paths:
        try:
            if os.path.exists(p):
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass
    log("info", "[清理] 最近文档记录完成")


def clean_clipboard(log):
    """清空剪贴板"""
    try:
        subprocess.run(
            ["powershell", "-Command", "Set-Clipboard ''"],
            capture_output=True, check=False
        )
        log("info", "[清理] 剪贴板已清空")
    except Exception:
        log("warning", "  剪贴板清空失败")


def clean_font_cache(log):
    """清理字体缓存（合并 stop/start 子进程调用）"""
    windir = os.environ.get("WINDIR", "C:\\Windows")
    cache_dir = os.path.join(windir, "ServiceProfiles", "LocalService", "AppData", "Local", "FontCache")
    try:
        subprocess.run("net stop FontCache", shell=True, capture_output=True)
        try:
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir, ignore_errors=True)
        finally:
            subprocess.run("net start FontCache", shell=True, capture_output=True)
    except Exception:
        pass
    log("info", "[清理] 字体缓存完成")


def start_disk_cleanup(log):
    """启动磁盘清理工具"""
    subprocess.Popen("cleanmgr.exe")
    log("info", "[调用] 已打开磁盘清理工具")


def run_dism_clean(log):
    """运行 DISM 组件清理"""
    log("warning", "  此操作需要较长时间，请耐心等待...")
    result = subprocess.run(
        "dism /online /cleanup-image /startcomponentcleanup /quiet",
        shell=True, capture_output=True, text=True
    )
    if result.returncode == 0:
        log("success", "  DISM 组件清理完成")
    else:
        log("error", f"  DISM 清理失败: {result.stderr}")


def create_restore_point(log, description="WinSweep 操作前备份"):
    """创建 Windows 系统还原点（需要管理员权限，且系统保护已对 C: 启用）。
    返回 True 表示创建成功，False 表示失败。
    """
    log("info", f'[系统还原点] 正在创建还原点："{description}"...')
    ps_cmd = (
        f"Enable-ComputerRestore -Drive '$env:SystemDrive'; "
        f"Checkpoint-Computer -Description '{description}' "
        f"-RestorePointType 'MODIFY_SETTINGS'"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            log("success", '✔ 系统还原点创建成功，可在 "系统属性 -> 系统保护" 中查看')
            return True
        else:
            err = (result.stderr or result.stdout or "").strip()
            log("error", f"  还原点创建失败（退出码: {result.returncode}）")
            if err:
                for line in err.splitlines():
                    if line.strip():
                        log("error", f"  {line.strip()}")
            log("warning", '  提示：若系统保护未开启，请手动在 "系统属性 -> 系统保护" 中启用后重试。')
            return False
    except subprocess.TimeoutExpired:
        log("error", "  还原点创建超时（超过 2 分钟），请检查系统保护服务是否正常")
        return False
    except Exception as e:
        log("error", f"  还原点创建异常: {e}")
        return False


def backup_w11d_config(log=None):
    """备份 Win11Debloat 用户配置（CustomAppsList / SavedSettings），保留最近 5 份"""
    backup_dir = os.path.join(DATA_DIR, "win11debloat_backup")
    try:
        os.makedirs(backup_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        for name in ("CustomAppsList", "SavedSettings"):
            src = os.path.join(WIN11DEBLOAT_DIR, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(backup_dir, f"{name}.{stamp}"))
                if log:
                    log("info", f"  ✓ 已备份 {name} → data\\win11debloat_backup\\{name}.{stamp}")
        # 只保留最近 5 份
        for name in ("CustomAppsList", "SavedSettings"):
            files = sorted(glob.glob(os.path.join(backup_dir, f"{name}.*")))
            for old in files[:-5]:
                try:
                    os.remove(old)
                except Exception:
                    pass
    except Exception as e:
        if log:
            log("warning", f"  Win11Debloat 配置备份失败: {e}")


def run_win11debloat_gui(log):
    """启动 Win11Debloat 图形界面（隐藏 PowerShell 黑窗）。
    返回 (Popen 句柄, stderr 日志路径)；失败返回 None。"""
    if not os.path.isfile(WIN11DEBLOAT_GUI):
        log("error", "[系统预装清理] 未找到 Win11DebloatGUI.ps1，请确认脚本文件存在")
        log("gray", f"  预期路径: {WIN11DEBLOAT_GUI}")
        return None

    backup_w11d_config(log)

    log("cyan", "━━━━━━ 系统预装清理 (Win11Debloat) ━━━━━━")
    log("info", "  正在启动 Win11Debloat 图形界面…")
    log("info", "  请在弹窗中勾选要执行的优化项，点击「开始执行」。")
    log("warning", "  图形界面独立运行，执行完成后关闭窗口即可返回本工具。")

    err_path = ""
    try:
        fd, err_path = tempfile.mkstemp(suffix=".log", prefix="w11d_gui_")
        os.close(fd)
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", WIN11DEBLOAT_GUI],
            cwd=WIN11DEBLOAT_DIR,
            stderr=open(err_path, "wb"),
        )
        return proc, err_path
    except Exception as e:
        log("error", f"[系统预装清理] 启动失败: {e}")
        if err_path and os.path.exists(err_path):
            try:
                os.remove(err_path)
            except Exception:
                pass
        return None


def run_win11debloat_preset(log, params, name):
    """静默执行 Win11Debloat 指定参数（预设快速清理），返回是否成功"""
    if not os.path.isfile(WIN11DEBLOAT_PS1):
        log("error", "[系统预装清理] 未找到 Win11Debloat.ps1，请确认脚本文件存在")
        return False

    log("cyan", f"━━━━━━ 系统预装清理：{name} ━━━━━━")
    log("warning", "  执行过程中可能重启资源管理器（屏幕短暂闪烁），请勿操作…")

    ps_command = f'Set-Location "{WIN11DEBLOAT_DIR}"; & "{WIN11DEBLOAT_PS1}" {params} -Silent'
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", ps_command],
            capture_output=True, text=True, timeout=900
        )
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if any(kw in stripped for kw in ("错误", "失败", "Error", "fail")):
                    log("error", f"  {stripped}")
                elif any(kw in stripped for kw in ("警告", "Warning", "注意")):
                    log("warning", f"  {stripped}")
                elif any(kw in stripped for kw in ("移除", "禁用", "隐藏", "显示", "恢复", "复制", "替换", "成功", "执行", "完成", "Remove", "Disable", "Hide", "Show", "Restore", "Copy", "Replace")):
                    log("info", f"  {stripped}")
                else:
                    log("gray", f"  {stripped}")
        if result.stderr and result.stderr.strip():
            log("warning", "  --- 错误输出 ---")
            for line in result.stderr.strip().splitlines():
                if line.strip():
                    log("warning", f"  {line.strip()}")
        if result.returncode == 0:
            log("success", f"✔ {name}完成（可能需要重启以完全生效）")
            return True
        log("error", f"  {name}执行异常（退出码: {result.returncode}）")
        return False
    except subprocess.TimeoutExpired:
        log("error", f"[系统预装清理] {name}执行超时（超过 15 分钟），请检查脚本是否有交互提示")
        return False
    except Exception as e:
        log("error", f"[系统预装清理] {name}执行失败: {e}")
        return False


# ────────────── 清理项注册表（单一数据源，驱动按钮 / 自定义窗口 / 执行循环） ──────────────
CLEAN_ITEMS = [
    {"key": "a", "icon": "🧹", "name": "系统根目录临时文件", "group": "缓存清理", "func": clean_temp_files},
    {"key": "b", "icon": "🗂️", "name": "Windows 临时目录",   "group": "缓存清理", "func": clean_windows_temp},
    {"key": "c", "icon": "📦", "name": "用户临时文件",       "group": "缓存清理", "func": clean_user_temp},
    {"key": "d", "icon": "🗑️", "name": "回收站",             "group": "缓存清理", "func": clean_recycle_bin},
    {"key": "e", "icon": "🌐", "name": "浏览器缓存",         "group": "缓存清理", "func": clean_browser_cache},
    {"key": "f", "icon": "📁", "name": "最近文档记录",       "group": "缓存清理", "func": clean_recent_docs},
    {"key": "g", "icon": "⚡", "name": "预读取文件 (可选)",    "group": "缓存清理", "func": clean_prefetch,
     "optional": True, "danger": "low",
     "tip": "⚠ 清理后首次冷启动应用/系统会稍慢，Windows 会自动重建。日常建议不勾选。"},
    {"key": "i", "icon": "🖼️", "name": "缩略图缓存",         "group": "缓存清理", "func": clean_thumb_cache},
    {"key": "j", "icon": "🌍", "name": "DNS 缓存",           "group": "缓存清理", "func": clean_dns_cache},
    {"key": "k", "icon": "📋", "name": "Windows 错误报告",   "group": "缓存清理", "func": clean_error_reports},
    {"key": "m", "icon": "📋", "name": "剪贴板",             "group": "缓存清理", "func": clean_clipboard},
    {"key": "h", "icon": "🔄", "name": "Windows 更新缓存",   "group": "系统维护", "func": clean_software_dist},
    {"key": "l", "icon": "💾", "name": "内存转储文件",       "group": "系统维护", "func": clean_memory_dump},
    {"key": "n", "icon": "🔤", "name": "字体缓存",           "group": "系统维护", "func": clean_font_cache},
]
CLEAN_BY_KEY = {it["key"]: it for it in CLEAN_ITEMS}

QUICK_KEYS = ["a", "b", "c", "d", "e", "f", "h"]   # 快速清理组合（g=预读取为可选项，已移出）
# 深度清理 = 全部 14 项 + Windows.old 检查


# ────────────── 系统优化资源注册表（Neon 优化包，统一收纳于 Optimization/） ──────────────
OPT_BASE = os.path.join(RES_DIR, "Optimization")

# 每项：dir=相对 OPT_BASE 的目录名；readme=说明文档；entries=[(按钮标签, 相对文件, 类型)]
# 类型: reg→reg import | bat/cmd→独立窗口执行 | exe/lnk→os.startfile
OPT_ITEMS = [
    {"key": "o0", "name": "系统备份 (Dism++)", "color": "#3B82F6", "danger": "medium",
     "dir": "0 系统备份Dism++", "desc": "Dism++ 系统备份与还原（先读备份方法）",
     "readme": "备份方法(重要).txt",
     "entries": [("打开 Dism++ 主程序", "Dism++/Dism++x64.exe", "exe")]},
    {"key": "o1", "name": "彻底关闭 WinDefender", "color": "#FF6B6B", "danger": "high",
     "dir": "1 (可选)彻底关闭WinDefender", "desc": "彻底关闭 Windows Defender（不可逆，务必先关实时保护与篡改防护）",
     "readme": "方法与注意.txt",
     "entries": [("一键关闭 Defender", "关闭WinDefender.bat", "bat")]},
    {"key": "o2", "name": "电源与 CPU 优化", "color": "#00C896", "danger": "medium",
     "dir": "2 电源与CPU优化", "desc": "Neon 电源计划 / 电源与 CPU 注册表优化 / 异构大小核优化",
     "readme": "如需手动导入.txt",
     "entries": [("自动导入电源计划", "电源计划自动导入.bat", "bat"),
                 ("导入电源/CPU 注册表", "power.reg", "reg")]},
    {"key": "o3", "name": "设备管理", "color": "#3B82F6", "danger": "medium",
     "dir": "3 设备管理", "desc": "清理未使用设备（DeviceCleanup）与打开设备管理器",
     "readme": "方法.txt",
     "entries": [("清理设备(DeviceCleanup)", "DeviceCleanup.exe", "exe"),
                 ("打开设备管理器", "设备管理器.lnk", "lnk")]},
    {"key": "o6", "name": "游戏性能优化", "color": "#00C896", "danger": "medium",
     "dir": "6 游戏性能优化", "desc": "游戏性能注册表 / 关闭 Gamebar / 黑屏修复 / N 卡高频 / DesktopHeap",
     "readme": "注意.txt",
     "entries": [("导入游戏优化注册表", "gameReg.reg", "reg"),
                 ("禁用 Gamebar(RegOwnershipEx)", "禁用Win自带Gamebar/RegOwnershipEx.exe", "exe")]},
    {"key": "o7", "name": "键鼠优化", "color": "#00C896", "danger": "low",
     "dir": "7 键鼠优化", "desc": "键鼠响应注册表 / USB 轮询率 / FilterKeys 开关",
     "readme": "注意.txt",
     "entries": [("导入鼠标注册表", "mouse.reg", "reg"),
                 ("导入键盘注册表", "keyboard.reg", "reg"),
                 ("USB 轮询率", "USBPollRate.reg", "reg")]},
    {"key": "o8", "name": "服务与更新管理", "color": "#FF6B6B", "danger": "high",
     "dir": "8 服务与更新管理", "desc": "关闭 / 开启 Windows 更新，一键禁用无用系统服务",
     "readme": "关闭无用服务.txt",
     "entries": [("关闭 Windows 更新", "关闭Win更新.cmd", "cmd"),
                 ("开启 Windows 更新", "开启Win更新.cmd", "cmd"),
                 ("一键关闭无用服务", "关闭无用服务.ps1", "ps1")]},
    {"key": "o9", "name": "内存 / 硬盘 / 网络优化", "color": "#00C896", "danger": "medium",
     "dir": "9 内存硬盘网络优化", "desc": "内存/硬盘/网络一键优化（PS 脚本）与注册表导入",
     "readme": "内存硬盘优化.txt",
     "entries": [("内存硬盘一键优化", "内存硬盘优化.ps1", "ps1"),
                 ("网络延迟一键优化", "网络延迟优化.ps1", "ps1"),
                 ("导入内存硬盘注册表", "memorymanage.reg", "reg")]},
    {"key": "o10", "name": "中断机制与延迟优化", "color": "#FF6B6B", "danger": "high",
     "dir": "10 中断机制与延迟优化", "desc": "关闭 HPET / USB 中断仲裁 / 信号中断亲和（进阶操作，先读说明）",
     "readme": "关HPET+延迟优化.txt",
     "entries": [("关闭 HPET 延迟优化", "关闭HPET+延迟优化.bat", "bat"),
                 ("USB 中断仲裁(intMOD)", "(可选进阶)关闭USB中断仲裁/intMOD.cmd", "cmd"),
                 ("信号中断亲和(MSI Utility)", "信号中断与亲和/MSI Utility V3.exe", "exe")]},
    {"key": "o11", "name": "应用优先级", "color": "#00C896", "danger": "medium",
     "dir": "11 应用优先级", "desc": "通过注册表设置进程优先级 / CPU 亲和性",
     "readme": "格式.txt",
     "entries": [("导入优先级注册表", "注册表优先级.reg", "reg")]},
]
OPT_BY_KEY = {it["key"]: it for it in OPT_ITEMS}

# 危险等级显示配置（GUI 徽标 + 确认提示）
DANGER_LABELS = {"low": "低危", "medium": "中危", "high": "高危"}
DANGER_COLORS = {"low": "#00C896", "medium": "#F59E0B", "high": "#FF6B6B"}


def opt_item_dir(item):
    """优化项目录绝对路径"""
    return os.path.join(OPT_BASE, item["dir"])


def opt_open_dir(log, item):
    """在资源管理器中打开优化项目录"""
    d = opt_item_dir(item)
    if not os.path.isdir(d):
        log("error", f"[系统优化] 目录不存在: {d}")
        return
    os.startfile(d)
    log("info", f"[系统优化] 已打开目录：{item['name']}")


def opt_open_readme(log, item):
    """用记事本打开优化项说明文档"""
    p = os.path.join(opt_item_dir(item), item["readme"])
    if not os.path.isfile(p):
        log("error", f"[系统优化] 说明文档不存在: {p}")
        return
    os.startfile(p)
    log("info", f"[系统优化] 已打开说明：{item['name']}")


def opt_execute(log, item, label, fname, kind):
    """执行优化项入口文件（reg / bat / cmd / ps1 / exe / lnk）"""
    p = os.path.join(opt_item_dir(item), fname)
    if not os.path.exists(p):
        log("error", f"[系统优化] 文件不存在: {p}")
        return
    try:
        if kind == "reg":
            log("info", f"[系统优化] 导入注册表：{item['name']} → {fname}")
            result = subprocess.run(["reg", "import", p],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                log("success", f"  ✓ 注册表导入成功：{fname}")
            else:
                log("error", f"  注册表导入失败：{result.stderr or result.stdout}")
        elif kind in ("bat", "cmd"):
            log("warning", f"[系统优化] 执行脚本：{fname}（如弹窗请按说明操作）")
            subprocess.Popen(f'"{p}"', shell=True, cwd=os.path.dirname(p))
            log("info", f"  已在独立窗口启动：{fname}")
        elif kind == "ps1":
            log("warning", f"[系统优化] 执行 PowerShell 脚本：{fname}（请按脚本内提示操作）")
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", p],
                cwd=os.path.dirname(p),
            )
            log("info", f"  已在独立窗口启动：{fname}")
        elif kind in ("exe", "lnk"):
            log("info", f"[系统优化] 启动程序：{fname}")
            os.startfile(p)
        else:
            log("warning", f"[系统优化] 未知类型：{fname}")
    except Exception as e:
        log("error", f"[系统优化] 执行失败 {fname}: {e}")

# ────────────── 滚动容器（视图通用） ──────────────
class ScrollArea(tk.Frame):
    """滚轮按指针命中测试生效，替代旧版 bind_all 抢占全局滚轮的写法"""
    _instances = []

    def __init__(self, parent, bg=BG, inner_bg=BG, padx=0, pady=0):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical",
                                       command=self.canvas.yview,
                                       style="Slim.Vertical.TScrollbar")
        self.inner = tk.Frame(self.canvas, bg=inner_bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(padx, 2), pady=pady)
        self.scrollbar.pack(side="right", fill="y", pady=pady)
        self.inner.bind("<Configure>", self._on_inner, add="+")
        self.canvas.bind("<Configure>", self._on_canvas, add="+")
        ScrollArea._instances.append(self)

    def _on_inner(self, event=None):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))
            self._sync_bar()
        except Exception:
            pass

    def _sync_bar(self):
        """内容不满一屏时隐藏滚动条，避免无意义的轨道噪声"""
        try:
            region = self.canvas.bbox("all")
            need = region and region[3] > self.canvas.winfo_height() + 2
            if need and not self.scrollbar.winfo_manager():
                self.scrollbar.pack(side="right", fill="y")
            elif not need and self.scrollbar.winfo_manager():
                self.scrollbar.pack_forget()
        except Exception:
            pass

    def _on_canvas(self, event=None):
        try:
            self.canvas.itemconfigure(self._win, width=max(1, event.width))
            self._sync_bar()
        except Exception:
            pass

    def contains_pointer(self, x_root, y_root):
        try:
            w = self.canvas.winfo_containing(x_root, y_root)
        except Exception:
            return False
        while w is not None:
            if w is self:
                return True
            w = getattr(w, "master", None)
        return False

    def wheel(self, event):
        if not self.contains_pointer(event.x_root, event.y_root):
            return False
        step = -1 if getattr(event, "delta", 0) > 0 else 1
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        try:
            self.canvas.yview_scroll(step * 3, "units")
        except Exception:
            pass
        return True

    def scroll_home(self):
        try:
            self.canvas.yview_moveto(0)
        except Exception:
            pass


# ────────────── GUI 应用程序 ──────────────
class WinSweepApp:
    def __init__(self):
        # 先确保管理员权限
        run_as_admin()

        self.settings = load_settings()

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} — {APP_TAGLINE}")
        self.root.configure(bg=BG)

        self.font_scale = float(self.settings.get("font_scale", 1.0) or 1.0)
        self.ui_family = resolve_family(UI_FAMILY_CANDIDATES)
        self.mono_family = resolve_family(MONO_FAMILY_CANDIDATES)
        build_fonts(self.root, self.font_scale, self.ui_family, self.mono_family)

        self._size_to_screen()
        self._set_icon()

        # ── 运行状态 ──
        self.queue = Queue()
        self.busy = False
        self.action_buttons = []
        self.nav_items = {}
        self.views = {}
        self.current_view = "overview"
        self._task_started = None
        self._task_label = ""
        self._indeterminate = False
        self._marquee_id = None
        self._freed_bytes = 0
        self._session_freed = 0
        self._task_count = 0
        self._disk_ticks = 0

        # ── 日志状态 ──
        self.records = []
        self.log_filter = "all"
        self.log_search = ""
        self.auto_var = tk.BooleanVar(value=bool(self.settings.get("autoscroll", True)))
        self.autoscroll = self.auto_var.get()
        self._pending_jump = False
        self.level_pills = {}
        self.counters = {k: 0 for k in LEVEL_ORDER}

        self._setup_style()
        self._build_shell()
        self._build_views()
        self._build_shortcuts()

        start_view = self.settings.get("view")
        self.show_view(start_view if start_view in self.views else "overview")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        # 深色标题栏（需等窗口句柄创建完成）
        self.root.after(0, lambda: apply_dark_titlebar(self.root))
        self.root.bind("<Map>", lambda e: apply_dark_titlebar(self.root), add="+")
        self.root.after(60, self._apply_saved_sash)
        self.root.after(QUEUE_POLL_MS, self.process_queue)
        self.root.after(150, self._on_boot)
        self.root.after(TICK_MS, self._tick)

    def run(self):
        self.root.mainloop()

    # ────────────── 外观与布局基础 ──────────────
    def _size_to_screen(self):
        """恢复上次窗口尺寸；首次按屏幕比例给一个稳妥的初始尺寸（保底不被裁切）"""
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        minw, minh = min(880, int(sw * 0.86)), min(600, int(sh * 0.80))
        self.root.minsize(minw, minh)
        geo = self.settings.get("geometry")
        if not geo:
            w = min(1120, max(minw, int(sw * 0.72)))
            h = min(860, max(minh, int(sh * 0.80)))
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2 - 10)
            geo = f"{w}x{h}+{x}+{y}"
        try:
            self.root.geometry(geo)
        except Exception:
            pass

    def _set_icon(self):
        """优先 icon.ico；否则用内置逐像素扫帚图标（零外部依赖）"""
        ico = os.path.join(APP_DIR, "icon.ico")
        if os.path.exists(ico):
            try:
                self.root.iconbitmap(ico)
                return
            except Exception:
                pass
        try:
            self.root.iconphoto(True, self._draw_icon())
        except Exception:
            pass

    def _draw_icon(self):
        """逐像素绘制 128×128 扫帚图标（不依赖任何第三方库 / 外部文件）"""
        S = 128
        img = tk.PhotoImage(width=S, height=S)
        BG_C, HANDLE, BRUSH, DUST = "#161B26", "#E8ECF4", ACCENT, "#8B949E"

        def in_seg(px, py, x0, y0, x1, y1, half):
            vx, vy = x1 - x0, y1 - y0
            l2 = vx * vx + vy * vy
            if l2 == 0:
                dx, dy = px - x0, py - y0
            else:
                t = max(0.0, min(1.0, ((px - x0) * vx + (py - y0) * vy) / l2))
                dx, dy = px - (x0 + t * vx), py - (y0 + t * vy)
            return dx * dx + dy * dy <= half * half

        def in_ellipse(px, py, cx, cy, rx, ry):
            dx, dy = px - cx, py - cy
            return (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry) <= 1.0

        def in_circle(px, py, cx, cy, r):
            return (px - cx) ** 2 + (py - cy) ** 2 <= r * r

        brush_x = (66, 72, 78, 84, 90)
        dust = ((18, 16), (12, 26), (46, 10), (24, 40))
        for y in range(S):
            row = []
            for x in range(S):
                px, py = x + 0.5, y + 0.5
                c = BG_C
                if in_seg(px, py, 30, 18, 70, 60, 5) or in_circle(px, py, 30, 18, 6):
                    c = HANDLE
                elif in_ellipse(px, py, 78, 74, 24, 12):
                    c = BRUSH
                elif py > 84 and any(abs(px - bx) <= 1.6 for bx in brush_x):
                    c = BRUSH
                elif any(in_circle(px, py, cx, cy, 2) for cx, cy in dust):
                    c = DUST
                row.append(c)
            # Tk 在 Windows 上 put() 只认单色，需按颜色段用 to= 分块填充
            i = 0
            while i < S:
                c = row[i]
                j = i + 1
                while j < S and row[j] == c:
                    j += 1
                img.put(c, to=(i, y, j, y + 1))
                i = j
        return img

    def _setup_style(self):
        """ttk 主题：进度条配色/厚度 + 无箭头细滚动条"""
        style = ttk.Style(self.root)
        for theme in ("clam", "alt", "default"):
            try:
                style.theme_use(theme)
                break
            except Exception:
                continue
        style.configure(
            "TProgressbar", background=ACCENT, troughcolor=BG3,
            bordercolor=BG1, lightcolor=ACCENT, darkcolor=ACCENT,
            thickness=PROGRESSBAR_THICKNESS, padding=0,
        )
        style.configure(
            "Run.TProgressbar", background=CYAN, troughcolor=BG3,
            bordercolor=BG1, lightcolor=CYAN, darkcolor=CYAN,
            thickness=PROGRESSBAR_THICKNESS, padding=0,
        )
        style.configure(
            "Slim.Vertical.TScrollbar",
            background=BG3, troughcolor=BG1, bordercolor=BG1,
            lightcolor=BG3, darkcolor=BG3, arrowcolor=BG1,
            width=9, bordersize=0, relief="flat",
        )
        style.map("Slim.Vertical.TScrollbar",
                  background=[("pressed", FG_MUTE), ("active", BG4)])
        try:
            style.layout("Slim.Vertical.TScrollbar", [
                ("Vertical.Scrollbar.trough", {
                    "children": [("Vertical.Scrollbar.thumb",
                                  {"expand": "true", "sticky": "nswe"})],
                    "sticky": "ns"})])
        except Exception:
            pass

    def _build_shell(self):
        """三段式 grid：头部 / 主体(可拖拽分栏) / 状态栏 —— 彻底避免旧版底部控件被挤出窗口"""
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=1)

        self.header = tk.Frame(self.root, bg=BG1)
        self.header.grid(row=0, column=0, sticky="ew")
        tk.Frame(self.root, bg=LINE, height=1).grid(row=1, column=0, sticky="ew")

        self.paned = ttk.Panedwindow(self.root, orient="vertical")
        self.paned.grid(row=2, column=0, sticky="nsew")

        self.body = tk.Frame(self.paned, bg=BG)
        self.log_panel = tk.Frame(self.paned, bg=BG1)
        self.paned.add(self.body, weight=1)
        self.paned.add(self.log_panel, weight=0)
        # 两分区各自保底高度：避免日志 Text 的需求高度把主体挤成 0（旧版同类问题的根因）
        for pane, ms in ((self.body, 280), (self.log_panel, LOG_MIN_H)):
            try:
                self.paned.paneconfigure(pane, minsize=ms)
            except Exception:
                pass

        tk.Frame(self.root, bg=LINE, height=1).grid(row=3, column=0, sticky="ew")
        self.status = tk.Frame(self.root, bg=BG1)
        self.status.grid(row=4, column=0, sticky="ew")

        self._build_header()
        self._build_body()
        self._build_log_panel()
        self._build_status()

    # ────────────── 头部：品牌 + 磁盘信息条 ──────────────
    def _build_header(self):
        h = self.header
        row1 = tk.Frame(h, bg=BG1)
        row1.pack(fill="x", padx=14, pady=(10, 2))

        brand = tk.Frame(row1, bg=BG1)
        brand.pack(side="left")
        tk.Label(brand, text="◈", fg=ACCENT, bg=BG1, font=FONT["h1"]).pack(side="left", padx=(0, 6))
        tk.Label(brand, text=APP_NAME, fg=ACCENT, bg=BG1, font=FONT["brand"]).pack(side="left")
        ver = chip(row1, f"v{APP_VERSION}", fg=FG_DIM, bg=BG3, border=LINE, font=FONT["tiny"], padx=6, pady=2)
        ver.pack(side="left", padx=(8, 0), pady=(3, 0))
        tk.Label(row1, text=APP_TAGLINE, fg=FG_MUTE, bg=BG1, font=FONT["small"]).pack(side="left", padx=(10, 0))

        right = tk.Frame(row1, bg=BG1)
        right.pack(side="right")
        for key, tip in (("F5 刷新", "刷新磁盘与概览信息"),
                         ("Alt+1~6", "切换左侧视图"),
                         ("Ctrl+L", "清空日志"),
                         ("Ctrl+F", "搜索日志")):
            c = chip(right, key, fg=FG_MUTE, bg=BG3, border=LINE, font=FONT["tiny"], padx=7, pady=2)
            c.pack(side="left", padx=3, pady=(2, 0))
            ToolTip(c, tip)
            ToolTip(c.label, tip)
        self.admin_pill = chip(right, "● 管理员", fg=ACCENT, bg=BG3, border=LINE, font=FONT["small"], padx=9, pady=2)
        self.admin_pill.pack(side="left", padx=(10, 2), pady=(1, 0))
        self.clock_label = tk.Label(right, text="", fg=FG_MUTE, bg=BG1, font=FONT["small"])
        self.clock_label.pack(side="left", padx=(6, 0))

        # 第二行：磁盘信息条（胶囊条随窗口伸缩）
        row2 = tk.Frame(h, bg=BG1)
        row2.pack(fill="x", padx=14, pady=(2, 10))
        self.drive_chip = chip(row2, "C:", fg=FG, bg=BG3, border=LINE, font=FONT["small_b"], padx=9, pady=3)
        self.drive_chip.pack(side="left")
        self.disk_free_label = tk.Label(row2, text="可用 —", fg=ACCENT, bg=BG1, font=FONT["ui_b"])
        self.disk_free_label.pack(side="left", padx=(10, 0))
        self.disk_total_label = tk.Label(row2, text="/ —", fg=FG_MUTE, bg=BG1, font=FONT["small"])
        self.disk_total_label.pack(side="left", padx=(5, 0))

        self.disk_bar = tk.Canvas(row2, height=DISK_BAR_H, bg=BG1, highlightthickness=0, bd=0)
        self.disk_bar.pack(side="left", fill="x", expand=True, padx=(14, 10))
        self.disk_bar.bind("<Configure>", lambda e: self._draw_disk_bar())
        ToolTip(self.disk_bar, "系统盘使用率：< 80% 绿 / < 92% 黄 / ≥ 92% 红")

        self.disk_pct_label = tk.Label(row2, text="—", fg=FG_DIM, bg=BG1, font=FONT["small"])
        self.disk_pct_label.pack(side="left")
        self.oldos_chip = chip(row2, "⚠ Windows.old", fg=AMBER, bg=WARN_BG, border="#3A3320", font=FONT["tiny"], padx=7, pady=2)
        self.oldos_chip.pack(side="left", padx=(10, 0))
        self.oldos_chip.pack_forget()
        self.last_clean_chip = chip(row2, "上次预装清理 —", fg=FG_MUTE, bg=BG3, border=LINE, font=FONT["tiny"], padx=7, pady=2)
        self.last_clean_chip.pack(side="left", padx=(8, 0))
        self.last_clean_chip.pack_forget()
        refresh = make_button(row2, "刷新", lambda: self.refresh_info(True), style="ghost", size="sm",
                              color=FG_DIM, tooltip="重新读取磁盘与概览信息（F5）")
        refresh.pack(side="left", padx=(10, 0))

    def _draw_disk_bar(self, usage=None):
        """磁盘胶囊条：宽度跟随窗口，两端圆头"""
        c = self.disk_bar
        c.delete("all")
        w = max(40, c.winfo_width())
        h = DISK_BAR_H
        usage = usage or get_disk_usage()
        frac = (usage["pct_used"] / 100.0) if usage else 0.0
        col = usage_color(usage["pct_used"]) if usage else FG_MUTE
        r = h / 2.0
        c.create_rectangle(r, 0, w - r, h, fill=BG3, outline="")
        c.create_oval(0, 0, h, h, fill=BG3, outline="")
        c.create_oval(w - h, 0, w, h, fill=BG3, outline="")
        fill_w = max(h, int(w * min(max(frac, 0.0), 1.0)))
        c.create_rectangle(r, 0, fill_w - r, h, fill=col, outline="")
        c.create_oval(0, 0, h, h, fill=col, outline="")
        if fill_w > h:
            c.create_oval(fill_w - h, 0, fill_w, h, fill=col, outline="")
        # 80% / 92% 阈值刻度
        for th in (0.80, 0.92):
            x = int(w * th)
            c.create_line(x, 1, x, h - 1, fill=BG, width=1)

    # ────────────── 主体：侧边导航 + 视图容器 ──────────────
    def _build_body(self):
        self.body.grid_columnconfigure(2, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

        nav_area = ScrollArea(self.body, bg=BG1, inner_bg=BG1)
        nav_area.grid(row=0, column=0, sticky="ns")
        nav_area.canvas.configure(width=NAV_WIDTH)
        nav = nav_area.inner
        self.nav_area = nav_area
        tk.Frame(self.body, bg=LINE, width=1).grid(row=0, column=1, sticky="ns")

        self.view_host = tk.Frame(self.body, bg=BG)
        self.view_host.grid(row=0, column=2, sticky="nsew")
        self.view_host.grid_rowconfigure(0, weight=1)
        self.view_host.grid_columnconfigure(0, weight=1)

        self.nav_title_lbl = tk.Label(nav, text="功能导航", fg=FG_MUTE, bg=BG1, font=FONT["tiny"])
        self.nav_title_lbl.pack(anchor="w", padx=16, pady=(14, 4))
        self.nav_subs = []
        self._nav_compact = None
        nav_area.canvas.bind("<Configure>", lambda e: self._apply_nav_density(e.height), add="+")
        for idx, (key, icon, name, _sub, nav_sub) in enumerate(VIEWS, 1):
            item = tk.Frame(nav, bg=BG1, cursor="hand2")
            item.pack(fill="x", padx=8, pady=1)
            stripe = tk.Frame(item, bg=BG1, width=3)
            stripe.pack(side="left", fill="y", padx=(4, 0))
            textbox = tk.Frame(item, bg=BG1)
            textbox.pack(side="left", fill="x", expand=True, padx=(8, 8), pady=5)
            top = tk.Frame(textbox, bg=BG1)
            top.pack(fill="x")
            tk.Label(top, text=icon, fg=FG_DIM, bg=BG1, font=FONT["ui_b"]).pack(side="left", padx=(0, 7))
            tk.Label(top, text=name, fg=FG_DIM, bg=BG1, font=FONT["ui_b"]).pack(side="left")
            tk.Label(top, text=f"Alt+{idx}", fg="#3F4859", bg=BG1, font=FONT["tiny"]).pack(side="right")
            sub_lbl = tk.Label(textbox, text=nav_sub, fg=FG_MUTE, bg=BG1, font=FONT["tiny"], anchor="w")
            sub_lbl.pack(fill="x", padx=(21, 0), pady=(1, 0))
            self.nav_subs.append(sub_lbl)
            self.nav_items[key] = item
            bindable = [item, stripe, textbox]
            for c in textbox.winfo_children():
                bindable.append(c)
                bindable.extend(c.winfo_children())
            for w in bindable:
                w.bind("<Button-1>", lambda e, k=key: self.show_view(k), add="+")
                w.bind("<Enter>", lambda e, i=item: self._nav_hover(i, True), add="+")
                w.bind("<Leave>", lambda e, i=item: self._nav_hover(i, False), add="+")

        # 会话统计改到底部状态栏常驻，避免导航列在矮窗口下被裁切

    def _apply_nav_density(self, height):
        """窗口不高时收起导航副标题，保证 6 个入口始终可见（旧版小屏丢控件的同类问题）"""
        compact = height < 470
        if compact == self._nav_compact:
            return
        self._nav_compact = compact
        try:
            if compact:
                self.nav_title_lbl.pack_forget()
            else:
                self.nav_title_lbl.pack(anchor="w", padx=16, pady=(14, 4), before=self.nav_items[VIEWS[0][0]])
        except Exception:
            pass
        for lbl in self.nav_subs:
            try:
                if compact:
                    lbl.pack_forget()
                else:
                    lbl.pack(fill="x", padx=(21, 0), pady=(1, 0))
            except Exception:
                pass

    def _nav_hover(self, item, on):
        if getattr(self, "current_view_frame", None) is item:
            return
        self._paint_nav(item, BG3 if on else BG1)

    def _paint_nav(self, item, bg):
        try:
            item.configure(bg=bg)
            children = [item]
            while children:
                w = children.pop()
                for c in w.winfo_children():
                    children.append(c)
                    try:
                        if str(c.cget("bg")):
                            c.configure(bg=bg)
                    except Exception:
                        pass
        except Exception:
            pass

    def show_view(self, key):
        view = self.views.get(key)
        if view is None:
            return
        for k, v in self.views.items():
            try:
                if k == key:
                    v.grid(row=0, column=0, sticky="nsew")   # grid_remove 后必须重新 grid
                    v.tkraise()
                else:
                    v.grid_remove()
            except Exception:
                pass
        self.current_view = key
        for k, item in self.nav_items.items():
            active = (k == key)
            self._paint_nav(item, BG2 if active else BG1)
            self._nav_active_style(item, active)
        self.current_view_frame = self.nav_items.get(key)
        if key == "overview":
            self.refresh_info(False)

    def _nav_active_style(self, item, active):
        try:
            stripe = item.winfo_children()[0]
            stripe.configure(bg=ACCENT if active else BG1)
            for w in item.winfo_children()[1:]:
                self._recolor(w, FG if active else FG_DIM, ACCENT if active else FG_DIM)
        except Exception:
            pass

    def _recolor(self, w, fg, icon_fg):
        try:
            txt = str(w.cget("text"))
            if txt in ("", None):
                pass
            for c in w.winfo_children():
                self._recolor(c, fg, icon_fg)
            if isinstance(w, tk.Label):
                if len(txt) <= 2:
                    w.configure(fg=icon_fg)
                elif txt.startswith("Alt+"):
                    w.configure(fg="#3F4859")
                else:
                    w.configure(fg=fg)
        except Exception:
            pass

    # ────────────── 日志面板 ──────────────
    def _build_log_panel(self):
        panel = self.log_panel
        head = tk.Frame(panel, bg=BG1)
        head.pack(fill="x", padx=12, pady=(8, 2))
        tk.Label(head, text="▍", fg=ACCENT2, bg=BG1, font=FONT["h2"]).pack(side="left")
        tk.Label(head, text="执行日志", fg=FG, bg=BG1, font=FONT["ui_b"]).pack(side="left", padx=(2, 8))
        self.log_count_label = tk.Label(head, text="", fg=FG_MUTE, bg=BG1, font=FONT["tiny"])
        self.log_count_label.pack(side="left")

        self.jump_btn = make_button(head, "⤓ 跳到最新", lambda: self._jump_latest(), size="sm",
                                    style="soft", color=ACCENT2, tooltip="恢复自动滚动并滚到最新一行")
        self.btn_collapse = make_button(head, "收起日志", self._toggle_log, size="sm", style="ghost",
                                        color=FG_DIM, tooltip="折叠 / 展开日志区（Ctrl+J）")
        for b in (self.btn_collapse, make_button(head, "保存", self.save_log, size="sm", style="ghost",
                                                 color=FG_DIM, tooltip="导出日志到文本文件  Ctrl+S"),
                  make_button(head, "复制", self.copy_log, size="sm", style="ghost",
                              color=FG_DIM, tooltip="复制日志（有选区则只复制选区）  Ctrl+C"),
                  make_button(head, "清空", self.clear_log, size="sm", style="ghost",
                              color=FG_DIM, tooltip="清空日志区  Ctrl+L"), self.jump_btn):
            b.pack(side="right", padx=3)
        self.jump_btn.pack_forget()

        # 第二行：级别过滤 + 搜索 + 自动滚动
        tools = tk.Frame(panel, bg=BG1)
        tools.pack(fill="x", padx=12, pady=(0, 8))
        for lvl in LEVEL_ORDER:
            pill = make_button(tools, LEVEL_LABEL[lvl], lambda l=lvl: self.set_log_filter(l),
                               size="sm", style="ghost", color=FG_MUTE)
            pill.pack(side="left", padx=(0, 4))
            self.level_pills[lvl] = pill
        tk.Frame(tools, bg=LINE, width=1).pack(side="left", fill="y", padx=6, pady=2)

        self.search_var = tk.StringVar()
        box = tk.Frame(tools, bg=BG3, padx=6, pady=3)
        box.pack(side="left", padx=(0, 6))
        tk.Label(box, text="🔍", bg=BG3, fg=FG_MUTE, font=FONT["small"]).pack(side="left")
        entry = tk.Entry(box, textvariable=self.search_var, bg=BG3, fg=FG,
                         insertbackground=FG, relief="flat", bd=0, width=18,
                         font=FONT["small"], highlightthickness=0)
        entry.pack(side="left", padx=4)
        entry.bind("<Return>", lambda e: self._rerender_log())
        entry.bind("<KeyRelease>", lambda e: self._rerender_log())
        entry.bind("<Escape>", lambda e: (self.search_var.set(""), self._rerender_log()))
        self.search_entry = entry
        ToolTip(box, "按关键词过滤日志（Ctrl+F 聚焦）")

        chk = tk.Checkbutton(tools, text="自动滚动", variable=self.auto_var,
                             command=self._set_autoscroll,
                             bg=BG1, fg=FG_DIM, selectcolor=BG3, activebackground=BG1,
                             activeforeground=FG, font=FONT["small"],
                             highlightthickness=0, anchor="w", cursor="hand2")
        chk.pack(side="left")
        self.auto_check = chk
        ToolTip(chk, "关闭后可自由上翻查看历史，日志不再跳回底部")

        tk.Frame(panel, bg=LINE, height=1).pack(fill="x")

        self.log_body = tk.Frame(panel, bg=BG)
        self.log_body.pack(fill="both", expand=True)
        self.output_text = tk.Text(
            self.log_body, bg=BG, fg=FG, insertbackground=FG, wrap="word",
            state=tk.DISABLED, font=FONT["ui"], relief="flat", bd=0,
            highlightthickness=0, padx=12, pady=8, height=8,
            spacing1=1, spacing2=0, spacing3=2,
        )
        self.log_scroll = ttk.Scrollbar(self.log_body, orient="vertical",
                                        command=self.output_text.yview,
                                        style="Slim.Vertical.TScrollbar")
        self._at_bottom = True
        self._ignore_scroll = False
        self.output_text.configure(yscrollcommand=self._yscroll_cb)
        self.output_text.pack(side="left", fill="both", expand=True)
        self.log_scroll.pack(side="right", fill="y")
        self.output_text.tag_configure("sel", background="#22406B", foreground=FG)
        for lvl, (_code, fg, bgrow, bold) in LEVEL_STYLE.items():
            self.output_text.tag_configure(lvl, foreground=fg,
                                           font=FONT["ui_b"] if bold else FONT["ui"])
            self.output_text.tag_configure(lvl + "_bg", background=bgrow or BG)
            self.output_text.tag_configure("code_" + lvl, foreground=fg, font=FONT["mono_s"])
        self.output_text.tag_configure("ts", foreground="#4E5766", font=FONT["mono_s"])
        self.output_text.tag_configure("section", foreground=ACCENT2, font=FONT["ui_b"],
                                       background=SECTION_BG, spacing1=8, spacing3=3)

        # 让日志区滚轮保持原生行为（Text 自带 class 绑定），此处只补一个中键复制禁用
        self._log_collapsed = False
        self._log_h = int(self.settings.get("log_height", 0) or 0)   # 0 = 首次按窗口高度比例

    def _set_autoscroll(self):
        self.autoscroll = bool(self.auto_var.get())
        if self.autoscroll:
            self._jump_latest()

    # ────────────── 状态栏 ──────────────
    def _build_status(self):
        s = self.status
        s.grid_columnconfigure(1, weight=1)
        self.spinner = Spinner(s, size=14, bg=BG1)
        self.spinner.grid(row=0, column=0, padx=(14, 6), pady=7)
        self.spinner.stop()

        self.status_label = tk.Label(s, text="就绪", fg=FG_DIM, bg=BG1, font=FONT["small"], anchor="w")
        self.status_label.grid(row=0, column=1, sticky="w")
        sess = tk.Frame(s, bg=BG1)
        sess.grid(row=0, column=2, padx=(0, 10))
        self.session_freed_label = tk.Label(sess, text="本次会话 释放 0 B", fg=FG_MUTE, bg=BG1,
                                            font=FONT["tiny"])
        self.session_freed_label.pack(side="left")
        self.session_task_label = tk.Label(sess, text="· 0 次任务", fg="#3F4859", bg=BG1,
                                           font=FONT["tiny"])
        self.session_task_label.pack(side="left", padx=(5, 0))
        ToolTip(sess, "本次启动以来的累计释放空间与任务次数（仅当前会话）")
        self.freed_label = tk.Label(s, text="", fg=ACCENT, bg=BG1, font=FONT["small_b"])
        self.freed_label.grid(row=0, column=3, padx=8)
        self.elapsed_label = tk.Label(s, text="", fg=FG_MUTE, bg=BG1, font=FONT["mono_s"])
        self.elapsed_label.grid(row=0, column=4, padx=(0, 8))
        self.progress = ttk.Progressbar(s, style="TProgressbar", length=170, mode="determinate")
        self.progress.grid(row=0, column=5, padx=(0, 6))
        self.progress_label = tk.Label(s, text="", width=5, anchor="e",
                                       fg=FG_MUTE, bg=BG1, font=FONT["mono_s"])
        self.progress_label.grid(row=0, column=6, padx=(0, 14))

    def _apply_saved_sash(self):
        try:
            if not self._log_h:
                total = self.paned.winfo_height() or 640
                self._log_h = int(max(170, min(320, total * 0.32)))
            self._apply_log_height(self._log_h)
        except Exception:
            pass

    def _apply_log_height(self, h):
        def _do():
            try:
                total = self.paned.winfo_height()
            except Exception:
                total = 0
            if total < 220:                        # 等窗口真正布局完成后再设分隔条
                self.root.after(80, _do)
                return
            pos = max(140, total - int(h) - 8)
            for idx in (0, 1):                     # 兼容不同 Tk 版本的 sash 编号语义
                try:
                    self.paned.sashpos(idx, pos)
                except Exception:
                    continue
            self._log_h = int(h)
        self.root.after(0, _do)

    def _current_log_height(self):
        """从当前分隔条位置反推日志区高度，用于下次启动恢复"""
        try:
            total = self.paned.winfo_height()
            pos = self.paned.sashpos(0)
            h = total - pos - 8
            if h >= LOG_MIN_H:
                return int(h)
        except Exception:
            pass
        return int(self._log_h)

    def _toggle_log(self):
        self._log_collapsed = not self._log_collapsed
        if self._log_collapsed:
            self._log_h = max(LOG_MIN_H, self._log_h)
            self.log_body.pack_forget()
            self._apply_log_height(30)
            self.btn_collapse.configure(text="展开日志")
        else:
            self.log_body.pack(fill="both", expand=True)
            self._apply_log_height(self._log_h)
            self.btn_collapse.configure(text="收起日志")
        self._rerender_log()


    # ────────────── 快捷键 ──────────────
    def _build_shortcuts(self):
        r = self.root
        r.bind("<F5>", lambda e: self.refresh_info(True))
        r.bind("<Control-r>", lambda e: self.refresh_info(True))
        r.bind("<Control-l>", lambda e: self.clear_log())
        r.bind("<Control-c>", lambda e: self.copy_log())
        r.bind("<Control-s>", lambda e: self.save_log())
        r.bind("<Control-j>", lambda e: self._toggle_log())
        r.bind("<Control-f>", lambda e: self._focus_search())
        r.bind("<Control-plus>", lambda e: self._change_scale(0.1))
        r.bind("<Control-equal>", lambda e: self._change_scale(0.1))
        r.bind("<Control-minus>", lambda e: self._change_scale(-0.1))
        r.bind("<Escape>", lambda e: self._on_escape())
        for i, (key, _icon, _name, _sub, _nav) in enumerate(VIEWS, 1):
            r.bind(f"<Alt-{i}>", lambda e, k=key: self.show_view(k))
        # 滚轮：只在指针所在的滚动区内生效（替代旧版 bind_all 全局抢占）
        r.bind_all("<MouseWheel>", self._on_wheel_all, add="+")
        r.bind_all("<Button-4>", self._on_wheel_all, add="+")
        r.bind_all("<Button-5>", self._on_wheel_all, add="+")

    def _on_wheel_all(self, event):
        for area in list(ScrollArea._instances):
            try:
                if area.winfo_exists() and area.wheel(event):
                    return "break"
            except Exception:
                continue
        return None

    def _focus_search(self):
        if self._log_collapsed:
            self._toggle_log()
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)
        return "break"

    def _on_escape(self):
        if self.search_var.get():
            self.search_var.set("")
            self._rerender_log()
        else:
            self.root.focus_set()

    def _change_scale(self, delta):
        self.font_scale = min(1.45, max(0.85, round(self.font_scale + delta, 2)))
        build_fonts(self.root, self.font_scale, self.ui_family, self.mono_family)
        self._draw_disk_bar()
        self._rerender_log()
        self.log("info", f"界面字号已调整为 {int(self.font_scale * 100)}%（Ctrl+= 放大 / Ctrl+- 缩小）")

    # ────────────── 日志引擎 ──────────────
    def log(self, tag, message):
        """线程安全：日志先入队，由主线程批量取出渲染"""
        self.queue.put((tag if tag in LEVEL_STYLE else "info", message))

    def set_status(self, text, fraction=0.0):
        self.queue.put(("__status__", (text, min(max(float(fraction), 0.0), 1.0))))

    def _bump(self, tag, delta=1):
        self.counters["all"] += delta
        for group, tags in LEVEL_GROUP.items():
            if tag in tags:
                self.counters[group] += delta

    @staticmethod
    def _section_title(msg):
        if "━" not in msg:
            return None
        title = msg.replace("━", "").strip()
        return title

    def _passes(self, rec):
        _ts, tag, msg = rec
        if self.log_filter != "all" and tag not in LEVEL_GROUP.get(self.log_filter, ()):
            return False
        needle = self.log_search.strip().lower()
        if needle and needle not in msg.lower():
            return False
        return True

    def _is_at_bottom(self):
        return bool(getattr(self, "_at_bottom", True))

    def _yscroll_cb(self, first, last):
        """区分“用户上翻”与“程序自动滚到底”，避免新日志到达后不再跟随底部"""
        try:
            self.log_scroll.set(first, last)
        except Exception:
            pass
        if getattr(self, "_ignore_scroll", False):
            return
        try:
            self._at_bottom = float(last) >= 0.999
        except Exception:
            self._at_bottom = True
        if not self._at_bottom and self.autoscroll:
            self._show_jump(True)
        elif self._at_bottom:
            self._show_jump(False)

    def _scroll_to_end(self):
        self._ignore_scroll = True
        try:
            self.output_text.see(tk.END)
            self.output_text.update_idletasks()
        except Exception:
            pass
        finally:
            self._ignore_scroll = False
        self._at_bottom = True
        self._show_jump(False)

    def _render_record(self, rec):
        ts, tag, msg = rec
        code, _fg, _bg, _bold = LEVEL_STYLE.get(tag, LEVEL_STYLE["info"])
        t = self.output_text
        t.configure(state=tk.NORMAL)
        title = self._section_title(msg)
        if title:
            t.insert(tk.END, f"\n  ▎{title}\n", ("section",))
        else:
            t.insert(tk.END, f"[{ts}] ", ("ts", tag + "_bg"))
            t.insert(tk.END, f"{code} ", ("code_" + tag, tag + "_bg"))
            t.insert(tk.END, f"{msg}\n", (tag, tag + "_bg"))
        t.configure(state=tk.DISABLED)
        self._trim_text()

    def _trim_text(self):
        try:
            lines = int(self.output_text.index("end-1c").split(".")[0])
            if lines > MAX_LOG_LINES:
                self.output_text.configure(state=tk.NORMAL)
                self.output_text.delete("1.0", f"{lines - MAX_LOG_LINES // 2}.0")
                self.output_text.configure(state=tk.DISABLED)
        except Exception:
            pass

    def _append_record(self, rec):
        self.records.append(rec)
        if len(self.records) > MAX_LOG_RECORDS:
            del self.records[:len(self.records) - MAX_LOG_RECORDS]
        self._bump(rec[1])
        at_bottom = self._is_at_bottom()
        if self._passes(rec):
            self._render_record(rec)
            if self.autoscroll and at_bottom:
                self._scroll_to_end()
            elif not at_bottom:
                self._show_jump(True)
        self._update_log_meta()

    def _rerender_log(self):
        t = self.output_text
        t.configure(state=tk.NORMAL)
        t.delete("1.0", tk.END)
        t.configure(state=tk.DISABLED)
        shown = [r for r in self.records if self._passes(r)]
        if len(shown) > MAX_LOG_LINES:
            shown = shown[-MAX_LOG_LINES:]
        t.configure(state=tk.NORMAL)
        for rec in shown:
            ts, tag, msg = rec
            code = LEVEL_STYLE.get(tag, LEVEL_STYLE["info"])[0]
            title = self._section_title(msg)
            if title:
                t.insert(tk.END, f"\n  ▎{title}\n", ("section",))
            else:
                t.insert(tk.END, f"[{ts}] ", ("ts", tag + "_bg"))
                t.insert(tk.END, f"{code} ", ("code_" + tag, tag + "_bg"))
                t.insert(tk.END, f"{msg}\n", (tag, tag + "_bg"))
        t.configure(state=tk.DISABLED)
        if self.autoscroll:
            self._scroll_to_end()
        self._update_log_meta(len(shown))

    def _update_log_meta(self, shown_count=None):
        if shown_count is None:
            shown_count = sum(1 for r in self.records if self._passes(r))
        try:
            self.log_count_label.config(
                text=f"{shown_count} / {len(self.records)} 行"
                     + (f"   过滤：{LEVEL_LABEL[self.log_filter]}" if self.log_filter != "all" else ""))
            for lvl, btn in self.level_pills.items():
                n = self.counters[lvl]
                btn.configure(text=f"{LEVEL_LABEL[lvl]}{f' {n}' if n else ''}")
                self._paint_pill(btn, self.log_filter == lvl)
        except Exception:
            pass

    def _paint_pill(self, btn, active):
        try:
            bg, fg = (BG4, FG) if active else (BG1, FG_MUTE)
            btn._ws_base = (bg, fg, lighten(bg, 0.14))
            btn.configure(bg=bg, fg=fg, activebackground=lighten(bg, 0.14))
        except Exception:
            pass

    def _show_jump(self, show):
        try:
            if show and not self._log_collapsed:
                if not self.jump_btn.winfo_manager():
                    self.jump_btn.pack(side="right", padx=3)
            else:
                self.jump_btn.pack_forget()
        except Exception:
            pass

    def _jump_latest(self):
        self.autoscroll = True
        try:
            self.auto_var.set(True)
        except Exception:
            pass
        self._scroll_to_end()
        self._show_jump(False)

    def clear_log(self):
        self.records = []
        self.counters = {k: 0 for k in LEVEL_ORDER}
        self._rerender_log()
        self.log("info", "日志已清空")

    def copy_log(self):
        t = self.output_text
        try:
            if t.tag_ranges("sel"):
                content = t.get("sel.first", "sel.last")
            else:
                content = "\n".join(f"[{ts}] {msg}" for ts, _tag, msg in self.records)
        except Exception:
            content = "\n".join(f"[{ts}] {msg}" for ts, _tag, msg in self.records)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.log("info", f"已复制 {len(content.splitlines())} 行日志到剪贴板")

    def save_log(self):
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            default = os.path.join(LOG_DIR, f"WinSweep_{time.strftime('%Y%m%d_%H%M%S')}.txt")
            path = filedialog.asksaveasfilename(
                parent=self.root, title="保存日志", defaultextension=".txt",
                initialfile=os.path.basename(default), initialdir=LOG_DIR,
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
            if not path:
                return
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"{APP_NAME} v{APP_VERSION} 日志  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                fh.write("=" * 60 + "\n")
                for ts, _tag, msg in self.records:
                    fh.write(f"[{ts}] {msg}\n")
            self.log("success", f"✔ 日志已保存：{path}")
        except Exception as e:
            messagebox.showerror("保存失败", f"无法写入日志文件：\n{e}")

    def set_log_filter(self, lvl):
        self.log_filter = lvl
        self._rerender_log()

    # ────────────── 队列 / 状态 ──────────────
    def process_queue(self):
        """批量取空队列，一次刷完，减少 UI 抖动"""
        batch = []
        try:
            while len(batch) < 300:
                batch.append(self.queue.get_nowait())
        except Empty:
            pass
        for tag, data in batch:
            if tag == "__status__":
                self._apply_status(*data)
            elif tag == "__freed__":
                self._apply_freed(data)
            elif tag == "__taskend__":
                self._end_task_ui(*data)
            elif tag == "__done__":
                self._apply_done(data)
            else:
                self._append_record((time.strftime("%H:%M:%S"), tag, str(data)))
        self.root.after(QUEUE_POLL_MS, self.process_queue)

    def _apply_status(self, text, fraction):
        self.status_label.config(text=text, fg=FG if fraction < 1 else ACCENT)
        if self._indeterminate:
            self.progress_label.config(text="···", fg=CYAN)
            return
        self.progress["value"] = fraction * 100
        pct = int(fraction * 100)
        self.progress_label.config(text=f"{pct}%" if pct > 0 else "",
                                   fg=ACCENT if fraction >= 1 else FG_MUTE)

    def _apply_freed(self, freed):
        try:
            freed = int(freed)
        except Exception:
            freed = 0
        self._freed_bytes = max(freed, 0)
        if self._freed_bytes > 0:
            self.freed_label.config(text=f"↑ 释放 {format_size(self._freed_bytes)}")
            self._session_freed += self._freed_bytes
        else:
            self.freed_label.config(text="")

    def _apply_done(self, text):
        self.status_label.config(text=text, fg=ACCENT)
        self._set_indeterminate(False)
        if not self.busy:
            self.spinner.stop()

    def _set_indeterminate(self, on):
        self._indeterminate = bool(on)
        try:
            if on:
                self.progress.configure(mode="indeterminate", style="Run.TProgressbar")
                if self._marquee_id is None:
                    self._marquee()
            else:
                if self._marquee_id is not None:
                    self.root.after_cancel(self._marquee_id)
                    self._marquee_id = None
                self.progress.configure(mode="determinate", style="TProgressbar")
                self.progress["value"] = 0
        except Exception:
            pass

    def _marquee(self):
        if not self._indeterminate:
            self._marquee_id = None
            return
        try:
            self.progress.step(2.5)
        except Exception:
            pass
        self._marquee_id = self.root.after(50, self._marquee)

    # ────────────── 任务执行框架 ──────────────
    def _register_action(self, btn):
        self.action_buttons.append(btn)
        return btn

    def _set_action_buttons(self, enabled):
        for btn in getattr(self, "action_buttons", []):
            set_button_enabled(btn, enabled)

    def run_in_thread(self, target, label="任务", indeterminate=False):
        """后台线程执行任务：统一 busy 互斥、按钮锁定、进度形态与计时"""
        if self.busy:
            messagebox.showwarning("提示", f"「{self._task_label}」正在执行，请等待完成后再操作。")
            return False
        self.busy = True
        self._task_label = label
        self._task_started = time.time()
        self._freed_bytes = 0
        self._begin_task_ui(indeterminate)

        def _wrapper():
            ok = True
            try:
                target()
            except Exception as e:
                ok = False
                self.log("error", f"✗ {label} 执行异常：{e}")
            finally:
                cost = time.time() - (self._task_started or time.time())
                self.busy = False
                # 工作线程不得直接调 root.after（会抛 main thread is not in main loop），统一走队列
                self.queue.put(("__taskend__", (label, cost, ok)))

        threading.Thread(target=_wrapper, daemon=True).start()
        return True

    def _begin_task_ui(self, indeterminate):
        self.spinner.start()
        self._set_action_buttons(False)
        self._set_indeterminate(indeterminate)
        self.freed_label.config(text="")
        self.elapsed_label.config(text="00:00")
        self.status_label.config(text=f"{self._task_label} 执行中…", fg=FG)
        if indeterminate:
            self.progress_label.config(text="···", fg=CYAN)

    def _end_task_ui(self, label, cost, ok):
        self.spinner.stop()
        self._set_indeterminate(False)
        self._set_action_buttons(True)
        self._task_count += 1
        self.elapsed_label.config(text=f"耗时 {fmt_elapsed(cost)}")
        self.status_label.config(text=f"{label} 已结束" if ok else f"{label} 异常结束",
                                 fg=ACCENT if ok else RED)
        self.progress["value"] = 100 if ok else 0
        self.progress_label.config(text="完成" if ok else "失败",
                                   fg=ACCENT if ok else RED)
        try:
            self.session_freed_label.config(text=f"释放 {format_size(self._session_freed)}")
            self.session_task_label.config(text=f"· {self._task_count} 次任务")
        except Exception:
            pass
        self.refresh_info(False)
        self._save_settings()

    def _tick(self):
        self.clock_label.config(text=time.strftime("%H:%M:%S"))
        if self.busy and self._task_started:
            self.elapsed_label.config(text=f"耗时 {fmt_elapsed(time.time() - self._task_started)}")
        self._disk_ticks += 1
        if self._disk_ticks % DISK_EVERY == 0:
            self._refresh_disk_strip()
        self.root.after(TICK_MS, self._tick)

    # ────────────── 信息刷新 ─────────────────
    def _refresh_disk_strip(self):
        u = get_disk_usage()
        if not u:
            self.disk_free_label.config(text="磁盘信息不可用", fg=RED)
            return
        self.drive_chip.label.config(text=u["drive"][:-1])
        self.disk_free_label.config(text=f"可用 {format_size(u['free'])}", fg=usage_color(u["pct_used"]))
        self.disk_total_label.config(text=f"/ {format_size(u['total'])}")
        self.disk_pct_label.config(text=f"{u['pct_used']:.1f}%", fg=usage_color(u["pct_used"]))
        self._draw_disk_bar(u)
        if windows_old_path():
            if not self.oldos_chip.winfo_manager():
                self.oldos_chip.pack(side="left", padx=(10, 0), before=self.last_clean_chip)
        else:
            self.oldos_chip.pack_forget()
        last = self._last_w11d_time()
        if last:
            self.last_clean_chip.label.config(text=f"上次预装清理 {last[:16]}")
            if not self.last_clean_chip.winfo_manager():
                self.last_clean_chip.pack(side="left", padx=(8, 0))
        else:
            self.last_clean_chip.pack_forget()

    def refresh_info(self, verbose=False):
        self._refresh_disk_strip()
        self._refresh_overview()
        if verbose:
            self.log("info", "已刷新磁盘与概览信息  " + get_disk_summary())

    def show_disk_space(self):
        self.log("cyan", "━━━━━━ 磁盘空间信息 ━━━━━━")
        for line in format_disk_report():
            self.log("gray", line)

    def _on_boot(self):
        self._refresh_disk_strip()
        self._refresh_overview()
        self.log("cyan", f"━━━━━━ {APP_NAME} v{APP_VERSION} ━━━━━━")
        for line in format_disk_report():
            self.log("gray", line)
        self.log("gray", f"运行环境  Python {sys.version.split()[0]} / Tk {tk.TkVersion} / "
                         f"DPI {DPI_MODE}（缩放 {_dpi_scale() * 100:.0f}%）/ 字体 {self.ui_family}")
        last = self._last_w11d_time()
        if last:
            self.log("gray", f"上次系统预装清理：{last}")
        self.log("info", "提示：左侧切换功能；「概览」一键清理最常用；长耗时任务在「系统工具」；"
                         "执行中可随时拖动日志区上沿调整高度。")


    # ────────────── 视图框架与通用小部件 ──────────────
    def _build_views(self):
        for key, icon, name, sub, _nav in VIEWS:
            v = tk.Frame(self.view_host, bg=BG)
            v.grid(row=0, column=0, sticky="nsew")
            v.grid_remove()
            self.views[key] = v

            head = tk.Frame(v, bg=BG)
            head.pack(fill="x", padx=22, pady=(16, 4))
            tk.Label(head, text=icon, fg=ACCENT, bg=BG, font=FONT["h1"]).pack(side="left")
            tk.Label(head, text=name, fg=FG, bg=BG, font=FONT["h1"]).pack(side="left", padx=(8, 0))
            tk.Label(head, text=sub, fg=FG_MUTE, bg=BG, font=FONT["small"]).pack(
                side="left", padx=(12, 0), pady=(7, 0))
            actions = tk.Frame(head, bg=BG)
            actions.pack(side="right")
            tk.Frame(v, bg=LINE, height=1).pack(fill="x", padx=18, pady=(6, 0))

            area = ScrollArea(v, bg=BG, inner_bg=BG)
            area.pack(fill="both", expand=True, padx=8, pady=(4, 0))
            setattr(self, "view_" + key, v)
            setattr(self, "head_" + key, head)
            setattr(self, "actions_" + key, actions)
            setattr(self, "body_" + key, area.inner)
            setattr(self, "area_" + key, area)

        self._build_view_overview()
        self._build_view_clean()
        self._build_view_debloat()
        self._build_view_optimize()
        self._build_view_tools()
        self._build_view_about()

    def _new_card(self, parent, bg=BG2, padx=15, pady=13, hover=True, border=LINE):
        c = Card(parent, bg=bg, border=border, hover=hover, padx=padx, pady=pady)
        return c, c.body

    def _card_title(self, body, title, sub=None, accent=None, side_right=None):
        bg = str(body.cget("bg"))
        row = tk.Frame(body, bg=bg)
        row.pack(fill="x")
        tk.Label(row, text="▎", fg=accent or ACCENT2, bg=bg, font=FONT["h2"]).pack(side="left")
        tk.Label(row, text=title, fg=FG, bg=bg, font=FONT["h2"]).pack(side="left", padx=(1, 0))
        if sub:
            tk.Label(row, text=sub, fg=FG_MUTE, bg=bg, font=FONT["tiny"]).pack(
                side="left", padx=(9, 0), pady=(4, 0))
        if side_right is not None:
            side_right.pack(side="right")
        return row

    def _kv(self, parent, key, value="", vfg=None, mono=False, bold=False):
        bg = str(parent.cget("bg"))
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=key, fg=FG_MUTE, bg=bg, font=FONT["small"]).pack(side="left")
        lbl = tk.Label(row, text=value, fg=vfg or FG, bg=bg,
                       font=FONT["mono_s"] if mono else (FONT["ui_b"] if bold else FONT["small"]))
        lbl.pack(side="right")
        return row, lbl

    def _wrap(self, parent, text, fg=None, font=None, pady=(3, 0), padx=0, justify="left"):
        """宽度自适应标签：wraplength 跟随容器，避免卡片变窄时文字被裁切"""
        bg = str(parent.cget("bg"))
        lbl = tk.Label(parent, text=text, fg=fg or FG_DIM, bg=bg, font=font or FONT["small"],
                       anchor="w", justify=justify, wraplength=240)
        lbl.pack(fill="x", pady=pady, padx=padx)

        def _fit(e=None):
            try:
                lbl.configure(wraplength=max(60, int(e.width) - 4))
            except Exception:
                pass
        lbl.bind("<Configure>", _fit)
        return lbl

    def _note(self, parent, text, color=FG_MUTE, icon=""):
        prefix = (icon + " ") if icon else ""
        return self._wrap(parent, prefix + text, fg=color, font=FONT["tiny"], pady=(6, 0))

    # ────────────── 视图：概览 ──────────────
    def _build_view_overview(self):
        inner = self.body_overview
        self.actions_overview.pack()
        b_help = make_button(self.actions_overview, "使用说明", lambda: self.show_view("about"),
                             style="ghost", size="sm", color=FG_DIM)
        b_help.pack(side="left")

        # 三个主操作卡
        row = tk.Frame(inner, bg=BG)
        row.pack(fill="x", padx=10, pady=(6, 4))
        for i in range(3):
            row.grid_columnconfigure(i, weight=1, uniform="act")
        specs = [
            ("⚡", "快速清理", ACCENT, f"{len(QUICK_KEYS)} 项常用缓存",
             "临时文件 / 回收站 / 浏览器缓存等安全项，日常推荐", self.quick_clean),
            ("✦", "深度清理", ACCENT2, f"全部 {len(CLEAN_ITEMS)} 项",
             "含更新缓存、字体缓存、内存转储，耗时更长", self.deep_clean),
            ("▤", "自定义清理", PURPLE, "勾选项目后执行",
             "逐项查看风险说明，精确控制清理范围", lambda: self.show_view("clean")),
        ]
        for col, (icon, name, color, meta, desc, cmd) in enumerate(specs):
            c, b = self._new_card(row, padx=16, pady=14)
            c.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 9, 0))
            top = tk.Frame(b, bg=str(b.cget("bg")))
            top.pack(fill="x")
            tk.Label(top, text=icon, fg=color, bg=str(b.cget("bg")), font=FONT["h1"]).pack(side="left")
            tk.Label(top, text=name, fg=FG, bg=str(b.cget("bg")), font=FONT["h2"]).pack(
                side="left", padx=(8, 0))
            tk.Label(b, text=meta, fg=color, bg=str(b.cget("bg")), font=FONT["small_b"]).pack(
                anchor="w", pady=(4, 0))
            self._wrap(b, desc, fg=FG_MUTE, font=FONT["tiny"], pady=(2, 10))
            btn = make_button(b, "开始执行" if col < 2 else "进入选择", cmd, color=color, size="md")
            btn.pack(fill="x")
            if col < 2:
                self._register_action(btn)

        # 磁盘 + 状态
        row2 = tk.Frame(inner, bg=BG)
        row2.pack(fill="x", padx=10, pady=(6, 4))
        row2.grid_columnconfigure(0, weight=5, uniform="r2")
        row2.grid_columnconfigure(1, weight=7, uniform="r2")

        c1, b1 = self._new_card(row2)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        self._card_title(b1, "存储空间", accent=ACCENT)
        self.ov_free_big = tk.Label(b1, text="—", fg=ACCENT, bg=str(b1.cget("bg")), font=FONT["num"])
        self.ov_free_big.pack(anchor="w", pady=(8, 0))
        self.ov_free_sub = tk.Label(b1, text="", fg=FG_MUTE, bg=str(b1.cget("bg")), font=FONT["small"])
        self.ov_free_sub.pack(anchor="w")
        self.ov_bar = tk.Canvas(b1, height=14, bg=str(b1.cget("bg")), highlightthickness=0, bd=0)
        self.ov_bar.pack(fill="x", pady=(10, 2))
        self.ov_bar.bind("<Configure>", lambda e: self._draw_ov_bar())
        _b1 = str(b1.cget("bg"))
        self._ov_bar_lbls = tk.Frame(b1, bg=_b1)
        self._ov_bar_lbls.pack(fill="x")
        self.ov_bar_used = tk.Label(self._ov_bar_lbls, text="", fg=FG_MUTE, bg=_b1, font=FONT["tiny"])
        self.ov_bar_used.pack(side="left")
        self.ov_bar_pct = tk.Label(self._ov_bar_lbls, text="", fg=FG_MUTE, bg=_b1, font=FONT["tiny"])
        self.ov_bar_pct.pack(side="right")
        self.ov_oldos = self._note(b1, "", AMBER, icon="⚠")
        br = tk.Frame(b1, bg=str(b1.cget("bg")))
        br.pack(fill="x", pady=(10, 0))
        for text, cmd, tip in (("磁盘详情", self.show_disk_space, "在日志区输出磁盘明细"),
                               ("磁盘清理", self._run_cleanmgr, "打开系统 cleanmgr 工具")):
            bb = make_button(br, text, cmd, style="ghost", size="sm", color=FG_DIM, tooltip=tip)
            bb.pack(side="left", padx=(0, 6))

        c2, b2 = self._new_card(row2)
        c2.grid(row=0, column=1, sticky="nsew")
        self._card_title(b2, "运行环境与健康检查", accent=CYAN)
        self.ov = {}
        for k in ("admin", "dpi", "font", "runtime", "browser", "items", "opt", "res", "last", "session"):
            _row, lbl = self._kv(b2, {
                "admin": "管理员权限", "dpi": "高 DPI 适配", "font": "界面字体 / 字号",
                "runtime": "运行环境", "browser": "检测到浏览器", "items": "缓存清理项",
                "opt": "系统优化项", "res": "资源完整性", "last": "上次预装清理",
                "session": "本次会话"}[k], "—")
            self.ov[k] = lbl

        # 风险提示
        c3, b3 = self._new_card(inner, bg="#141821")
        c3.pack(fill="x", padx=10, pady=(6, 10))
        self._card_title(b3, "执行高危操作前", accent=RED)
        self._wrap(b3, "关闭 Defender、禁用 Windows 更新、中断延迟优化、预装应用移除等操作不可逆。"
                          "建议先在「系统工具」创建还原点，或用 Dism++ 备份系统镜像。",
                   fg=FG_DIM, pady=(4, 0))
        r3 = tk.Frame(b3, bg=str(b3.cget("bg")))
        r3.pack(fill="x", pady=(8, 0))
        b_rp = make_button(r3, "🛡 创建系统还原点", lambda: self.show_view("tools"),
                           color=RED, size="sm", tooltip="跳到系统工具视图并填写描述")
        b_rp.pack(side="left", padx=(0, 6))
        b_hk = make_button(r3, "查看全部高危项", lambda: self.show_view("optimize"),
                           style="ghost", size="sm", color=FG_DIM)
        b_hk.pack(side="left")
        self._kb_hint(b3)

    def _kb_hint(self, parent):
        bg = str(parent.cget("bg"))
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=(8, 0))
        tk.Label(row, text="快捷键", fg=FG_MUTE, bg=bg, font=FONT["tiny"]).pack(side="left", padx=(0, 8))
        for t in ("F5 刷新", "Alt+1~6 切换视图", "Ctrl+L 清空日志", "Ctrl+F 搜索",
                  "Ctrl+S 保存日志", "Ctrl+J 折叠日志", "Ctrl+= / Ctrl+- 字号"):
            chip(row, t, fg=FG_MUTE, bg=BG3, border=LINE, font=FONT["tiny"], padx=6, pady=1).pack(
                side="left", padx=(0, 5))

    def _draw_ov_bar(self):
        c = self.ov_bar
        c.delete("all")
        w, h = max(40, c.winfo_width()), 14
        u = get_disk_usage()
        frac = (u["pct_used"] / 100.0) if u else 0.0
        col = usage_color(u["pct_used"]) if u else FG_MUTE
        r = h / 2.0
        c.create_rectangle(r, 0, w - r, h, fill=BG3, outline="")
        c.create_oval(0, 0, h, h, fill=BG3, outline="")
        c.create_oval(w - h, 0, w, h, fill=BG3, outline="")
        fw = max(h, int(w * min(max(frac, 0.0), 1.0)))
        c.create_rectangle(r, 0, max(r, fw - r), h, fill=col, outline="")
        c.create_oval(0, 0, h, h, fill=col, outline="")
        if fw > h:
            c.create_oval(fw - h, 0, fw, h, fill=col, outline="")
        for th in (0.80, 0.92):
            x = int(w * th)
            c.create_line(x, 1, x, h - 1, fill=BG2, width=1)

    def _refresh_overview(self):
        u = get_disk_usage()
        if u:
            self.ov_free_big.config(text=f"{format_size(u['free'])}", fg=usage_color(u["pct_used"]))
            self.ov_free_sub.config(text=f"{u['drive'][:-1]} 盘可用 · 总容量 {format_size(u['total'])}")
            self.ov_bar_used.config(text=f"已用 {u['pct_used']:.1f}%", fg=usage_color(u["pct_used"]))
            self.ov_bar_pct.config(text=f"剩余 {format_size(u['free'])}", fg=FG_MUTE)
        else:
            self.ov_free_big.config(text="不可用", fg=RED)
        old = windows_old_path()
        self.ov_oldos.config(text=("发现 Windows.old（通常 10-30GB），请用「磁盘清理 → 清理系统文件」删除"
                                   if old else ""))
        high = sum(1 for it in OPT_ITEMS if it.get("danger") == "high")
        miss = self._missing_opt_files()
        res_missing = []
        if not os.path.isfile(WIN11DEBLOAT_PS1):
            res_missing.append("Win11Debloat.ps1")
        if not os.path.isfile(WIN11DEBLOAT_GUI):
            res_missing.append("Win11DebloatGUI.ps1")
        if not os.path.isdir(OPT_BASE):
            res_missing.append("Optimization/")
        res_text = "完整" if not (res_missing or miss) else \
            f"缺失 {len(res_missing) + len(miss)} 项：{', '.join((res_missing + miss)[:3])}"
        vals = {
            "admin": ("已提权（UAC）" if is_admin() else "未提权（功能受限）"),
            "dpi": f"{DPI_MODE} · 缩放 {_dpi_scale() * 100:.0f}%",
            "font": f"{self.ui_family} · {int(self.font_scale * 100)}%",
            "runtime": f"Python {sys.version.split()[0]} · Tk {tk.TkVersion}",
            "browser": "、".join(installed_browser_names()) or "未检测到",
            "items": f"{len(CLEAN_ITEMS)} 项（快速 {len(QUICK_KEYS)} 项 · 可选 1 项）",
            "opt": f"{len(OPT_ITEMS)} 项（高危 {high} 项）",
            "res": res_text,
            "last": self._last_w11d_time() or "从未执行",
            "session": f"释放 {format_size(self._session_freed)} · {self._task_count} 次任务",
        }
        colors = {
            "admin": ACCENT if is_admin() else AMBER,
            "res": FG if res_text == "完整" else AMBER,
            "last": FG_DIM,
            "session": ACCENT if self._session_freed else FG_DIM,
        }
        for k, lbl in self.ov.items():
            try:
                lbl.config(text=vals[k], fg=colors.get(k, FG_DIM))
            except Exception:
                pass

    def _missing_opt_files(self):
        miss = []
        for it in OPT_ITEMS:
            for _label, fname, _kind in it["entries"]:
                if not os.path.exists(os.path.join(opt_item_dir(it), fname)):
                    miss.append(f"{it['name']}/{fname}")
        return miss

    # ────────────── 视图：缓存清理 ──────────────
    def _build_view_clean(self):
        inner = self.body_clean
        self.actions_clean.pack()
        b_q = make_button(self.actions_clean, "⚡ 快速清理", self.quick_clean, color=ACCENT,
                          size="sm", tooltip=f"一键执行 {len(QUICK_KEYS)} 项安全缓存清理")
        b_q.pack(side="left", padx=(0, 6))
        self._register_action(b_q)
        b_d = make_button(self.actions_clean, "✦ 深度清理", self.deep_clean, color=ACCENT2, size="sm",
                          tooltip=f"全部 {len(CLEAN_ITEMS)} 项 + Windows.old 检查")
        b_d.pack(side="left")
        self._register_action(b_d)

        bar, bb = self._new_card(inner, bg=BG2, pady=10)
        bar.pack(fill="x", padx=10, pady=(4, 8))
        left = tk.Frame(bb, bg=str(bb.cget("bg")))
        left.pack(side="left")
        tk.Label(left, text="自定义选择", fg=FG, bg=str(bb.cget("bg")), font=FONT["h2"]).pack(side="left")
        self.clean_sel_label = tk.Label(left, text="", fg=ACCENT, bg=str(bb.cget("bg")), font=FONT["small_b"])
        self.clean_sel_label.pack(side="left", padx=(10, 0))
        right = tk.Frame(bb, bg=str(bb.cget("bg")))
        right.pack(side="right")
        for text, cmd, tip in (
                ("推荐", self._select_recommend, "只选缓存清理中的安全项（排除预读取等可选项）"),
                ("全选", lambda: self._select_all(True), "勾选全部 14 项"),
                ("清空", lambda: self._select_all(False), "取消全部勾选")):
            make_button(right, text, cmd, style="ghost", size="sm", color=FG_DIM, tooltip=tip).pack(
                side="left", padx=(0, 6))
        b_run = make_button(right, "▶ 执行选中", self.custom_clean, color=PURPLE, size="sm",
                            tooltip="按当前勾选执行清理")
        b_run.pack(side="left")
        self._register_action(b_run)

        self.item_vars = {}
        self.item_rows = {}
        group_color = {"缓存清理": ACCENT, "系统维护": ORANGE}
        current = None
        for it in CLEAN_ITEMS:
            if it["group"] != current:
                current = it["group"]
                head = tk.Frame(inner, bg=BG)
                head.pack(fill="x", padx=14, pady=(8, 2))
                tk.Label(head, text="▎" + current, fg=group_color.get(current, FG_DIM),
                         bg=BG, font=FONT["ui_b"]).pack(side="left")
                tk.Label(head, text={
                    "缓存清理": "删除后可自动重建，风险低",
                    "系统维护": "涉及系统服务，执行时会短暂停止相关服务"}[current],
                    fg=FG_MUTE, bg=BG, font=FONT["tiny"]).pack(side="left", padx=(8, 0), pady=(2, 0))
            c, b = self._new_card(inner, padx=12, pady=8)
            c.pack(fill="x", padx=10, pady=2)
            var = tk.IntVar(value=1 if it["key"] in QUICK_KEYS else 0)
            self.item_vars[it["key"]] = var
            row = tk.Frame(b, bg=str(b.cget("bg")))
            row.pack(fill="x")
            cb = tk.Checkbutton(row, text=f"{it['icon']}  {it['name']}", variable=var,
                                command=self._update_sel_count,
                                bg=str(b.cget("bg")), fg=(AMBER if it.get("optional") else FG),
                                selectcolor=BG3, activebackground=str(b.cget("bg")),
                                activeforeground=FG, font=FONT["ui"], anchor="w",
                                highlightthickness=0, cursor="hand2", wraplength=520, justify="left")
            cb.pack(side="left")
            c.bind("<Configure>", lambda e, w=cb: w.configure(
                wraplength=max(160, int(e.width) - 150)), add="+")
            badges = tk.Frame(row, bg=str(b.cget("bg")))
            badges.pack(side="right")
            if it["key"] in QUICK_KEYS:
                chip(badges, "快速", fg=ACCENT, bg=mix(BG3, ACCENT, 0.16), font=FONT["tiny"],
                     padx=6, pady=1).pack(side="left", padx=(0, 5))
            if it.get("optional"):
                chip(badges, "可选 · 谨慎", fg=AMBER, bg=mix(BG3, AMBER, 0.16), font=FONT["tiny"],
                     padx=6, pady=1).pack(side="left", padx=(0, 5))
            tip = it.get("tip") or _CLEAN_ITEM_DESC.get(it["key"], "")
            self._note(b, tip.replace("⚠ ", ""), FG_MUTE).pack(anchor="w", pady=(2, 0))
            self.item_rows[it["key"]] = (c, cb, badges)
        self._update_sel_count()

    def _update_sel_count(self):
        try:
            n = sum(1 for v in self.item_vars.values() if v.get())
            self.clean_sel_label.config(text=f"已选 {n} / {len(self.item_vars)} 项")
        except Exception:
            pass

    def _select_all(self, on):
        for v in self.item_vars.values():
            v.set(1 if on else 0)
        self._update_sel_count()

    def _select_recommend(self):
        for k, v in self.item_vars.items():
            it = CLEAN_BY_KEY[k]
            v.set(1 if it["group"] == "缓存清理" and not it.get("optional") else 0)
        self._update_sel_count()

    # ────────────── 视图：预装清理 ──────────────
    def _build_view_debloat(self):
        self.actions_debloat.pack()
        make_button(self.actions_debloat, "重新检测", lambda: self._build_debloat_list(),
                    style="ghost", size="sm", color=FG_DIM).pack(side="left")
        self._debloat_host = self.body_debloat
        self._build_debloat_list()

    def _build_debloat_list(self):
        inner = self._debloat_host
        for w in inner.winfo_children():
            w.destroy()
        c, b = self._new_card(inner, bg="#141821")
        c.pack(fill="x", padx=10, pady=(4, 8))
        self._card_title(b, "组件状态", accent=CYAN)
        ok_ps1, ok_gui = os.path.isfile(WIN11DEBLOAT_PS1), os.path.isfile(WIN11DEBLOAT_GUI)
        self._kv(b, "Win11Debloat.ps1（预设执行）",
                 "✓ 已就绪" if ok_ps1 else "✗ 文件缺失", vfg=ACCENT if ok_ps1 else RED, mono=True)
        self._kv(b, "Win11DebloatGUI.ps1（图形界面）",
                 "✓ 已就绪" if ok_gui else "✗ 文件缺失", vfg=ACCENT if ok_gui else RED, mono=True)
        self._kv(b, "上次执行", self._last_w11d_time() or "从未执行", vfg=FG_DIM)
        self._note(b, f"目录  {WIN11DEBLOAT_DIR}", FG_MUTE, icon="").pack(anchor="w", pady=(6, 0))
        self._note(b, "执行前会自动备份 CustomAppsList / SavedSettings 到 data/win11debloat_backup/（保留 5 份）",
                   FG_MUTE).pack(anchor="w")

        tk.Label(inner, text="▎快速预设（静默执行，不可逆）", fg=AMBER, bg=BG,
                 font=FONT["ui_b"]).pack(anchor="w", padx=14, pady=(6, 2))
        for i, preset in enumerate(W11D_PRESETS):
            pc, pb = self._new_card(inner)
            pc.pack(fill="x", padx=10, pady=3)
            head = self._card_title(pb, preset["name"], side_right=None)
            chip(head, preset.get("tag", ""), fg=preset["color"], bg=mix(BG3, preset["color"], 0.18),
                 font=FONT["tiny"], padx=6, pady=1).pack(side="right")
            self._wrap(pb, preset["desc"], fg=FG_DIM, pady=(3, 0))
            self._wrap(pb, "参数  " + preset["params"], fg=FG_MUTE, font=FONT["mono_s"], pady=(2, 0))
            btn = make_button(pb, "▶ 执行此预设", lambda idx=i: self._w11d_preset_confirm(idx),
                              color=preset["color"], size="sm")
            btn.pack(anchor="w", pady=(8, 0))
            self._register_action(btn)
            if not ok_ps1:
                set_button_enabled(btn, False)

        gc, gb = self._new_card(inner, bg="#171426", border="#2A2440")
        gc.pack(fill="x", padx=10, pady=(10, 12))
        self._card_title(gb, "完整图形界面", sub="逐项勾选，功能最全", accent=PURPLE)
        self._wrap(gb, "打开 Win11DebloatGUI，可精细选择移除应用、隐私、任务栏、"
                       "OneDrive 等全部选项；窗口独立运行，关闭后自动刷新磁盘信息。", fg=FG_DIM)
        b2 = make_button(gb, "🖥  打开完整图形界面", self._w11d_open_gui, color=PURPLE, size="md")
        b2.pack(anchor="w", pady=(9, 0))
        self._register_action(b2)
        if not ok_gui:
            set_button_enabled(b2, False)

    # ────────────── 视图：系统优化 ──────────────
    def _build_view_optimize(self):
        self.actions_optimize.pack()
        make_button(self.actions_optimize, "重新检测资源", self._build_optimize_list,
                    style="ghost", size="sm", color=FG_DIM).pack(side="left")
        self._opt_host = self.body_optimize
        self._build_optimize_list()

    def _build_optimize_list(self):
        inner = self._opt_host
        for w in inner.winfo_children():
            w.destroy()
        c, b = self._new_card(inner, bg="#141821")
        c.pack(fill="x", padx=10, pady=(4, 8))
        self._card_title(b, "危险等级说明", accent=AMBER)
        lg = tk.Frame(b, bg=str(b.cget("bg")))
        lg.pack(fill="x", pady=(6, 0))
        for lvl, text in (("low", "改注册表/可逆，影响小"),
                          ("medium", "修改系统设置，建议先读说明"),
                          ("high", "不可逆或影响安全/稳定性，务必先建还原点")):
            box = tk.Frame(lg, bg=mix(BG2, DANGER_COLORS[lvl], 0.16), padx=9, pady=6)
            box.pack(side="left", expand=True, fill="x", padx=(0, 8))
            tk.Label(box, text=DANGER_LABELS[lvl], fg=DANGER_COLORS[lvl], bg=str(box.cget("bg")),
                     font=FONT["ui_b"]).pack(anchor="w")
            self._wrap(box, text, fg=FG_DIM, font=FONT["tiny"])

        for item in OPT_ITEMS:
            danger = item.get("danger", "low")
            dcol = DANGER_COLORS[danger]
            pc, pb = self._new_card(inner)
            pc.pack(fill="x", padx=10, pady=4)
            head = self._card_title(pb, item["name"], accent=dcol)
            chip(head, DANGER_LABELS[danger], fg=dcol, bg=mix(BG3, dcol, 0.18),
                 font=FONT["tiny"], padx=7, pady=1).pack(side="right")
            self._wrap(pb, item["desc"], fg=FG_DIM, pady=(3, 0))
            missing = [f for _l, f, _k in item["entries"]
                       if not os.path.exists(os.path.join(opt_item_dir(item), f))]
            if not os.path.isdir(opt_item_dir(item)):
                missing.append(item["dir"])
            if missing:
                tk.Label(pb, text="⚠ 资源缺失：" + "、".join(missing[:3]) +
                         ("…" if len(missing) > 3 else ""),
                         fg=AMBER, bg=str(pb.cget("bg")), font=FONT["tiny"]).pack(anchor="w")
            flow = FlowFrame(pb, bg=str(pb.cget("bg")), spacing=5)
            flow.pack(fill="x", pady=(8, 0))
            dir_ok = os.path.isdir(opt_item_dir(item))
            b_dir = flow.add(make_button(flow, "📂 打开目录",
                                         lambda i=item: opt_open_dir(self.log, i),
                                         style="ghost", size="sm", color=FG_DIM))
            if not dir_ok:
                set_button_enabled(b_dir, False)
                ToolTip(b_dir, "目录不存在：" + item["dir"])
            if item.get("readme"):
                b_doc = flow.add(make_button(flow, "📄 查看说明",
                                             lambda i=item: opt_open_readme(self.log, i),
                                             style="ghost", size="sm", color=FG_DIM))
                if not (dir_ok and os.path.isfile(os.path.join(opt_item_dir(item), item["readme"]))):
                    set_button_enabled(b_doc, False)
                    ToolTip(b_doc, "说明文档不存在：" + item["readme"])
            for label, fname, kind in item["entries"]:
                exists = os.path.exists(os.path.join(opt_item_dir(item), fname))
                btn = flow.add(make_button(
                    flow, f"▶ {label}",
                    lambda i=item, f=fname, k=kind, l=label: self._opt_exec_confirm(i, f, k, l),
                    color=dcol if danger == "high" else item.get("color", ACCENT2), size="sm"))
                if not exists:
                    set_button_enabled(btn, False)
                    ToolTip(btn, f"文件不存在：{fname}")

    # ────────────── 视图：系统工具 ──────────────
    def _build_view_tools(self):
        inner = self.body_tools
        c, b = self._new_card(inner, bg="#12201B", border="#1E3A2C")
        c.pack(fill="x", padx=10, pady=(4, 8))
        self._card_title(b, "创建系统还原点", sub="高危操作前的推荐备份", accent=ACCENT)
        self.rp_default = f"{APP_NAME} 操作前备份 {time.strftime('%Y-%m-%d %H:%M')}"
        self.rp_var = tk.StringVar(value=self.rp_default)
        box = tk.Frame(b, bg=BG3, padx=8, pady=5)
        box.pack(fill="x", pady=(8, 0))
        tk.Label(box, text="描述", bg=BG3, fg=FG_MUTE, font=FONT["small"]).pack(side="left")
        ent = tk.Entry(box, textvariable=self.rp_var, bg=BG3, fg=FG, insertbackground=FG,
                       relief="flat", bd=0, font=FONT["ui"], highlightthickness=0)
        ent.pack(side="left", fill="x", expand=True, padx=8)
        b_rp = make_button(box, "▶ 创建还原点", self._create_restore_point, color=ACCENT, size="sm")
        b_rp.pack(side="right")
        self._register_action(b_rp)
        self._note(b, "需要系统保护对 C: 已启用；创建约需 10-60 秒，完成后可在「系统属性 → 系统保护」查看/恢复。",
                   FG_MUTE).pack(anchor="w", pady=(6, 0))

        tools = [
            ("🧹 磁盘清理 (cleanmgr)", "系统自带图形工具，可清理系统文件与旧更新", ACCENT2,
             lambda: self._run_cleanmgr(), "低风险"),
            ("🚿 DISM 组件清理", "清理 WinSxS 组件存储，通常可释放数 GB", ORANGE,
             lambda: self._run_dism(), "15-30 分钟"),
            ("🩺 系统文件检查 (sfc /scannow)", "扫描并修复受损系统文件，输出显示在日志区", CYAN,
             lambda: self._run_sfc(), "15-30 分钟"),
            ("💿 磁盘错误检查 (chkdsk /f)", "安排在下次重启时执行，需要重启才生效", AMBER,
             lambda: self._run_chkdsk(), "需重启"),
            ("💽 磁盘空间明细", "在日志区输出总容量/已用/可用与 Windows.old 提示", FG_DIM,
             self.show_disk_space, "即时"),
        ]
        for title, desc, color, cmd, badge in tools:
            tc, tb = self._new_card(inner)
            tc.pack(fill="x", padx=10, pady=3)
            head = self._card_title(tb, title, accent=color)
            chip(head, badge, fg=FG_MUTE, bg=BG3, font=FONT["tiny"], padx=6, pady=1).pack(side="right")
            self._wrap(tb, desc, fg=FG_DIM)
            btn = make_button(tb, "执行", cmd, color=color, size="sm")
            btn.pack(anchor="w", pady=(7, 0))
            self._register_action(btn)

    # ────────────── 视图：关于 ──────────────
    def _build_view_about(self):
        inner = self.body_about
        c, b = self._new_card(inner, bg="#141821")
        c.pack(fill="x", padx=10, pady=(4, 8))
        self._card_title(b, f"{APP_NAME} v{APP_VERSION}", sub=APP_TAGLINE, accent=ACCENT)
        self._kv(b, "主程序", os.path.join(APP_DIR, "WinSweep.pyw"), vfg=FG_DIM, mono=True)
        self._kv(b, "资源目录", RES_DIR, vfg=FG_DIM, mono=True)
        self._kv(b, "数据目录", DATA_DIR, vfg=FG_DIM, mono=True)
        self._kv(b, "第三方依赖", "无（仅 Python 标准库 + tkinter）", vfg=ACCENT)
        ab = tk.Frame(b, bg=str(b.cget("bg")))
        ab.pack(fill="x", pady=(8, 0))
        for text, cmd in (("打开项目目录", lambda: self._open_path(APP_DIR)),
                          ("打开数据目录", lambda: self._open_path(DATA_DIR)),
                          ("打开 README", lambda: self._open_path(os.path.join(APP_DIR, "README.md")))):
            make_button(ab, text, cmd, style="ghost", size="sm", color=FG_DIM).pack(side="left", padx=(0, 6))

        c2, b2 = self._new_card(inner)
        c2.pack(fill="x", padx=10, pady=4)
        self._card_title(b2, "v3.4 界面与显示改进", accent=ACCENT2)
        for line in (
            "布局：修复日志区抢占空间导致底部按钮与状态栏被挤出窗口；改为分区 + 可拖拽分隔条",
            "导航：弹窗功能全部内嵌为视图（清理 / 预装 / 优化 / 工具），滚轮按指针命中区域生效",
            "显示：深色标题栏与圆角边框、磁盘胶囊条随窗口伸缩、日志等宽时间戳与级别列对齐",
            "日志：级别过滤 + 计数、关键词搜索、自动滚动开关与「跳到最新」、导出日志文件",
            "进度：长耗时外部任务改为跑马灯 + 已用时 + 旋转指示器，不再停在 0% 像卡死",
            "按钮：内容自适应宽度并自动换行，中文/emoji 混排不再截断；禁用态明显变暗",
            "偏好：字号可缩放（Ctrl+= / Ctrl+-），视图、布局、窗口尺寸记忆到 data/settings.json",
        ):
            self._wrap(b2, "·  " + line, fg=FG_DIM, pady=(1, 1))

        c3, b3 = self._new_card(inner)
        c3.pack(fill="x", padx=10, pady=4)
        self._card_title(b3, "免责声明", accent=RED)
        self._wrap(b3, "本工具会修改系统设置并删除文件，请在了解每项操作含义后使用；"
                       "因使用本工具造成的数据丢失或系统不稳定，作者不承担责任。"
                       "Win11Debloat 为第三方开源项目（MIT 许可证）。", fg=FG_MUTE)


    # ────────────── 清理执行 ──────────────
    def _run_items(self, items, mode_name):
        """统一执行清理项：逐项计时 + 失败统计 + 释放空间对比"""
        total = len(items)
        start_free = get_free_bytes()
        t_all = time.time()
        self.queue.put(("__freed__", 0))
        self.log("cyan", f"━━━━━━ {mode_name}（共 {total} 项） ━━━━━━")
        failed = []
        for i, it in enumerate(items, 1):
            self.log("info", f"▶ [{i}/{total}] {it['icon']} {it['name']}")
            self.set_status(f"正在清理：{it['name']}  ({i}/{total})", (i - 1) / total * 0.98)
            t0 = time.time()
            try:
                it["func"](self.log)
                cost = time.time() - t0
                if cost >= 1.0:
                    self.log("gray", f"   本项耗时 {cost:.1f}s")
            except Exception as e:
                failed.append(it["name"])
                self.log("error", f"   ✗ {it['name']} 清理失败：{e}")
        self.set_status(f"{mode_name}完成", 0.99)

        freed = get_free_bytes() - start_free
        self.queue.put(("__freed__", max(freed, 0)))
        cost = time.time() - t_all
        if failed:
            self.log("warning", f"◈ {mode_name}结束：{total - len(failed)}/{total} 项成功，"
                                f"失败 {len(failed)} 项（{'、'.join(failed[:3])}），耗时 {fmt_elapsed(cost)}")
        elif freed > 0:
            self.log("success", f"✔ {mode_name}完成：{total} 项全部成功，释放约 "
                                f"{format_size(freed)}，耗时 {fmt_elapsed(cost)}")
        else:
            self.log("success", f"✔ {mode_name}完成：{total} 项全部成功，本次无明显空间变化，"
                                f"耗时 {fmt_elapsed(cost)}")
        self.set_status(f"{mode_name}完成 · 耗时 {fmt_elapsed(cost)}", 1.0)

    def quick_clean(self):
        items = [CLEAN_BY_KEY[k] for k in QUICK_KEYS]
        self.run_in_thread(lambda: self._run_items(items, "快速清理"), "快速清理")

    def deep_clean(self):
        self.log("warning", "注意：深度清理会清除更多系统缓存（更新缓存 / 字体缓存等），耗时更长")
        items = list(CLEAN_ITEMS)
        self.run_in_thread(lambda: (self._run_items(items, "深度清理"),
                                    check_old_windows(self.log)), "深度清理")

    def custom_clean(self):
        selected = [k for k, v in self.item_vars.items() if v.get()]
        if not selected:
            messagebox.showinfo("提示", "未选择任何清理项，请先在左侧列表勾选。")
            return
        items = [CLEAN_BY_KEY[k] for k in selected]
        names = "、".join(it["name"] for it in items[:4]) + ("…" if len(items) > 4 else "")
        risky = [it["name"] for it in items if it.get("optional")]
        if risky:
            if not messagebox.askyesno(
                    "确认执行", f"已选 {len(items)} 项：{names}\n\n"
                    f"其中包含可选/谨慎项：{'、'.join(risky)}\n"
                    "预读取文件清理后首次冷启动会略慢。\n\n是否继续？"):
                return
        self.run_in_thread(lambda: self._run_items(items, "自定义清理"), "自定义清理")

    # ────────────── 系统优化 / 工具 ──────────────
    def _opt_exec_confirm(self, item, fname, kind, label):
        """执行优化项入口前二次确认（按危险等级强化提示）"""
        risk_note = {
            "reg": "\n\n将导入注册表文件（更改系统设置，不可逆）。",
            "bat": "\n\n将运行批处理脚本（可能弹窗请求操作）。",
            "cmd": "\n\n将运行命令脚本（可能弹窗请求操作）。",
            "ps1": "\n\n将以 PowerShell 运行脚本（请按脚本内提示操作）。",
            "exe": "\n\n将启动第三方程序（系统级工具，请按说明操作）。",
            "lnk": "\n\n将打开快捷方式目标。",
        }.get(kind, "")
        danger = item.get("danger", "low")
        danger_note = {
            "high": "\n\n⚠ 高危操作：可能影响系统安全/稳定性。\n建议先在「系统工具 → 创建系统还原点」备份。",
            "medium": "\n\n⚠ 中危操作：修改系统设置，建议先阅读说明文档。",
            "low": "",
        }.get(danger, "")
        if not messagebox.askyesno(
                "确认执行",
                f"{item['name']} → {label}\n文件：{fname}{risk_note}{danger_note}\n\n是否继续？"):
            return
        self.run_in_thread(lambda: opt_execute(self.log, item, label, fname, kind),
                           f"系统优化：{label}", indeterminate=(kind in ("bat", "cmd", "ps1", "exe")))

    def _open_path(self, path):
        try:
            if os.path.exists(path):
                os.startfile(path)
                self.log("info", f"已打开：{path}")
            else:
                messagebox.showinfo("提示", f"路径不存在：\n{path}")
        except Exception as e:
            messagebox.showerror("打开失败", str(e))

    def _run_cleanmgr(self):
        self.run_in_thread(lambda: start_disk_cleanup(self.log), "磁盘清理工具")

    def _run_dism(self):
        if not messagebox.askyesno("确认执行", "DISM 组件清理通常需要 15-30 分钟，"
                                              "期间占用较高 CPU/磁盘。\n是否继续？"):
            return
        self.run_in_thread(lambda: run_dism_clean(self.log), "DISM 组件清理", indeterminate=True)

    def _run_sfc(self):
        if not messagebox.askyesno("确认执行", "sfc /scannow 通常需要 15-30 分钟。\n是否继续？"):
            return
        self.run_in_thread(lambda: self.run_sfc(), "系统文件检查", indeterminate=True)

    def run_sfc(self):
        """运行 sfc /scannow（输出回显到日志区）"""
        self.log("info", "[调用] 系统文件检查… 可能需要 15-30 分钟，请耐心等待")
        result = subprocess.run("sfc /scannow", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            self.log("success", "✔ 系统文件检查完成")
        else:
            self.log("warning", f"系统文件检查结束（退出码 {result.returncode}）")
        for line in (result.stdout or "").splitlines()[-8:]:
            if line.strip():
                self.log("gray", line.strip())

    def _run_chkdsk(self):
        if messagebox.askyesno("确认", "磁盘检查将在下次重启时执行，期间无法开机引导。\n是否继续？"):
            self.run_in_thread(lambda: self.run_chkdsk(), "磁盘错误检查")

    def run_chkdsk(self):
        subprocess.Popen(f"chkdsk {get_drive()} /f", shell=True)
        self.log("warning", "磁盘检查已安排，将在系统重启时执行")

    def _create_restore_point(self):
        desc = (self.rp_var.get() or "").strip() or self.rp_default
        if not messagebox.askyesno("确认", f"将创建系统还原点：\n\n{desc}\n\n是否继续？"):
            return
        self.run_in_thread(lambda: create_restore_point(self.log, desc),
                           "创建系统还原点", indeterminate=True)

    # ────────────── 系统预装清理 ──────────────
    def _w11d_preset_confirm(self, idx):
        preset = W11D_PRESETS[idx]
        if not os.path.isfile(WIN11DEBLOAT_PS1):
            messagebox.showerror("缺少组件", f"未找到 Win11Debloat.ps1：\n{WIN11DEBLOAT_PS1}")
            return
        if not messagebox.askyesno(
                "确认执行",
                f"将执行：{preset['name']}\n\n{preset['desc']}\n\n"
                "更改不可逆，部分设置需要重启后完全生效。\n执行中可能重启资源管理器（屏幕短暂闪烁）。\n\n是否继续？"):
            return
        self.run_in_thread(
            lambda: run_win11debloat_preset(self.log, preset["params"], preset["name"]),
            f"预装清理：{preset['name']}", indeterminate=True)

    def _w11d_open_gui(self):
        """启动 Win11Debloat 完整图形界面，并轮询检测启动失败 / 关闭联动"""
        if not os.path.isfile(WIN11DEBLOAT_GUI):
            messagebox.showwarning(
                "缺少组件",
                f"未找到 Win11DebloatGUI.ps1\n预期路径: {WIN11DEBLOAT_GUI}\n\n请确认 resources/Win11Debloat 目录完整。")
            return
        started = run_win11debloat_gui(self.log)
        if started is None:
            return
        self.w11d_proc, self.w11d_err_path = started
        self.w11d_started = time.time()
        self.w11d_success_logged = False
        self.set_status("正在启动 Win11Debloat 图形界面…", 0)
        self.root.after(1500, self._poll_w11d)

    def _poll_w11d(self):
        """轮询 Win11Debloat GUI 进程：启动失败检测 + 关闭后刷新磁盘 + 记录时间"""
        proc = getattr(self, "w11d_proc", None)
        if proc is None:
            return
        code = proc.poll()
        if code is None:
            if not self.w11d_success_logged and time.time() - self.w11d_started > 1.5:
                self.w11d_success_logged = True
                self.log("success", "✔ Win11Debloat 图形界面已启动")
                self.set_status("系统预装清理界面运行中…", 0)
            self.root.after(1500, self._poll_w11d)
            return

        self.w11d_proc = None
        err_text = ""
        if os.path.exists(self.w11d_err_path):
            try:
                with open(self.w11d_err_path, "r", encoding="utf-8", errors="ignore") as fh:
                    err_text = fh.read()
                os.remove(self.w11d_err_path)
            except Exception:
                pass

        if time.time() - self.w11d_started < 1.5:
            self.log("error", "[系统预装清理] Win11Debloat 图形界面启动失败")
            for line in err_text.strip().splitlines():
                if line.strip():
                    self.log("error", f"  {line.strip()}")
        else:
            try:
                with open(W11D_LAST_FILE, "w", encoding="utf-8") as fh:
                    fh.write(time.strftime("%Y-%m-%d %H:%M:%S"))
            except Exception:
                pass
            self.log("info", "[系统预装清理] Win11Debloat 图形界面已关闭")
            self.refresh_info(False)
        self.set_status("就绪", 0)

    def _last_w11d_time(self):
        """读取最近一次系统预装清理时间"""
        try:
            if os.path.isfile(W11D_LAST_FILE):
                with open(W11D_LAST_FILE, "r", encoding="utf-8") as fh:
                    return fh.read().strip()
        except Exception:
            pass
        return None

    # ────────────── 关闭 / 偏好保存 ──────────────
    def _save_settings(self):
        try:
            geo = self.root.geometry()
        except Exception:
            geo = None
        if not self._log_collapsed:
            self._log_h = self._current_log_height()
        save_settings({
            "geometry": geo,
            "font_scale": self.font_scale,
            "view": self.current_view,
            "log_height": self._log_h,
            "autoscroll": self.autoscroll,
        })

    def on_close(self):
        if self.busy:
            if not messagebox.askyesno(
                    "确认退出", f"「{self._task_label}」正在执行中。\n\n"
                    "强制退出可能中断当前清理/脚本，是否仍要退出？"):
                return
        self._save_settings()
        try:
            self.root.destroy()
        except Exception:
            pass


# 清理项一句话说明（仅用于界面展示，不影响执行逻辑）
_CLEAN_ITEM_DESC = {
    "a": "删除系统盘根目录下的 *.tmp / *.old / *.bak 等散落临时文件（不递归，速度快）",
    "b": "清空 C:\\Windows\\Temp（正在被占用的文件会自动跳过）",
    "c": "清空当前用户临时目录，安装器与解压残留多在此处",
    "d": "清空所有驱动器的回收站",
    "e": "动态检测 Edge / Chrome / Brave / Opera / Vivaldi / IE 缓存，仅清理实际存在的目录",
    "f": "清除「最近使用的文件」跳转列表记录（不影响文件本身）",
    "g": "⚠ 清理后首次冷启动应用/系统会稍慢，Windows 会自动重建，日常不建议勾选",
    "i": "删除 Explorer 缩略图 *.db，下次浏览文件夹时重新生成",
    "j": "ipconfig /flushdns，网页打不开时可先试这一项",
    "k": "清理 WER 错误报告队列与存档",
    "m": "清空系统剪贴板内容",
    "h": "停止 wuauserv / bits 后清空 SoftwareDistribution\\Download，再重启服务",
    "l": "删除 MEMORY.DMP / Minidump / LiveKernelReports 蓝转储文件",
    "n": "停止 FontCache 后清理字体缓存，再重启服务",
}


# ────────────── 程序入口 ──────────────
SysCleanTempApp = WinSweepApp   # 兼容旧类名

if __name__ == "__main__":
    app = WinSweepApp()
    app.run()
