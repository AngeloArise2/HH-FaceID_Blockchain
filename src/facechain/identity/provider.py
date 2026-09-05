"""InsightFace/OpenCV face provider adapter."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

import cv2
import numpy as np

from contracts.domain import AuthorizedImage, FaceScan
from facechain.identity.exceptions import (
    IdentityError,
    InputValidationError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    RecognitionUnavailableError,
)

MODEL_NAME = "buffalo_l"


class _FaceLike(Protocol):
    @property
    def embedding(self) -> np.ndarray | None: ...

    @property
    def normed_embedding(self) -> np.ndarray | None: ...


class _AnalyzerLike(Protocol):
    def get(self, img: np.ndarray) -> list[_FaceLike]: ...


class InsightFaceFaceScanner:
    """InsightFace adapter behind the FaceScanner protocol.

    Enforces exactly one detected face and returns a FaceScan containing a
    SHA-256 of the L2-normalized embedding — never the raw embedding vector.
    """

    def __init__(
        self,
        *,
        analyzer: _AnalyzerLike | None = None,
        model_name: str = MODEL_NAME,
        root: str = "~/.insightface",
        allowed_modules: tuple[str, ...] = ("detection", "recognition"),
        ctx_id: int = 0,
        det_thresh: float = 0.5,
        det_size: tuple[int, int] = (640, 640),
    ) -> None:
        self._analyzer = analyzer
        self._model_name = model_name
        self._root = root
        self._allowed_modules = allowed_modules
        self._ctx_id = ctx_id
        self._det_thresh = det_thresh
        self._det_size = det_size

    @property
    def detector(self) -> str:
        """Return the configured model name used as the detector label."""
        return self._model_name

    def scan(self, image: AuthorizedImage) -> FaceScan:
        """Detect exactly one face and emit a normalized embedding hash.

        Args:
            image: Authorized image with verified consent reference.

        Returns:
            FaceScan with embedding_sha256 of the L2-normalized embedding.

        Raises:
            InputValidationError: When the image file cannot be read or decoded.
            NoFaceDetectedError: When zero faces are detected.
            MultipleFacesDetectedError: When more than one face is detected.
            RecognitionUnavailableError: When the recognition engine fails.
        """
        analyzer = self._ensure_analyzer()
        frame = self._read_image(Path(image.image_path))
        try:
            faces = analyzer.get(frame)
        except IdentityError:
            raise
        except Exception as exc:
            raise RecognitionUnavailableError(f"Face detection failed: {exc}") from exc
        if not faces:
            raise NoFaceDetectedError("No face detected in the input image")
        if len(faces) > 1:
            raise MultipleFacesDetectedError(
                f"Expected exactly one face, got {len(faces)}"
            )
        embedding = self._normalized_embedding(faces[0])
        return FaceScan(
            embedding_sha256=hashlib.sha256(embedding.tobytes()).hexdigest(),
            detector=self.detector,
            face_count=1,
            scanned_at=datetime.now(UTC),
        )

    def _ensure_analyzer(self) -> _AnalyzerLike:
        """Return an injected analyzer or lazily initialize the real model."""
        if self._analyzer is not None:
            return self._analyzer
        try:
            from insightface.app import FaceAnalysis  # type: ignore

            app = FaceAnalysis(
                name=self._model_name,
                root=self._root,
                allowed_modules=list(self._allowed_modules),
            )
            app.prepare(
                ctx_id=self._ctx_id,
                det_thresh=self._det_thresh,
                det_size=self._det_size,
            )
        except Exception as exc:
            raise RecognitionUnavailableError(
                f"Failed to initialize the InsightFace model: {exc}"
            ) from exc
        self._analyzer = cast(_AnalyzerLike, app)
        return self._analyzer

    def _read_image(self, path: Path) -> np.ndarray:
        """Read and decode the image file into an RGB array."""
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if frame is None:
            raise InputValidationError(f"Unable to read image file: {path}")
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def _normalized_embedding(self, face: _FaceLike) -> np.ndarray:
        """Return the L2-normalized embedding as a contiguous float32 array."""
        normed = face.normed_embedding
        if normed is None:
            raw = face.embedding
            if raw is None:
                raise RecognitionUnavailableError(
                    "Face detected but recognition returned no embedding"
                )
            norm = float(np.linalg.norm(raw, ord=2))
            normed = raw / norm if norm > 0.0 else raw
        return np.ascontiguousarray(normed, dtype=np.float32)