"""Identity module tests. Uses deterministic fakes; no network calls."""

import hashlib
import sys
import types
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from contracts.domain import AuthorizedImage, FaceScan
from facechain.identity import (
    FakeFaceScanner,
    IdentityService,
    InputValidationError,
    InsightFaceFaceScanner,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    RecognitionUnavailableError,
)

# ── helpers ──────────────────────────────────────────────────────────────


def make_image(tmp_path: Path, content: bytes = b"sample-image-bytes") -> AuthorizedImage:
    path = tmp_path / "input.jpg"
    path.write_bytes(content)
    return AuthorizedImage(
        image_path=str(path),
        sha256=hashlib.sha256(content).hexdigest(),
        consent_reference="consent-abc-123",
    )


def make_real_image(tmp_path: Path) -> Path:
    arr = np.full((48, 64, 3), 120, dtype=np.uint8)
    path = tmp_path / "face.jpg"
    assert cv2.imwrite(str(path), arr)
    return path


def make_authorized(tmp_path: Path) -> AuthorizedImage:
    path = make_real_image(tmp_path)
    data = path.read_bytes()
    return AuthorizedImage(
        image_path=str(path),
        sha256=hashlib.sha256(data).hexdigest(),
        consent_reference="consent-abc-123",
    )


# ── fake objects for the InsightFace adapter ─────────────────────────────


class FakeFace:
    def __init__(
        self,
        embedding: np.ndarray | None = None,
        normed: np.ndarray | None = None,
    ) -> None:
        self._embedding = embedding
        self._normed = normed

    @property
    def embedding(self) -> np.ndarray | None:
        return self._embedding

    @property
    def normed_embedding(self) -> np.ndarray | None:
        return self._normed


class FakeAnalyzer:
    def __init__(
        self,
        faces: list[FakeFace] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.faces = list(faces) if faces is not None else []
        self.error = error
        self.get_calls: list[np.ndarray] = []

    def get(self, img: np.ndarray) -> list[FakeFace]:
        self.get_calls.append(img)
        if self.error is not None:
            raise self.error
        return self.faces


# ── Phase 1: AuthorizedImage validation ──────────────────────────────────


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
    service = IdentityService(FakeFaceScanner())
    service.validate_image(image)


def test_validate_image_missing_file(tmp_path: Path) -> None:
    image = AuthorizedImage(
        image_path=str(tmp_path / "missing.jpg"),
        sha256=hashlib.sha256(b"x").hexdigest(),
        consent_reference="consent-123",
    )
    service = IdentityService(FakeFaceScanner())
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


# ── Phase 1: FakeFaceScanner / IdentityService ───────────────────────────


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


# ── Phase 2: InsightFaceFaceScanner adapter ──────────────────────────────


def test_single_face_returns_normalized_hash(tmp_path: Path) -> None:
    raw = np.array([3.0, 4.0], dtype=np.float32)
    normed = raw / np.linalg.norm(raw)
    expected = hashlib.sha256(np.ascontiguousarray(normed, dtype=np.float32).tobytes()).hexdigest()
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer([FakeFace(embedding=raw)]))
    scan = scanner.scan(make_authorized(tmp_path))
    assert scan.embedding_sha256 == expected
    assert scan.embedding_sha256 != hashlib.sha256(raw.tobytes()).hexdigest()
    assert scan.face_count == 1
    assert scan.detector == "buffalo_l"


def test_single_face_uses_pre_normed_embedding(tmp_path: Path) -> None:
    normed = np.array([0.6, 0.8], dtype=np.float32)
    expected = hashlib.sha256(np.ascontiguousarray(normed, dtype=np.float32).tobytes()).hexdigest()
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer([FakeFace(normed=normed)]))
    scan = scanner.scan(make_authorized(tmp_path))
    assert scan.embedding_sha256 == expected


def test_zero_faces_raises(tmp_path: Path) -> None:
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer([]))
    with pytest.raises(NoFaceDetectedError, match="No face detected"):
        scanner.scan(make_authorized(tmp_path))


