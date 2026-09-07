"""Integration tests for settings, the verification pipeline, and the CLI."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import HttpUrl, ValidationError
from typer.testing import CliRunner

from contracts.discovery import DiscoveryMatch, DiscoveryResult
from contracts.domain import AuthorizedImage, EvidenceBundle, PublicPost
from contracts.hashing import compute_evidence_hash
from contracts.ledger import LedgerReceipt, VerificationResult
from facechain import cli
from facechain.config import Settings, SettingsValidationError
from facechain.discovery import (
    DiscoveryService,
    FakeDiscoveryProvider,
)
from facechain.identity import FakeFaceScanner, IdentityService
from facechain.ledger import LedgerUnavailableError
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

    def __init__(
        self,
        *,
        report_mismatch: bool = False,
        always_match: bool = False,
        anchor_error: Exception | None = None,
    ) -> None:
        self._report_mismatch = report_mismatch
        self._always_match = always_match
        self._anchor_error = anchor_error
        self._store: dict[str, LedgerReceipt] = {}
        self.anchor_calls = 0
        self.verify_calls = 0

    def anchor(self, evidence: EvidenceBundle) -> LedgerReceipt:
        self.anchor_calls += 1
        if self._anchor_error is not None:
            raise self._anchor_error
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
        self.verify_calls += 1
        digest = compute_evidence_hash(evidence)
        if self._always_match:
            return VerificationResult(matched=True, evidence_sha256=digest)
        if self._report_mismatch:
            return VerificationResult(matched=False, evidence_sha256=digest)
        receipt = self._store.get(digest)
        if receipt is None:
            return VerificationResult(matched=False, evidence_sha256=digest)
        return VerificationResult(matched=True, evidence_sha256=digest, receipt=receipt)


def _post(source_url: str = "https://example.com/posts/101", platform: str = "ExamplePlatform") -> PublicPost:
    return PublicPost(
        source_url=HttpUrl(source_url),
        platform=platform,
        title="Public Profile Photo",
        retrieved_at=datetime.now(UTC),
    )


def _discovery_result() -> DiscoveryResult:
    primary = _post()
    return DiscoveryResult(
        provider="fake_lens",
        matched_post=primary,
        matches=[
            DiscoveryMatch(post=primary, confidence=0.92),
            DiscoveryMatch(
                post=_post("https://x.example/user/1", "XProfile"),
                confidence=0.71,
            ),
            DiscoveryMatch(
                post=_post("https://ig.example/u/2", "InstagramProfile"),
                confidence=None,
            ),
        ],
    )


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


# ── Mocked end-to-end (four-case) ─────────────────────────────────────────


def _ledger() -> StubLedger:
    return StubLedger()


def test_e2e_success_emits_ordered_events_and_matched_true(tmp_path: Path) -> None:
    pipeline, image = _make_pipeline(tmp_path)

    result = pipeline.run(image)

    assert [event.stage for event in result.events] == [
        "validated",
        "face_scanned",
        "post_found",
        "anchored",
        "verified",
    ]
    assert result.verification is not None
    assert result.verification.matched is True
    assert result.receipt is not None
    assert result.evidence is not None


def test_e2e_no_search_match_failed_event_and_no_ledger_call(tmp_path: Path) -> None:
    ledger = _ledger()
    pipeline, image = _make_pipeline(
        tmp_path,
        ledger=ledger,
        provider=FakeDiscoveryProvider(),  # raises NoMatchFoundError
    )

    result = pipeline.run(image)

    assert ledger.anchor_calls == 0
    assert ledger.verify_calls == 0
    assert [event.stage for event in result.events] == [
        "validated",
        "face_scanned",
        "failed",
    ]
    assert isinstance(result.events[-1].detail, str)
    assert len(result.events[-1].detail) > 0


def test_e2e_chain_write_error_emits_failed_and_keeps_evidence(tmp_path: Path) -> None:
    ledger = StubLedger(anchor_error=LedgerUnavailableError("Anvil unreachable"))
    pipeline, image = _make_pipeline(tmp_path, ledger=ledger)

    result = pipeline.run(image)

    assert [event.stage for event in result.events] == [
        "validated",
        "face_scanned",
        "post_found",
        "failed",
    ]
    assert result.evidence is not None  # discovery result survives for evidence.json
    assert result.receipt is None  # unanchored
    assert result.verification is None
    assert ledger.anchor_calls == 1
    assert isinstance(result.events[-1].detail, str)
    assert "Anvil unreachable" in result.events[-1].detail


def test_e2e_altered_evidence_verify_returns_matched_false(tmp_path: Path) -> None:
    ledger = _ledger()
    pipeline, image = _make_pipeline(tmp_path, ledger=ledger)

    first = pipeline.run(image)
    assert first.evidence is not None
    altered = first.evidence.model_copy(update={"provider": "tampered-provider"})

    verification = pipeline.verify_bundle(altered)  # must not raise

    assert verification.matched is False
    assert verification.receipt is None
    assert pipeline.verify_bundle(first.evidence).matched is True


# ── CLI integration ────────────────────────────────────────────────────────


_cli_runner = CliRunner()


def _stub_build_pipeline() -> FaceVerificationPipeline:
    return FaceVerificationPipeline(
        identity=IdentityService(FakeFaceScanner("b" * 64)),
        discovery=DiscoveryService(FakeDiscoveryProvider(canned_result=_discovery_result())),
        ledger=StubLedger(),
    )


def _stub_no_match_pipeline() -> FaceVerificationPipeline:
    return FaceVerificationPipeline(
        identity=IdentityService(FakeFaceScanner("b" * 64)),
        discovery=DiscoveryService(FakeDiscoveryProvider()),
        ledger=StubLedger(),
    )


def test_cli_help_lists_commands() -> None:
    result = _cli_runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
    assert "verify" in result.output


def test_cli_run_success_prints_events_and_writes_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_build_pipeline", _stub_build_pipeline)
    image_path = tmp_path / "input.jpg"
    image_path.write_bytes(b"sample-image-bytes")

    result = _cli_runner.invoke(
        cli.app,
        ["run", "--image", str(image_path), "--runs-dir", str(tmp_path / "runs"), "--save"],
    )

    assert result.exit_code == 0
    for stage in ("validated", "face_scanned", "post_found", "anchored", "verified"):
        assert f"[{stage}]" in result.output
    assert "3 platform match" in result.output
    assert "ExamplePlatform" in result.output
    assert "92%" in result.output
    assert "XProfile" in result.output
    assert "71%" in result.output
    assert "no provider score" in result.output
    assert "Evidence bundle" in result.output
    assert "Evidence saved to" in result.output
    run_dirs = list((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    evidence_file = run_dirs[0] / "evidence.json"
    assert evidence_file.exists()
    EvidenceBundle.model_validate_json(evidence_file.read_text())


def test_cli_run_default_prints_evidence_without_writing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_build_pipeline", _stub_build_pipeline)
    image_path = tmp_path / "input.jpg"
    image_path.write_bytes(b"sample-image-bytes")

    result = _cli_runner.invoke(
        cli.app,
        ["run", "--image", str(image_path), "--runs-dir", str(tmp_path / "runs")],
    )

    assert result.exit_code == 0
    assert "Evidence bundle" in result.output
    assert '"provider": "fake_lens"' in result.output
    assert "Evidence saved to" not in result.output
    assert not (tmp_path / "runs").exists()


def test_cli_run_no_match_exits_six(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_build_pipeline", _stub_no_match_pipeline)
    image_path = tmp_path / "input.jpg"
    image_path.write_bytes(b"sample-image-bytes")

    result = _cli_runner.invoke(cli.app, ["run", "--image", str(image_path)])

    assert result.exit_code == 6
    assert "[failed]" in result.output


def test_cli_run_missing_image_exits_one(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jpg"

    result = _cli_runner.invoke(cli.app, ["run", "--image", str(missing)])

    assert result.exit_code == 1
    assert "cannot read image" in result.output


def test_cli_run_surfaces_documented_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_face_pipeline() -> FaceVerificationPipeline:
        return FaceVerificationPipeline(
            identity=IdentityService(FakeFaceScanner("b" * 64, fail=True)),
            discovery=DiscoveryService(FakeDiscoveryProvider(canned_result=_discovery_result())),
            ledger=StubLedger(),
        )

    monkeypatch.setattr(cli, "_build_pipeline", _no_face_pipeline)
    image_path = tmp_path / "input.jpg"
    image_path.write_bytes(b"sample-image-bytes")

    result = _cli_runner.invoke(cli.app, ["run", "--image", str(image_path)])

    assert result.exit_code == 3
    assert "no face detected" in result.output


def test_cli_run_chain_write_error_writes_evidence_and_exits_nine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _failing_anchor_pipeline() -> FaceVerificationPipeline:
        return FaceVerificationPipeline(
            identity=IdentityService(FakeFaceScanner("b" * 64)),
            discovery=DiscoveryService(FakeDiscoveryProvider(canned_result=_discovery_result())),
            ledger=StubLedger(anchor_error=LedgerUnavailableError("Anvil unreachable")),
        )

    monkeypatch.setattr(cli, "_build_pipeline", _failing_anchor_pipeline)
    image_path = tmp_path / "input.jpg"
    image_path.write_bytes(b"sample-image-bytes")

    result = _cli_runner.invoke(
        cli.app,
        ["run", "--image", str(image_path), "--runs-dir", str(tmp_path / "runs"), "--save"],
    )

    assert result.exit_code == 9
    assert "[failed]" in result.output
    assert "Run failed; evidence was not anchored on-chain" in result.output
    run_dirs = list((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    evidence_file = run_dirs[0] / "evidence.json"
    assert evidence_file.exists()
    bundle = EvidenceBundle.model_validate_json(evidence_file.read_text())
    assert bundle.face_embedding_sha256 == "b" * 64


def test_cli_verify_matched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _matched_pipeline() -> FaceVerificationPipeline:
        return FaceVerificationPipeline(
            identity=IdentityService(FakeFaceScanner("b" * 64)),
            discovery=DiscoveryService(FakeDiscoveryProvider(canned_result=_discovery_result())),
            ledger=StubLedger(always_match=True),
        )

    monkeypatch.setattr(cli, "_build_pipeline", _matched_pipeline)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        EvidenceBundle(
            consent_reference="consent-ref-12345",
            input_image_sha256="b" * 64,
            face_embedding_sha256="c" * 64,
            provider="fake_lens",
            post=_post(),
        ).model_dump_json()
    )

    result = _cli_runner.invoke(cli.app, ["verify", "--evidence", str(evidence_path)])

    assert result.exit_code == 0
    assert "Verified: matched" in result.output


def test_cli_verify_unmatched_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _mismatched_pipeline() -> FaceVerificationPipeline:
        return FaceVerificationPipeline(
            identity=IdentityService(FakeFaceScanner("b" * 64)),
            discovery=DiscoveryService(FakeDiscoveryProvider(canned_result=_discovery_result())),
            ledger=StubLedger(report_mismatch=True),
        )

    monkeypatch.setattr(cli, "_build_pipeline", _mismatched_pipeline)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        EvidenceBundle(
            consent_reference="consent-ref-12345",
            input_image_sha256="b" * 64,
            face_embedding_sha256="c" * 64,
            provider="fake_lens",
            post=_post(),
        ).model_dump_json()
    )

    result = _cli_runner.invoke(cli.app, ["verify", "--evidence", str(evidence_path)])

    assert result.exit_code == 1
    assert "Not matched" in result.output


def test_cli_verify_missing_evidence_exits_one(tmp_path: Path) -> None:
    result = _cli_runner.invoke(
        cli.app, ["verify", "--evidence", str(tmp_path / "missing.json")]
    )
    assert result.exit_code == 1
    assert "cannot read evidence file" in result.output


def test_score_matches_fill_confidence_from_identity_similarity(tmp_path: Path) -> None:
    """When a match has image_url, pipeline fetches + scans + fills confidence."""
    from pydantic import HttpUrl

    from facechain.discovery.provider import FakeDiscoveryProvider
    from facechain.identity.service import FakeFaceScanner, IdentityService

    provider = FakeDiscoveryProvider(
        canned_result=DiscoveryResult(
            provider="fake_lens",
            matched_post=_post(),
            matches=[
                DiscoveryMatch(
                    post=PublicPost(
                        source_url="https://x.example/user/1",
                        platform="XProfile",
                        retrieved_at=datetime.now(UTC),
                        image_url=HttpUrl("https://cdn.example.com/thumb.jpg"),
                    ),
                    confidence=None,
                ),
                DiscoveryMatch(
                    post=PublicPost(
                        source_url="https://ig.example/u/2",
                        platform="InstagramProfile",
                        retrieved_at=datetime.now(UTC),
                        image_url=None,
                    ),
                    confidence=None,
                ),
            ],
        ),
        canned_image_bytes=b"fake-thumbnail-bytes",
    )
    scanner = FakeFaceScanner()
    pipeline = FaceVerificationPipeline(
        identity=IdentityService(scanner),
        discovery=DiscoveryService(provider),
        ledger=StubLedger(),
    )
    path = tmp_path / "input.jpg"
    path.write_bytes(b"input-bytes")
    result = pipeline.run(_make_image(path))

    assert result.verification is not None
    assert len(result.matches) == 2
    # match with image_url → confidence filled from similarity
    assert result.matches[0].confidence == 0.87
    # match without image_url → confidence preserved as None
    assert result.matches[1].confidence is None


def test_score_matches_keeps_provider_confidence_on_fetch_failure(tmp_path: Path) -> None:
    """When fetch_image raises, provider's original confidence is preserved."""
    from pydantic import HttpUrl

    from facechain.discovery.exceptions import DiscoveryUnavailableError
    from facechain.discovery.provider import FakeDiscoveryProvider
    from facechain.identity.service import FakeFaceScanner, IdentityService

    provider = FakeDiscoveryProvider(
        canned_result=DiscoveryResult(
            provider="fake_lens",
            matched_post=_post(),
            matches=[
                DiscoveryMatch(
                    post=PublicPost(
                        source_url="https://x.example/user/1",
                        platform="XProfile",
                        retrieved_at=datetime.now(UTC),
                        image_url=HttpUrl("https://cdn.example.com/thumb.jpg"),
                    ),
                    confidence=0.75,
                ),
            ],
        ),
        raise_fetch_error=DiscoveryUnavailableError("timeout"),
    )
    scanner = FakeFaceScanner()
    pipeline = FaceVerificationPipeline(
        identity=IdentityService(scanner),
        discovery=DiscoveryService(provider),
        ledger=StubLedger(),
    )
    path = tmp_path / "input.jpg"
    path.write_bytes(b"input-bytes")
    result = pipeline.run(_make_image(path))

    # fetch failed → original provider confidence preserved
    assert result.matches[0].confidence == 0.75


