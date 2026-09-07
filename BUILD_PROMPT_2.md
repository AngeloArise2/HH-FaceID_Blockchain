# Build prompts 2 — single-owner completion plan

You are now doing everything (ledger owner + integrator). `main` is protected — never commit or push directly to it. For every prompt below: first `git switch main && git pull --ff-only`, then create a fresh branch (`git switch -c <branch>`), do the work, run the quality gate, commit, push, open a PR, and merge via PR approval. Follow `GIT_WORKFLOW.md`, and run the quality gate after every phase:

```
uv run ruff check .
uv run mypy src
uv run pytest
```

then the `/contract-check` and `/review` flows. After each phase, finish your branch: commit, push, open a PR into `main`, get it approved/merged, then delete the merged remote branch. Do **not** begin a prompt that assumes an unapproved contract shape, and do not advance to the next prompt until the previous branch is merged (so you build on the latest `main`).

> Note: the previously merged `ledger/` directory is a Node.js/Hardhat/Solidity implementation that does **not** conform to `contracts/ledger.py` or the Python module spec. Do not build the integration on it. **Remove it entirely in Phase 0b below.**

---

## Phase 0 — Contract gap: shared canonical hashing

This is the **critical blocker** and must be resolved first. Discovery currently owns
`canonicalize_evidence` / `compute_evidence_hash` in `src/facechain/discovery/service.py`.
The ledger must hash an `EvidenceBundle` to an identical SHA-256, but `AGENTS.md` forbids
importing a sibling module's internals, and duplicating the logic ad hoc would let the two
drift apart (verification would always fail).

Resolve it by extracting the canonicalizer to the shared contract layer so both modules import it.

> Open a contract-only branch `codex/contract/hashing`. Add a canonical hashing helper to the
> shared contract layer (suggest `contracts/hashing.py`, but `contracts/domain.py` is acceptable
> if the team prefers). It must expose (a) `canonicalize_evidence(evidence: EvidenceBundle) -> str`
> producing UTF-8 JSON with sorted keys and compact separators, and (b)
> `compute_evidence_hash(evidence: EvidenceBundle) -> str` returning the lowercase SHA-256 hex of
> the canonical bytes. Add contract tests proving key-order stability and determinism. Do not couple
> this to any single module implementation. Merge the contract PR first, then update
> `src/facechain/discovery/service.py` to delegate to the shared helper (its own `canonicalize` /
> `fingerprint` add no logic). Keep behavior byte-identical; existing discovery tests must still pass.

**Affected owners to acknowledge:** discovery, ledger (both you). State compatibility impact and
fixture updates in the PR.

---

## Phase 0b — Remove the Node.js/Hardhat/Solidity ledger

The `ledger/` directory merged on `main` (Node/Hardhat/Solidity: `ledger/contracts/*.sol`,
`ledger/ledgerService.js`, `ledger/hardhat.config.js`, `ledger/scripts/`, `ledger/test/`,
`ledger/package.json`, `ledger/package-lock.json`, `ledger/.gitignore`) does **not** conform to
`contracts/ledger.py` and would confuse the integration. Remove it via a normal branch + PR.

> Open branch `codex/cleanup/remove-js-ledger`. Delete the entire `ledger/` directory. Verify that
> nothing under `src/`, `contracts/`, `tests/`, or the Python code imports or references the Node
> implementation (search for `ledgerService`, `hardhat`, `FaceVerificationLedger`, and any
> `require(`/`ethers`/`console.log` Node artifacts). Confirm no `.github/` workflow depends on it.
> Ensure `uv run ruff check .`, `uv run mypy src`, and `uv run pytest` stay green (these should be
> unaffected since the JS ledger was never wired into the Python code). Commit, push, open a PR,
> get it approved, and merge. Then delete the local and remote `feature/ledger` branches
> (`git branch -D feature/ledger` locally is fine **after** its PR is merged or abandoned — note it
> was never merged via PR into `main`; the ledger code reached `main` through a merged PR, so just
> remove the branch that still exists on the remote with
> `git push origin --delete feature/ledger`).

---

## Ledger module

Branch naming follows `codex/ledger/<short-description>`.

### Ledger Phase 1 — canonical hash

