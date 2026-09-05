"""Identity module tests. Uses deterministic fakes; no network calls."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from contracts.domain import AuthorizedImage, FaceScan
from facechain.identity import (
    FakeFaceScanner,
    IdentityService,
    InputValidationError,
    NoFaceDetectedError,
)


def make_image(tmp_path: Path, content: bytes = b"sample-image-bytes") -> AuthorizedImage:
    path = tmp_path / "input.jpg"
    path.write_bytes(content)
    return AuthorizedImage(
        image_path=str(path),
        sha256=hashlib.sha256(content).hexdigest(),
        consent_reference="consent-abc-123",
    )


def test_authorized_image_valid() -> None:
    sha = hashlib.sha256(b"abc").hexdigest()
    image = AuthorizedImage(
        image_path="/some/path/input.jpg",
        sha256=sha,
        consent_reference="consent-123",
    )
    assert image.image_path == "/some/path/input.jpg"
    assert image.sha256 == sha


@pytest.mark.parametrize(
    "override, message",
    [
        ({"image_path": ""}, "image_path"),
        ({"sha256": "not-a-hash"}, "sha256"),
        ({"consent_reference": "ab"}, "consent_reference"),
    ],
)
def test_authorized_image_rejects_invalid_fields(override: dict, message: str) -> None:
    sha = hashlib.sha256(b"abc").hexdigest()
    base: dict = {
        "image_path": "/some/path/input.jpg",
        "sha256": sha,
        "consent_reference": "consent-123",
    }
    base.update(override)
    with pytest.raises(ValidationError) as exc_info:
        AuthorizedImage(**base)
    assert message in str(exc_info.value)


def test_validate_image_ok(tmp_path: Path) -> None:
    image = make_image(tmp_path)
    scanner = FakeFaceScanner()
    service = IdentityService(scanner)
    service.validate_image(image)


def test_validate_image_missing_file(tmp_path: Path) -> None:
    image = AuthorizedImage(
        image_path=str(tmp_path / "missing.jpg"),
        sha256=hashlib.sha256(b"x").hexdigest(),
        consent_reference="consent-123",
    )
    scanner = FakeFaceScanner()
    service = IdentityService(scanner)
    with pytest.raises(InputValidationError, match="does not exist"):
        service.validate_image(image)


def test_validate_image_hash_mismatch(tmp_path: Path) -> None:
    image = AuthorizedImage(
        image_path=str(tmp_path / "input.jpg"),
        sha256=hashlib.sha256(b"different").hexdigest(),
        consent_reference="consent-123",
    )
    (tmp_path / "input.jpg").write_bytes(b"actual-bytes")
    service = IdentityService(FakeFaceScanner())
    with pytest.raises(InputValidationError, match="SHA-256 mismatch"):
        service.validate_image(image)


def test_scan_returns_face_scan(tmp_path: Path) -> None:
    image = make_image(tmp_path)
    scanner = FakeFaceScanner()
    service = IdentityService(scanner)
    scan = service.scan(image)
    assert isinstance(scan, FaceScan)
    assert scan.face_count == 1
    assert scan.detector == "fake"
    assert len(scan.embedding_sha256) == 64
    assert scanner.call_count == 1


def test_scan_deterministic_with_stable_embedding(tmp_path: Path) -> None:
    image = make_image(tmp_path)
    scanner = FakeFaceScanner()
    service = IdentityService(scanner)
    first = service.scan(image)
    second = service.scan(image)
    assert first.embedding_sha256 == second.embedding_sha256
    assert first.scanned_at <= second.scanned_at


def test_scan_custom_embedding(tmp_path: Path) -> None:
    image = make_image(tmp_path)
    custom = hashlib.sha256(b"custom").hexdigest()
    service = IdentityService(FakeFaceScanner(embedding_sha256=custom))
    scan = service.scan(image)
    assert scan.embedding_sha256 == custom


def test_scan_no_face_raises(tmp_path: Path) -> None:
    image = make_image(tmp_path)
    service = IdentityService(FakeFaceScanner(fail=True))
    with pytest.raises(NoFaceDetectedError, match="No face detected"):
        service.scan(image)


def test_scan_invalid_image_raises(tmp_path: Path) -> None:
    image = AuthorizedImage(
        image_path=str(tmp_path / "missing.jpg"),
        sha256=hashlib.sha256(b"x").hexdigest(),
        consent_reference="consent-123",
    )
    service = IdentityService(FakeFaceScanner())
    with pytest.raises(InputValidationError):
        service.scan(image)
