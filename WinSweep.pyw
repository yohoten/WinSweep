#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WinSweep v3.1 - 系统垃圾清理工具 (.pyw)
图形界面版本，双击运行无控制台窗口。
需要管理员权限，如未提权会自动请求。

v3.0 更新：
  * 全新现代深色 UI：品牌栏 / 主次按钮 / 状态栏 + 进度条 / hover 反馈
  * 日志带时间戳、限制最大行数，长时运行不再卡顿
  * 清理前后磁盘空间对比，直观显示本次释放空间
  * 大幅提速：移除全盘 os.walk 扫描、合并子进程调用、非递归清临时文件
  * 支持 Windows 高 DPI 缩放，界面不再模糊

v3.1 更新：
  * 集成 Win11Debloat 系统预装清理，新增"📦 系统预装清理"按钮
  * 弹出预设选择：3 个快速预设一键执行（含二次确认）+ 完整图形界面入口
  * 启动前自动备份 CustomAppsList/SavedSettings；GUI 关闭后自动刷新磁盘信息
  * 启动失败检测并回显错误；隐藏 PowerShell 黑窗
  * 新增"🧰 系统优化"：统一收纳 Optimization/ 下 Neon 优化包（系统备份/关闭Defender/
    电源CPU/设备管理/游戏/键鼠/服务更新/内存硬盘网络/中断延迟/应用优先级）
  * 每项支持打开目录 / 查看说明 / 执行入口（reg 导入、bat/cmd 脚本、exe/lnk 启动，均带二次确认）
  * 项目结构规范化：资源统一收纳 resources/（Optimization/ Win11Debloat/）、
    运行时数据统一 data/、旧备份归档 archive/；路径经 APP_DIR/RES_DIR/DATA_DIR 统一管理
  * 系统优化资源完善：补齐一键脚本（关闭 Defender / 关闭无用服务 / 内存硬盘 / 网络延迟 / HPET），
    修复硬编码路径，每项标注危险等级（低/中/高危）并在执行确认框强化提示
  * UI 优化：主按钮按「清理/系统」分组 + 悬停提示，日志区清空/复制按钮，
    磁盘容量可视化条，进度百分比，F5/Ctrl+L/Ctrl+C 快捷键，执行期间自动禁用按钮
