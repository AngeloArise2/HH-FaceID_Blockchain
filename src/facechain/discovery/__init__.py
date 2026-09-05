"""Discovery module boundary."""

from facechain.discovery.exceptions import (
    DiscoveryConfigError,
    DiscoveryError,
    DiscoveryUnavailableError,
    NoMatchFoundError,
)
from facechain.discovery.provider import (
    DiscoveryProvider,
    FakeDiscoveryProvider,
    SerpAPILensProvider,
)
from facechain.discovery.service import (
    DiscoveryService,
    canonicalize_evidence,
    compute_evidence_hash,
)

__all__ = [
    "DiscoveryConfigError",
    "DiscoveryError",
    "DiscoveryProvider",
    "DiscoveryService",
    "DiscoveryUnavailableError",
    "FakeDiscoveryProvider",
    "NoMatchFoundError",
    "SerpAPILensProvider",
    "canonicalize_evidence",
    "compute_evidence_hash",
]
