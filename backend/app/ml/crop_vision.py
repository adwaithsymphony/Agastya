"""Crop-vision inference service.

The service only reports what the model actually produced. If the model files are missing or
inference fails, it returns an explicit failure status and never fabricates a class or a confidence.
Business decisions (what to tell the farmer, whether review is required) are made by callers.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from app.core.config import get_settings

log = logging.getLogger("agastya.ml")

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


@dataclass
class InferenceResult:
    status: str  # completed | uncertain | unsupported_input | failed
    model_key: str
    model_version: str | None
    predicted_class: str | None = None
    predicted_crop: str | None = None
    predicted_condition: str | None = None
    confidence: float | None = None
    top_k: list[dict] = field(default_factory=list)
    processing_ms: int | None = None
    status_reason: str | None = None
    review_recommended: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def split_class(name: str) -> tuple[str, str]:
    crop, _, cond = name.partition("___")
    crop = crop.replace("_(including_sour)", "").replace(",_bell", " (bell)").replace("_(maize)", " (maize)")
    crop = crop.replace("_", " ").strip()
    cond = cond.replace("_", " ").strip()
    return crop, cond


def preprocess(img: Image.Image, size: int = 224) -> np.ndarray:
    img = img.convert("RGB")
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((size, size), Image.BILINEAR)
    a = (np.asarray(img, dtype=np.float32) / 255.0 - MEAN) / STD
    return a.transpose(2, 0, 1)[None]


class CropVisionModel:
    KEY = "crop-vision-plantvillage"

    def __init__(self, model_dir: str | Path):
        self.model_dir = Path(model_dir)
        self._session = None
        self._lock = threading.Lock()
        self.card: dict | None = None
        self.load_error: str | None = None
        self._guard = None

    # -- lifecycle -------------------------------------------------------------------------
    def load(self) -> bool:
        with self._lock:
            if self._session is not None:
                return True
            try:
                import onnxruntime as ort

                card_path = self.model_dir / "model_card.json"
                model_path = self.model_dir / "model.onnx"
                if not card_path.exists() or not model_path.exists():
                    self.load_error = "model_files_missing"
                    return False
                card = json.loads(card_path.read_text())
                blob = model_path.read_bytes()
                if card.get("artifact_sha256") and hashlib.sha256(blob).hexdigest() != card["artifact_sha256"]:
                    self.load_error = "checksum_mismatch"
                    return False
                opts = ort.SessionOptions()
                opts.log_severity_level = 3
                self._session = ort.InferenceSession(blob, opts, providers=["CPUExecutionProvider"])
                guard_path = self.model_dir / "ood_guard.npz"
                if guard_path.exists():
                    g = np.load(guard_path)
                    self._guard = (g["mean"], g["scale"], g["centroids"])
                self.card = card
                self.load_error = None
                log.info("crop-vision model loaded: %s %s", card.get("key"), card.get("version"))
                return True
            except Exception as exc:  # pragma: no cover - depends on runtime install
                log.exception("crop-vision model failed to load")
                self.load_error = f"load_failed:{exc.__class__.__name__}"
                self._session = None
                return False

    @property
    def available(self) -> bool:
        return self._session is not None or self.load()

    @property
    def version(self) -> str | None:
        return self.card.get("version") if self.card else None

    @property
    def classes(self) -> list[str]:
        return list(self.card.get("classes", [])) if self.card else []

    def supported_crops(self) -> list[str]:
        return sorted({c.split("___")[0] for c in self.classes})

    def status(self) -> dict:
        ok = self.available
        return {
            "key": self.KEY,
            "available": ok,
            "version": self.version,
            "error": None if ok else self.load_error,
            "classes": len(self.classes),
            "supported_crop_prefixes": self.supported_crops(),
            "metrics": {k: v for k, v in (self.card or {}).get("metrics", {}).items() if k != "per_class"},
        }

    # -- inference -------------------------------------------------------------------------
    def predict(self, image_bytes: bytes, *, expected_crop_prefix: str | None) -> InferenceResult:
        if not self.available:
            return InferenceResult(
                status="failed", model_key=self.KEY, model_version=None, status_reason=self.load_error or "model_unavailable"
            )
        threshold = get_settings().uncertainty_threshold
        t0 = time.perf_counter()
        try:
            img = Image.open(io.BytesIO(image_bytes))
            x = preprocess(img)
            feats, probs = self._session.run(["features", "probabilities"], {"image": x})
        except Exception as exc:
            log.warning("inference failed: %s", exc.__class__.__name__)
            return InferenceResult(
                status="failed", model_key=self.KEY, model_version=self.version, status_reason="inference_error"
            )
        ms = int((time.perf_counter() - t0) * 1000)
        p = probs[0].astype(float)
        order = np.argsort(p)[::-1][:3]
        classes = self.classes
        top = []
        for i in order:
            crop, cond = split_class(classes[i])
            top.append({"class": classes[i], "crop": crop, "condition": cond, "probability": round(float(p[i]), 4)})
        best = int(order[0])
        crop, cond = split_class(classes[best])
        result = InferenceResult(
            status="completed",
            model_key=self.KEY,
            model_version=self.version,
            predicted_class=classes[best],
            predicted_crop=crop,
            predicted_condition=cond,
            confidence=round(float(p[best]), 4),
            top_k=top,
            processing_ms=ms,
        )

        # Unsupported crop: the cycle's crop is not one the model was trained on.
        if expected_crop_prefix is None:
            result.status = "unsupported_input"
            result.status_reason = "crop_not_covered_by_model"
            result.review_recommended = True
            return result

        # Out-of-distribution guard (image does not resemble the single-leaf training images).
        if self._guard is not None:
            mean, scale, cent = self._guard
            z = (feats[0] - mean) / scale
            zn = z / (np.linalg.norm(z) + 1e-9)
            cos = float((zn @ cent.T).max())
            if cos < float(self.card["metrics"].get("ood_guard_cosine_threshold", 0)):
                result.status = "unsupported_input"
                result.status_reason = "image_not_recognised_as_leaf"
                result.review_recommended = True
                return result

        predicted_prefix = classes[best].split("___")[0]
        if predicted_prefix != expected_crop_prefix:
            result.status = "uncertain"
            result.status_reason = "predicted_crop_mismatch"
            result.review_recommended = True
        elif result.confidence is not None and result.confidence < threshold:
            result.status = "uncertain"
            result.status_reason = "low_confidence"
            result.review_recommended = True
        elif cond.lower() != "healthy":
            result.review_recommended = True
            result.status_reason = "condition_detected"
        return result


_model: CropVisionModel | None = None


def get_model() -> CropVisionModel:
    global _model
    if _model is None:
        _model = CropVisionModel(get_settings().model_dir)
    return _model


def set_model(model: CropVisionModel | None) -> None:
    global _model
    _model = model
