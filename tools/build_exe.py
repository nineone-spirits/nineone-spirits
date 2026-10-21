"""把项目打包成单文件 exe（PyInstaller）。

用法：
    .venv\\Scripts\\python tools\\build_exe.py            # 窗口版（发布用）
    .venv\\Scripts\\python tools\\build_exe.py --console  # 带控制台，排错用

产物：dist/TextGrabber.exe（约 110–120 MB）

为什么要额外塞 DLL：PyInstaller 的钩子按 CPython 官方布局找库，而 Anaconda 会把
ffi.dll、tcl86t.dll 等放在 Library\\bin，Tcl 脚本库放在 Library\\lib，
钩子找不到就会在启动时报「DLL load failed while importing _ctypes / _tkinter」。
这里按需探测并补进去，非 Anaconda 环境自动跳过。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(sys.base_prefix)


def main() -> int:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile",
        "--name", "TextGrabber",
        "--icon", str(ROOT / "icon.ico"),
        "--collect-data", "rapidocr",
        "--collect-data", "onnxruntime",
        "--hidden-import", "PIL._tkinter_finder",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        str(ROOT / "run.py"),
    ]
    if "--console" not in sys.argv:
        args.insert(3, "--windowed")

    lib = BASE / "Library" / "bin"
    for dll in ("ffi.dll", "tcl86t.dll", "tk86t.dll", "zlib.dll",
                "libssl-3-x64.dll", "libcrypto-3-x64.dll"):
        path = lib / dll
        if path.is_file():
            args += ["--add-binary", f"{path};."]

    for pkg in ("tcl8.6", "tk8.6"):
        path = BASE / "Library" / "lib" / pkg
        if path.is_dir():
            args += ["--add-data", f"{path};tcl/{pkg}"]

    print(f"解释器 : {sys.executable}")
    print(f"前缀   : {BASE}")
    print(f"模式   : {'console' if '--console' in sys.argv else 'windowed'}")
    return subprocess.run(args, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
