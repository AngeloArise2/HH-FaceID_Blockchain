# Parallel build prompts

All contributors first read `AGENTS.md`, `SKILLS.md`, and the relevant contract. Use only consented test fixtures stored outside Git. Do not begin implementation work that assumes an unapproved contract shape.

## Identity module

### Phase 1 — input and contracts

> Work only in `src/facechain/identity/` and `tests/test_identity.py`. Implement validation for `AuthorizedImage` and conversion to `FaceScan` exactly as defined in `contracts/domain.py` and `contracts/face.py`. Add deterministic fake-provider tests; do not call a network service.

### Phase 2 — face provider adapter

> Work only in `src/facechain/identity/` and its tests. Add the InsightFace/OpenCV adapter behind the protocol established in Phase 1. Enforce exactly one face and return a normalized embedding hash, not raw embedding in logs. Handle unreadable image, no face, and multiple faces through typed errors.

### Phase 3 — quality gate

> Work only in the identity module and its tests. Run Ruff, mypy, pytest, and `/contract-check`. Confirm the public service returns `FaceScan` with no extra cross-module dependency.

## Discovery module

### Phase 1 — normalized provider boundary

> Work only in `src/facechain/discovery/` and `tests/test_discovery.py`. Implement a `DiscoveryProvider` protocol and service that consumes `AuthorizedImage` plus `FaceScan` metadata and produces `DiscoveryResult` exactly per `contracts/discovery.py`. Use fake HTTP tests only.

### Phase 2 — real search adapter

> Work only in the discovery module and its tests. Implement the SerpAPI Google Lens adapter using `httpx`, timeout/retry rules, and configured key. It must execute a real provider call in real mode and return `NoMatchFoundError` when no qualifying public post is found. Preserve source URL and retrieval timestamp.

### Phase 3 — evidence assembly

> Work only in discovery and its tests. Build the canonical `EvidenceBundle` specified by `contracts/domain.py`; include only normalized, public result fields and a consent reference. Verify canonical serialization is stable.

## Ledger module

### Phase 1 — canonical hash

> Work only in `src/facechain/ledger/` and `tests/test_ledger.py`. Implement canonical JSON SHA-256 fingerprinting for `EvidenceBundle` and return the models in `contracts/ledger.py`. Add alteration and key-order stability tests.

### Phase 2 — Ethereum adapter

> Work only in the ledger module and its tests. Implement an injected `web3.py` adapter for Anvil that records the evidence hash and retrieval time. Read RPC URL/private key via settings; never log either. Fakes must cover receipt failure and wrong chain ID.

### Phase 3 — verification

> Work only in ledger and tests. Implement re-verification against the chain; changed evidence must produce `matched=false`, not an exception. Run the module quality gate and `/contract-check`.

## Integration phases

1. A rotating integrator implements `src/facechain/pipeline/` and `cli.py`, calling module public services in the pipeline order and emitting `PipelineEvent` values from `contracts/events.py`.
2. Add mocked end-to-end tests: success, no search match, blockchain write error, and altered evidence.
3. Run Anvil plus one consented manual demo, record only the screen/output necessary for submission, and document known provider limitations in the README.

## Contract changes during build

1. Open a contract-only PR describing the incompatibility, affected modules, compatibility impact, and fixture updates.
2. Get acknowledgement from every affected module owner before merging.
3. Merge the contract change first; each owner updates their module in a separate PR. Do not couple a contract rewrite to one module implementation unless all owners approve.