def test_multiple_faces_raises(tmp_path: Path) -> None:
    faces = [FakeFace(embedding=np.zeros(3)) for _ in range(3)]
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer(faces))
    with pytest.raises(MultipleFacesDetectedError, match="Expected exactly one face"):
        scanner.scan(make_authorized(tmp_path))


def test_no_embedding_raises(tmp_path: Path) -> None:
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer([FakeFace(embedding=None, normed=None)]))
    with pytest.raises(RecognitionUnavailableError, match="recognition returned no embedding"):
        scanner.scan(make_authorized(tmp_path))


def test_unreadable_image_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.txt"
    path.write_bytes(b"not-an-image")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    image = AuthorizedImage(image_path=str(path), sha256=sha, consent_reference="consent-123")
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer([]))
    with pytest.raises(InputValidationError, match="Unable to read image"):
        scanner.scan(image)


def test_analyzer_error_is_wrapped(tmp_path: Path) -> None:
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer(error=RuntimeError("engine down")))
    with pytest.raises(RecognitionUnavailableError, match="engine down"):
        scanner.scan(make_authorized(tmp_path))


def test_analyzer_identity_error_passes_through(tmp_path: Path) -> None:
    scanner = InsightFaceFaceScanner(
        analyzer=FakeAnalyzer(error=NoFaceDetectedError("from provider")),
    )
    with pytest.raises(NoFaceDetectedError):
        scanner.scan(make_authorized(tmp_path))


def test_analyzer_receives_rgb_image(tmp_path: Path) -> None:
    analyzer = FakeAnalyzer([FakeFace(embedding=np.ones(4, dtype=np.float32))])
    scanner = InsightFaceFaceScanner(analyzer=analyzer)
    scanner.scan(make_authorized(tmp_path))
    assert len(analyzer.get_calls) == 1
    img = analyzer.get_calls[0]
    assert img.ndim == 3 and img.shape[2] == 3 and img.dtype == np.uint8


def test_analyzer_call_count(tmp_path: Path) -> None:
    analyzer = FakeAnalyzer([FakeFace(embedding=np.ones(4, dtype=np.float32))])
    scanner = InsightFaceFaceScanner(analyzer=analyzer)
    scanner.scan(make_authorized(tmp_path))
    scanner.scan(make_authorized(tmp_path))
    assert len(analyzer.get_calls) == 2


def test_raw_embedding_never_leaked(tmp_path: Path) -> None:
    raw = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer([FakeFace(embedding=raw)]))
    scan = scanner.scan(make_authorized(tmp_path))
    assert scan.embedding_sha256 != hashlib.sha256(raw.tobytes()).hexdigest()
    assert isinstance(scan, FaceScan)
    dumped = scan.model_dump()
    assert set(dumped) == {"embedding_sha256", "detector", "face_count", "scanned_at"}
    assert set(dumped) <= {"face_count", "embedding_sha256", "detector", "scanned_at"}
    assert all(key != "embedding" for key in dumped)


def test_init_failure_wrapped(tmp_path: Path) -> None:
    fake_mod = types.ModuleType("insightface")
    fake_app = types.ModuleType("insightface.app")

    class _BadFaceAnalysis:
        def __init__(self, **kwargs: object) -> None:
            raise RuntimeError("no models available")

        def prepare(self, **kwargs: object) -> None:
            pass

    fake_app.FaceAnalysis = _BadFaceAnalysis  # type: ignore[attr-defined]
    fake_mod.app = fake_app  # type: ignore[attr-defined]

    saved = sys.modules.pop("insightface", None)
    saved_app = sys.modules.pop("insightface.app", None)
    sys.modules["insightface"] = fake_mod
    sys.modules["insightface.app"] = fake_app
    try:
        scanner = InsightFaceFaceScanner()
        with pytest.raises(RecognitionUnavailableError, match="Failed to initialize"):
            scanner.scan(make_authorized(tmp_path))
    finally:
        sys.modules.pop("insightface", None)
        sys.modules.pop("insightface.app", None)
        if saved is not None:
            sys.modules["insightface"] = saved
        if saved_app is not None:
            sys.modules["insightface.app"] = saved_app


# ── Phase 2: integration through IdentityService ─────────────────────────


