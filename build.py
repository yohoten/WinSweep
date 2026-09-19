#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WinSweep — 一键打包为可安装的 Windows 安装包（PyInstaller + Inno Setup）

产物
    dist/app/WinSweep.exe                    免安装运行目录（exe + _internal + 依赖）
    dist/installer/WinSweep-<版本>-setup.exe  可安装的安装包（Inno Setup 编译）

为什么 exe 是「启动器」而不是把 .pyw 直接打进 exe
    WinSweep.pyw 用 __file__ 定位同级的 resources / data / README.md / icon.ico。
    若把脚本塞进 PyInstaller 单文件包，__file__ 会指向临时解压目录：
      · resources 找不到（或每次重新解压 16MB）
      · data 落在临时目录，退出即被清理 —— 字号、视图、日志等偏好无法持久化
    因此 exe 只做启动器：读取安装目录下的 WinSweep.pyw，并以
    __file__ = <安装目录>\\WinSweep.pyw 执行，路径语义与双击 .pyw 完全一致。
    附带好处：只有 exe 没有 Python 的机器也能运行；安装目录里的 .pyw 仍可读可改。

用法
    python build.py                    全流程：图标 → exe → 安装包
    python build.py --exe-only         只打包 exe，跳过 Inno Setup
    python build.py --installer-only   复用已有 exe，只编译安装包
    python build.py --onefile          exe 打成单文件（启动略慢，分发更简）
    python build.py --icon-only        只生成 icon.ico
    python build.py --clean            只清理 build/ 与 dist/
    python build.py --open             完成后打开产物目录
    python build.py --version 3.5      覆盖版本号（默认从 WinSweep.pyw 读取）
    python build.py --iscc <路径>      指定 ISCC.exe（默认自动查找）
    python build.py --upx <目录>       使用 UPX 压缩（可能增加杀软误报，默认关闭）
"""

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
import webbrowser
import zlib
from pathlib import Path

# ────────────────────────────── 项目常量 ──────────────────────────────

PROJECT_DIR = Path(__file__).resolve().parent
APP_SCRIPT = PROJECT_DIR / "WinSweep.pyw"          # 主程序（唯一入口，元数据来源）
ICON_FILE = PROJECT_DIR / "icon.ico"               # 由本脚本生成 / 可自行替换
RES_DIR = PROJECT_DIR / "resources"                # 运行期资源（Optimization / Win11Debloat）
README_FILE = PROJECT_DIR / "README.md"            # 「关于」视图的「打开 README」按钮
LANDING_PAGE = PROJECT_DIR / "index.html"          # 落地页（随包分发，可选）

INSTALLER_DIR = PROJECT_DIR / "installer"
ISCC_SCRIPT = INSTALLER_DIR / "WinSweep.iss"       # Inno Setup 脚本（种子模板）
BUILD_META_ISS = INSTALLER_DIR / "build_meta.iss"  # 构建期生成：版本号与开关宏
CHINESE_ISL = INSTALLER_DIR / "languages" / "ChineseSimplified.isl"

BUILD_DIR = PROJECT_DIR / "build"                  # 中间产物（启动器 / 版本资源 / spec）
DIST_DIR = PROJECT_DIR / "dist"
PYI_DIST = DIST_DIR / "pyinstaller"                # PyInstaller 原始输出
STAGE_DIR = DIST_DIR / "app"                       # 暂存目录：安装包唯一来源
INSTALLER_OUT = DIST_DIR / "installer"             # 安装包输出

APP_EXE_NAME = "WinSweep.exe"
LAUNCHER_SRC = BUILD_DIR / "_launcher.py"
VERSION_FILE = BUILD_DIR / "version_info.txt"

# 应用图标：复用 WinSweep.pyw 内置逐像素图标的几何与配色（零第三方依赖）
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICON_BG = "#161B26"
ICON_HANDLE = "#E8ECF4"
ICON_BRUSH = "#37D67A"
ICON_DUST = "#8B949E"

ISCC_CANDIDATES = (
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
)


# ────────────────────────────── 输出辅助 ──────────────────────────────

def _init_console():
    """让 Windows 控制台正确显示中文与符号。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def info(msg):
    print(f"  {msg}")


