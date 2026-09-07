"""Ledger service orchestrator built on the shared canonical evidence hash."""

from contracts.domain import EvidenceBundle
from contracts.hashing import compute_evidence_hash
from contracts.ledger import LedgerReceipt, VerificationResult
from facechain.ledger.provider import LedgerProvider


class EvidenceLedger:
    """Anchors and verifies a canonical evidence fingerprint on a chain provider.

    Fingerprinting always delegates to the shared helper in ``contracts.hashing``;
    canonicalization is never reimplemented in this module.
    """

    def __init__(self, provider: LedgerProvider) -> None:
        self._provider = provider

    @property
    def provider(self) -> LedgerProvider:
        """Return the active ledger provider."""
        return self._provider

    def fingerprint(self, evidence: EvidenceBundle) -> str:
        """Compute the canonical SHA-256 fingerprint of the evidence bundle."""
        return compute_evidence_hash(evidence)

    def anchor(self, evidence: EvidenceBundle) -> LedgerReceipt:
        """Anchor the evidence fingerprint on-chain and return its receipt.

        Args:
            evidence: Canonical evidence bundle assembled from consented inputs.

        Returns:
            The on-chain receipt for the evidence fingerprint.

        Raises:
            LedgerUnavailableError: When the chain provider is unreachable or fails.
        """
        return self._provider.anchor(self.fingerprint(evidence))

    def verify(self, evidence: EvidenceBundle) -> VerificationResult:
        """Verify that an identical evidence fingerprint exists on-chain.

        Altered evidence yields a different fingerprint and therefore an
        unmatched result, never an exception.

        Args:
            evidence: Canonical evidence bundle assembled from consented inputs.

        Returns:
            VerificationResult with matched set to whether a receipt exists on-chain.

        Raises:
            LedgerUnavailableError: When the chain provider is unreachable or fails.
        """
        digest = self.fingerprint(evidence)
        receipt = self._provider.verify(digest)
        if receipt is None:
            return VerificationResult(matched=False, evidence_sha256=digest)
        return VerificationResult(matched=True, evidence_sha256=digest, receipt=receipt)