"""Pipeline orchestration; calls module public services in order."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from contracts.discovery import DiscoveryMatch
from contracts.domain import AuthorizedImage, EvidenceBundle, FaceScan
from contracts.events import PipelineEvent
from contracts.ledger import LedgerReceipt, VerificationResult
from facechain.discovery import DiscoveryService, DiscoveryUnavailableError, NoMatchFoundError
from facechain.identity import (
    IdentityService,
    InputValidationError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    RecognitionUnavailableError,
)
from facechain.ledger import EvidenceLedger, LedgerUnavailableError

EventStage = Literal["validated", "face_scanned", "post_found", "anchored", "verified", "failed"]


class PipelineRunResult(BaseModel):
    """Outcome of a single pipeline run with every emitted event."""

    run_id: str
    evidence: EvidenceBundle | None = None
    matches: list[DiscoveryMatch] = Field(default_factory=list)
    receipt: LedgerReceipt | None = None
    verification: VerificationResult | None = None
    events: list[PipelineEvent] = Field(default_factory=list)


class FaceVerificationPipeline:
    """Orchestrates identity scan, public search, and on-chain anchor/verify.

    Only canonical metadata travels between stages: SHA-256 fingerprints and
    normalized post fields. Raw image bytes and embeddings never leave the
    identity module.
    """

    def __init__(
        self,
        identity: IdentityService,
        discovery: DiscoveryService,
        ledger: EvidenceLedger,
    ) -> None:
        self._identity = identity
        self._discovery = discovery
        self._ledger = ledger

    def verify_bundle(self, evidence: EvidenceBundle) -> VerificationResult:
        """Verify an existing evidence bundle against the ledger."""
        return self._ledger.verify(evidence)

    def run(self, image: AuthorizedImage) -> PipelineRunResult:
        """Execute one consented verification run and emit pipeline events."""
        run_id = uuid4().hex
        events: list[PipelineEvent] = []
        emit: Callable[[EventStage, str], None] = lambda stage, detail: events.append(
            PipelineEvent(
                run_id=run_id,
                stage=stage,
                occurred_at=datetime.now(UTC),
                detail=detail,
            )
        )
        evidence: EvidenceBundle | None = None
        matches: list[DiscoveryMatch] = []
        receipt: LedgerReceipt | None = None
        verification: VerificationResult | None = None

        try:
            scan = self._identity.scan(image)
            emit(
                "validated",
                f"input image {image.sha256} validated under consent {image.consent_reference}",
            )
            emit(
                "face_scanned",
                f"detector={scan.detector}, embedding_sha256={scan.embedding_sha256}",
            )

            result = self._discovery.discover(image, scan)
            matches = self._score_matches(scan, result.matches)
            emit(
                "post_found",
                f"provider={result.provider}, source={result.matched_post.source_url}, platforms={len(matches)}",
            )

            evidence = self._discovery.assemble_evidence(result, image, scan)
            receipt = self._ledger.anchor(evidence)
            emit(
                "anchored",
                f"chain_id={receipt.chain_id}, transaction_hash={receipt.transaction_hash}",
            )

            verification = self._ledger.verify(evidence)
            emit(
                "verified",
                f"matched={verification.matched}, evidence_sha256={verification.evidence_sha256}",
            )
        except NoMatchFoundError as exc:
            emit("failed", str(exc))
        except LedgerUnavailableError as exc:
            emit("failed", f"evidence not anchored: {exc}")

        return PipelineRunResult(
            run_id=run_id,
            evidence=evidence,
            matches=matches,
            receipt=receipt,
            verification=verification,
            events=events,
        )

    def _score_matches(
        self,
        source_scan: FaceScan,
        candidate_matches: list[DiscoveryMatch],
    ) -> list[DiscoveryMatch]:
        """Fill each match's confidence with a real face-similarity score.

        When a match has an image URL the thumbnail is fetched, scanned, and
        compared against the source scan.  Raw embeddings stay inside the
        identity module; only a 0..1 score is recorded.  Any per-thumbnail
        failure (unreachable image, no face, multiple faces, recognition
        hiccup) leaves the provider's original confidence intact rather than
        failing the run.  When no image URL is available the provider's
        confidence is preserved as-is.
        """
        scored: list[DiscoveryMatch] = []
        for match in candidate_matches:
            confidence = match.confidence
            image_url = match.post.image_url
            if image_url is not None:
                try:
                    thumbnail = self._discovery.fetch_image(image_url)
                    candidate_scan = self._identity.scan_bytes(thumbnail)
                    confidence = self._identity.similarity(source_scan, candidate_scan)
                except (
                    DiscoveryUnavailableError,
                    InputValidationError,
                    NoFaceDetectedError,
                    MultipleFacesDetectedError,
                    RecognitionUnavailableError,
                    OSError,
                ):
                    confidence = match.confidence
            scored.append(match.model_copy(update={"confidence": confidence}))
        return scored
