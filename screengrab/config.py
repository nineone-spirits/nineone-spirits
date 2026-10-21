"""配置持久化：%APPDATA%/TextGrabber/config.json（纯本地，不上传）。"""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "TextGrabber"

DEFAULTS: dict = {
    "hotkey": "ctrl+alt+q",
    "hotkey_retry": "ctrl+alt+d",
    "layout_mode": "verbatim",   # verbatim | paragraph
    "tidy_enabled": True,        # 识别后自动整理（纠错 / 合段 / 统一标点）
    "result_view": "tidy",       # tidy | raw，结果窗默认展示哪一版
    "min_score": 0.5,
    "auto_invert": True,
    # 主体文字过滤：auto 自动挑主体（大字号/彩色），off 全部保留，
    # large 只留最大字号，red / color:blue 只留指定色系
    "subject_filter": "auto",
    "pill_pos": None,            # [x, y]，None 表示右下角默认位
    "last_region": None,         # [x0, y0, x1, y1] 上次框选区域
    "result_geometry": None,
}


def config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d / "config.json"


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    p = config_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
