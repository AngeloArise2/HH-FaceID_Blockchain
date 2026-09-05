"""Identity service orchestrator."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from contracts.domain import AuthorizedImage, FaceScan
from contracts.face import FaceScanner
from facechain.identity.exceptions import (
    InputValidationError,
    NoFaceDetectedError,
)


class IdentityService:
    """Validates input images and delegates face scanning to an injected provider."""

    def __init__(self, scanner: FaceScanner) -> None:
        self._scanner = scanner

    @property
    def scanner(self) -> FaceScanner:
        """Return the active face scanner."""
        return self._scanner

    def validate_image(self, image: AuthorizedImage) -> None:
        """Validate that the image file exists and its SHA-256 matches.

        Args:
            image: The authorized image to validate.

        Raises:
            InputValidationError: When the file is missing or the hash does not match.
        """
        path = Path(image.image_path)
        if not path.exists():
            raise InputValidationError(
                f"Image file does not exist: {image.image_path}"
            )
        if not path.is_file():
            raise InputValidationError(
                f"Image path is not a file: {image.image_path}"
            )
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != image.sha256:
            raise InputValidationError(
                f"SHA-256 mismatch for {image.image_path}: "
                f"expected {image.sha256}, got {actual}"
            )

    def scan(self, image: AuthorizedImage) -> FaceScan:
        """Validate the image and return a face scan.

        Args:
            image: Authorized image with verified consent reference.

        Returns:
            FaceScan containing the normalized embedding hash and metadata.

        Raises:
            InputValidationError: When the image file is missing or corrupt.
            NoFaceDetectedError: When the scanner detects no face.
        """
        self.validate_image(image)
        return self._scanner.scan(image)


class FakeFaceScanner:
    """Deterministic face scanner for tests. No network calls."""

    def __init__(
        self,
        embedding_sha256: str | None = None,
        detector: str = "fake",
        *,
        fail: bool = False,
    ) -> None:
        self._embedding = embedding_sha256 or (
            hashlib.sha256(b"fake-embedding").hexdigest()
        )
        self._detector = detector
        self._fail = fail
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def scan(self, image: AuthorizedImage) -> FaceScan:
        """Return a deterministic FaceScan for the given image.

        Args:
            image: Authorized image (used only for deterministic embedding derivation).

        Returns:
            FaceScan with a fixed embedding hash and face_count=1.

        Raises:
            NoFaceDetectedError: When constructed with fail=True.
        """
        self._call_count += 1
        if self._fail:
            raise NoFaceDetectedError("No face detected in the input image")
        return FaceScan(
            embedding_sha256=self._embedding,
            detector=self._detector,
            face_count=1,
            scanned_at=datetime.now(UTC),
        )
