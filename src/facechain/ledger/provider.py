"""Ledger provider protocol and implementations."""

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Protocol, runtime_checkable

from eth_account import Account
from web3 import Web3

from contracts.ledger import LedgerReceipt
from facechain.config import Settings
from facechain.ledger.exceptions import LedgerUnavailableError


@runtime_checkable
class Web3Adapter(Protocol):
    """Protocol defining the injected web3.py adapter boundary.

    Kept tiny so tests inject fakes and never need a live Anvil node.
    """

    def chain_id(self) -> int:
        """Return the chain ID currently served by the node.

        Raises:
            LedgerUnavailableError: When the adapter cannot be reached (e.g. network failure).
        """
        ...

    def anchor(self, evidence_sha256: str) -> tuple[str, datetime]:
        """Submit and confirm an anchoring transaction for the evidence fingerprint.

        Args:
            evidence_sha256: Canonical SHA-256 fingerprint of the evidence bundle.

        Returns:
            A tuple of the 0x transaction hash and the on-chain anchored timestamp
            (block timestamp the transaction was mined at).

        Raises:
            LedgerUnavailableError: When submission fails or the receipt indicates failure.
        """
        ...

    def verify(self, evidence_sha256: str) -> LedgerReceipt | None:
        """Return the on-chain receipt for a fingerprint, or None if not anchored.

        Args:
            evidence_sha256: Canonical SHA-256 fingerprint of the evidence bundle.

        Returns:
            The anchored receipt if an identical fingerprint exists on-chain, otherwise None.

        Raises:
            LedgerUnavailableError: When the chain provider is unreachable or fails.
        """
        ...


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


class AnvilWeb3Adapter:
    """Real ledger adapter using an injected web3.py HTTP connection to Anvil."""

    ANCHOR_GAS = 30000

    def __init__(self, rpc_url: str, private_key: str, chain_id: int) -> None:
        if not private_key:
            raise LedgerUnavailableError("ANVIL_PRIVATE_KEY is not configured.")
        self._rpc_url = rpc_url
        self._chain_id = chain_id
        self._w3 = Web3(Web3.HTTPProvider(rpc_url))
        self._account = Account.from_key(private_key)

    def chain_id(self) -> int:
        """Return the chain ID currently served by the node."""
        return int(self._w3.eth.chain_id)

    def anchor(self, evidence_sha256: str) -> tuple[str, datetime]:
        """Submit a self-transfer carrying the evidence fingerprint and confirm the receipt."""
        nonce = self._w3.eth.get_transaction_count(self._account.address)
        tx = {
            "to": self._account.address,
            "value": 0,
            "nonce": nonce,
            "data": f"0x{evidence_sha256}",
            "chainId": self._chain_id,
            "gas": self.ANCHOR_GAS,
            "gasPrice": self._w3.eth.gas_price,
        }
        signed = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt["status"] == 0:
            raise LedgerUnavailableError("Anchoring transaction failed on-chain (receipt status 0).")
        block = self._w3.eth.get_block(receipt["blockNumber"])
        anchored_at = datetime.fromtimestamp(int(block["timestamp"]), tz=UTC)
        return tx_hash.to_0x_hex(), anchored_at

    def verify(self, evidence_sha256: str) -> LedgerReceipt | None:
        """Return the on-chain receipt for a fingerprint, or None if not anchored.

        On Anvil the anchor is a self-transfer whose calldata equals the fingerprint,
        so re-verification scans blocks for that exact calldata from our account.
        """
        calldata = f"0x{evidence_sha256}"
        block_number = int(self._w3.eth.block_number)
        for number in range(block_number + 1):
            block = self._w3.eth.get_block(number, full_transactions=True)
            for raw_tx in block["transactions"]:
                tx: Any = raw_tx
                if (
                    str(tx["from"]).lower() == self._account.address.lower()
                    and tx["input"].lower() == calldata.lower()
                ):
                    return LedgerReceipt(
                        evidence_sha256=evidence_sha256,
                        chain_id=self._chain_id,
                        transaction_hash=tx["hash"].to_0x_hex(),
                        anchored_at=datetime.fromtimestamp(int(block["timestamp"]), tz=UTC),
                    )
        return None


class Web3LedgerProvider:
    """Ledger provider that anchors evidence fingerprints on Anvil via an injected web3 adapter."""

    def __init__(self, settings: Settings, adapter: Web3Adapter | None = None) -> None:
        self._settings = settings
        resolved: Web3Adapter
        if adapter is None:
            resolved = AnvilWeb3Adapter(
                rpc_url=settings.anvil_rpc_url,
                private_key=settings.anvil_private_key,
                chain_id=settings.chain_id,
            )
        else:
            resolved = adapter
        self._adapter = resolved

    def _guard(self, exc: Exception) -> LedgerUnavailableError:
        if isinstance(exc, LedgerUnavailableError):
            return exc
        return LedgerUnavailableError(f"Ledger chain unavailable: {exc}")

    def _ensure_chain(self) -> None:
        try:
            on_chain = int(self._adapter.chain_id())
        except Exception as exc:
            raise self._guard(exc) from exc
        if on_chain != self._settings.chain_id:
            raise LedgerUnavailableError(
                f"Wrong chain id: node serves {on_chain}, expected {self._settings.chain_id}."
            )

    def anchor(self, evidence_sha256: str) -> LedgerReceipt:
        """Anchor an evidence fingerprint on Anvil and return its contract receipt."""
        self._ensure_chain()
        try:
            tx_hash, anchored_at = self._adapter.anchor(evidence_sha256)
        except LedgerUnavailableError:
            raise
        except Exception as exc:
            raise self._guard(exc) from exc
        return LedgerReceipt(
            evidence_sha256=evidence_sha256,
            chain_id=self._settings.chain_id,
            transaction_hash=tx_hash,
            anchored_at=anchored_at,
        )

    def verify(self, evidence_sha256: str) -> LedgerReceipt | None:
        """Re-verify a fingerprint against the chain and return its receipt if present."""
        self._ensure_chain()
        try:
            receipt = self._adapter.verify(evidence_sha256)
        except LedgerUnavailableError:
            raise
        except Exception as exc:
            raise self._guard(exc) from exc
        return receipt


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