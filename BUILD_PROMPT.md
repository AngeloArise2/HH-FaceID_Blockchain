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

The integrator does no module implementation and edits only `config.py`, `pipeline/`, `cli.py`, and `test_pipeline.py`. It calls module public services only — never a sibling module's internals.

### Pre-ledger work (can start as soon as `contracts/ledger.py` is approved, no need to wait for Ledger's implementation)

**Prompt — settings boundary:**

> Work only in `src/facechain/config.py`. Implement a pydantic-settings class exposing `SERPAPI_KEY`, `ANVIL_RPC_URL`, `ANVIL_PRIVATE_KEY`, `CHAIN_ID` (default `31337`), and `DISCOVERY_MODE` (`fake` or `real`, default `fake`). Load from `.env` via `.env.example` as the documented template. Add a `validate()` method that raises a clear typed error before any provider call is attempted if a required field for the selected mode is missing (e.g. `DISCOVERY_MODE=real` requires `SERPAPI_KEY`). Add unit tests for missing-key and valid-config cases. Do not read these settings anywhere outside `config.py`, `pipeline/`, and `cli.py`.

**Prompt — pipeline skeleton against fakes:**

> Work only in `src/facechain/pipeline/` and `tests/test_pipeline.py`. Build the orchestration skeleton that calls, in order: `IdentityService.scan()` → `FaceScan`; `DiscoveryService.discover()` then `assemble_evidence()` → `EvidenceBundle`; a placeholder `EvidenceLedger` protocol call for `anchor()` → `LedgerReceipt` and `verify()` → `VerificationResult`, using a fake/stub `EvidenceLedger` implementation that satisfies `contracts/ledger.py` (since the real one isn't merged yet). Pass only allowed metadata between stages — no raw image bytes or raw embeddings beyond the SHA-256 fingerprint. At each stage emit the corresponding `PipelineEvent` from `contracts/events.py` (`validated`, `face_scanned`, `post_found`, `anchored`, `verified`, `failed`). Write tests against the fake ledger for: success, no search match (`NoMatchFoundError` propagates as a `failed` event, not an exception escaping the pipeline), and altered evidence producing `matched=false`. Do not import anything from `src/facechain/ledger/` — only from `contracts/ledger.py`.

**Prompt — CLI scaffold:**

> Work only in `src/facechain/cli.py`. Implement Typer commands `facechain run --image <path>` and `facechain verify --evidence <path>` calling the pipeline skeleton above. `run` writes `runs/<run-id>/evidence.json` and prints each emitted event as it happens. Map every documented module error (`NoFaceDetectedError`, `NoMatchFoundError`, `LedgerUnavailableError`, and any others defined in the module contracts) to a concise one-line message and a non-zero exit code — never fall back to fixture data on error. Add `--help` text matching the README's documented usage. Test against the fake ledger from the pipeline skeleton.

### Once Ledger's Phase 2/3 (`EvidenceLedger` real adapter) is merged into `main`

**Prompt — wire in the real ledger:**

> Rebase your integration branch on the latest `main` now that Ledger is merged. In `src/facechain/pipeline/`, replace the fake `EvidenceLedger` stub with the real implementation imported from `src/facechain/ledger/` (its public service only — do not reach into ledger internals). Update `config.py` usage if the real adapter needs additional settings beyond what you scaffolded (e.g. confirm `ANVIL_RPC_URL`/`ANVIL_PRIVATE_KEY`/`CHAIN_ID` match what Ledger's adapter actually expects — check `contracts/ledger.py` and Ledger's own tests for the exact call signature). Re-run all existing `test_pipeline.py` tests with the fake ledger still available as a fallback test double for the "no network/Anvil" mocked tests — do not require a live Anvil instance for CI.

**Prompt — mocked end-to-end tests (full four-case suite):**

> In `tests/test_pipeline.py`, using fakes for Identity, Discovery, and Ledger (no network, no Anvil), cover: (1) success — full pipeline emits all six events in order and returns a `VerificationResult` with `matched=true`; (2) no search match — `DiscoveryService.discover()` raises `NoMatchFoundError`, pipeline emits `failed` with a clear reason, no ledger call is attempted; (3) blockchain write error — `EvidenceLedger.anchor()` raises a `LedgerUnavailableError`, pipeline emits `failed`, evidence.json is still written to `runs/` with the discovery result but marked unanchored; (4) altered evidence — construct an `EvidenceBundle`, anchor it, then mutate one field before calling `verify()`, and confirm the pipeline surfaces `matched=false` without raising.

**Prompt — real end-to-end run against Anvil:**

> With Anvil running locally (`anvil` in a separate terminal) and `DISCOVERY_MODE=real` with a valid `SERPAPI_KEY` set in `.env`, run `facechain run --image <path>` against a consented test image whose `AuthorizedImage.consent_reference` is populated. Confirm: the CLI prints all six pipeline events in order; `runs/<run-id>/evidence.json` is written and contains no raw image bytes or raw embeddings, only hashes and normalized fields; the transaction hash returned by `anchor()` is visible on your local Anvil instance's logs. Then run `facechain verify --evidence runs/<run-id>/evidence.json` and confirm it reports `matched=true` against the same chain state. Do not commit `runs/` output, real API keys, or Anvil private keys — confirm `.gitignore` covers all three.

**Prompt — open the integration PR:**

> Open a PR from your integration branch into `main` titled clearly as an integration PR (e.g. `feat(pipeline): wire identity → discovery → ledger end-to-end`). In the description, list which module public APIs you called (function/class names only, no internals), confirm you did not modify any file under `src/facechain/identity/`, `src/facechain/discovery/`, or `src/facechain/ledger/`, and link the four mocked test cases plus the real Anvil run's evidence.json (redacted of any real API key or private key) as verification. Tag all three module owners as reviewers and ask each to confirm the pipeline calls their module's public service correctly per its contract.

### Demo recording (final step)

> With Anvil running and one participant's consented image ready, record a single screen capture showing: `facechain run --image <consented-image-path>` executing end-to-end (face detected → real search match found → evidence anchored on-chain), followed by `facechain verify --evidence <path>` showing `matched=true` against the live chain. No editing needed. Do not include any non-consented image, real private key, or real API key on screen — mask the terminal if `.env` values would otherwise be visible during the recording. Upload per the submission instructions and document any known provider limitations (e.g. SerpAPI rate limits, InsightFace accuracy caveats) in the README.

## Contract changes during build

1. Open a contract-only PR describing the incompatibility, affected modules, compatibility impact, and fixture updates.
2. Get acknowledgement from every affected module owner before merging.
3. Merge the contract change first; each owner updates their module in a separate PR. Do not couple a contract rewrite to one module implementation unless all owners approve.