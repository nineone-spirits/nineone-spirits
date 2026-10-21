"""测试用字体查找：拿不到能渲染中文的字体时，让依赖字形的用例优雅跳过。

为什么需要这个：GitHub 的 `windows-latest` 镜像默认不带中文字体，Arial 渲染汉字
得到的是空心方框，OCR 认出来是乱码，断言必挂。而这类用例要验证的是「识别 + 拼版」
对不对，不该因为跑测试的机器没装中文字体就判失败。

判定方式看**字体族名**而不是文件名：候选文件名的列表不可避免会漏，
族名里带 yahei / simhei / simsun / noto sans cjk 之类才说明真的能渲染中文。

`TEXTGRABBER_NO_CJK_FONT=1` 可强制走「没有中文字体」的分支，用来验证降级路径本身。
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import ImageFont

# 常见中文字体文件名（只是候选入口，最终以族名为准）
CANDIDATES = (
    "msyh.ttc", "msyhbd.ttc", "msyhl.ttc", "simhei.ttf", "simsun.ttc", "simkai.ttf",
    "Deng.ttf", "msjh.ttc", "YuGothM.ttc", "NotoSansCJK-Regular.ttc",
    "SourceHanSansSC-Regular.otf", "wqy-microhei.ttc", "PingFang.ttc",
)
FONT_DIRS = (
    Path("C:/Windows/Fonts"),
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
    Path("/usr/share/fonts"),
    Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
)
# 字体族名里出现这些词，基本可以认定能渲染中文
CJK_FAMILY_HINTS = (
    "yahei", "simhei", "simsun", "nsimsun", "jhenghei", "dengxian", "kaiti",
    "fangsong", "ms gothic", "ms mincho", "meiryo", "yu gothic", "noto sans cjk",
    "noto serif cjk", "source han", "wenquanyi", "pingfang",
)


def _family(font) -> str:
    try:
        name = font.getname() or ()
        return " ".join(str(x) for x in name if x).lower()
    except Exception:                     # 少数字体没有 name 表
        return ""


def cjk_font(size: int):
    """返回一个能渲染中文的字体对象；环境里没有则返回 None。"""
    if os.environ.get("TEXTGRABBER_NO_CJK_FONT") == "1":
        return None
    seen: set[str] = set()
    for directory in FONT_DIRS:
        for name in CANDIDATES:
            path = directory / name
            key = str(path).lower()
            if key in seen or not path.is_file():
                continue
            seen.add(key)
            try:
                font = ImageFont.truetype(str(path), size)
            except OSError:
                continue
            if any(hint in _family(font) for hint in CJK_FAMILY_HINTS):
                return font
    return None


def has_cjk_font() -> bool:
    return cjk_font(24) is not None


def skip_note(what: str = "依赖中文字形的用例") -> str:
    return (f"跳过：本机没有可渲染中文的字体，{what}无法执行。"
            f"装上中文字体（Windows：设置 → 时间和语言 → 语言 → 添加中文）后重跑即可。")