def test_score_matches_no_face_in_thumbnail_keeps_provider_confidence(
    tmp_path: Path,
) -> None:
    """When thumbnail has no face, provider's original confidence is preserved."""
    from pydantic import HttpUrl

    from facechain.discovery.provider import FakeDiscoveryProvider
    from facechain.identity.service import FakeFaceScanner, IdentityService

    provider = FakeDiscoveryProvider(
        canned_result=DiscoveryResult(
            provider="fake_lens",
            matched_post=_post(),
            matches=[
                DiscoveryMatch(
                    post=PublicPost(
                        source_url="https://x.example/user/1",
                        platform="XProfile",
                        retrieved_at=datetime.now(UTC),
                        image_url=HttpUrl("https://cdn.example.com/thumb.jpg"),
                    ),
                    confidence=0.80,
                ),
            ],
        ),
        canned_image_bytes=b"no-face",
    )
    scanner = FakeFaceScanner(fail_scan_bytes=True)
    pipeline = FaceVerificationPipeline(
        identity=IdentityService(scanner),
        discovery=DiscoveryService(provider),
        ledger=StubLedger(),
    )
    path = tmp_path / "input.jpg"
    path.write_bytes(b"input-bytes")
    result = pipeline.run(_make_image(path))

    # scan_bytes raised NoFaceDetectedError → original provider confidence preserved
    assert result.matches[0].confidence == 0.80