"""Windows 平台底层工具：DPI 感知、窗口定位、显示器枚举、单实例、剪贴板。

所有函数都在物理像素坐标系下工作（PER_MONITOR_AWARE_V2），
因此 Tk 控件坐标 == 截图坐标 == 屏幕坐标，避免高 DPI 缩放导致的框选错位。
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# 64 位下 HWND/HANDLE 是指针宽度，必须显式声明，否则 ctypes 会按 32 位 int 截断句柄
user32.GetParent.restype = ctypes.c_void_p
user32.GetParent.argtypes = [ctypes.c_void_p]
user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
kernel32.CreateMutexW.restype = ctypes.c_void_p
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]

# ---------------------------------------------------------------- DPI 感知
# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def enable_dpi_awareness() -> None:
    """必须在创建任何 Tk 窗口之前调用，否则 125%/150% 缩放下框选区域会偏移。"""
    if sys.platform != "win32":
        return
    try:
        user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        return
    except Exception:
        pass
    try:  # Win8.1 及以上
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except Exception:
        user32.SetProcessDPIAware()


# ---------------------------------------------------------------- 显示器
class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


@dataclass(frozen=True)
class Monitor:
    x: int
    y: int
    w: int
    h: int

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)


def enum_monitors() -> list[Monitor]:
    """枚举所有物理显示器（坐标为物理像素，可为负值，即主屏左侧的副屏）。"""
    monitors: list[Monitor] = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                               ctypes.POINTER(_RECT), wintypes.LPARAM)

    def _cb(hmon, hdc, lprc, data):
        r = lprc.contents
        monitors.append(Monitor(r.left, r.top, r.right - r.left, r.bottom - r.top))
        return 1

    user32.EnumDisplayMonitors(0, 0, proto(_cb), 0)
    if not monitors:  # 兜底：主屏
        w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        monitors.append(Monitor(0, 0, w, h))
    return monitors


@dataclass(frozen=True)
class VirtualScreen:
    x: int
    y: int
    w: int
    h: int


def virtual_screen() -> VirtualScreen:
    """整个桌面（所有显示器拼接）的包围盒，ImageGrab(all_screens=True) 的原点即此。"""
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
    return VirtualScreen(
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


# ---------------------------------------------------------------- 窗口
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040


def hwnd_of(tk_window) -> int:
    """取 Tk 窗口的 HWND（overrideredirect 窗口的 wm_frame 即真实句柄）。"""
    tk_window.update_idletasks()
    try:
        return int(tk_window.wm_frame(), 16)
    except Exception:
        return user32.GetParent(tk_window.winfo_id()) or tk_window.winfo_id()


def place_window(tk_window, x: int, y: int, w: int, h: int, topmost: bool = True) -> None:
    """用 Win32 SetWindowPos 精确摆放窗口。

    不能用 Tk 的 geometry("+-1920+0") —— Tk 会把负值解释为「距右边缘的距离」，
    多显示器（副屏在主屏左侧）时窗口会跑到错误的位置。
    """
    tk_window.update_idletasks()
    hwnd = hwnd_of(tk_window)
    flags = SWP_SHOWWINDOW | SWP_NOACTIVATE
    user32.SetWindowPos(hwnd, HWND_TOPMOST if topmost else 0, int(x), int(y),
                        int(w), int(h), flags)


# ---------------------------------------------------------------- 单实例
ERROR_ALREADY_EXISTS = 183
_mutex_handle = None


def acquire_single_instance(name: str = "Global\\TextGrabber.SingleInstance") -> bool:
    """命名互斥体保证只跑一个实例（重复启动会争抢全局热键）。"""
    global _mutex_handle
    _mutex_handle = kernel32.CreateMutexW(None, True, name)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def focus_window(tk_window) -> None:
    """overrideredirect 窗口默认拿不到焦点，需强制激活才能接收 Esc。"""
    hwnd = hwnd_of(tk_window)
    user32.SetForegroundWindow(hwnd)
    tk_window.focus_force()


# ---------------------------------------------------------------- 剪贴板
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
user32.OpenClipboard.argtypes = [ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]


def set_clipboard_text(text: str) -> bool:
    """直接写 Win32 剪贴板，避免 Tk 在进程退出后丢失内容。

    注意：HGLOBAL 是 64 位指针，必须声明 restype/argtypes，
    否则 ctypes 按 int 截断句柄，GlobalLock 会返回 NULL 导致访问违例。
    """
    CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        data = text.replace("\r\n", "\n").replace("\n", "\r\n")
        buf = data.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(buf))
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return False
        try:
            ctypes.memmove(ptr, buf, len(buf))
        finally:
            kernel32.GlobalUnlock(handle)
        return bool(user32.SetClipboardData(CF_UNICODETEXT, handle))
    finally:
        user32.CloseClipboard()
