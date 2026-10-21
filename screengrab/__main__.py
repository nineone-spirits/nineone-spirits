"""让包可以直接跑：`python -m screengrab`（等价于 `python run.py`）。"""
from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