def test_scan_via_identity_service(tmp_path: Path) -> None:
    raw = np.array([0.0, 1.0], dtype=np.float32)
    expected = hashlib.sha256(
        np.ascontiguousarray(raw / np.linalg.norm(raw), dtype=np.float32).tobytes()
    ).hexdigest()
    service = IdentityService(
        InsightFaceFaceScanner(analyzer=FakeAnalyzer([FakeFace(embedding=raw)]))
    )
    scan = service.scan(make_authorized(tmp_path))
    assert scan.embedding_sha256 == expected
    assert scan.face_count == 1


def test_service_error_paths_with_provider(tmp_path: Path) -> None:
    image = make_authorized(tmp_path)
    service_zero = IdentityService(InsightFaceFaceScanner(analyzer=FakeAnalyzer([])))
    with pytest.raises(NoFaceDetectedError):
        service_zero.scan(image)

    multi_faces = [FakeFace(embedding=np.ones(3)) for _ in range(2)]
    service_multi = IdentityService(InsightFaceFaceScanner(analyzer=FakeAnalyzer(multi_faces)))
    with pytest.raises(MultipleFacesDetectedError):
        service_multi.scan(image)


def test_service_unreadable_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"not-an-image")
    sha = hashlib.sha256(b"not-an-image").hexdigest()
    image = AuthorizedImage(image_path=str(bad), sha256=sha, consent_reference="consent-123")
    service = IdentityService(InsightFaceFaceScanner(analyzer=FakeAnalyzer([])))
    with pytest.raises(InputValidationError):
        service.scan(image)


def test_scan_bytes_decodes_and_hashes_raw_images(tmp_path: Path) -> None:
    raw = np.array([0.0, 1.0], dtype=np.float32)
    expected = hashlib.sha256(
        np.ascontiguousarray(raw / np.linalg.norm(raw), dtype=np.float32).tobytes()
    ).hexdigest()
    scanner = InsightFaceFaceScanner(
        analyzer=FakeAnalyzer([FakeFace(embedding=raw)])
    )
    image_bytes = make_real_image(tmp_path).read_bytes()
    scan = scanner.scan_bytes(image_bytes)
    assert scan.embedding_sha256 == expected
    assert scan.face_count == 1


def test_scan_bytes_invalid_bytes_raises() -> None:
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer([]))
    with pytest.raises(InputValidationError):
        scanner.scan_bytes(b"not-an-image")


def test_scan_bytes_no_face_raises(tmp_path: Path) -> None:
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer([]))
    with pytest.raises(NoFaceDetectedError):
        scanner.scan_bytes(make_real_image(tmp_path).read_bytes())


def test_similarity_compares_cached_embedding_for_same_subject(tmp_path: Path) -> None:
    raw = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer([FakeFace(embedding=raw)]))
    a = scanner.scan_bytes(make_real_image(tmp_path).read_bytes())
    b = scanner.scan_bytes(make_real_image(tmp_path).read_bytes())
    # identical normalized embeddings → cosine similarity 1.0
    assert scanner.similarity(a, b) == pytest.approx(1.0)


def test_similarity_raises_for_foreign_scan() -> None:
    raw = np.array([1.0, 0.0], dtype=np.float32)
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer([FakeFace(embedding=raw)]))
    foreign = FaceScan(
        embedding_sha256="f" * 64,
        detector="other",
        face_count=1,
        scanned_at=datetime.now(UTC),
    )
    with pytest.raises(RecognitionUnavailableError):
        scanner.similarity(foreign, foreign)


def test_scan_caches_embedding_for_similarity(tmp_path: Path) -> None:
    raw = np.array([0.0, 1.0], dtype=np.float32)
    scanner = InsightFaceFaceScanner(analyzer=FakeAnalyzer([FakeFace(embedding=raw)]))
    image_bytes = make_real_image(tmp_path).read_bytes()
    image_scan = scanner.scan(make_authorized(tmp_path))
    candidate_scan = scanner.scan_bytes(image_bytes)
    assert scanner.similarity(image_scan, candidate_scan) == pytest.approx(1.0)
