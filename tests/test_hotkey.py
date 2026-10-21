"""全局热键的真实按键测试：注册 → 系统合成按键 → 验证回调被触发。

这是「跨应用调用」的核心链路，必须真按键验证，不能只验证注册成功。
运行：python -m tests.test_hotkey
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screengrab.hotkey import HotkeyManager, parse_hotkey   # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
KEYEVENTF_KEYUP = 0x0002
SPEC = "ctrl+alt+f9"


def press_combo(spec: str) -> None:
    """按 Win32 keybd_event 合成一次组合键，模拟用户在别的软件里按下热键。"""
    mods, vk = parse_hotkey(spec)
    keys = []
    if mods & 0x0002:
        keys.append(0x11)   # Ctrl
    if mods & 0x0001:
        keys.append(0x12)   # Alt
    if mods & 0x0004:
        keys.append(0x10)   # Shift
    for k in keys:
        user32.keybd_event(k, 0, 0, 0)
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    for k in reversed(keys):
        user32.keybd_event(k, 0, KEYEVENTF_KEYUP, 0)


def test_parse() -> None:
    cases = {
        "ctrl+alt+q": (0x0003 | 0x4000, 0x51),
        "ctrl+shift+f9": (0x0006 | 0x4000, 0x78),
        "alt+space": (0x0001 | 0x4000, 0x20),
    }
    for spec, (mods, vk) in cases.items():
        got_mods, got_vk = parse_hotkey(spec)
        assert (got_mods, got_vk) == (mods, vk), f"{spec} -> {(got_mods, got_vk)}"
    for bad in ("q", "ctrl+", "ctrl+alt+不存在"):
        try:
            parse_hotkey(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} 应当解析失败")
    print("[ok] 热键字符串解析（含功能键 / 命名键 / 非法输入）")


def test_fire() -> None:
    fired = threading.Event()
    hk = HotkeyManager({7: (SPEC, fired.set)})
    hk.start()

    deadline = time.time() + 2
    while time.time() < deadline and not hk.failed and hk._tid is None:
        time.sleep(0.02)
    assert not hk.failed, f"热键 {SPEC} 注册失败（可能被占用）: {hk.failed}"

    press_combo(SPEC)
    assert fired.wait(2.0), "注册成功但按键未触发回调"
    print(f"[ok] 真实按键触发回调：{SPEC}")

    # 停止后不应再触发
    hk.stop()
    time.sleep(0.3)
    fired.clear()
    press_combo(SPEC)
    assert not fired.wait(0.6), "热键已注销但仍在响应"
    print("[ok] 注销后不再响应")


if __name__ == "__main__":
    test_parse()
    test_fire()
    print("\n热键链路测试通过")
