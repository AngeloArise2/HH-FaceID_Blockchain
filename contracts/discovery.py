"""Discovery module interface."""

from pydantic import BaseModel

from contracts.domain import AuthorizedImage, EvidenceBundle, FaceScan, PublicPost


class DiscoveryResult(BaseModel):
    provider: str
    matched_post: PublicPost
    confidence: float | None = None

    def to_evidence(self, image: AuthorizedImage, scan: FaceScan) -> EvidenceBundle:
        return EvidenceBundle(
            schema_version="1.0",
            consent_reference=image.consent_reference,
            input_image_sha256=image.sha256,
            face_embedding_sha256=scan.embedding_sha256,
            provider=self.provider,
            post=self.matched_post,
        )
