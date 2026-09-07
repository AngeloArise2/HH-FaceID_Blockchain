"""Unit tests for the Ledger module."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from contracts.domain import EvidenceBundle, PublicPost
from contracts.hashing import canonicalize_evidence, compute_evidence_hash
from contracts.ledger import LedgerReceipt, VerificationResult
from facechain.ledger import (
    EvidenceLedger,
    FakeLedgerProvider,
    LedgerError,
    LedgerProvider,
    LedgerUnavailableError,
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