"""Identity module interface."""

from typing import Protocol

from contracts.domain import AuthorizedImage, FaceScan


class FaceScanner(Protocol):
    def scan(self, image: AuthorizedImage) -> FaceScan:
        """Return one-face scan or raise a typed identity error."""

    def scan_bytes(self, data: bytes) -> FaceScan:
        """Return a one-face scan from raw image bytes (e.g. match thumbnails)."""

    def similarity(self, source: FaceScan, candidate: FaceScan) -> float:
        """Return cosine similarity (0..1) between two scans from this scanner.

        The raw embeddings never leave the identity module; this comparison
        happens against embeddings cached inside the scanner.
        """
