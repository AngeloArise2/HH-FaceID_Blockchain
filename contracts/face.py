"""Identity module interface."""

from typing import Protocol
from contracts.domain import AuthorizedImage, FaceScan


class FaceScanner(Protocol):
    def scan(self, image: AuthorizedImage) -> FaceScan:
        """Return one-face scan or raise a typed identity error."""
