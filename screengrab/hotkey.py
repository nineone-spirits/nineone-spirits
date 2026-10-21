"""全局热键：RegisterHotKey + 独立消息循环线程。

相比键盘钩子（SetWindowsHookEx / 第三方 keyboard 库），RegisterHotKey 更轻、
不需要管理员权限、不会被输入法吞掉，也不存在被安全软件判定为键盘记录器的风险。
代价是组合键必须包含 Win / Ctrl / Alt / Shift 中的一个修饰键。
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_MOD_NAMES = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
              "shift": MOD_SHIFT, "win": MOD_WIN}

# 命名键的虚拟键码。字母/数字/符号走 VkKeyScanW，功能键等必须查表，
# 否则 "f9" 会被 VkKeyScanW 当成首字母 'f'（注册成 Ctrl+Alt+F，静默错位）。
_VK_NAMED = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "backspace": 0x08, "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "pause": 0x13, "capslock": 0x14,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
for _i in range(1, 25):
    _VK_NAMED[f"f{_i}"] = 0x6F + _i


def _vk_of(key: str) -> int:
    if key in _VK_NAMED:
        return _VK_NAMED[key]
    if len(key) == 1:
        vk = user32.VkKeyScanW(ord(key.upper()))
        if vk != -1:
            return vk & 0xFF
    return -1


def parse_hotkey(spec: str) -> tuple[int, int]:
    """"ctrl+alt+q" / "ctrl+shift+f9" -> (modifiers, virtual-key code)"""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"非法热键: {spec!r}")
    *mods, key = parts
    modifiers = MOD_NOREPEAT
    for m in mods:
        if m not in _MOD_NAMES:
            raise ValueError(f"不支持的修饰键: {m!r}")
        modifiers |= _MOD_NAMES[m]
    if modifiers == MOD_NOREPEAT:
        raise ValueError("全局热键必须包含 ctrl/alt/shift/win 之一")
    vk = _vk_of(key)
    if vk == -1:
        raise ValueError(f"无法解析按键: {key!r}")
    return modifiers, vk


class HotkeyManager(threading.Thread):
    """后台线程注册热键并跑消息循环，回调在主线程之外触发，调用方需自行切回 UI 线程。"""

    def __init__(self, bindings: dict[int, tuple[str, callable]]):
        super().__init__(daemon=True, name="hotkey-loop")
        self._bindings = bindings
        self._tid: int | None = None
        self.failed: list[str] = []

    def run(self) -> None:
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)  # 确保本线程消息队列已创建
        self._tid = kernel32.GetCurrentThreadId()
        for hid, (spec, _cb) in self._bindings.items():
            try:
                mods, vk = parse_hotkey(spec)
            except ValueError:
                self.failed.append(spec)
                continue
            if not user32.RegisterHotKey(None, hid, mods, vk):
                self.failed.append(spec)  # 被其它程序占用

        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                entry = self._bindings.get(int(msg.wParam))
                if entry:
                    try:
                        entry[1]()
                    except Exception:
                        pass

        for hid in self._bindings:
            user32.UnregisterHotKey(None, hid)

    def stop(self) -> None:
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
