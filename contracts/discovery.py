"""Discovery module interface."""

from pydantic import BaseModel

from contracts.domain import AuthorizedImage, EvidenceBundle, FaceScan, PublicPost


class DiscoveryResult(BaseModel):
    provider: str
    matched_post: PublicPost
    confidence: float | None = None

    def to_evidence(self, image: AuthorizedImage, scan: FaceScan) -> EvidenceBundle: ...
