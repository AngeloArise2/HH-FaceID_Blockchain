"""Discovery service orchestrator and canonical evidence assembly."""

import hashlib
import json

from contracts.discovery import DiscoveryResult
from contracts.domain import AuthorizedImage, EvidenceBundle, FaceScan
from facechain.discovery.provider import DiscoveryProvider


def canonicalize_evidence(evidence: EvidenceBundle) -> str:
    """Serialize an EvidenceBundle into canonical UTF-8 JSON with sorted keys and compact separators.

    Guarantees deterministic, reproducible byte representations across platforms.
    """
    data = evidence.model_dump(mode="json")
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_evidence_hash(evidence: EvidenceBundle) -> str:
    """Compute the deterministic SHA-256 lowercase hex fingerprint of canonical evidence JSON."""
    canonical_bytes = canonicalize_evidence(evidence).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest().lower()


class DiscoveryService:
    """Orchestrates public visual discovery and canonical evidence assembly."""

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

        Ensures only normalized, public result fields and consent references are included,
        strictly excluding raw image bytes, private paths, or provider credentials.

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

    def canonicalize(self, evidence: EvidenceBundle) -> str:
        """Serialize evidence to deterministic canonical JSON."""
        return canonicalize_evidence(evidence)

    def fingerprint(self, evidence: EvidenceBundle) -> str:
        """Calculate the SHA-256 fingerprint of the canonical evidence."""
        return compute_evidence_hash(evidence)
