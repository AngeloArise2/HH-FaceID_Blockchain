"""Pipeline orchestration skeleton; calls module public services in order."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field

from contracts.domain import AuthorizedImage, EvidenceBundle
from contracts.events import PipelineEvent
from contracts.ledger import LedgerReceipt, VerificationResult
from facechain.discovery import DiscoveryService, NoMatchFoundError
from facechain.identity import IdentityService

EventStage = Literal["validated", "face_scanned", "post_found", "anchored", "verified", "failed"]


@runtime_checkable
class EvidenceLedger(Protocol):
    """Placeholder ledger boundary; structurally matches ``contracts/ledger.py``."""

    def anchor(self, evidence: EvidenceBundle) -> LedgerReceipt: ...

    def verify(self, evidence: EvidenceBundle) -> VerificationResult: ...


class PipelineRunResult(BaseModel):
    """Outcome of a single pipeline run with every emitted event."""

    run_id: str
    evidence: EvidenceBundle | None = None
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
            emit(
                "post_found",
                f"provider={result.provider}, source={result.matched_post.source_url}",
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

            return PipelineRunResult(
                run_id=run_id,
                evidence=evidence,
                receipt=receipt,
                verification=verification,
                events=events,
            )
        except NoMatchFoundError as exc:
            emit("failed", str(exc))
            return PipelineRunResult(run_id=run_id, events=events)