"""ArcFace embedding adapter for the existing YuNet video pipeline.

The detector and five-point alignment intentionally stay identical to the
OpenCV SFace baseline.  This makes encoder comparisons attributable to the
recognition model instead of silently changing several pipeline stages.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from .opencv_analyzer import AnalyzerConfig, OpenCvAnalyzer


class ArcFaceAnalyzer(OpenCvAnalyzer):
    """Use an InsightFace ArcFace ONNX model behind the analyzer interface."""

    def __init__(self, config: AnalyzerConfig, embedding_model: Path) -> None:
        super().__init__(config)
        if not embedding_model.is_file():
            raise FileNotFoundError(f"ArcFace model not found: {embedding_model}")
        self.embedding_model = embedding_model
        self.embedding_session = ort.InferenceSession(
            str(embedding_model), providers=["CPUExecutionProvider"]
        )
        inputs = self.embedding_session.get_inputs()
        if len(inputs) != 1:
            raise ValueError("ArcFace model must have exactly one image input")
        self.embedding_input_name = inputs[0].name

    @staticmethod
    def _embedding_blob(aligned: np.ndarray) -> np.ndarray:
        """Apply the normalization used by InsightFace recognition exports."""
        return cv2.dnn.blobFromImage(
            aligned,
            scalefactor=1.0 / 127.5,
            size=(112, 112),
            mean=(127.5, 127.5, 127.5),
            swapRB=True,
            crop=False,
        ).astype(np.float32, copy=False)

    def _feature(self, image: np.ndarray, face: np.ndarray) -> np.ndarray:
        aligned = self.recognizer.alignCrop(image, face)
        blob = self._embedding_blob(aligned)
        output = self.embedding_session.run(
            None, {self.embedding_input_name: blob}
        )[0]
        feature = np.asarray(output, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(feature))
        if norm <= 0 or not np.isfinite(norm):
            raise ValueError("ArcFace recognizer returned an invalid feature")
        return feature / norm
