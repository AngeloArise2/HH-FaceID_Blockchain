from datetime import datetime, timezone

from contracts.discovery import DiscoveryResult
from contracts.domain import PublicPost


def test_discovery_contract_accepts_a_normalized_public_post() -> None:
    result = DiscoveryResult(
        provider="fake",
        matched_post=PublicPost(
            source_url="https://example.org/post/1",
            platform="example",
            retrieved_at=datetime.now(timezone.utc),
        ),
    )
    assert result.provider == "fake"
