"""Discovery module interface."""

from pydantic import BaseModel, Field

from contracts.domain import AuthorizedImage, EvidenceBundle, FaceScan, PublicPost


class DiscoveryMatch(BaseModel):
    """A single qualifying public match surfaced by a discovery provider."""

    post: PublicPost
    confidence: float | None = None


class DiscoveryResult(BaseModel):
    provider: str
    matched_post: PublicPost
    confidence: float | None = None
    matches: list[DiscoveryMatch] = Field(default_factory=list)

    def to_evidence(self, image: AuthorizedImage, scan: FaceScan) -> EvidenceBundle:
        return EvidenceBundle(
            schema_version="1.0",
            consent_reference=image.consent_reference,
            input_image_sha256=image.sha256,
            face_embedding_sha256=scan.embedding_sha256,
            provider=self.provider,
            post=self.matched_post,
        )