"""

import os
import sys
import glob
import shutil
import stat
import subprocess
import threading
import time
import ctypes
import tempfile
from queue import Queue, Empty
import tkinter as tk
from tkinter import ttk, messagebox

# ────────────── 项目路径（统一基础常量：资源与运行时数据分层） ──────────────
APP_DIR  = os.path.dirname(os.path.abspath(__file__))
RES_DIR  = os.path.join(APP_DIR, "resources")     # 资源目录（Optimization / Win11Debloat）
DATA_DIR = os.path.join(APP_DIR, "data")          # 运行时数据（自动生成）
os.makedirs(DATA_DIR, exist_ok=True)

# ────────────── Win11Debloat 系统预装清理路径 ──────────────
# 已内置到 resources/Win11Debloat/ 子目录（自包含，可整体移动）
WIN11DEBLOAT_DIR  = os.path.join(RES_DIR, "Win11Debloat")
WIN11DEBLOAT_PS1  = os.path.join(WIN11DEBLOAT_DIR, "Win11Debloat.ps1")
WIN11DEBLOAT_GUI  = os.path.join(WIN11DEBLOAT_DIR, "Win11DebloatGUI.ps1")
W11D_LAST_FILE    = os.path.join(DATA_DIR, "w11d_last.txt")

# 系统预装清理快速预设（params 直接传给 Win11Debloat.ps1，追加 -Silent 静默执行）
W11D_PRESETS = [
    {"name": "仅移除默认预装应用", "color": "#F59E0B",
     "params": "-RemoveApps",
     "desc": "移除 Appslist.txt 中列出的默认预装应用（winget / Remove-AppxPackage）"},
    {"name": "禁用遥测、必应、广告与建议", "color": "#F59E0B",
     "params": "-DisableTelemetry -DisableBing -DisableLockscreenTips -DisableSuggestions",
     "desc": "禁用遥测诊断数据、必应搜索/Cortana、锁屏提示、系统建议与广告"},
    {"name": "默认模式（常用组合）", "color": "#3B82F6",
     "params": ("-RemoveApps -DisableTelemetry -DisableBing -DisableLockscreenTips "
                "-DisableSuggestions -ShowKnownFileExt -DisableWidgets -HideChat -DisableCopilot"),
     "desc": "Win11Debloat 官方默认模式：移除预装应用 + 常用隐私/任务栏/资源管理器优化"},
]

# ────────────── Windows 高 DPI 适配（窗口在缩放屏上不模糊） ──────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# ────────────── 主题颜色 ──────────────
BG      = "#0F1115"   # 主背景
BG2     = "#171A21"   # 面板背景
BG3     = "#1E232C"   # 按钮 / 边框
FG      = "#E8EAED"   # 主文字
FG_DIM  = "#8B949E"   # 次要文字
ACCENT  = "#00C896"   # 主色 薄荷绿
ACCENT2 = "#3B82F6"   # 次色 蓝
ORANGE  = "#F59E0B"   # 系统工具
PURPLE  = "#A78BFA"   # 自定义
WARN    = "#F5C542"   # 警告黄
DANGER  = "#FF6B6B"   # 危险红

# 日志文本标签配色
TAG_CONFIGS = {
    "title":   {"foreground": ACCENT2, "font": ("微软雅黑", 10, "bold")},
    "info":    {"foreground": FG,      "font": ("微软雅黑", 9)},
    "success": {"foreground": ACCENT,  "font": ("微软雅黑", 9)},
    "warning": {"foreground": WARN,    "font": ("微软雅黑", 9)},
    "error":   {"foreground": DANGER,  "font": ("微软雅黑", 9)},
    "gray":    {"foreground": FG_DIM,  "font": ("微软雅黑", 9)},
    "bold":    {"foreground": FG,      "font": ("微软雅黑", 9, "bold")},
    "cyan":    {"foreground": ACCENT2, "font": ("微软雅黑", 10, "bold")},
}
FONT_N = ("微软雅黑", 9)
FONT_B = ("微软雅黑", 9, "bold")

MAX_LOG_LINES = 800   # 日志区最大行数，超过后截断前半，防止 Text 无限膨胀变卡
QUEUE_POLL_MS  = 80   # 消息队列轮询间隔


# ══════════════ 通用小工具 ══════════════

def format_size(n):
    """字节数转可读字符串"""
    if n >= 1 << 30:
        return f"{n / (1 << 30):.2f} GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.0f} KB"
    return f"{n} B"


def lighten(color, amount=0.18):
    """颜色加亮，用于按钮 hover 效果"""
    c = color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))
    return f"#{r:02x}{g:02x}{b:02x}"


def center(win, w, h):
    """使窗口在屏幕居中"""
    win.update_idletasks()
    x = max(0, (win.winfo_screenwidth() - w) // 2)
    y = max(0, (win.winfo_screenheight() - h) // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")


class ToolTip:
    """简单悬停提示（零依赖，纯 Tk）"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")

    def _enter(self, e=None):
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        self.tip.configure(bg="#2A2F3A")
        tk.Label(self.tip, text=self.text, bg="#2A2F3A", fg=FG,
                 font=("微软雅黑", 8), padx=8, pady=3).pack()

    def _leave(self, e=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


def make_button(parent, text, command, color, width=13, height=1, tooltip=None):
    """统一样式的扁平按钮，带 hover 加亮、手型光标与可选悬停提示"""
    btn = tk.Button(
        parent, text=text, command=command, bg=color, fg="#FFFFFF",
        activebackground=lighten(color), activeforeground="#FFFFFF",
        relief="flat", bd=0, highlightthickness=0,
        width=width, height=height, cursor="hand2", font=FONT_B,
    )
    btn.bind("<Enter>", lambda e: btn.configure(bg=lighten(color)))
    btn.bind("<Leave>", lambda e: btn.configure(bg=color))
    if tooltip:
        ToolTip(btn, tooltip)
    return btn


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


def get_disk_space():
    """获取磁盘空间信息字符串"""
    drive = get_drive()
    try:
        total, used, free = shutil.disk_usage(drive)
        gb = 1024 ** 3
        pct_free = (free / total) * 100
        info = (
            f"  驱动器:  {drive}\n"
            f"  总大小:  {total / gb:.1f} GB\n"
            f"  已用:    {used / gb:.1f} GB\n"
            f"  可用:    {free / gb:.1f} GB  ({pct_free:.1f}% 可用)"
        )
        old_path = os.path.join(drive, "Windows.old")
        if os.path.exists(old_path):
            info += ("\n  ⚠ 发现 Windows.old 备份目录（可能占 10-30GB）\n"
                     "     请使用 “磁盘清理 → 清理系统文件” 删除")
        return info
    except Exception:
        return "无法获取磁盘信息"


def get_disk_summary():
    """一行磁盘摘要，用于信息栏常驻显示"""
    try:
        total, used, free = shutil.disk_usage(get_drive())
        return f"磁盘 {get_drive()[:-1]}  可用 {format_size(free)} / {format_size(total)}"
    except Exception:
        return "磁盘信息不可用"


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


def clean_browser_cache(log):
    """清理主流浏览器缓存"""
    userprofile = os.environ.get("USERPROFILE", "")
    paths = [
        os.path.join(userprofile, "AppData", "Local", "Microsoft", "Edge", "User Data", "Default", "Cache"),
        os.path.join(userprofile, "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Cache"),
        os.path.join(userprofile, "AppData", "Local", "Microsoft", "Windows", "INetCache"),
        os.path.join(userprofile, "AppData", "Local", "Microsoft", "Internet Explorer"),
    ]
    for p in paths:
        try:
            if os.path.exists(p):
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
        except Exception:
            pass
    log("info", "[清理] 浏览器缓存完成")


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
    {"key": "g", "icon": "⚡", "name": "预读取文件",          "group": "缓存清理", "func": clean_prefetch},
    {"key": "i", "icon": "🖼️", "name": "缩略图缓存",         "group": "缓存清理", "func": clean_thumb_cache},
    {"key": "j", "icon": "🌍", "name": "DNS 缓存",           "group": "缓存清理", "func": clean_dns_cache},
    {"key": "k", "icon": "📋", "name": "Windows 错误报告",   "group": "缓存清理", "func": clean_error_reports},
    {"key": "m", "icon": "📋", "name": "剪贴板",             "group": "缓存清理", "func": clean_clipboard},
    {"key": "h", "icon": "🔄", "name": "Windows 更新缓存",   "group": "系统维护", "func": clean_software_dist},
    {"key": "l", "icon": "💾", "name": "内存转储文件",       "group": "系统维护", "func": clean_memory_dump},
    {"key": "n", "icon": "🔤", "name": "字体缓存",           "group": "系统维护", "func": clean_font_cache},
]
CLEAN_BY_KEY = {it["key"]: it for it in CLEAN_ITEMS}

