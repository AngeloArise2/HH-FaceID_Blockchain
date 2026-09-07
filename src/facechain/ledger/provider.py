"""Ledger provider protocol and implementations."""

from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol, runtime_checkable

from contracts.ledger import LedgerReceipt


@runtime_checkable
class LedgerProvider(Protocol):
    """Protocol defining the blockchain ledger provider interface."""

    def anchor(self, evidence_sha256: str) -> LedgerReceipt:
        """Anchor an evidence fingerprint to the chain and return its receipt.

        Args:
            evidence_sha256: Canonical SHA-256 fingerprint of the evidence bundle.

        Returns:
            LedgerReceipt containing the on-chain transaction details.

        Raises:
            LedgerUnavailableError: When the chain provider is unreachable or fails.
        """
        ...

    def verify(self, evidence_sha256: str) -> LedgerReceipt | None:
        """Return the on-chain receipt for a fingerprint, or None if not anchored.

        Args:
            evidence_sha256: Canonical SHA-256 fingerprint of the evidence bundle.

        Returns:
            The anchored receipt if the fingerprint exists on-chain, otherwise None.

        Raises:
            LedgerUnavailableError: When the chain provider is unreachable or fails.
        """
        ...


class FakeLedgerProvider:
    """Deterministic in-memory ledger provider for tests and offline runs."""

    DEFAULT_CHAIN_ID = 31337

    def __init__(
        self,
        chain_id: int = DEFAULT_CHAIN_ID,
        raise_error: Exception | None = None,
    ) -> None:
        self._chain_id = chain_id
        self._raise_error = raise_error
        self._receipts: dict[str, LedgerReceipt] = {}
        self.anchored_fingerprints: list[str] = []

    def anchor(self, evidence_sha256: str) -> LedgerReceipt:
        """Anchor a fingerprint in memory and return a deterministic receipt."""
        if self._raise_error is not None:
            raise self._raise_error
        receipt = LedgerReceipt(
            evidence_sha256=evidence_sha256,
            chain_id=self._chain_id,
            transaction_hash=f"0x{sha256(evidence_sha256.encode()).hexdigest()}",
            anchored_at=datetime.now(UTC),
        )
        self._receipts[evidence_sha256] = receipt
        self.anchored_fingerprints.append(evidence_sha256)
        return receipt

    def verify(self, evidence_sha256: str) -> LedgerReceipt | None:
        """Return the stored receipt for a fingerprint, or None if not anchored."""
        if self._raise_error is not None:
            raise self._raise_error
        return self._receipts.get(evidence_sha256)