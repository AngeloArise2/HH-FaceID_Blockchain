"""Discovery module boundary."""

from facechain.discovery.exceptions import (
    DiscoveryConfigError,
    DiscoveryError,
    DiscoveryUnavailableError,
    NoMatchFoundError,
)
from facechain.discovery.provider import DiscoveryProvider, FakeDiscoveryProvider
from facechain.discovery.service import DiscoveryService

__all__ = [
    "DiscoveryConfigError",
    "DiscoveryError",
    "DiscoveryProvider",
    "DiscoveryService",
    "DiscoveryUnavailableError",
    "FakeDiscoveryProvider",
    "NoMatchFoundError",
]