> Work only in `src/facechain/ledger/`, its tests, and the shared hashing helper from Phase 0.
> Create `exceptions.py` (base `LedgerError` plus `LedgerUnavailableError`), `models.py` if an
> internal model is needed, and `service.py` defining `EvidenceLedger` with
> `anchor(evidence: EvidenceBundle) -> LedgerReceipt` and
> `verify(evidence: EvidenceBundle) -> VerificationResult`, with types exactly as in
> `contracts/ledger.py`. Compute the evidence fingerprint via the shared helper from Phase 0 — never
> reimplement canonicalization. Add tests in `tests/test_ledger.py` for canonical hash stability,
> key-order independence, and altered-evidence producing a different hash.

### Ledger Phase 2 — Ethereum adapter (Anvil)

> Work only in the ledger module and its tests. Implement `provider.py` with an injected `web3.py`
> adapter behind a protocol so tests use fakes. It anchors the canonical evidence hash and retrieval
> time on Anvil and returns the transaction details. Read `ANVIL_RPC_URL`, `ANVIL_PRIVATE_KEY`, and
> `CHAIN_ID` via `src/facechain/config.py` only; never log any of them. Fakes must cover receipt
> failure, an unreachable chain (raising `LedgerUnavailableError`), and a wrong chain ID. No test may
> require a live Anvil node or network.

### Ledger Phase 3 — verification

> Work only in ledger and its tests. Implement re-verification: re-hash the evidence, query the
> chain, and compare. Changed evidence must return `matched=false` — never raise. An unreachable
> chain returns/raises a typed `LedgerUnavailableError`. Run the module quality gate and
> `/contract-check`. Ensure the public entry points return the exact `LedgerReceipt` /
> `VerificationResult` models with **no cross-module dependency beyond `contracts/` and config**.

---

## Integration (you are also the integrator)

You edit only `src/facechain/config.py`, `src/facechain/pipeline/`, `src/facechain/cli.py`, and
`tests/test_pipeline.py`. Call module **public services** only. Branch naming uses
`codex/integration/<short-description>`.

### Integration A — settings boundary

> Work only in `src/facechain/config.py`. Implement a pydantic-settings class exposing
> `SERPAPI_KEY`, `ANVIL_RPC_URL`, `ANVIL_PRIVATE_KEY`, `CHAIN_ID` (default `31337`), and
> `DISCOVERY_MODE` (`fake` or `real`). Load from `.env` using `.env.example` as the template. Add a
> `validate()` method that, before any provider call, raises a clear typed error if a required field
> for the selected mode is missing (e.g. `DISCOVERY_MODE=real` requires `SERPAPI_KEY`; the real
> ledger requires `ANVIL_RPC_URL`/`ANVIL_PRIVATE_KEY`). Add unit tests for missing-key and
> valid-config cases. Do not read settings anywhere outside `config.py`, `pipeline/`, and `cli.py`.
> Sync `.env.example` with the real defaults actually used by the code (it currently shows
> `DISCOVERY_MODE=real` while this prompt defaults to `fake` — pick one and keep them consistent).

### Integration B — pipeline skeleton against fakes

> Work only in `src/facechain/pipeline/` and `tests/test_pipeline.py`. Build the orchestration
> skeleton that calls, in order: `IdentityService.scan()` → `FaceScan`;
> `DiscoveryService.discover()` then `assemble_evidence()` → `EvidenceBundle`; a placeholder
> `EvidenceLedger` protocol call for `anchor()` → `LedgerReceipt` and `verify()` →
> `VerificationResult`, using a fake/stub `EvidenceLedger` that satisfies `contracts/ledger.py`
> (use the fake while the real adapter is being merged). Pass only allowed metadata between stages —
> no raw image bytes or raw embeddings beyond the SHA-256 fingerprint. At each stage emit the
> `PipelineEvent` from `contracts/events.py` (`validated`, `face_scanned`, `post_found`, `anchored`,
> `verified`, `failed`). Write tests against the fake ledger for: success, no search match
> (`NoMatchFoundError` surfaces as a `failed` event, not an exception escaping the pipeline), and
> altered evidence producing `matched=false`. Do not import anything from `src/facechain/ledger/` —
> only from `contracts/ledger.py`.

### Integration C — CLI scaffold

