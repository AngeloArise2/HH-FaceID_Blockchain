"""Integration tests for settings and the verification pipeline."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import HttpUrl, ValidationError

from contracts.discovery import DiscoveryResult
from contracts.domain import AuthorizedImage, EvidenceBundle, PublicPost
from contracts.hashing import compute_evidence_hash
from contracts.ledger import LedgerReceipt, VerificationResult
from facechain.config import Settings, SettingsValidationError
from facechain.discovery import (
    DiscoveryService,
    FakeDiscoveryProvider,
)
from facechain.identity import FakeFaceScanner, IdentityService
from facechain.pipeline import EvidenceLedger, FaceVerificationPipeline


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "anvil_rpc_url": "http://127.0.0.1:8545",
        "anvil_private_key": "0x" + "1" * 64,
        "chain_id": 31337,
        "discovery_mode": "fake",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def test_settings_defaults_to_fake_discovery_and_anvil_chain() -> None:
    settings = _settings()
    assert settings.discovery_mode == "fake"
    assert settings.chain_id == 31337
    assert settings.anvil_rpc_url == "http://127.0.0.1:8545"


def test_settings_validate_passes_for_fake_discovery() -> None:
    _settings().validate()


def test_settings_validate_passes_for_real_discovery_with_key() -> None:
    _settings(discovery_mode="real", serpapi_key="secret").validate()


def test_settings_validate_requires_serpapi_key_in_real_mode() -> None:
    with pytest.raises(SettingsValidationError, match="SERPAPI_KEY"):
        _settings(discovery_mode="real").validate()


def test_settings_validate_requires_anvil_private_key() -> None:
    with pytest.raises(SettingsValidationError, match="ANVIL_PRIVATE_KEY"):
        _settings(anvil_private_key="").validate()


def test_settings_validate_requires_anvil_rpc_url() -> None:
    with pytest.raises(SettingsValidationError, match="ANVIL_RPC_URL"):
        _settings(anvil_rpc_url="").validate()


def test_settings_loads_serpapi_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERPAPI_KEY", "env-key")
    settings = _settings(discovery_mode="real")
    assert settings.serpapi_key == "env-key"


def test_settings_rejects_unknown_discovery_mode() -> None:
    with pytest.raises(ValidationError):
        _settings(discovery_mode="live")


# ── Pipeline integration ──────────────────────────────────────────────────


class StubLedger:
    """Fake EvidenceLedger; anchors into an in-memory store and verifies against it."""

    def __init__(self, *, report_mismatch: bool = False) -> None:
        self._report_mismatch = report_mismatch
        self._store: dict[str, LedgerReceipt] = {}

    def anchor(self, evidence: EvidenceBundle) -> LedgerReceipt:
        digest = compute_evidence_hash(evidence)
        receipt = LedgerReceipt(
            evidence_sha256=digest,
            chain_id=31337,
            transaction_hash="0x" + "1" * 64,
            anchored_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        self._store[digest] = receipt
        return receipt

    def verify(self, evidence: EvidenceBundle) -> VerificationResult:
        digest = compute_evidence_hash(evidence)
        if self._report_mismatch:
            return VerificationResult(matched=False, evidence_sha256=digest)
        receipt = self._store.get(digest)
        if receipt is None:
            return VerificationResult(matched=False, evidence_sha256=digest)
        return VerificationResult(matched=True, evidence_sha256=digest, receipt=receipt)


def _post() -> PublicPost:
    return PublicPost(
        source_url=HttpUrl("https://example.com/posts/101"),
        platform="ExamplePlatform",
        title="Public Profile Photo",
        retrieved_at=datetime.now(UTC),
    )


def _discovery_result() -> DiscoveryResult:
    return DiscoveryResult(provider="fake_lens", matched_post=_post())


def _make_image(path: Path) -> AuthorizedImage:
    return AuthorizedImage(
        image_path=str(path),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        consent_reference="consent-ref-12345",
    )


def _make_pipeline(
    tmp_path: Path,
    ledger: EvidenceLedger | None = None,
    provider: FakeDiscoveryProvider | None = None,
) -> tuple[FaceVerificationPipeline, AuthorizedImage]:
    path = tmp_path / "input.jpg"
    path.write_bytes(b"sample-image-bytes")
    image = _make_image(path)
    pipeline = FaceVerificationPipeline(
        identity=IdentityService(FakeFaceScanner("b" * 64)),
        discovery=DiscoveryService(
            provider or FakeDiscoveryProvider(canned_result=_discovery_result())
        ),
        ledger=ledger or StubLedger(),
    )
    return pipeline, image


def _run_stages(pipeline: FaceVerificationPipeline, image: AuthorizedImage) -> list[str]:
    return [event.stage for event in pipeline.run(image).events]


def test_success_emits_expected_stages(tmp_path: Path) -> None:
    pipeline, image = _make_pipeline(tmp_path)
    assert _run_stages(pipeline, image) == [
        "validated",
        "face_scanned",
        "post_found",
        "anchored",
        "verified",
    ]


def test_success_returns_evidence_receipt_and_verification(tmp_path: Path) -> None:
    pipeline, image = _make_pipeline(tmp_path)

    result = pipeline.run(image)

    assert isinstance(result.evidence, EvidenceBundle)
    assert isinstance(result.receipt, LedgerReceipt)
    assert isinstance(result.verification, VerificationResult)
    assert result.verification.matched is True
    assert result.receipt.evidence_sha256 == result.verification.evidence_sha256


def test_all_events_share_run_id(tmp_path: Path) -> None:
    pipeline, image = _make_pipeline(tmp_path)
    result = pipeline.run(image)

    assert len(result.events) == 5
    assert all(event.run_id == result.run_id for event in result.events)


def test_no_match_surfaces_failed_event_not_exception(tmp_path: Path) -> None:
    pipeline, image = _make_pipeline(
        tmp_path,
        provider=FakeDiscoveryProvider(),  # raises NoMatchFoundError
    )

    result = pipeline.run(image)

    assert result.evidence is None
    assert result.receipt is None
    assert result.verification is None
    stages = [event.stage for event in result.events]
    assert stages == ["validated", "face_scanned", "failed"]


def test_altered_evidence_matched_false(tmp_path: Path) -> None:
    pipeline, image = _make_pipeline(tmp_path, ledger=StubLedger(report_mismatch=True))

    result = pipeline.run(image)

    assert isinstance(result.verification, VerificationResult)
    assert result.verification.matched is False
    assert result.verification.receipt is None
    assert result.receipt is not None  # anchored ok
    assert result.evidence is not None


def test_failed_event_detail_includes_reason(tmp_path: Path) -> None:
    pipeline, image = _make_pipeline(
        tmp_path,
        provider=FakeDiscoveryProvider(),
    )

    result = pipeline.run(image)

    failed_event = result.events[-1]
    assert failed_event.stage == "failed"
    assert isinstance(failed_event.detail, str)
    assert len(failed_event.detail) > 0