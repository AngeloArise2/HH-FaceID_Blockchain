# AI agent instructions

This repository is a Python 3.11 `uv` CLI project. It processes only consented input images, queries an approved public visual-search provider, and writes a SHA-256 fingerprint of normalized evidence to an Ethereum-compatible chain. Read [SKILLS.md](SKILLS.md), the relevant `contracts/*.py`, and [BUILD_PROMPT.md](BUILD_PROMPT.md) before editing.

## Boundaries

- Work only in your assigned `src/facechain/<module>/`, its matching tests, and docs explicitly assigned to you.
- Treat `contracts/` as shared API. Do not change it unless the contract-change process in `BUILD_PROMPT.md` is followed and the affected owners are flagged in the PR.
- Do not edit another module merely to make your code pass. Use adapters or raise a contract gap.
- Do not add surveillance features, identity databases, account login automation, private-content access, bulk searching, or a fake discovery result. Keep consent and provider-source metadata with each run.

## Working loop

1. Read the matching contract and build prompt.
2. Make the smallest coherent change in your boundary.
3. Run `uv run ruff check .`, `uv run mypy src`, and the relevant `uv run pytest` target.
4. Run `/contract-check`, then `/review`; resolve findings before committing.

Never print secrets, access tokens, facial embeddings, or raw image bytes in logs. Document assumptions in the PR when external provider behavior is uncertain.
