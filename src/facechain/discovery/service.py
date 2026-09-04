"""Discovery service orchestrator."""

from contracts.discovery import DiscoveryResult
from contracts.domain import AuthorizedImage, EvidenceBundle, FaceScan
from facechain.discovery.provider import DiscoveryProvider


class DiscoveryService:
    """Orchestrates public visual discovery using an injected provider."""

    def __init__(self, provider: DiscoveryProvider) -> None:
        self._provider = provider

    @property
    def provider(self) -> DiscoveryProvider:
        """Return the active discovery provider."""
        return self._provider

    def discover(self, image: AuthorizedImage, scan: FaceScan) -> DiscoveryResult:
        """Search for a matching public post for the given authorized image and scan.

        Args:
            image: Authorized image with verified consent reference.
            scan: Face scan containing normalized embedding SHA-256.

        Returns:
            DiscoveryResult containing the matched public post and provider details.

        Raises:
            NoMatchFoundError: When no qualifying public post matches the subject.
            DiscoveryUnavailableError: When provider communication fails.
        """
        return self._provider.search(image, scan)

    def assemble_evidence(
        self,
        result: DiscoveryResult,
        image: AuthorizedImage,
        scan: FaceScan,
    ) -> EvidenceBundle:
        """Assemble a canonical EvidenceBundle from discovery result, image, and scan.

        Args:
            result: Discovery result containing matched post and provider.
            image: Authorized input image.
            scan: Face scan details.

        Returns:
            EvidenceBundle containing normalized discovery details.
        """
        return EvidenceBundle(
            schema_version="1.0",
            consent_reference=image.consent_reference,
            input_image_sha256=image.sha256,
            face_embedding_sha256=scan.embedding_sha256,
            provider=result.provider,
            post=result.matched_post,
        )
