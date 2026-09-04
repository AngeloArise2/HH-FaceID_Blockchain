"""Discovery module exceptions."""


class DiscoveryError(Exception):
    """Base exception for all discovery module errors."""


class DiscoveryUnavailableError(DiscoveryError):
    """Raised when the discovery provider service is unreachable or returns an error."""


class NoMatchFoundError(DiscoveryError):
    """Raised when no qualifying matching public post is found."""


class DiscoveryConfigError(DiscoveryError):
    """Raised when discovery configuration or credentials are invalid or missing."""
