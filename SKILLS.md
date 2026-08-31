# Coding conventions

## Python shape

Use Python 3.11, `uv`, Pydantic v2, and type annotations on all public functions. Packages use lowercase snake_case; classes and Pydantic models use `PascalCase`; functions, fields, files, and CLI options use `snake_case`/kebab-case as appropriate. Import only from `contracts` for cross-module types; never import a sibling module's internals.

Each module has `service.py` (orchestrating public API), `provider.py` (external adapter), `models.py` (internal models), and `exceptions.py`. Public entry points return the exact Pydantic contract model or raise a module exception. Keep provider HTTP calls behind injected protocols so tests use fakes.

## Errors and evidence

Raise typed errors: `InputValidationError`, `NoFaceDetectedError`, `DiscoveryUnavailableError`, `NoMatchFoundError`, `LedgerUnavailableError`, or `VerificationFailedError`. The CLI maps expected errors to a concise message and non-zero exit code; no silent fallback to fixture data. Serialize evidence with canonical JSON: UTF-8, sorted keys, compact separators, SHA-256 lowercase hex. Store provider name, source URL, retrieval time, and consent reference, but never an API key or private key.

## Tests and quality bar

Use `pytest`, `respx` for HTTP boundaries, and deterministic fakes for face and ledger providers. Unit-test invalid images, zero/multiple faces, provider timeouts, no match, canonical hash stability, transaction failure, and altered evidence verification. Contract tests import every contract model and validate representative JSON. New executable paths need 85% line coverage in their module and all tests must run without network or Anvil.

## Configuration

Read settings once through `src/facechain/config.py` using `pydantic-settings`. `.env.example` contains names only; `.env` stays untracked. Required run-time variables are `SERPAPI_KEY`, `ANVIL_RPC_URL`, and `ANVIL_PRIVATE_KEY`; `CHAIN_ID=31337` and `DISCOVERY_MODE=real` are safe defaults. Validate configuration before calling a provider.
