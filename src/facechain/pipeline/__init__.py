"""Integration pipeline boundary."""

from facechain.ledger import EvidenceLedger
from facechain.pipeline.service import (
    EventStage,
    FaceVerificationPipeline,
    PipelineRunResult,
)

__all__ = [
    "EventStage",
    "EvidenceLedger",
    "FaceVerificationPipeline",
    "PipelineRunResult",
]