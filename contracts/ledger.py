"""Ledger module interface."""

from datetime import datetime
from pydantic import BaseModel, Field
from contracts.domain import EvidenceBundle


class LedgerReceipt(BaseModel):
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    chain_id: int
    transaction_hash: str = Field(pattern=r"^0x[a-fA-F0-9]{64}$")
    anchored_at: datetime


class VerificationResult(BaseModel):
    matched: bool
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt: LedgerReceipt | None = None


class EvidenceLedger:
    def anchor(self, evidence: EvidenceBundle) -> LedgerReceipt: ...
    def verify(self, evidence: EvidenceBundle) -> VerificationResult: ...