def ok(msg):
    print(f"  [OK] {msg}")


def warn(msg):
    print(f"  [!!] {msg}")


def fail(msg):
    print(f"\n  [失败] {msg}\n")
    sys.exit(1)


def step(title):
    print(f"\n── {title} " + "─" * max(0, 58 - len(title)))


def human_size(path):
    try:
        size = path.stat().st_size if path.is_file() else _dir_size(path)
    except Exception:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024.0


def _dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


# ────────────────────────────── 元数据 ──────────────────────────────

def read_app_meta():
    """从 WinSweep.pyw 读取应用元数据，避免版本号在两处维护。"""
    if not APP_SCRIPT.is_file():
        fail(f"未找到主程序：{APP_SCRIPT}")
    text = APP_SCRIPT.read_text(encoding="utf-8", errors="replace")

    def grab(pattern, default):
        m = re.search(pattern, text, re.M)
        return m.group(1) if m else default

    meta = {
        "name": grab(r'^APP_NAME\s*=\s*"([^"]+)"', "WinSweep"),
        "version": grab(r'^APP_VERSION\s*=\s*"([^"]+)"', "0.0"),
        "tagline": grab(r'^APP_TAGLINE\s*=\s*"([^"]+)"', ""),
    }
    return meta


def write_build_meta_iss(meta, has_chinese, include_landing, arch_macro, bundle_mode):
    """生成 ISPP 宏文件，供 .iss 包含。

    不通过 ISCC 命令行 /D 传递：命令行宏无法区分数字与字符串
    （`/DFlag=1` 会变成字符串 "1"，与 `#if Flag == 1` 的数值比较冲突），
    也无法安全传递含引号、反斜杠或中文的值。
    """
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_META_ISS.write_text(
        "; 由 build.py 自动生成，请勿手工修改\n"
        "; 版本号以 WinSweep.pyw 的 APP_VERSION 为准\n"
        f'#define MyAppVersion "{meta["version"]}"\n'
        f"#define HasChineseLanguage {1 if has_chinese else 0}\n"
        f"#define IncludeLandingPage {1 if include_landing else 0}\n"
        f'#define ArchAllowed "{arch_macro}"\n'
        f'#define BundleMode "{bundle_mode}"\n',
        encoding="utf-8",
    )
    return BUILD_META_ISS


# ────────────────────────────── 图标生成 ──────────────────────────────

def _hex_rgba(value):
    value = value.lstrip("#")
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return (b, g, r, 255)  # ICO 使用 BGRA 排列


def _icon_pixels(size):
    """在 size×size 网格上按内置扫帚图标几何逐像素着色。

    几何常量沿用 WinSweep.pyw 的 128×128 设计稿，按 size/128 等比缩放，
    使小尺寸图标与大尺寸视觉一致。
    """
    scale = size / 128.0
    bg = _hex_rgba(ICON_BG)
    handle = _hex_rgba(ICON_HANDLE)
    brush = _hex_rgba(ICON_BRUSH)
    dust = _hex_rgba(ICON_DUST)

    def in_seg(px, py, x0, y0, x1, y1, half):
        x0, y0, x1, y1, half = x0 * scale, y0 * scale, x1 * scale, y1 * scale, half * scale
        vx, vy = x1 - x0, y1 - y0
        length2 = vx * vx + vy * vy
        if length2 == 0:
            dx, dy = px - x0, py - y0
        else:
            t = max(0.0, min(1.0, ((px - x0) * vx + (py - y0) * vy) / length2))
            dx, dy = px - (x0 + t * vx), py - (y0 + t * vy)
        return dx * dx + dy * dy <= half * half

    def in_ellipse(px, py, cx, cy, rx, ry):
        cx, cy, rx, ry = cx * scale, cy * scale, rx * scale, ry * scale
        dx, dy = px - cx, py - cy
        return (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry) <= 1.0

    def in_circle(px, py, cx, cy, r):
        cx, cy, r = cx * scale, cy * scale, r * scale
        return (px - cx) ** 2 + (py - cy) ** 2 <= r * r

    brush_x = (66, 72, 78, 84, 90)
    dust_dots = ((18, 16), (12, 26), (46, 10), (24, 40))

    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            color = bg
            if in_seg(px, py, 30, 18, 70, 60, 5) or in_circle(px, py, 30, 18, 6):
                color = handle
            elif in_ellipse(px, py, 78, 74, 24, 12):
                color = brush
            elif py > 84 * scale and any(abs(px - bx * scale) <= 1.6 * scale for bx in brush_x):
                color = brush
            elif any(in_circle(px, py, cx, cy, 2) for cx, cy in dust_dots):
                color = dust
            row.append(color)
        rows.append(row)
    return rows


