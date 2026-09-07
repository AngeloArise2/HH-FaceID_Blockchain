"""Shared canonical hashing for EvidenceBundle. Implementation-independent contract helper."""

import hashlib
import json

from contracts.domain import EvidenceBundle


def canonicalize_evidence(evidence: EvidenceBundle) -> str:
    """Serialize an EvidenceBundle into canonical UTF-8 JSON with sorted keys and compact separators.

    Guarantees deterministic, reproducible byte representations across platforms. This is the
    single source of truth for evidence canonicalization shared by all modules.
    """
    data = evidence.model_dump(mode="json")
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_evidence_hash(evidence: EvidenceBundle) -> str:
    """Compute the deterministic SHA-256 lowercase hex fingerprint of canonical evidence JSON."""
    canonical_bytes = canonicalize_evidence(evidence).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest().lower()