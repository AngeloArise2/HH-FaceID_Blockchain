"""Discovery provider protocol and base implementations."""

from typing import Protocol, runtime_checkable

from contracts.discovery import DiscoveryResult
from contracts.domain import AuthorizedImage, FaceScan
from facechain.discovery.exceptions import NoMatchFoundError


@runtime_checkable
class DiscoveryProvider(Protocol):
    """Protocol defining the visual search discovery provider interface."""

    def search(self, image: AuthorizedImage, scan: FaceScan) -> DiscoveryResult:
        """Search for a matching public post for the given authorized image.

        Args:
            image: Validated authorized image with consent.
            scan: Validated face scan metadata.

        Returns:
            DiscoveryResult containing the matched public post and provider info.

        Raises:
            NoMatchFoundError: When no matching public post is found.
            DiscoveryUnavailableError: When the provider service is unreachable or fails.
        """
        ...


class FakeDiscoveryProvider:
    """Deterministic fake provider for testing and offline runs."""

    def __init__(
        self,
        canned_result: DiscoveryResult | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self.canned_result = canned_result
        self.raise_error = raise_error
        self.recorded_calls: list[tuple[AuthorizedImage, FaceScan]] = []

    def search(self, image: AuthorizedImage, scan: FaceScan) -> DiscoveryResult:
        """Execute fake search returning canned response or raising specified error."""
        self.recorded_calls.append((image, scan))
        if self.raise_error is not None:
            raise self.raise_error
        if self.canned_result is not None:
            return self.canned_result
        raise NoMatchFoundError("No qualifying public match found by fake provider.")
