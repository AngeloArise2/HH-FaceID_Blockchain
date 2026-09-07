"""Unit tests for the Discovery module."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import HttpUrl

from contracts.discovery import DiscoveryResult
from contracts.domain import AuthorizedImage, FaceScan, PublicPost
from facechain.discovery.exceptions import (
    DiscoveryConfigError,
    DiscoveryError,
    DiscoveryUnavailableError,
    NoMatchFoundError,
)
from facechain.discovery.models import (
    DiscoveryResult as DiscoveryResultModel,
)
from facechain.discovery.models import (
    EvidenceBundle as EvidenceBundleModel,
)
from facechain.discovery.models import (
    PublicPost as PublicPostModel,
)
from facechain.discovery.provider import (
    DiscoveryProvider,
    FakeDiscoveryProvider,
    SerpAPILensProvider,
)
from facechain.discovery.service import (
    DiscoveryService,
    canonicalize_evidence,
    compute_evidence_hash,
)


@pytest.fixture
def sample_authorized_image() -> AuthorizedImage:
    return AuthorizedImage(
        image_path="/path/to/consented-subject.jpg",
        sha256="a" * 64,
        consent_reference="consent-ref-12345",
    )


@pytest.fixture
def sample_face_scan() -> FaceScan:
    return FaceScan(
        embedding_sha256="b" * 64,
        detector="insightface-buffalo_l",
        face_count=1,
        scanned_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_public_post() -> PublicPost:
    return PublicPost(
        source_url=HttpUrl("https://example.com/posts/101"),
        platform="ExamplePlatform",
        title="Public Profile Photo",
        text_excerpt="Publicly shared portrait photo.",
        image_url=HttpUrl("https://example.com/images/101.jpg"),
        retrieved_at=datetime.now(UTC),
    )


def test_discovery_provider_protocol_conformance() -> None:
    provider = FakeDiscoveryProvider()
    assert isinstance(provider, DiscoveryProvider)
    serp_provider = SerpAPILensProvider(api_key="test_key")
    assert isinstance(serp_provider, DiscoveryProvider)


def test_discovery_exception_hierarchy() -> None:
    assert issubclass(DiscoveryUnavailableError, DiscoveryError)
    assert issubclass(NoMatchFoundError, DiscoveryError)
    assert issubclass(DiscoveryConfigError, DiscoveryError)


def test_discovery_models_reexport() -> None:
    assert DiscoveryResultModel is DiscoveryResult
    assert EvidenceBundleModel is not None
    assert PublicPostModel is PublicPost


def test_discovery_service_successful_match(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
    sample_public_post: PublicPost,
) -> None:
    expected_result = DiscoveryResult(
        provider="fake_visual_search",
        matched_post=sample_public_post,
        confidence=0.95,
    )
    provider = FakeDiscoveryProvider(canned_result=expected_result)
    service = DiscoveryService(provider=provider)

    assert service.provider is provider

    result = service.discover(sample_authorized_image, sample_face_scan)

    assert result.provider == "fake_visual_search"
    assert result.confidence == 0.95
    assert result.matched_post.source_url == HttpUrl("https://example.com/posts/101")
    assert result.matched_post.platform == "ExamplePlatform"
    assert len(provider.recorded_calls) == 1
    assert provider.recorded_calls[0] == (sample_authorized_image, sample_face_scan)


def test_discovery_service_no_match_raises_error(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
) -> None:
    provider = FakeDiscoveryProvider(canned_result=None)
    service = DiscoveryService(provider=provider)

    with pytest.raises(NoMatchFoundError, match="No qualifying public match"):
        service.discover(sample_authorized_image, sample_face_scan)


def test_discovery_service_unavailable_raises_error(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
) -> None:
    provider = FakeDiscoveryProvider(
        raise_error=DiscoveryUnavailableError("Provider endpoint unreachable")
    )
    service = DiscoveryService(provider=provider)

    with pytest.raises(DiscoveryUnavailableError, match="Provider endpoint unreachable"):
        service.discover(sample_authorized_image, sample_face_scan)


def test_assemble_evidence_bundle(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
    sample_public_post: PublicPost,
) -> None:
    result = DiscoveryResult(
        provider="fake_provider",
        matched_post=sample_public_post,
    )
    service = DiscoveryService(provider=FakeDiscoveryProvider(canned_result=result))

    bundle = service.assemble_evidence(result, sample_authorized_image, sample_face_scan)

    assert bundle.schema_version == "1.0"
    assert bundle.consent_reference == sample_authorized_image.consent_reference
    assert bundle.input_image_sha256 == sample_authorized_image.sha256
    assert bundle.face_embedding_sha256 == sample_face_scan.embedding_sha256
    assert bundle.provider == "fake_provider"
    assert bundle.post == sample_public_post


# =========================================================================
# SerpAPI Google Lens Adapter Tests
# =========================================================================


def test_serpapi_missing_key_raises_config_error(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    provider = SerpAPILensProvider(api_key="")
    with pytest.raises(DiscoveryConfigError, match="SERPAPI_KEY is required"):
        provider.search(sample_authorized_image, sample_face_scan)


@respx.mock
def test_serpapi_remote_url_search_success(
    sample_face_scan: FaceScan,
) -> None:
    image = AuthorizedImage(
        image_path="https://example.com/subject.jpg",
        sha256="c" * 64,
        consent_reference="consent-remote-123",
    )
    search_route = respx.get("https://serpapi.com/search.json").respond(
        status_code=200,
        json={
            "visual_matches": [
                {
                    "position": 1,
                    "title": "Public Article Featuring Subject",
                    "link": "https://news.example.org/article/42",
                    "source": "NewsOutlet",
                    "thumbnail": "https://news.example.org/images/thumb.jpg",
                    "snippet": "Subject attending conference in Goa.",
                }
            ]
        },
    )

    provider = SerpAPILensProvider(api_key="secret_test_key")
    result = provider.search(image, sample_face_scan)

    assert search_route.called
    assert result.provider == "serpapi_google_lens"
    assert result.matched_post.source_url == HttpUrl("https://news.example.org/article/42")
    assert result.matched_post.platform == "NewsOutlet"
    assert result.matched_post.title == "Public Article Featuring Subject"
    assert result.matched_post.text_excerpt == "Subject attending conference in Goa."
    assert result.matched_post.image_url == HttpUrl("https://news.example.org/images/thumb.jpg")


@respx.mock
def test_serpapi_local_file_upload_and_search_success(
    tmp_path: Path,
    sample_face_scan: FaceScan,
) -> None:
    test_img = tmp_path / "consented_test.jpg"
    test_img.write_bytes(b"dummy image data")

    image = AuthorizedImage(
        image_path=str(test_img),
        sha256="d" * 64,
        consent_reference="consent-local-456",
    )

    upload_route = respx.post("https://serpapi.com/image").respond(
        status_code=200,
        json={"image_id": "serpapi_img_id_999"},
    )
    search_route = respx.get("https://serpapi.com/search.json").respond(
        status_code=200,
        json={
            "visual_matches": [
                {
                    "title": "Public Profile",
                    "link": "https://social.example.com/profile/1",
                    "source": "SocialNet",
                    "thumbnail": "https://social.example.com/img.jpg",
                }
            ]
        },
    )

    provider = SerpAPILensProvider(api_key="secret_test_key")
    result = provider.search(image, sample_face_scan)

    assert upload_route.called
    assert search_route.called
    assert search_route.calls.last.request.url.params["image_id"] == "serpapi_img_id_999"
    assert result.matched_post.source_url == HttpUrl("https://social.example.com/profile/1")
    assert result.matched_post.platform == "SocialNet"


def test_serpapi_local_file_not_found(
    sample_face_scan: FaceScan,
) -> None:
    image = AuthorizedImage(
        image_path="D:/nonexistent/image.jpg",
        sha256="e" * 64,
        consent_reference="consent-missing-file",
    )
    provider = SerpAPILensProvider(api_key="secret_test_key")
    with pytest.raises(DiscoveryUnavailableError, match="Image file not found"):
        provider.search(image, sample_face_scan)


@respx.mock
def test_serpapi_upload_failure_invalid_json(
    tmp_path: Path,
    sample_face_scan: FaceScan,
) -> None:
    test_img = tmp_path / "test.jpg"
    test_img.write_bytes(b"img")
    image = AuthorizedImage(image_path=str(test_img), sha256="f" * 64, consent_reference="ref")

    respx.post("https://serpapi.com/image").respond(status_code=200, text="not json")
    provider = SerpAPILensProvider(api_key="test_key")
    with pytest.raises(DiscoveryUnavailableError, match="Invalid JSON response"):
        provider.search(image, sample_face_scan)


@respx.mock
def test_serpapi_upload_missing_image_id(
    tmp_path: Path,
    sample_face_scan: FaceScan,
) -> None:
    test_img = tmp_path / "test.jpg"
    test_img.write_bytes(b"img")
    image = AuthorizedImage(image_path=str(test_img), sha256="f" * 64, consent_reference="ref")

    respx.post("https://serpapi.com/image").respond(status_code=200, json={})
    provider = SerpAPILensProvider(api_key="test_key")
    with pytest.raises(DiscoveryUnavailableError, match="No image_id returned"):
        provider.search(image, sample_face_scan)


@respx.mock
def test_serpapi_no_matches_raises_no_match_found(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
) -> None:
    respx.get("https://serpapi.com/search.json").respond(
        status_code=200,
        json={"visual_matches": []},
    )
    provider = SerpAPILensProvider(
        api_key="test_key",
        http_client=httpx.Client(),
    )
    # Use image with url to skip upload
    image = AuthorizedImage(
        image_path="https://example.com/img.jpg",
        sha256="1" * 64,
        consent_reference="ref-1",
    )
    with pytest.raises(NoMatchFoundError, match="No qualifying public match"):
        provider.search(image, sample_face_scan)


@respx.mock
def test_serpapi_matches_without_valid_links_raises_no_match(
    sample_face_scan: FaceScan,
) -> None:
    respx.get("https://serpapi.com/search.json").respond(
        status_code=200,
        json={"visual_matches": [{"title": "No Link"}, {"link": "ftp://invalid"}]},
    )
    image = AuthorizedImage(
        image_path="https://example.com/img.jpg",
        sha256="2" * 64,
        consent_reference="ref-2",
    )
    provider = SerpAPILensProvider(api_key="test_key")
    with pytest.raises(NoMatchFoundError, match="No visual match with a valid public source URL"):
        provider.search(image, sample_face_scan)


@respx.mock
def test_serpapi_401_unauthorized_raises_config_error(
    sample_face_scan: FaceScan,
) -> None:
    respx.get("https://serpapi.com/search.json").respond(
        status_code=401,
        text="Invalid API key",
    )
    image = AuthorizedImage(
        image_path="https://example.com/img.jpg",
        sha256="3" * 64,
        consent_reference="ref-3",
    )
    provider = SerpAPILensProvider(api_key="bad_key")
    with pytest.raises(DiscoveryConfigError, match="SerpAPI authentication failed"):
        provider.search(image, sample_face_scan)


@respx.mock
def test_serpapi_error_field_in_json(
    sample_face_scan: FaceScan,
) -> None:
    respx.get("https://serpapi.com/search.json").respond(
        status_code=200,
        json={"error": "Invalid API key provided."},
    )
    image = AuthorizedImage(
        image_path="https://example.com/img.jpg",
        sha256="4" * 64,
        consent_reference="ref-4",
    )
    provider = SerpAPILensProvider(api_key="bad_key")
    with pytest.raises(DiscoveryConfigError, match="SerpAPI authentication failed"):
        provider.search(image, sample_face_scan)

    # General error
    respx.get("https://serpapi.com/search.json").respond(
        status_code=200,
        json={"error": "Rate limit reached"},
    )
    with pytest.raises(DiscoveryUnavailableError, match="Rate limit reached"):
        provider.search(image, sample_face_scan)


@respx.mock
def test_serpapi_retry_on_500_then_succeed(
    sample_face_scan: FaceScan,
) -> None:
    route = respx.get("https://serpapi.com/search.json")
    route.side_effect = [
        httpx.Response(status_code=500),
        httpx.Response(
            status_code=200,
            json={
                "visual_matches": [
                    {
                        "link": "https://pub.example.com/photo",
                        "source": "PhotoBlog",
                    }
                ]
            },
        ),
    ]
    image = AuthorizedImage(
        image_path="https://example.com/img.jpg",
        sha256="5" * 64,
        consent_reference="ref-5",
    )
    provider = SerpAPILensProvider(api_key="key", max_retries=2, retry_backoff=0.0)
    result = provider.search(image, sample_face_scan)
    assert result.matched_post.source_url == HttpUrl("https://pub.example.com/photo")


@respx.mock
def test_serpapi_retries_exhausted_raises_unavailable(
    sample_face_scan: FaceScan,
) -> None:
    respx.get("https://serpapi.com/search.json").respond(status_code=503)
    image = AuthorizedImage(
        image_path="https://example.com/img.jpg",
        sha256="6" * 64,
        consent_reference="ref-6",
    )
    provider = SerpAPILensProvider(api_key="key", max_retries=2, retry_backoff=0.0)
    with pytest.raises(DiscoveryUnavailableError, match="SerpAPI error"):
        provider.search(image, sample_face_scan)


@respx.mock
def test_serpapi_timeout_retries_exhausted(
    sample_face_scan: FaceScan,
) -> None:
    route = respx.get("https://serpapi.com/search.json")
    route.side_effect = httpx.TimeoutException("Connection timed out")

    image = AuthorizedImage(
        image_path="https://example.com/img.jpg",
        sha256="7" * 64,
        consent_reference="ref-7",
    )
    provider = SerpAPILensProvider(api_key="key", max_retries=2, retry_backoff=0.0)
    with pytest.raises(DiscoveryUnavailableError, match="SerpAPI connection failed after 2 attempts"):
        provider.search(image, sample_face_scan)


@respx.mock
def test_serpapi_search_response_invalid_json(
    sample_face_scan: FaceScan,
) -> None:
    respx.get("https://serpapi.com/search.json").respond(status_code=200, text="not json")
    image = AuthorizedImage(
        image_path="https://example.com/img.jpg",
        sha256="8" * 64,
        consent_reference="ref-8",
    )
    provider = SerpAPILensProvider(api_key="key")
    with pytest.raises(DiscoveryUnavailableError, match="Failed to decode SerpAPI JSON response"):
        provider.search(image, sample_face_scan)


@respx.mock
def test_serpapi_fallback_platform_and_truncated_snippet(
    sample_face_scan: FaceScan,
) -> None:
    long_snippet = "x" * 600
    respx.get("https://serpapi.com/search.json").respond(
        status_code=200,
        json={
            "visual_matches": [
                "not-a-dict",  # will be skipped
                {
                    "link": "https://fallback.domain.org/page",
                    "snippet": long_snippet,
                    "thumbnail": "https://[invalid-url-domain",
                },
            ]
        },
    )
    image = AuthorizedImage(
        image_path="https://example.com/img.jpg",
        sha256="9" * 64,
        consent_reference="ref-9",
    )
    provider = SerpAPILensProvider(api_key="key")
    result = provider.search(image, sample_face_scan)
    assert result.matched_post.platform == "fallback.domain.org"
    assert result.matched_post.text_excerpt is not None
    assert len(result.matched_post.text_excerpt) == 500
    assert result.matched_post.text_excerpt.endswith("...")
    assert result.matched_post.image_url is None


# =========================================================================
# Phase 3: Evidence Assembly and Canonical Serialization Tests
# =========================================================================


def test_canonicalize_evidence_stability(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
    sample_public_post: PublicPost,
) -> None:
    result = DiscoveryResult(
        provider="serpapi_google_lens",
        matched_post=sample_public_post,
    )
    service = DiscoveryService(provider=FakeDiscoveryProvider(canned_result=result))
    bundle = service.assemble_evidence(result, sample_authorized_image, sample_face_scan)

    canonical_1 = canonicalize_evidence(bundle)
    canonical_2 = canonicalize_evidence(bundle)

    assert canonical_1 == canonical_2
    assert compute_evidence_hash(bundle) == compute_evidence_hash(bundle)


def test_canonicalize_evidence_format_and_compact_separators(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
    sample_public_post: PublicPost,
) -> None:
    result = DiscoveryResult(
        provider="serpapi_google_lens",
        matched_post=sample_public_post,
    )
    service = DiscoveryService(provider=FakeDiscoveryProvider(canned_result=result))
    bundle = service.assemble_evidence(result, sample_authorized_image, sample_face_scan)

    canonical_str = canonicalize_evidence(bundle)

    # Must be compact: no space after colon or comma
    assert ": " not in canonical_str
    assert ", " not in canonical_str
    # Keys must be sorted alphabetically at root
    keys_in_order = [
        "consent_reference",
        "face_embedding_sha256",
        "input_image_sha256",
        "post",
        "provider",
        "schema_version",
    ]
    last_idx = -1
    for key in keys_in_order:
        idx = canonical_str.index(f'"{key}":')
        assert idx > last_idx
        last_idx = idx


def test_evidence_hash_deterministic_sha256_format(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
    sample_public_post: PublicPost,
) -> None:
    result = DiscoveryResult(
        provider="serpapi_google_lens",
        matched_post=sample_public_post,
    )
    service = DiscoveryService(provider=FakeDiscoveryProvider(canned_result=result))
    bundle = service.assemble_evidence(result, sample_authorized_image, sample_face_scan)

    hash_val = compute_evidence_hash(bundle)

    assert len(hash_val) == 64
    assert hash_val == hash_val.lower()
    assert all(c in "0123456789abcdef" for c in hash_val)


def test_evidence_hash_sensitivity_to_modifications(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
    sample_public_post: PublicPost,
) -> None:
    result = DiscoveryResult(
        provider="serpapi_google_lens",
        matched_post=sample_public_post,
    )
    service = DiscoveryService(provider=FakeDiscoveryProvider(canned_result=result))
    bundle = service.assemble_evidence(result, sample_authorized_image, sample_face_scan)
    base_hash = compute_evidence_hash(bundle)

    # Modifying consent_reference
    altered_consent = bundle.model_copy(update={"consent_reference": "altered-consent-999"})
    assert compute_evidence_hash(altered_consent) != base_hash

    # Modifying input_image_sha256
    altered_img_hash = bundle.model_copy(update={"input_image_sha256": "f" * 64})
    assert compute_evidence_hash(altered_img_hash) != base_hash

    # Modifying face_embedding_sha256
    altered_face_hash = bundle.model_copy(update={"face_embedding_sha256": "0" * 64})
    assert compute_evidence_hash(altered_face_hash) != base_hash

    # Modifying provider
    altered_provider = bundle.model_copy(update={"provider": "different_provider"})
    assert compute_evidence_hash(altered_provider) != base_hash

    # Modifying post title
    altered_post_title = bundle.model_copy(
        update={"post": sample_public_post.model_copy(update={"title": "Altered Title"})}
    )
    assert compute_evidence_hash(altered_post_title) != base_hash

    # Modifying post source_url
    altered_post_url = bundle.model_copy(
        update={
            "post": sample_public_post.model_copy(
                update={"source_url": HttpUrl("https://example.com/altered")}
            )
        }
    )
    assert compute_evidence_hash(altered_post_url) != base_hash


def test_evidence_bundle_privacy_cleanliness(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
    sample_public_post: PublicPost,
) -> None:
    result = DiscoveryResult(
        provider="serpapi_google_lens",
        matched_post=sample_public_post,
    )
    service = DiscoveryService(provider=FakeDiscoveryProvider(canned_result=result))
    bundle = service.assemble_evidence(result, sample_authorized_image, sample_face_scan)
    serialized = canonicalize_evidence(bundle)

    # Must not contain private image paths, api keys, or raw face embeddings
    assert "/path/to/consented-subject.jpg" not in serialized
    assert "api_key" not in serialized
    assert "private_key" not in serialized
    assert "secret" not in serialized


def test_service_canonicalize_and_fingerprint_delegation(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
    sample_public_post: PublicPost,
) -> None:
    result = DiscoveryResult(
        provider="serpapi_google_lens",
        matched_post=sample_public_post,
    )
    service = DiscoveryService(provider=FakeDiscoveryProvider(canned_result=result))
    bundle = service.assemble_evidence(result, sample_authorized_image, sample_face_scan)

    assert service.canonicalize(bundle) == canonicalize_evidence(bundle)
    assert service.fingerprint(bundle) == compute_evidence_hash(bundle)


@respx.mock
def test_serpapi_multiple_platforms_deduplicated_and_primary_first(
    sample_face_scan: FaceScan,
) -> None:
    respx.get("https://serpapi.com/search.json").respond(
        status_code=200,
        json={
            "visual_matches": [
                {
                    "title": "News Feature",
                    "link": "https://news.example.org/article/42",
                    "source": "NewsOutlet",
                },
                {
                    "title": "Twin Post on Same Platform",
                    "link": "https://news.example.org/article/99",
                    "source": "NewsOutlet",
                },
                {
                    "title": "Social Profile",
                    "link": "https://x.example/user/1",
                    "source": "XProfile",
                    "snippet": "Short bio.",
                },
                {
                    "title": "Photo Page",
                    "link": "https://ig.example/u/2",
                    "source": "InstagramProfile",
                },
                {"title": "No Http Link", "link": "ftp://invalid"},
            ]
        },
    )
    image = AuthorizedImage(
        image_path="https://example.com/subject.jpg",
        sha256="c" * 64,
        consent_reference="consent-multi-123",
    )

    provider = SerpAPILensProvider(api_key="key")
    result = provider.search(image, sample_face_scan)

    assert [m.post.platform for m in result.matches] == [
        "NewsOutlet",
        "XProfile",
        "InstagramProfile",
    ]
    assert result.matched_post.source_url == HttpUrl("https://news.example.org/article/42")
    assert result.matched_post == result.matches[0].post
    assert all(m.confidence is None for m in result.matches)


@respx.mock
def test_serpapi_fetch_image_returns_raw_bytes() -> None:
    respx.get("https://cdn.example.com/thumb.jpg").respond(
        status_code=200,
        content=b"\x89PNG-fake-image-bytes",
    )
    provider = SerpAPILensProvider(api_key="key")
    data = provider.fetch_image(HttpUrl("https://cdn.example.com/thumb.jpg"))
    assert data == b"\x89PNG-fake-image-bytes"


@respx.mock
def test_serpapi_fetch_image_http_error_raises_unavailable() -> None:
    respx.get("https://cdn.example.com/missing.jpg").respond(status_code=404)
    provider = SerpAPILensProvider(api_key="key")
    with pytest.raises(DiscoveryUnavailableError):
        provider.fetch_image(HttpUrl("https://cdn.example.com/missing.jpg"))


@respx.mock
def test_serpapi_fetch_image_timeout_raises_unavailable() -> None:
    respx.get("https://cdn.example.com/slow.jpg").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    provider = SerpAPILensProvider(api_key="key")
    with pytest.raises(DiscoveryUnavailableError):
        provider.fetch_image(HttpUrl("https://cdn.example.com/slow.jpg"))


def test_discovery_service_fetch_image_delegates_to_provider(sample_face_scan: FaceScan) -> None:
    fake = FakeDiscoveryProvider(canned_image_bytes=b"thumbnail-bytes")
    service = DiscoveryService(fake)
    data = service.fetch_image(HttpUrl("https://cdn.example.com/thumb.jpg"))
    assert data == b"thumbnail-bytes"
    assert fake.fetched_urls == ["https://cdn.example.com/thumb.jpg"]

