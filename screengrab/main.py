"""入口：DPI 感知必须先于 tkinter 导入，所以 app 在函数内延迟导入。"""
from __future__ import annotations

import ctypes
import sys


def main() -> int:
    if sys.platform != "win32":
        print("当前实现基于 Windows（RegisterHotKey / SetWindowPos / GDI 抓屏）。")
        return 1

    from .winutil import acquire_single_instance, enable_dpi_awareness

    enable_dpi_awareness()
    if not acquire_single_instance():
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.MessageBoxW(0, "文字提取已在运行。\n按 Ctrl+Alt+Q 开始框选。",
                           "NineOne Spirits 屏幕取字", 0x40)
        return 0

    from .app import TextGrabberApp

    TextGrabberApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