def _icon_dib(rows, size):
    """32bpp BGRA 的 DIB 数据（BITMAPINFOHEADER + 自下而上的像素 + AND 掩码）。"""
    header = struct.pack(
        "<IiiHHIIiiII",
        40,           # biSize
        size,         # biWidth
        size * 2,     # biHeight（XOR + AND 两段）
        1,            # biPlanes
        32,           # biBitCount
        0,            # biCompression = BI_RGB
        0, 0, 0, 0, 0,
    )
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        for b, g, r, a in rows[y]:
            pixels += bytes((b, g, r, a))
    stride = ((size + 31) // 32) * 4          # AND 掩码按 4 字节对齐
    mask = b"\x00" * (stride * size)          # 有 alpha 通道，掩码全 0
    return header + bytes(pixels) + mask


def _png_bytes(rows, size):
    """把像素行编码为 RGBA PNG；ICO 中 256×256 按规范使用 PNG 更省空间。"""
    raw = bytearray()
    for row in rows:
        raw.append(0)                     # 每行过滤器类型：None
        for b, g, r, a in row:
            raw += bytes((r, g, b, a))

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8bit / RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def write_ico(path, sizes=ICON_SIZES):
    """写出多尺寸 ICO（纯标准库，无需 Pillow）。

    256×256 使用 PNG 压缩（Windows Vista+ 支持），其余尺寸使用 32bpp DIB。
    """
    images = []
    for size in sizes:
        rows = _icon_pixels(size)
        data = _png_bytes(rows, size) if size >= 256 else _icon_dib(rows, size)
        images.append((size, data))
    out = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for size, data in images:
        dim = 0 if size >= 256 else size       # 256 在目录项中写 0
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _size, data in images:
        out += data
    path.write_bytes(bytes(out))
    return path


def make_icon(force=False):
    """生成 icon.ico；已存在且未指定 --force-icon 时保留用户图标。"""
    step("应用图标 icon.ico")
    if ICON_FILE.is_file() and not force:
        ok(f"已存在，保留现有图标：{ICON_FILE.name}（如需重建请加 --force-icon）")
        return ICON_FILE
    write_ico(ICON_FILE)
    ok(f"已生成 {ICON_FILE.name}（{len(ICON_SIZES)} 种尺寸，{human_size(ICON_FILE)}）")
    info("尺寸：" + " / ".join(str(s) for s in ICON_SIZES))
    return ICON_FILE


# ────────────────────────────── 启动器与版本资源 ──────────────────────────────

LAUNCHER_TEMPLATE = '''# -*- coding: utf-8 -*-
"""WinSweep 启动器（由 build.py 自动生成，请勿手工修改）

读取安装目录下的 WinSweep.pyw，并以 __file__ = <安装目录>\\\\WinSweep.pyw 执行，
使 APP_DIR / RES_DIR / DATA_DIR 全部落在安装目录，路径语义与双击 .pyw 完全一致。
"""

import os
import sys

APP_DIR_NAME = "{app_exe_name}"
SCRIPT_NAME = "{script_name}"


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _read_source(app_dir):
    """返回 (源码文本, __file__ 逻辑路径)；找不到时返回 (None, 逻辑路径)。"""
    logical = os.path.join(app_dir, SCRIPT_NAME)
    candidates = [logical]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, SCRIPT_NAME))
    for path in candidates:
        if not os.path.isfile(path):
            continue
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                with open(path, "r", encoding=encoding) as handle:
                    return handle.read(), logical
            except UnicodeDecodeError:
                continue
            except OSError:
                break
    return None, logical


def _alert(message):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "{app_name} 启动失败", 0x10)
    except Exception:
        pass


def main():
    app_dir = _app_dir()
    source, logical = _read_source(app_dir)
    if source is None:
        _alert(
            "未找到主程序 {script_name}\\n\\n"
            "请确认安装目录完整（应有 {script_name} 与 resources 目录）：\\n"
            + app_dir
        )
        return 2

    sys.argv[0] = logical
    namespace = {{
        "__name__": "__main__",
        "__file__": logical,
        "__builtins__": __builtins__,
        "__spec__": None,
        "__package__": None,
        "__loader__": None,
    }}
    exec(compile(source, logical, "exec"), namespace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def write_launcher(meta):
    step("生成启动器")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCHER_SRC.write_text(
        LAUNCHER_TEMPLATE.format(
            app_exe_name=APP_EXE_NAME,
            script_name=APP_SCRIPT.name,
            app_name=meta["name"],
        ),
        encoding="utf-8",
    )
    ok(f"{LAUNCHER_SRC.relative_to(PROJECT_DIR)}（{LAUNCHER_SRC.stat().st_size} B）")


def _version_tuple(version):
    parts = re.findall(r"\d+", version)[:4]
    while len(parts) < 4:
        parts.append("0")
    return tuple(int(p) for p in parts)


def write_version_info(meta):
    """PyInstaller 版本资源：写入 exe 属性，减少“未知发行者”观感。"""
    step("生成 exe 版本资源")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    v = _version_tuple(meta["version"])
    vtext = f"{v[0]}.{v[1]}.{v[2]}.{v[3]}"
    description = f'{meta["name"]} — {meta["tagline"]}' if meta["tagline"] else meta["name"]
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({v[0]}, {v[1]}, {v[2]}, {v[3]}),
    prodvers=({v[0]}, {v[1]}, {v[2]}, {v[3]}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404b0',
        [StringStruct('CompanyName', '{meta["name"]}'),
         StringStruct('FileDescription', '{description}'),
         StringStruct('FileVersion', '{vtext}'),
         StringStruct('InternalName', '{meta["name"]}'),
         StringStruct('OriginalFilename', '{APP_EXE_NAME}'),
         StringStruct('ProductName', '{meta["name"]}'),
         StringStruct('ProductVersion', '{vtext}')])
    ]),
    VarFileInfo([VarStruct('Translation', [0x0804, 1200])])
  ]
)
"""
    VERSION_FILE.write_text(content, encoding="utf-8")
    ok(f"{VERSION_FILE.relative_to(PROJECT_DIR)}（版本 {vtext}）")


# ────────────────────────────── PyInstaller ──────────────────────────────

def ensure_pyinstaller():
    step("检查 PyInstaller")
    try:
        import PyInstaller  # noqa: F401
        ok("已安装")
        return
    except ImportError:
        warn("未安装，正在安装 …")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        ok("安装完成")


def run_pyinstaller(meta, onefile, upx_dir):
    step("PyInstaller 打包 exe")

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile" if onefile else "--onedir",
        "--windowed",                       # 无控制台窗口（.pyw 语义）
        "--name", "WinSweep",
        "--distpath", str(PYI_DIST),
        "--workpath", str(BUILD_DIR / "pyinstaller"),
        "--specpath", str(BUILD_DIR),
        # tkinter 相关模块在运行时动态引用，显式声明避免漏收
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.font",
        "--hidden-import", "tkinter.filedialog",
        "--hidden-import", "tkinter.messagebox",
        # 内嵌一份源码作兜底：仅拷贝 exe 时仍能提示或运行
        "--add-data", f"{APP_SCRIPT}{os.pathsep}.",
        str(LAUNCHER_SRC),
    ]
    if ICON_FILE.is_file():
        args.insert(5, f"--icon={ICON_FILE}")
    else:
        warn(f"未找到 {ICON_FILE.name}，跳过 --icon")
    if VERSION_FILE.is_file():
        args.insert(5, f"--version-file={VERSION_FILE}")
    if upx_dir:
        args.insert(5, f"--upx-dir={upx_dir}")

    info(f"模式：{'单文件 onefile' if onefile else '目录 onedir'}")
    print()
    result = subprocess.run(args, cwd=str(PROJECT_DIR))
    if result.returncode != 0:
        fail("PyInstaller 打包失败，请查看上方输出")


def stage_app(onefile, include_landing):
    """把 PyInstaller 输出与所有运行所需外置文件整理成完整自包含的 dist/app。

    dist/app 既是「免安装运行目录」，也是安装包的唯一内容来源，
    避免安装包文件清单与源目录两处维护、遗漏文件。
    注意：不复制 data/（本机偏好与日志），程序首次运行会自行创建。
    """
    step("暂存运行目录 dist/app")
    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True)

    # 1) PyInstaller 产物：exe 启动器 + 依赖
    if onefile:
        source = PYI_DIST / "WinSweep.exe"
        if not source.is_file():
            fail(f"未找到打包结果：{source}")
        shutil.copy2(str(source), str(STAGE_DIR / APP_EXE_NAME))
    else:
        source = PYI_DIST / "WinSweep"
        if not source.is_dir():
            fail(f"未找到打包结果目录：{source}")
        for item in source.iterdir():
            shutil.move(str(item), str(STAGE_DIR / item.name))

    if not (STAGE_DIR / APP_EXE_NAME).is_file():
        fail(f"暂存目录缺少 {APP_EXE_NAME}")

    # 2) 外置文件：与 WinSweep.pyw 内的 APP_DIR 路径假设一一对应
    externals = [(APP_SCRIPT, APP_SCRIPT.name), (RES_DIR, RES_DIR.name)]
    if ICON_FILE.is_file():
        externals.append((ICON_FILE, ICON_FILE.name))
    if README_FILE.is_file():
        externals.append((README_FILE, README_FILE.name))
    else:
        warn("缺少 README.md —— 程序「关于」视图的「打开 README」将不可用")
    if include_landing and LANDING_PAGE.is_file():
        externals.append((LANDING_PAGE, LANDING_PAGE.name))

    for src, name in externals:
        target = STAGE_DIR / name
        if src.is_dir():
            shutil.copytree(str(src), str(target))
        else:
            shutil.copy2(str(src), str(target))
        info(f"+ {name}")

    ok(f"{STAGE_DIR.relative_to(PROJECT_DIR)}（{human_size(STAGE_DIR)}）")


def verify_app_meta():
    """读取 exe 的产品版本，确认版本资源已写入。"""
    exe = STAGE_DIR / APP_EXE_NAME
    try:
        import ctypes
        from ctypes import wintypes
        version = ctypes.windll.version
        size = version.GetFileVersionInfoSizeW(str(exe), None)
        if not size:
            return
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(exe), 0, size, buffer):
            return
        pointer = ctypes.c_void_p()
        length = wintypes.UINT()
        if not version.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
            return

        class FixedInfo(ctypes.Structure):
            _fields_ = [
                ("dwSignature", wintypes.DWORD),
                ("dwStrucVersion", wintypes.DWORD),
                ("dwFileVersionMS", wintypes.DWORD),
                ("dwFileVersionLS", wintypes.DWORD),
                ("dwProductVersionMS", wintypes.DWORD),
                ("dwProductVersionLS", wintypes.DWORD),
            ]

        fixed = ctypes.cast(pointer, ctypes.POINTER(FixedInfo)).contents
        ms, ls = fixed.dwProductVersionMS, fixed.dwProductVersionLS
        text = f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
        ok(f"exe 产品版本确认：{text}")
    except Exception as exc:
        warn(f"版本资源校验跳过（{exc}）")


# ────────────────────────────── Inno Setup ──────────────────────────────

def find_iscc(explicit=None):
    step("查找 Inno Setup 编译器 ISCC.exe")
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            fail(f"指定的 ISCC.exe 不存在：{path}")
        ok(str(path))
        return path

    for env_name in ("INNO_SETUP_ISCC", "ISCC"):
        candidate = os.environ.get(env_name)
        if candidate and Path(candidate).is_file():
            ok(f"{candidate}（环境变量 {env_name}）")
            return Path(candidate)

    found = shutil.which("ISCC")
    if found:
        ok(f"{found}（PATH）")
        return Path(found)

    for candidate in ISCC_CANDIDATES:
        if Path(candidate).is_file():
            ok(candidate)
            return Path(candidate)

    try:
        import winreg
        key = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as handle:
            location = winreg.QueryValueEx(handle, "InstallLocation")[0]
        candidate = Path(location) / "ISCC.exe"
        if candidate.is_file():
            ok(f"{candidate}（注册表）")
            return Path(candidate)
    except Exception:
        pass

    fail(
        "未找到 Inno Setup 编译器。\n"
        "  安装方式：winget install JRSoftware.InnoSetup\n"
        "  或从 https://jrsoftware.org/isdl.php 安装后重试\n"
        "  也可用 --iscc <ISCC.exe 完整路径> 指定"
    )


def run_inno(meta, iscc, onefile, include_landing, arch_macro, quiet):
    step("Inno Setup 编译安装包")

    if not ISCC_SCRIPT.is_file():
        fail(f"未找到安装脚本：{ISCC_SCRIPT}")

    has_chinese = CHINESE_ISL.is_file()
    if not has_chinese:
        warn("未找到中文语言文件，安装向导将使用英文：")
        info(f"可放入 {CHINESE_ISL.relative_to(PROJECT_DIR)} 后重新编译")

    meta_iss = write_build_meta_iss(
        meta,
        has_chinese,
        include_landing,
        arch_macro,
        "onefile" if onefile else "onedir",
    )
    ok(f"{meta_iss.relative_to(PROJECT_DIR)}")

    INSTALLER_OUT.mkdir(parents=True, exist_ok=True)

    args = [str(iscc)]
    if quiet:
        args.append("/Q")
    args.append(str(ISCC_SCRIPT))

    print()
    result = subprocess.run(args, cwd=str(INSTALLER_DIR))
    if result.returncode != 0:
        fail("Inno Setup 编译失败，请查看上方输出")

    outputs = sorted(INSTALLER_OUT.glob("*.exe"), key=lambda p: p.stat().st_mtime)
    if not outputs:
        fail(f"未在 {INSTALLER_OUT} 找到安装包")
    return outputs[-1]


# ────────────────────────────── 清理与流程 ──────────────────────────────

def clean():
    step("清理中间产物")
    for path in (BUILD_DIR, DIST_DIR):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            info(f"已删除 {path.relative_to(PROJECT_DIR)}")
    if BUILD_META_ISS.exists():
        BUILD_META_ISS.unlink()
        info("已删除 installer/build_meta.iss")
    pycache = PROJECT_DIR / "__pycache__"
    if pycache.exists():
        shutil.rmtree(pycache, ignore_errors=True)
        info("已删除 __pycache__")
    ok("清理完成")


def check_sources(onefile):
    """预检：主程序与资源目录必须存在，否则安装包会缺失运行所需文件。"""
    step("源文件预检")
    if not APP_SCRIPT.is_file():
        fail(f"缺少主程序：{APP_SCRIPT}")
    ok(f"主程序 {APP_SCRIPT.name}（{human_size(APP_SCRIPT)}）")
    if not RES_DIR.is_dir():
        fail(f"缺少资源目录：{RES_DIR}")
    ok(f"资源目录 resources/（{human_size(RES_DIR)}）")
    if not README_FILE.is_file():
        warn("缺少 README.md ——「关于」视图的「打开 README」将不可用")
    if not CHINESE_ISL.is_file():
        warn("缺少中文语言文件，安装向导将显示英文")
    if onefile:
        info("单文件模式：resources 与 WinSweep.pyw 仍外置安装（见 README 说明）")


def main():
    _init_console()

    parser = argparse.ArgumentParser(
        description="WinSweep 打包脚本（PyInstaller + Inno Setup）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--exe-only", action="store_true", help="只打包 exe，跳过安装包编译")
    parser.add_argument("--installer-only", action="store_true", help="复用已有 exe，只编译安装包")
    parser.add_argument("--onefile", action="store_true", help="exe 打成单文件（启动略慢）")
    parser.add_argument("--icon-only", action="store_true", help="只生成 icon.ico")
    parser.add_argument("--clean", action="store_true", help="只清理 build/ 与 dist/")
    parser.add_argument("--force-icon", action="store_true", help="覆盖已存在的 icon.ico")
    parser.add_argument("--no-landing", action="store_true", help="安装包不含 index.html 落地页")
    parser.add_argument("--open", action="store_true", help="完成后打开产物目录")
    parser.add_argument("--quiet", action="store_true", help="隐藏 ISCC 编译细节")
    parser.add_argument("--version", dest="version_override", help="覆盖版本号（默认取 WinSweep.pyw）")
    parser.add_argument("--iscc", help="指定 ISCC.exe 路径")
    parser.add_argument("--upx", dest="upx_dir", help="UPX 目录（默认不压缩）")
    args = parser.parse_args()

    os.chdir(str(PROJECT_DIR))
    meta = read_app_meta()
    if args.version_override:
        meta["version"] = args.version_override

    print("\nWinSweep 打包")
    print(f"  项目目录 : {PROJECT_DIR}")
    print(f"  应用     : {meta['name']} {meta['version']}")

    if args.clean:
        clean()
        return

    if args.icon_only:
        make_icon(force=args.force_icon)
        return

    arch_macro = "x64compatible" if sys.maxsize > 2 ** 32 else "x86compatible"
    include_landing = LANDING_PAGE.is_file() and not args.no_landing
    if not args.installer_only:
        check_sources(args.onefile)

    # ── 1. 图标 ──
    if not args.installer_only:
        make_icon(force=args.force_icon)

    # ── 2. exe ──
    if not args.installer_only:
        ensure_pyinstaller()
        write_launcher(meta)
        write_version_info(meta)
        run_pyinstaller(meta, args.onefile, args.upx_dir)
        stage_app(args.onefile, include_landing)
        verify_app_meta()

    if args.exe_only:
        print("\n完成：仅打包 exe（已跳过安装包）")
        print(f"  免安装运行目录：{STAGE_DIR}")
        print(f"  可直接双击其中的 {APP_EXE_NAME} 运行（会自动请求管理员权限）")
        if args.open:
            _open_dir(STAGE_DIR)
        return

    # ── 3. 安装包 ──
    if not (STAGE_DIR / APP_EXE_NAME).is_file():
        fail(f"暂存目录缺少 {APP_EXE_NAME}，请先执行 python build.py --exe-only")
    iscc = find_iscc(args.iscc)
    installer = run_inno(
        meta, iscc, args.onefile, include_landing, arch_macro, args.quiet
    )

    print("\n构建完成")
    print(f"  免安装目录 : {STAGE_DIR}")
    print(f"  安装包     : {installer}  ({human_size(installer)})")
    if args.open:
        _open_dir(INSTALLER_OUT)


def _open_dir(path):
    try:
        os.startfile(str(path))
    except Exception:
        webbrowser.open(path.as_uri())


if __name__ == "__main__":
    main()
