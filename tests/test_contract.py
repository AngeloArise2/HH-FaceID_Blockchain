from datetime import UTC, datetime

from contracts.discovery import DiscoveryMatch, DiscoveryResult
from contracts.domain import EvidenceBundle, PublicPost
from contracts.hashing import canonicalize_evidence, compute_evidence_hash


def test_discovery_contract_accepts_a_normalized_public_post() -> None:
    result = DiscoveryResult(
        provider="fake",
        matched_post=PublicPost(
            source_url="https://example.org/post/1",
            platform="example",
            retrieved_at=datetime.now(UTC),
        ),
    )
    assert result.provider == "fake"
    assert result.matches == []
    assert result.confidence is None


def test_discovery_contract_surfaces_multiple_matches_and_primary_anchor() -> None:
    primary = PublicPost(
        source_url="https://example.org/post/1",
        platform="example",
        retrieved_at=datetime.now(UTC),
    )
    result = DiscoveryResult(
        provider="fake",
        matched_post=primary,
        confidence=0.9,
        matches=[
            DiscoveryMatch(post=primary, confidence=0.9),
            DiscoveryMatch(
                post=PublicPost(
                    source_url="https://other.example/post/2",
                    platform="other",
                    retrieved_at=datetime.now(UTC),
                ),
                confidence=None,
            ),
        ],
    )
    assert len(result.matches) == 2
    assert result.matches[0].post is primary
    # Evidence anchor stays the primary match so the on-chain fingerprint is stable.
    assert result.to_evidence is not None


def _sample_bundle() -> EvidenceBundle:
    return EvidenceBundle(
        consent_reference="consent-abc-123",
        input_image_sha256="a" * 64,
        face_embedding_sha256="b" * 64,
        provider="serpapi_google_lens",
        post=PublicPost(
            source_url="https://example.org/post/1",
            platform="example",
            title="A title",
            retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )


def test_hashing_contract_deterministic() -> None:
    bundle = _sample_bundle()
    assert canonicalize_evidence(bundle) == canonicalize_evidence(bundle)
    assert compute_evidence_hash(bundle) == compute_evidence_hash(bundle)
    assert canonicalize_evidence(bundle) == canonicalize_evidence(bundle.model_copy())


def test_hashing_contract_key_order_independent() -> None:
    bundle = _sample_bundle()
    canonical = canonicalize_evidence(bundle)
    keys = ("consent_reference", "face_embedding_sha256", "input_image_sha256", "post", "provider", "schema_version")
    indices = [canonical.index(f'"{key}":') for key in keys]
    assert indices == sorted(indices)


def test_hashing_contract_sha256_format() -> None:
    digest = compute_evidence_hash(_sample_bundle())
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(c in "0123456789abcdef" for c in digest)


def test_hashing_contract_sensitive_to_changes() -> None:
    bundle = _sample_bundle()
    base = compute_evidence_hash(bundle)
    altered = bundle.model_copy(update={"provider": "different"})
    assert compute_evidence_hash(altered) != base