QUICK_KEYS = ["a", "b", "c", "d", "e", "f", "g", "h"]   # 快速清理组合
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


# ────────────── GUI 应用程序 ──────────────
class SysCleanTempApp:
    def __init__(self):
        # 先确保管理员权限
        run_as_admin()

        self.root = tk.Tk()
        self.root.title("WinSweep - 系统垃圾清理工具")
        self.root.configure(bg=BG)
        self._size_to_screen()
        self._set_icon()

        self.queue = Queue()
        self.busy = False   # 是否正在执行清理（防止并发点击）

        self._setup_style()
        self.create_widgets()
        self.root.after(QUEUE_POLL_MS, self.process_queue)
        self.root.after(200, self.show_disk_info_on_start)
        self.root.mainloop()

    def _size_to_screen(self):
        """按屏幕逻辑分辨率自适应初始尺寸：
        - 大屏（≥1920 逻辑宽）取上限 1020×840，更舒展
        - 小屏 / 高 DPI（如 1366×768@125% 逻辑高仅 614）自动收缩，防止溢出屏幕
        """
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = min(1020, max(720, int(sw * 0.80)))
        h = min(840, max(520, int(sh * 0.84)))
        self.root.minsize(min(720, sw), min(520, sh))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _set_icon(self):
        """设置窗口图标：
        1) 优先加载同目录 icon.ico（用户可自定义）；
        2) 否则用内置逐像素绘制的“扫帚”图标，零依赖开箱即用。
        """
        here = APP_DIR
        ico = os.path.join(here, "icon.ico")
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
        BG_C, HANDLE, BRUSH, DUST = "#1E232C", "#E8EAED", "#00C896", "#8B949E"

        def in_seg(px, py, x0, y0, x1, y1, half):
            """点到线段距离 <= half"""
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

        brush_x = (66, 72, 78, 84, 90)   # 刷毛的 5 条竖线 X 坐标
        dust = ((18, 16), (12, 26), (46, 10), (24, 40))   # 灰尘点
        for y in range(S):
            row = []
            for x in range(S):
                px, py = x + 0.5, y + 0.5
                c = BG_C
                if in_seg(px, py, 30, 18, 70, 60, 5) or in_circle(px, py, 30, 18, 6):
                    c = HANDLE                                  # 扫帚手柄
                elif in_ellipse(px, py, 78, 74, 24, 12):
                    c = BRUSH                                   # 刷头
                elif py > 84 and any(abs(px - bx) <= 1.6 for bx in brush_x):
                    c = BRUSH                                   # 刷毛
                elif any(in_circle(px, py, cx, cy, 2) for cx, cy in dust):
                    c = DUST                                    # 灰尘
                row.append(c)
            # 合并连续同色段为矩形 put。
            # 注意：Tk 在 Windows 上不支持 put() 的多像素字符串（只认第一个颜色），
            # 必须用 to=(x1,y1,x2,y2) 按颜色段分块填充。
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
        """配置 ttk 主题（进度条配色）"""
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "TProgressbar", background=ACCENT, troughcolor=BG3,
            bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT, thickness=8,
        )
        style.configure(
            "Vertical.TScrollbar", background=BG3, troughcolor=BG,
            bordercolor=BG, arrowcolor=FG_DIM,
        )

    # ────────────── 界面搭建 ──────────────
    def create_widgets(self):
        # —— 品牌栏 ——
        header = tk.Frame(self.root, bg=BG2)
        header.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(
            header, text="🧹  WinSweep", fg=ACCENT, bg=BG2,
            font=("微软雅黑", 15, "bold"),
        ).pack(side="left", padx=(12, 0), pady=10)
        tk.Label(
            header, text="系统垃圾文件清理工具  v3.1", fg=FG_DIM, bg=BG2,
            font=("微软雅黑", 9),
        ).pack(side="left", padx=(10, 0), pady=10)

        # —— 信息栏：时间 / 管理员状态 / 磁盘摘要 ——
        info_bar = tk.Frame(self.root, bg=BG)
        info_bar.pack(fill="x", padx=14, pady=(8, 0))
        self.time_label = tk.Label(info_bar, text="", fg=FG_DIM, bg=BG, font=FONT_N)
        self.time_label.pack(side="left")
        admin_ok = is_admin()
        self.admin_label = tk.Label(
            info_bar,
            text="●  管理员模式：已启用" if admin_ok else "●  管理员模式：未启用",
            fg=ACCENT if admin_ok else WARN, bg=BG, font=FONT_N,
        )
        self.admin_label.pack(side="left", padx=(20, 0))
        self.disk_label = tk.Label(info_bar, text="", fg=FG_DIM, bg=BG, font=FONT_N)
        self.disk_label.pack(side="right")
        self.disk_canvas = tk.Canvas(info_bar, width=140, height=10,
                                     bg=BG, highlightthickness=0)
        self.disk_canvas.pack(side="right", padx=(8, 0), pady=2)

        # —— 日志输出区（含工具按钮行） ——
        output_panel = tk.Frame(self.root, bg=BG2)
        output_panel.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        log_tools = tk.Frame(output_panel, bg=BG2)
        log_tools.pack(fill="x", pady=(2, 0))
        tk.Label(
            log_tools, text="执行日志", fg=FG_DIM, bg=BG2,
            font=("微软雅黑", 8, "bold"),
        ).pack(side="left", padx=(6, 0))
        make_button(log_tools, "🗑 清空", self.clear_log,
                    "#2D3748", width=6, height=1,
                    tooltip="清空日志区内容").pack(side="right", padx=2, pady=1)
        make_button(log_tools, "📋 复制", self.copy_log,
                    "#2D3748", width=6, height=1,
                    tooltip="复制全部日志到剪贴板").pack(side="right", padx=2, pady=1)
        text_frame = tk.Frame(output_panel, bg=BG2)
        text_frame.pack(fill="both", expand=True)
        self.output_text = tk.Text(
            text_frame, bg=BG2, fg=FG, insertbackground=FG,
            wrap="word", state=tk.DISABLED, font=FONT_N,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=BG3, highlightcolor=ACCENT2,
            padx=10, pady=8, spacing1=1, spacing3=1,
        )
        scrollbar = ttk.Scrollbar(
            text_frame, orient="vertical", command=self.output_text.yview,
            style="Vertical.TScrollbar",
        )
        self.output_text.configure(yscrollcommand=scrollbar.set)
        self.output_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for tag, config in TAG_CONFIGS.items():
            self.output_text.tag_configure(tag, **config)

        # —— 操作按钮区（按职责分组：清理 / 系统） ——
        btn_panel = tk.Frame(self.root, bg=BG)
        btn_panel.pack(fill="x", padx=10, pady=(10, 4))
        self.action_buttons = []

        def _group(title, color):
            grp = tk.LabelFrame(
                btn_panel, text=f"  {title}  ", bg=BG, fg=color,
                font=("微软雅黑", 9, "bold"),
                relief="groove", bd=1, highlightthickness=0,
            )
            grp.pack(fill="x", padx=2, pady=(2, 4))
            return grp

        def _abtn(parent, text, cmd, color, tip):
            b = make_button(parent, text, cmd, color, tooltip=tip)
            b.pack(side="left", padx=3, pady=4)
            self.action_buttons.append(b)
            return b

        grp_clean = _group("🧹 清理", ACCENT)
        _abtn(grp_clean, "⚡ 快速清理", self.quick_clean, ACCENT, "清理 8 项常用缓存（安全项）")
        _abtn(grp_clean, "🚀 深度清理", self.deep_clean, ACCENT2, "清理全部 14 项 + 检查 Windows.old")
        _abtn(grp_clean, "🎯 自定义清理", self.custom_clean, PURPLE, "勾选要清理的项目")
        _abtn(grp_clean, "📦 系统预装清理", self.win11debloat_menu, "#8B5CF6", "移除 Win11 预装应用 / 系统优化")

        grp_sys = _group("🛠 系统", ORANGE)
        _abtn(grp_sys, "🧰 系统优化", self.system_optimize_menu, "#06B6D4", "Neon 优化包：电源/游戏/键鼠/服务等")
        _abtn(grp_sys, "💽 磁盘空间", self.show_disk_space, "#64748B", "查看磁盘空间详情")
        _abtn(grp_sys, "🛠 系统工具", self.tools_menu, ORANGE, "DISM / SFC / chkdsk 等")
        _abtn(grp_sys, "❌ 退出", self.root.quit, DANGER, "退出程序")

        hint = tk.Label(
            btn_panel, text="清理区执行缓存清理；系统区为系统级操作（多需管理员确认）。",
            fg=FG_DIM, bg=BG, font=("微软雅黑", 8), anchor="w",
        )
        hint.pack(fill="x", padx=3, pady=(2, 0))

        # —— 底部状态栏 + 进度条 ——
        status_panel = tk.Frame(self.root, bg=BG2)
        status_panel.pack(fill="x", side="bottom", padx=10, pady=(6, 10))
        self.status_label = tk.Label(
            status_panel, text="就绪", fg=FG_DIM, bg=BG2,
            font=FONT_N, anchor="w",
        )
        self.status_label.pack(side="left", padx=12, fill="x", expand=True, pady=4)
        self.progress_label = tk.Label(
            status_panel, text="0%", fg=FG_DIM, bg=BG2, font=FONT_N,
        )
        self.progress_label.pack(side="right", padx=(0, 4), pady=4)
        self.progress = ttk.Progressbar(status_panel, style="TProgressbar",
                                        length=200, mode="determinate")
        self.progress.pack(side="right", padx=12, pady=4)

        # —— 键盘快捷键 ——
        self.root.bind("<F5>", lambda e: self.update_time())
        self.root.bind("<Control-l>", lambda e: self.clear_log())
        self.root.bind("<Control-c>", lambda e: self.copy_log())

    # ────────────── 日志 / 队列 ──────────────
    def clear_log(self):
        """清空日志区"""
        self.output_text.configure(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.configure(state=tk.DISABLED)
        self.log("info", "  日志已清空")

    def copy_log(self):
        """复制全部日志到剪贴板"""
        content = self.output_text.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.log("info", "  日志已复制到剪贴板")

    def _set_action_buttons(self, enabled):
        """启用/禁用主操作按钮（执行期间防误点）"""
        state = tk.NORMAL if enabled else tk.DISABLED
        for btn in getattr(self, "action_buttons", []):
            try:
                btn.config(state=state)
            except Exception:
                pass

    def log(self, tag, message):
        """将日志消息放入队列，主线程定时取出更新文本框（线程安全）"""
        self.queue.put((tag, message))

    def set_status(self, text, fraction=0.0):
        """更新状态栏与进度条（线程安全，经队列中转）"""
        self.queue.put(("__status__", (text, min(max(fraction, 0.0), 1.0))))

    def _append_log(self, tag, message):
        ts = time.strftime("%H:%M:%S")
        self.output_text.configure(state=tk.NORMAL)
        self.output_text.insert(tk.END, f"[{ts}] {message}\n", tag)
        # 限制最大行数，超过后截断前半，防止 Text 无限增长拖慢界面
        line_count = int(self.output_text.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_LINES:
            self.output_text.delete("1.0", f"{line_count // 2}.0")
        self.output_text.see(tk.END)
        self.output_text.configure(state=tk.DISABLED)

    def process_queue(self):
        """一次性批量取空队列，减少 UI 刷新开销"""
        try:
            while True:
                tag, data = self.queue.get_nowait()
                if tag == "__status__":
                    text, fraction = data
                    self.status_label.config(text=text, fg=FG if fraction < 1 else ACCENT)
                    self.progress["value"] = fraction * 100
                    self.progress_label.config(text=f"{int(fraction * 100)}%")
                else:
                    self._append_log(tag, data)
        except Empty:
            pass
        self.root.after(QUEUE_POLL_MS, self.process_queue)

    def update_time(self):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.config(text=f"当前时间: {now}")
        self.disk_label.config(text=get_disk_summary())
        self._update_disk_bar()
        self.root.after(1000, self.update_time)

    def _update_disk_bar(self):
        """重绘磁盘容量可视化条"""
        try:
            total, used, free = shutil.disk_usage(get_drive())
            frac = used / total
            c = self.disk_canvas
            c.delete("all")
            w = c.winfo_width() or 140
            c.create_rectangle(0, 0, w, 10, fill=BG3, outline="")
            c.create_rectangle(0, 0, max(1, int(w * frac)), 10,
                               fill=ACCENT if frac < 0.85 else WARN, outline="")
        except Exception:
            pass

    def show_disk_info_on_start(self):
        self.update_time()
        self.log("cyan", "━━━━━━ WinSweep v3.1 ━━━━━━")
        self.log("gray", get_disk_space())
        last = self._last_w11d_time()
        if last:
            self.log("gray", f"上次系统预装清理：{last}（可点「📦 系统预装清理」再次清理）")
        else:
            self.log("gray", "提示：深度清理耗时更长；DISM / sfc 在“系统工具”中单独使用；“系统预装清理”可移除 Win11 预装应用。")

    def run_in_thread(self, target):
        """在新线程中执行任务（统一管理 busy 与按钮状态，避免界面冻结）"""
        if self.busy:
            messagebox.showwarning("提示", "已有任务正在执行，请稍候…")
            return False
        self.busy = True
        self.progress["value"] = 0
        self.progress_label.config(text="0%")
        self._set_action_buttons(False)

        def _wrapper():
            try:
                target()
            finally:
                self.busy = False
                self.root.after(0, lambda: self._set_action_buttons(True))

        threading.Thread(target=_wrapper, daemon=True).start()
        return True

    # ────────────── 清理执行循环 ──────────────
    def _run_items(self, items, mode_name):
        """统一执行清理项：逐个执行 + 进度 + 磁盘空间对比"""
        total = len(items)
        start_free = get_free_bytes()
        self.log("cyan", f"━━━━━━ {mode_name}（共 {total} 项） ━━━━━━")
        for i, it in enumerate(items, 1):
            name = f"{it['icon']} {it['name']}"
            self.log("info", f"▶ [{i}/{total}] {name}")
            self.set_status(f"正在清理：{name}  ({i}/{total})", i / total)
            try:
                it["func"](self.log)
            except Exception as e:
                self.log("error", f"  ✗ {it['name']} 清理失败：{e}")

        freed = get_free_bytes() - start_free
        if freed > 0:
            self.log("success", f"✔ {mode_name}完成，本次释放约 {format_size(freed)} 空间")
        else:
            self.log("success", f"✔ {mode_name}完成")
        self.set_status("完成", 1.0)
        self.busy = False

    # ────────────── 清理任务组合 ──────────────
    def quick_clean(self):
        items = [CLEAN_BY_KEY[k] for k in QUICK_KEYS]
        if self.run_in_thread(lambda: self._run_items(items, "快速清理")):
            self.set_status("正在启动快速清理…", 0)

    def deep_clean(self):
        self.log("warning", "  注意：深度清理将清除更多系统缓存，可能需要更长时间")
        items = list(CLEAN_ITEMS)
        if self.run_in_thread(
            lambda: (self._run_items(items, "深度清理"), check_old_windows(self.log))
        ):
            self.set_status("正在启动深度清理…", 0)

    def system_optimize_menu(self):
        """系统优化 — 统一入口：列出 Optimization/ 下全部优化项，支持打开目录 / 说明 / 执行"""
        win = tk.Toplevel(self.root)
        win.title("系统优化 (Neon 优化包)")
        win.configure(bg=BG)
        center(win, 640, 560)
        win.transient(self.root)

        canvas = tk.Canvas(win, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            win, orient="vertical", command=canvas.yview,
            style="Vertical.TScrollbar",
        )
        inner = tk.Frame(canvas, bg=BG)
        inner_window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(14, 0), pady=8)
        scrollbar.pack(side="right", fill="y", pady=8, padx=(0, 6))
        win.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        tk.Label(
            inner, text="▎系统优化资源（打开目录 / 说明文档，或直接执行入口）",
            fg=ACCENT2, bg=BG, font=("微软雅黑", 9, "bold"), anchor="w",
        ).pack(fill="x", padx=6, pady=(6, 4))

        for item in OPT_ITEMS:
            frame = tk.Frame(inner, bg=BG2, highlightbackground=BG3, highlightthickness=1)
            frame.pack(fill="x", padx=4, pady=3)
            name_row = tk.Frame(frame, bg=BG2)
            name_row.pack(fill="x", padx=8, pady=(6, 0))
            tk.Label(
                name_row, text=item["name"], fg=item["color"], bg=BG2,
                font=("微软雅黑", 10, "bold"), anchor="w",
            ).pack(side="left")
            tk.Label(
                name_row,
                text=f"  [{DANGER_LABELS.get(item.get('danger', 'low'), '低危')}]",
                fg=DANGER_COLORS.get(item.get('danger', 'low'), FG_DIM), bg=BG2,
                font=("微软雅黑", 9, "bold"), anchor="w",
            ).pack(side="left")
            tk.Label(
                frame, text=item["desc"], fg=FG_DIM, bg=BG2,
                font=FONT_N, anchor="w", wraplength=520, justify="left",
            ).pack(fill="x", padx=8, pady=(2, 0))
            btns = tk.Frame(frame, bg=BG2)
            btns.pack(fill="x", padx=6, pady=(4, 6))
            make_button(btns, "📂 打开目录",
                        lambda i=item: opt_open_dir(self.log, i), "#2D3748", width=10).pack(side="left", padx=2)
            if item["readme"]:
                make_button(btns, "📄 查看说明",
                            lambda i=item: opt_open_readme(self.log, i), "#2D3748", width=10).pack(side="left", padx=2)
            for label, fname, kind in item["entries"]:
                make_button(
                    btns, f"▶ {label}",
                    lambda i=item, f=fname, k=kind, l=label: self._opt_exec_confirm(i, f, k, l),
                    item["color"], width=16,
                ).pack(side="left", padx=2)

        def close():
            win.unbind_all("<MouseWheel>")
            win.destroy()

        make_button(win, "关闭", close, DANGER, width=15).pack(side="bottom", pady=(4, 10))
        win.protocol("WM_DELETE_WINDOW", close)

    def _opt_exec_confirm(self, item, fname, kind, label):
        """执行优化项入口前二次确认（按危险等级强化提示）"""
        risk_note = {
            "reg": "\n\n将导入注册表文件（更改系统设置，不可逆）。",
            "bat": "\n\n将运行脚本（可能弹窗请求操作）。",
            "cmd": "\n\n将运行命令脚本（可能弹窗请求操作）。",
            "ps1": "\n\n将以 PowerShell 运行脚本（可能弹窗请求操作）。",
            "exe": "\n\n将启动第三方程序（系统级工具，请按说明操作）。",
            "lnk": "\n\n将打开快捷方式目标。",
        }.get(kind, "")
        danger = item.get("danger", "low")
        danger_note = {
            "high": "\n\n⚠️ 高危操作：可能影响系统安全/稳定性，建议先创建系统还原点。",
            "medium": "\n\n⚠️ 中危操作：修改系统设置，请先阅读说明文档。",
            "low": "",
        }.get(danger, "")
        if not messagebox.askyesno(
            "确认执行",
            f"{item['name']} → {label}\n文件：{fname}{risk_note}{danger_note}\n\n是否继续？"
        ):
            return
        opt_execute(self.log, item, label, fname, kind)

    def win11debloat_menu(self):
        """系统预装清理 — 弹出预设选择窗口：快速预设一键执行 + 完整图形界面"""
        win = tk.Toplevel(self.root)
        win.title("系统预装清理")
        win.configure(bg=BG)
        center(win, 420, 330)
        win.resizable(False, False)
        win.transient(self.root)

        tk.Label(
            win, text="⚡ 快速预设（一键执行，删除应用不可逆）", fg=WARN,
            bg=BG, font=("微软雅黑", 10, "bold"), anchor="w",
        ).pack(fill="x", padx=20, pady=(14, 4))

        for i, preset in enumerate(W11D_PRESETS):
            make_button(
                win, f"  {preset['name']}",
                lambda idx=i: self._w11d_preset_confirm(win, idx),
                preset["color"], width=40,
            ).pack(fill="x", padx=20, pady=3)

        tk.Label(
            win, text="完整功能", fg=FG_DIM, bg=BG,
            font=("微软雅黑", 10, "bold"), anchor="w",
        ).pack(fill="x", padx=20, pady=(10, 2))
        make_button(
            win, "🖥  打开完整图形界面",
            lambda: self._w11d_open_gui(win), PURPLE, width=40,
        ).pack(fill="x", padx=20, pady=3)
        make_button(win, "关闭", win.destroy, DANGER, width=15).pack(fill="x", padx=20, pady=(8, 14))

    def _w11d_preset_confirm(self, win, idx):
        """预设执行前二次确认（删除/更改不可逆）"""
        preset = W11D_PRESETS[idx]
        win.destroy()
        if not messagebox.askyesno(
            "确认执行",
            f"将执行：{preset['name']}\n\n{preset['desc']}\n\n"
            "更改不可逆，部分设置需要重启后完全生效。\n是否继续？"
        ):
            return
        if self.run_in_thread(
            lambda: run_win11debloat_preset(self.log, preset["params"], preset["name"])
        ):
            self.set_status(f"正在执行系统预装清理：{preset['name']}…", 0)

    def _w11d_open_gui(self, win):
        """启动 Win11Debloat 完整图形界面，并轮询检测启动失败 / 关闭联动"""
        win.destroy()
        if not os.path.isfile(WIN11DEBLOAT_GUI):
            messagebox.showwarning(
                "提示",
                f"未找到 Win11DebloatGUI.ps1\n预期路径: {WIN11DEBLOAT_GUI}\n\n请确认 Win11Debloat 目录完整。"
            )
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
            # 仍在运行：超过 1.5s 即认为已成功启动
            if not self.w11d_success_logged and time.time() - self.w11d_started > 1.5:
                self.w11d_success_logged = True
                self.log("success", "✔ Win11Debloat 图形界面已启动")
                self.set_status("系统预装清理界面运行中…", 0)
            self.root.after(1500, self._poll_w11d)
            return

        # 进程已退出
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
            # 快速退出 = 启动失败
            self.log("error", "[系统预装清理] Win11Debloat 图形界面启动失败")
            if err_text.strip():
                for line in err_text.strip().splitlines():
                    if line.strip():
                        self.log("error", f"  {line.strip()}")
        else:
            # 正常关闭：记录时间并刷新磁盘信息
            try:
                with open(W11D_LAST_FILE, "w", encoding="utf-8") as fh:
                    fh.write(time.strftime("%Y-%m-%d %H:%M:%S"))
            except Exception:
                pass
            self.log("info", "[系统预装清理] Win11Debloat 图形界面已关闭")
            self.update_time()
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

    def custom_clean(self):
        """打开自定义选择窗口（带滚动、分组、推荐预设）"""
        win = tk.Toplevel(self.root)
        win.title("自定义清理 - 选择项目")
        win.configure(bg=BG)
        center(win, 430, 560)
        win.resizable(False, False)
        win.transient(self.root)

        # 分组标题配色
        GROUP_COLORS = {"缓存清理": ACCENT, "系统维护": ORANGE}

        canvas = tk.Canvas(win, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview,
                                  style="Vertical.TScrollbar")
        inner = tk.Frame(canvas, bg=BG)
        inner_window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(14, 0), pady=8)
        scrollbar.pack(side="right", fill="y", pady=8, padx=(0, 6))
        win.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        # 复选框变量
        vars_dict = {}
        current_group = None
        for it in CLEAN_ITEMS:
            if it["group"] != current_group:
                current_group = it["group"]
                tk.Label(
                    inner, text=f"▎{current_group}", fg=GROUP_COLORS[current_group],
                    bg=BG, font=("微软雅黑", 9, "bold"), anchor="w",
                ).pack(fill="x", padx=4, pady=(8, 2))
            var = tk.IntVar()
            cb = tk.Checkbutton(
                inner, text=f"{it['icon']}  {it['name']}", variable=var,
                fg=FG, bg=BG, selectcolor=BG2,
                activebackground=BG, activeforeground=ACCENT,
                font=FONT_N, anchor="w", highlightthickness=0, cursor="hand2",
            )
            cb.pack(fill="x", padx=6, pady=1)
            vars_dict[it["key"]] = var

        # 操作行
        def select_all():
            for var in vars_dict.values():
                var.set(1)

        def deselect_all():
            for var in vars_dict.values():
                var.set(0)

        def recommend():
            # 推荐 = 全部缓存清理（安全项）
            for k, var in vars_dict.items():
                var.set(1 if CLEAN_BY_KEY[k]["group"] == "缓存清理" else 0)

        btn_frame = tk.Frame(win, bg=BG)
        btn_frame.pack(fill="x", padx=14, pady=(0, 6))
        make_button(btn_frame, "全选",     select_all, "#2D3748", width=8).pack(side="left", padx=3)
        make_button(btn_frame, "推荐",     recommend,  ACCENT,   width=8).pack(side="left", padx=3)
        make_button(btn_frame, "取消全选", deselect_all, "#2D3748", width=8).pack(side="left", padx=3)

        def close():
            """关闭窗口并解除全局滚轮绑定，防止影响其他窗口"""
            win.unbind_all("<MouseWheel>")
            win.destroy()

        def execute():
            selected = [k for k, var in vars_dict.items() if var.get() == 1]
            if not selected:
                messagebox.showinfo("提示", "未选择任何项目")
                return
            close()
            items = [CLEAN_BY_KEY[k] for k in selected]
            if self.run_in_thread(lambda: self._run_items(items, "自定义清理")):
                self.set_status("正在启动自定义清理…", 0)

        make_button(win, "开始清理", execute, "#006400", width=24).pack(fill="x", padx=14, pady=(0, 4))
        make_button(win, "关闭", close, DANGER, width=24).pack(fill="x", padx=14, pady=(0, 12))
        win.protocol("WM_DELETE_WINDOW", close)

    # ────────────── 系统工具 ──────────────
    def tools_menu(self):
        win = tk.Toplevel(self.root)
        win.title("系统工具")
        win.configure(bg=BG)
        center(win, 340, 300)
        win.resizable(False, False)
        win.transient(self.root)

        tools = [
            ("🧹 打开磁盘清理工具 (cleanmgr)", lambda: start_disk_cleanup(self.log)),
            ("🚿 DISM 组件清理 (WinSxS)", lambda: self.run_in_thread(
                lambda: (run_dism_clean(self.log), setattr(self, "busy", False))
            )),
            ("🩺 系统文件检查 (sfc /scannow)", lambda: self.run_in_thread(
                lambda: (self.run_sfc(), setattr(self, "busy", False))
            )),
            ("💿 检查磁盘错误 (chkdsk /f)", self.run_chkdsk),
        ]
        for text, cmd in tools:
            make_button(win, text, cmd, "#2D3748", width=34).pack(fill="x", padx=20, pady=4)
        make_button(win, "关闭", win.destroy, DANGER, width=15).pack(fill="x", padx=20, pady=(8, 14))

    def run_sfc(self):
        """运行 sfc /scannow"""
        self.log("info", "[调用] 系统文件检查... 此操作可能需要 15-30 分钟")
        result = subprocess.run("sfc /scannow", shell=True, capture_output=True, text=True)
        self.log("success", "系统文件检查完成")
        for line in result.stdout.splitlines()[-5:]:
            self.log("gray", line)

    def run_chkdsk(self):
        """检查磁盘错误（提示将在下次重启执行）"""
        drive = get_drive()
        if messagebox.askyesno("确认", "磁盘检查将在下次重启时执行。是否继续？"):
            subprocess.Popen(f"chkdsk {drive} /f", shell=True)
            self.log("warning", "  磁盘检查已安排，将在系统重启时执行")

    def show_disk_space(self):
        self.log("cyan", "━━━━━━ 磁盘空间信息 ━━━━━━")
        self.log("gray", get_disk_space())


# ────────────── 程序入口 ──────────────
if __name__ == "__main__":
    app = SysCleanTempApp()

