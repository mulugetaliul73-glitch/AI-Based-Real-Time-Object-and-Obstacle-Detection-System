"""YOLO object detection integration."""

from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class DetectorUnavailable(RuntimeError):
    """Raised when the configured object-detection model cannot be loaded."""


class ObstacleDetector:
    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path or os.getenv(
            "YOLO_MODEL_PATH",
            "models/yolov8n.pt",
        )
        self._model: Any = None
        self._lock = Lock()

    def detect(self, frame: Any) -> list[dict[str, Any]]:
        with self._lock:
            model = self._load_model()
            result = model.predict(source=frame, verbose=False)[0]

        if result.boxes is None:
            return []

        detections = []
        for box in result.boxes:
            class_id = int(box.cls[0].item())
            detections.append(
                {
                    "label": result.names[class_id],
                    "confidence": float(box.conf[0].item()),
                    "bbox": [float(value) for value in box.xyxy[0].tolist()],
                }
            )
        return detections

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise DetectorUnavailable(
                "Object detection dependencies are missing. Run `uv sync --locked`."
            ) from exc

        try:
            self._model = YOLO(self.model_path)
        except (ConnectionError, OSError, RuntimeError, ValueError) as exc:
            logger.exception("Could not load YOLO model %r", self.model_path)
            raise DetectorUnavailable(
                "The YOLO model could not be loaded. Check YOLO_MODEL_PATH and model access."
            ) from exc

        return self._model
