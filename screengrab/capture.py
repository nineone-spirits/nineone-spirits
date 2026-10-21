"""屏幕抓取：整屏一次性抓到内存，供遮罩实时预览与最终裁剪共用。

关键点：抓图前必须把自己的悬浮球 / 结果窗藏起来，否则会被拍进画面。
"""
from __future__ import annotations

import ctypes

from PIL import Image, ImageGrab

from .winutil import virtual_screen

user32 = ctypes.WinDLL("user32", use_last_error=True)


class ScreenShot:
    """整个虚拟桌面的位图，坐标换算以虚拟屏原点为基准。"""

    def __init__(self, image: Image.Image, origin: tuple[int, int]):
        self.image = image
        self.vx, self.vy = origin

    def crop(self, x0: int, y0: int, x1: int, y1: int) -> Image.Image:
        """按全局屏幕坐标裁剪（自动做虚拟屏原点偏移与边界裁剪）。"""
        x0, x1 = sorted((int(x0), int(x1)))
        y0, y1 = sorted((int(y0), int(y1)))
        lx0 = max(0, x0 - self.vx)
        ly0 = max(0, y0 - self.vy)
        lx1 = min(self.image.width, x1 - self.vx)
        ly1 = min(self.image.height, y1 - self.vy)
        if lx1 <= lx0 or ly1 <= ly0:
            return Image.new("RGB", (1, 1), "white")
        return self.image.crop((lx0, ly0, lx1, ly1))


def grab_all_screens() -> ScreenShot:
    """抓取全部显示器（物理像素，含隐藏窗口过滤）。"""
    vs = virtual_screen()
    image = ImageGrab.grab(all_screens=True)
    # Pillow 的 all_screens 返回的图从虚拟屏左上角开始，宽高与 GetSystemMetrics 一致
    return ScreenShot(image.convert("RGB"), (vs.x, vs.y))


def release_modifiers() -> None:
    """框选前松开 Ctrl/Alt，避免用户按着热键拖动时输入法/软件误响应。"""
    VK_CONTROL, VK_MENU, VK_SHIFT, KEYEVENTF_KEYUP = 0x11, 0x12, 0x10, 0x0002
    for vk in (VK_CONTROL, VK_MENU, VK_SHIFT):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
