"""启动入口（双击、pythonw 或打包成 exe 都走这里）。

打包成窗口程序（PyInstaller --windowed）时，进程没有控制台，
``sys.stdout`` / ``sys.stderr`` 是 ``None``：任何库往它们写日志都会抛
``AttributeError: 'NoneType' object has no attribute 'write'``，表现为双击后
进程闪退。所以这里先把它们接到空设备，再做正事。
"""
import os
import sys

if sys.stdout is None or sys.stderr is None:
    _devnull = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = sys.stdout or _devnull
    sys.stderr = sys.stderr or _devnull

from screengrab.main import main  # noqa: E402  (必须在 stdio 兜底之后导入)

if __name__ == "__main__":
    raise SystemExit(main())
