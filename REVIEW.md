# Pull-request review

Every PR must be small, scoped to one module, linked to its contract, tested, and approved by one teammate. The author runs `uv run ruff check .`, `uv run mypy src`, and `uv run pytest`; CI must be green before merge.

Reviewers check: exact contract fields/types and canonical JSON behavior; no imports across module internals; tests use fakes rather than a real face provider, web service, or chain; failure paths are explicit; keys, face embeddings, raw images, and private URLs are absent from logs and commits; and `DISCOVERY_MODE=fixture` cannot be used by the normal demo command.

For discovery, verify the real adapter performs a live search and attributes source URL/time rather than returning a preset post. For the ledger, verify chain ID, transaction receipt confirmation, deterministic hashes, and a modified-evidence mismatch. For identity, verify one-face enforcement and no retained biometric database. Contract changes require acknowledgements from all affected owners before review approval.
