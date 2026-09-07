"""Unit tests for the Ledger module."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from contracts.domain import EvidenceBundle, PublicPost
from contracts.hashing import canonicalize_evidence, compute_evidence_hash
from contracts.ledger import LedgerReceipt, VerificationResult
from facechain.config import Settings
from facechain.ledger import (
    AnvilWeb3Adapter,
    EvidenceLedger,
    FakeLedgerProvider,
    LedgerError,
    LedgerProvider,
    LedgerUnavailableError,
    Web3Adapter,
    Web3LedgerProvider,
)


def _sample_bundle() -> EvidenceBundle:
    return EvidenceBundle(
        consent_reference="consent-ref-12345",
        input_image_sha256="a" * 64,
        face_embedding_sha256="b" * 64,
        provider="serpapi_google_lens",
        post=PublicPost(
            source_url=HttpUrl("https://example.com/posts/101"),
            platform="ExamplePlatform",
            title="Public Profile Photo",
            text_excerpt="Publicly shared portrait photo.",
            image_url=HttpUrl("https://example.com/images/101.jpg"),
            retrieved_at=datetime.now(UTC),
        ),
    )


def test_ledger_exception_hierarchy() -> None:
    assert issubclass(LedgerUnavailableError, LedgerError)


def test_fake_ledger_provider_conforms_to_protocol() -> None:
    provider = FakeLedgerProvider()
    assert isinstance(provider, LedgerProvider)


def test_ledger_fingerprint_is_stable_and_delegates_to_shared_helper() -> None:
    ledger = EvidenceLedger(provider=FakeLedgerProvider())
    bundle = _sample_bundle()

    assert ledger.fingerprint(bundle) == ledger.fingerprint(bundle)
    assert ledger.fingerprint(bundle) == compute_evidence_hash(bundle)
    assert ledger.fingerprint(bundle) == ledger.fingerprint(bundle.model_copy())


def test_ledger_fingerprint_is_key_order_independent() -> None:
    ledger = EvidenceLedger(provider=FakeLedgerProvider())
    bundle = _sample_bundle()
    digest = ledger.fingerprint(bundle)

    parsed = json.loads(canonicalize_evidence(bundle))
    reordered = {key: parsed[key] for key in reversed(list(parsed))}
    reordered["post"] = {
        key: parsed["post"][key] for key in reversed(list(parsed["post"]))
    }
    rebuilt = EvidenceBundle(**reordered)

    assert ledger.fingerprint(rebuilt) == digest


def test_ledger_fingerprint_changes_when_evidence_is_altered() -> None:
    ledger = EvidenceLedger(provider=FakeLedgerProvider())
    bundle = _sample_bundle()
    base = ledger.fingerprint(bundle)

    altered_consent = bundle.model_copy(update={"consent_reference": "altered-consent-999"})
    assert ledger.fingerprint(altered_consent) != base

    altered_face = bundle.model_copy(update={"face_embedding_sha256": "0" * 64})
    assert ledger.fingerprint(altered_face) != base

    altered_post = bundle.model_copy(
        update={"post": bundle.post.model_copy(update={"title": "Altered Title"})}
    )
    assert ledger.fingerprint(altered_post) != base


def test_ledger_anchor_returns_receipt_per_contract() -> None:
    ledger = EvidenceLedger(provider=FakeLedgerProvider(chain_id=31337))
    bundle = _sample_bundle()

    receipt = ledger.anchor(bundle)

    assert isinstance(receipt, LedgerReceipt)
    assert receipt.evidence_sha256 == ledger.fingerprint(bundle)
    assert receipt.chain_id == 31337
    assert receipt.transaction_hash.startswith("0x")
    assert len(receipt.transaction_hash) == 66
    assert all(c in "0123456789abcdef" for c in receipt.transaction_hash[2:])


def test_ledger_verify_roundtrip_and_mismatch() -> None:
    provider = FakeLedgerProvider()
    ledger = EvidenceLedger(provider=provider)
    bundle = _sample_bundle()

    receipt = ledger.anchor(bundle)
    result = ledger.verify(bundle)

    assert isinstance(result, VerificationResult)
    assert result.matched is True
    assert result.evidence_sha256 == receipt.evidence_sha256
    assert result.receipt == receipt

    altered = bundle.model_copy(update={"provider": "different_provider"})
    missing = ledger.verify(altered)

    assert missing.matched is False
    assert missing.evidence_sha256 == ledger.fingerprint(altered)
    assert missing.receipt is None


def test_ledger_propagates_typed_unavailable_error() -> None:
    unavailable = LedgerUnavailableError("chain unreachable")
    ledger = EvidenceLedger(provider=FakeLedgerProvider(raise_error=unavailable))
    bundle = _sample_bundle()

    with pytest.raises(LedgerUnavailableError):
        ledger.anchor(bundle)
    with pytest.raises(LedgerUnavailableError):
        ledger.verify(bundle)


class FakeWeb3Adapter:
    """Deterministic in-memory web3 adapter for provider tests (no live node)."""

    def __init__(
        self,
        *,
        chain_id: int = 31337,
        chain_id_error: Exception | None = None,
        anchor_error: Exception | None = None,
    ) -> None:
        self._chain_id = chain_id
        self._chain_id_error = chain_id_error
        self._anchor_error = anchor_error
        self.last_anchored_sha256: str | None = None
        self.anchored_at = datetime(2026, 1, 1, tzinfo=UTC)

    def chain_id(self) -> int:
        if self._chain_id_error is not None:
            raise self._chain_id_error
        return self._chain_id

    def anchor(self, evidence_sha256: str) -> tuple[str, datetime]:
        if self._anchor_error is not None:
            raise self._anchor_error
        self.last_anchored_sha256 = evidence_sha256
        return "0x" + "1" * 64, self.anchored_at


def _web3_settings(*, chain_id: int = 31337) -> Settings:
    return Settings(
        anvil_rpc_url="http://127.0.0.1:8545",
        anvil_private_key="0x" + "1" * 64,
        chain_id=chain_id,
    )


def test_anvil_web3_adapter_conforms_to_protocol() -> None:
    adapter = AnvilWeb3Adapter(
        rpc_url="http://127.0.0.1:8545",
        private_key="0x" + "1" * 64,
        chain_id=31337,
    )
    assert isinstance(adapter, Web3Adapter)


def test_web3_provider_anchors_successfully() -> None:
    fake = FakeWeb3Adapter(chain_id=31337)
    provider = Web3LedgerProvider(settings=_web3_settings(), adapter=fake)

    receipt = provider.anchor("a" * 64)

    assert isinstance(receipt, LedgerReceipt)
    assert receipt.evidence_sha256 == "a" * 64
    assert receipt.chain_id == 31337
    assert receipt.transaction_hash == "0x" + "1" * 64
    assert receipt.anchored_at == fake.anchored_at
    assert fake.last_anchored_sha256 == "a" * 64


def test_web3_provider_rejects_wrong_chain_id() -> None:
    fake = FakeWeb3Adapter(chain_id=1337)
    provider = Web3LedgerProvider(settings=_web3_settings(chain_id=31337), adapter=fake)

    with pytest.raises(LedgerUnavailableError, match="Wrong chain id"):
        provider.anchor("a" * 64)

    assert fake.last_anchored_sha256 is None


def test_web3_provider_surfaces_unreachable_chain() -> None:
    fake = FakeWeb3Adapter(chain_id_error=ConnectionError("connection refused"))
    provider = Web3LedgerProvider(settings=_web3_settings(), adapter=fake)

    with pytest.raises(LedgerUnavailableError):
        provider.anchor("a" * 64)


def test_web3_provider_propagates_receipt_failure() -> None:
    fake = FakeWeb3Adapter(anchor_error=LedgerUnavailableError("receipt status 0"))
    provider = Web3LedgerProvider(settings=_web3_settings(), adapter=fake)

    with pytest.raises(LedgerUnavailableError, match="receipt status 0"):
        provider.anchor("a" * 64)


def test_web3_provider_wraps_unknown_adapter_failure() -> None:
    fake = FakeWeb3Adapter(anchor_error=RuntimeError("boom"))
    provider = Web3LedgerProvider(settings=_web3_settings(), adapter=fake)

    with pytest.raises(LedgerUnavailableError):
        provider.anchor("a" * 64)


def test_settings_load_anvil_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANVIL_RPC_URL", "http://127.0.0.1:8545")
    monkeypatch.setenv("CHAIN_ID", "31337")

    settings = Settings(anvil_private_key="0x" + "2" * 64)

    assert settings.anvil_rpc_url == "http://127.0.0.1:8545"
    assert settings.chain_id == 31337
    assert settings.anvil_private_key == "0x" + "2" * 64