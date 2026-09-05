"""Unit tests for the Discovery module."""

from datetime import UTC, datetime

import httpx
import pytest
import respx
from pydantic import HttpUrl

from contracts.discovery import DiscoveryResult
from contracts.domain import AuthorizedImage, FaceScan, PublicPost
from facechain.discovery.exceptions import (
    DiscoveryError,
    DiscoveryUnavailableError,
    NoMatchFoundError,
)
from facechain.discovery.provider import DiscoveryProvider, FakeDiscoveryProvider
from facechain.discovery.service import DiscoveryService


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


def test_discovery_exception_hierarchy() -> None:
    assert issubclass(DiscoveryUnavailableError, DiscoveryError)
    assert issubclass(NoMatchFoundError, DiscoveryError)


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


@respx.mock
def test_fake_http_discovery_flow(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
) -> None:
    api_url = "https://api.fake-search.internal/v1/search"
    respx.post(api_url).respond(
        status_code=200,
        json={
            "status": "success",
            "matches": [
                {
                    "source_url": "https://example.org/article/99",
                    "platform": "NewsPortal",
                    "title": "Subject Portrait",
                    "text_excerpt": "A photo of the subject at an event.",
                    "image_url": "https://example.org/images/portrait.jpg",
                }
            ],
        },
    )

    class SimpleHttpDiscoveryProvider:
        def search(self, image: AuthorizedImage, scan: FaceScan) -> DiscoveryResult:
            try:
                response = httpx.post(
                    api_url,
                    json={"image_sha256": image.sha256},
                    timeout=5.0,
                )
                response.raise_for_status()
                data = response.json()
                matches = data.get("matches", [])
                if not matches:
                    raise NoMatchFoundError("No matching public post.")
                match = matches[0]
                post = PublicPost(
                    source_url=match["source_url"],
                    platform=match["platform"],
                    title=match.get("title"),
                    text_excerpt=match.get("text_excerpt"),
                    image_url=match.get("image_url"),
                    retrieved_at=datetime.now(UTC),
                )
                return DiscoveryResult(provider="http_fake", matched_post=post)
            except httpx.HTTPError as exc:
                raise DiscoveryUnavailableError(f"HTTP request failed: {exc}") from exc

    http_provider = SimpleHttpDiscoveryProvider()
    assert isinstance(http_provider, DiscoveryProvider)

    service = DiscoveryService(provider=http_provider)
    res = service.discover(sample_authorized_image, sample_face_scan)
    assert res.provider == "http_fake"
    assert res.matched_post.platform == "NewsPortal"
    assert res.matched_post.source_url == HttpUrl("https://example.org/article/99")


@respx.mock
def test_fake_http_discovery_flow_service_error(
    sample_authorized_image: AuthorizedImage,
    sample_face_scan: FaceScan,
) -> None:
    api_url = "https://api.fake-search.internal/v1/search"
    respx.post(api_url).respond(status_code=503)

    class SimpleHttpDiscoveryProvider:
        def search(self, image: AuthorizedImage, scan: FaceScan) -> DiscoveryResult:
            try:
                response = httpx.post(
                    api_url,
                    json={"image_sha256": image.sha256},
                    timeout=5.0,
                )
                response.raise_for_status()
                return DiscoveryResult(  # pragma: no cover
                    provider="http_fake",
                    matched_post=PublicPost(
                        source_url=HttpUrl("https://example.com"),
                        platform="example",
                        retrieved_at=datetime.now(UTC),
                    ),
                )
            except httpx.HTTPError as exc:
                raise DiscoveryUnavailableError(f"HTTP request failed: {exc}") from exc

    service = DiscoveryService(provider=SimpleHttpDiscoveryProvider())
    with pytest.raises(DiscoveryUnavailableError, match="HTTP request failed"):
        service.discover(sample_authorized_image, sample_face_scan)