> Work only in `src/facechain/cli.py`. Implement Typer commands `facechain run --image <path>` and
> `facechain verify --evidence <path>` calling the pipeline skeleton. `run` writes
> `runs/<run-id>/evidence.json` and prints each emitted event as it happens. Map every documented
> module error (`NoFaceDetectedError`, `NoMatchFoundError`, `LedgerUnavailableError`, and any others
> defined in the module contracts, including identity's `MultipleFacesDetectedError` /
> `RecognitionUnavailableError` and discovery's `DiscoveryUnavailableError` /
> `DiscoveryConfigError`) to a concise one-line message and a non-zero exit code — never fall back to
> fixture data on error. Add `--help` text matching the README's documented usage. Test against the
> fake ledger.

### Integration D — wire in the real ledger

> Rebase your integration branch on the latest `main` now that Ledger's real adapter is merged.
> In `src/facechain/pipeline/`, replace the fake `EvidenceLedger` with the real implementation
> imported from `src/facechain/ledger/` (public service only). Update `config.py` usage so
> `ANVIL_RPC_URL` / `ANVIL_PRIVATE_KEY` / `CHAIN_ID` match what Ledger's adapter expects — check
> `contracts/ledger.py` and Ledger's own tests for the exact call signature. Keep the fake ledger
> available as a test double. Re-run all `test_pipeline.py` tests — no live Anvil required for CI.

### Integration E — full mocked end-to-end suite

> In `tests/test_pipeline.py`, using fakes for Identity, Discovery, and Ledger (no network, no
> Anvil), cover: (1) success — full pipeline emits all six events in order and returns a
> `VerificationResult` with `matched=true`; (2) no search match — `DiscoveryService.discover()`
> raises `NoMatchFoundError`, pipeline emits `failed` with a clear reason, no ledger call is
> attempted; (3) blockchain write error — `EvidenceLedger.anchor()` raises `LedgerUnavailableError`,
> pipeline emits `failed`, evidence.json is still written to `runs/` with the discovery result but
> marked unanchored; (4) altered evidence — anchor an `EvidenceBundle`, mutate one field, call
> `verify()`, and confirm the pipeline surfaces `matched=false` without raising.

### Integration F — real end-to-end run against Anvil

> With Anvil running locally (`anvil` in a separate terminal) and `DISCOVERY_MODE=real` with a valid
> `SERPAPI_KEY` in `.env`, run `facechain run --image <path>` against a consented test image with a
> populated `consent_reference`. Confirm: the CLI prints all six pipeline events in order;
> `runs/<run-id>/evidence.json` contains no raw image bytes or raw embeddings, only hashes and
> normalized fields; the transaction hash from `anchor()` appears on your local Anvil logs. Then run
> `facechain verify --evidence runs/<run-id>/evidence.json` and confirm `matched=true` against the
> same chain state. Do not commit `runs/` output, real API keys, or Anvil private keys — confirm
> `.gitignore` covers all three.

### Integration G — open the integration PR

> Open a PR from your integration branch to `main` titled clearly (e.g.
> `feat(pipeline): wire identity → discovery → ledger end-to-end`). List which module public APIs
> you called (names only), confirm you did not modify anything under
> `src/facechain/identity/`, `src/facechain/discovery/`, or `src/facechain/ledger/`, and link the
> four mocked test cases plus the real Anvil run's evidence.json (redacted). Review the boundaries.

---

## Demo recording (final step)

> With Anvil running and one participant's consented image ready, record a single screen capture
> showing: `facechain run --image <consented-image-path>` executing end-to-end (face detected →
> real search match found → evidence anchored on-chain), followed by
> `facechain verify --evidence <path>` showing `matched=true` against the live chain. No editing.
> Do not include any non-consented image, real private key, or real API key on screen — mask the
> terminal if `.env` values would otherwise be visible. Upload per submission instructions and
> document known provider limitations (e.g. SerpAPI rate limits, InsightFace accuracy caveats) in the
> README. Also fill in the module owner names in the `README.md` ownership table if still "TBD".

---

## Recommended order (just do these top to bottom)

1. Phase 0 — contract hashing (merge first)
2. Phase 0b — remove the Node.js/Hardhat/Solidity ledger
3. Ledger Phase 1 → 2 → 3
4. Integration A (config) — can run in parallel with Ledger 2
5. Integration B (pipeline skeleton) and C (CLI) — depend on A
6. Integration D and E — depend on Ledger + B/C
7. Integration F — real run
8. Demo + docs

## Contract-change reminder

Never silently edit `contracts/`. Any shared change (like Phase 0) is a small contract-only PR,
acknowledged by all affected owners, merged before dependent module/integration work.
