"""OCR 引擎封装：可插拔后端 + 屏幕文本预处理 + 结果规范化。

选型：默认 rapidocr 3.x（PP-OCRv6 small 的 ONNX 版本）。
  · 中英混排准确率实测最高：西文单词间空格、标点、金额数字都能完整保留
    （旧版 PP-OCRv3 mobile 会把英文空格吃掉，是选型的决定性差异）。
  · 没有 paddlepaddle 这类数百 MB 的框架依赖，onnxruntime CPU 单张 0.5s 左右，
    模型随包分发、纯离线，截屏内容不会离开本机。
  · 后端做了抽象并带降级链：新版 rapidocr → 旧版 rapidocr-onnxruntime → PaddleOCR，
    需要更高精度时可直接切 PaddleOCR 的 server 模型，上层接口不变。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps

from .layout import TextItem, stats
from . import subject


@dataclass
class OcrResult:
    items: list[TextItem] = field(default_factory=list)
    elapsed: float = 0.0
    scale: float = 1.0
    inverted: bool = False
    engine: str = ""

    @property
    def stats(self) -> dict:
        return stats(self.items)


class OcrEngine:
    """后端接口：输入 PIL.Image，输出 [(四点框, 文本, 置信度)]。"""

    name = "base"

    def run(self, image: np.ndarray) -> list[tuple]:
        raise NotImplementedError

    def warmup(self) -> None:
        try:
            self.run(np.full((64, 256, 3), 255, dtype=np.uint8))
        except Exception:
            pass


class RapidOcrEngine(OcrEngine):
    """主后端：rapidocr >= 3.0（PP-OCRv6 small，ONNX Runtime CPU 推理）。

    选它的理由：同一套 PP-OCR 系列模型里新款对「中英混排 + 界面字号」最友好，
    西文单词间的空格、标点都能保住；模型随包分发，完全离线。
    """

    name = "RapidOCR 3.x / PP-OCRv6 (ONNX)"

    def __init__(self) -> None:
        from rapidocr import RapidOCR

        self._ocr = RapidOCR(params={
            "Global.log_level": "error",      # GUI 程序不往控制台刷日志
            "Global.max_side_len": 3000,      # 默认 2000，宽选区会被过度缩小丢细节
        })

    def run(self, image: np.ndarray) -> list[tuple]:
        out = self._ocr(image)
        boxes = getattr(out, "boxes", None)
        txts = getattr(out, "txts", None)
        scores = getattr(out, "scores", None)
        if boxes is None or txts is None:
            return []
        if scores is None:
            scores = [1.0] * len(txts)
        return [[b, t, s] for b, t, s in zip(boxes, txts, scores)]


class LegacyRapidOcrEngine(OcrEngine):
    """兼容后端：rapidocr-onnxruntime 1.x（PP-OCRv3/v4，接口为 (result, elapse)）。"""

    name = "RapidOCR 1.x (PP-OCRv3 ONNX)"

    def __init__(self, det_model: str | None = None, rec_model: str | None = None,
                 cls_model: str | None = None):
        from rapidocr_onnxruntime import RapidOCR

        kwargs = {}
        if det_model:
            kwargs["det_model_path"] = det_model
        if rec_model:
            kwargs["rec_model_path"] = rec_model
        if cls_model:
            kwargs["cls_model_path"] = cls_model
        try:
            self._ocr = RapidOCR(**kwargs)
        except Exception:  # 老版本不支持自定义模型路径
            self._ocr = RapidOCR()

    def run(self, image: np.ndarray) -> list[tuple]:
        out = self._ocr(image)
        result = out[0] if isinstance(out, tuple) else out
        return result or []


class PaddleOcrEngine(OcrEngine):
    """可选后端：装了 paddleocr 才可用，默认走 server 模型精度更高但更慢。"""

    name = "PaddleOCR (server)"

    def __init__(self) -> None:
        from paddleocr import PaddleOCR

        self._ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

    def run(self, image: np.ndarray) -> list[tuple]:
        raw = self._ocr.ocr(image, cls=True)
        out = []
        for page in raw or []:
            for box, (text, score) in page or []:
                out.append([box, text, score])
        return out


def _median_luma(image: Image.Image) -> float:
    small = image.convert("L")
    small.thumbnail((160, 160))
    return float(np.median(np.asarray(small, dtype=np.uint8)))


def preprocess(image: Image.Image, auto_invert: bool = True,
               upscale: float = 1.0) -> tuple[np.ndarray, dict]:
    """屏幕截图 → 模型输入。

    两个针对屏幕文本的关键处理：
      1. 深色主题反色：PP-OCR 的识别模型按「浅底深字」训练，暗色 UI 上的白字识别率
         会明显下降，按背景亮度中位数判断后整体反色，把输入拉回训练分布。
      2. 可选放大：默认 1:1（实测 v6 模型对 9px 原生小字已接近满分，放大反而略降精度、
         且耗时翻倍）；只有在极低分辨率屏幕上才建议用配置项开启。
    """
    meta = {"inverted": False, "scale": upscale}
    if auto_invert and _median_luma(image) < 110:
        image = ImageOps.invert(image.convert("RGB"))
        meta["inverted"] = True
    else:
        image = image.convert("RGB")

    if upscale > 1.01:
        image = image.resize((max(1, int(image.width * upscale)),
                              max(1, int(image.height * upscale))), Image.LANCZOS)
    # RapidOCR 的 ndarray 入参按 BGR 解释
    arr = np.asarray(image, dtype=np.uint8)[:, :, ::-1].copy()
    return arr, meta


class OcrService:
    """负责：懒加载引擎（含降级链）、预热、预处理、结果规范化。"""

    def __init__(self, min_score: float = 0.5, max_side: int = 4000, upscale: float = 1.0):
        self.min_score = min_score
        self.max_side = max_side
        self.upscale = upscale
        self._engine: OcrEngine | None = None

    @property
    def engine(self) -> OcrEngine:
        if self._engine is None:
            self._engine = self._build_engine()
        return self._engine

    def _build_engine(self) -> OcrEngine:
        """按能力降级：新版 rapidocr → 旧版 rapidocr-onnxruntime → PaddleOCR。"""
        errors = []
        for factory in (RapidOcrEngine, LegacyRapidOcrEngine, PaddleOcrEngine):
            try:
                return factory()
            except Exception as exc:  # 未安装 / 模型缺失 / 依赖冲突
                errors.append(f"{factory.__name__}: {exc}")
        raise RuntimeError("没有可用的 OCR 后端；请执行 pip install -r requirements.txt\n"
                           + "\n".join(errors))

    def warmup(self) -> None:
        self.engine.warmup()

    def recognize(self, image: Image.Image) -> OcrResult:
        t0 = time.perf_counter()
        if image.width > self.max_side or image.height > self.max_side:
            image = image.copy()
            image.thumbnail((self.max_side, self.max_side), Image.LANCZOS)

        arr, meta = preprocess(image, upscale=self.upscale)
        raw = self.engine.run(arr)
        items = self._normalize(raw, meta["scale"])
        # 主体过滤要靠「墨迹颜色」判断，必须在未反色的原图上采样：
        # 反色后的像素颜色已经不是用户看到的颜色了。
        try:
            pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
            subject.annotate(pixels, items)
        except Exception:
            pass                    # 采样失败只影响主体过滤，不影响识别结果
        return OcrResult(items=items, elapsed=time.perf_counter() - t0,
                         scale=meta["scale"], inverted=meta["inverted"],
                         engine=self.engine.name)

    def _normalize(self, raw: list[tuple], scale: float) -> list[TextItem]:
        items: list[TextItem] = []
        for entry in raw:
            try:
                quad, text, score = entry[0], entry[1], float(entry[2])
            except (IndexError, TypeError, ValueError):
                continue
            text = (text or "").strip()
            if not text or score < self.min_score:
                continue
            it = TextItem.from_quad(quad, text, score)
            if scale > 1.01:  # 换算回屏幕坐标，便于调试与区域提示
                it = TextItem(it.text, it.x0 / scale, it.y0 / scale,
                              it.x1 / scale, it.y1 / scale, it.score)
            items.append(it)
        return items
