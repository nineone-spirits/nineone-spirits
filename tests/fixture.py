"""测试用真实截图的查找。

公开仓库**不附带**真实桌面截图（含个人文件名、任务栏等），所以这类端到端测试
按下面的优先级找图，找不到就跳过：

  1. 环境变量 `TEXTGRABBER_SHOT`
  2. `tests/fixtures/desktop-grid.png`
  3. `tests/fixtures/` 下任意一张 png 作为兜底

需要跑回归时，把自己的截图（4 列桌面图标那种）放到 `tests/fixtures/desktop-grid.png`。
该目录已在 `.gitignore` 里，不会被误提交。
"""
from __future__ import annotations

import os
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ENV = "TEXTGRABBER_SHOT"


def shot_path(name: str = "desktop-grid.png") -> Path | None:
    """返回可用的截图路径；一个都找不到时返回 None。"""
    env = os.environ.get(ENV)
    if env and Path(env).is_file():
        return Path(env)
    target = FIXTURES / name
    if target.is_file():
        return target
    if FIXTURES.is_dir():
        for png in sorted(FIXTURES.glob("*.png")):
            return png
    return None


def skip_note(name: str = "desktop-grid.png") -> str:
    return (f"跳过：找不到真实截图。把桌面图标网格截图放到 tests/fixtures/{name}，"
            f"或设置环境变量 {ENV} 指向它（详见 tests/fixture.py）。")
