# FaceID + Blockchain Verification

A consent-based command-line demonstration that accepts an authorized face image, extracts a facial embedding, performs a real reverse-image/web search for a matching public post, then anchors a fingerprint of the discovery result on an Ethereum-compatible blockchain and verifies it again.

The intended users are the three-person HH Goa 2026 team and demo reviewers. It is deliberately a local, single-subject demo: it is not a surveillance product, does not crawl private accounts, and must only be run with documented consent and search-provider terms.

## Stack and assumptions

- Python 3.11, `uv`, Typer CLI, Pydantic v2, InsightFace + OpenCV, and `httpx`.
- A configured visual-search provider (SerpAPI Google Lens by default) performs the genuine discovery step; `DISCOVERY_MODE=fixture` is test-only.
- Anvil (Foundry) provides a local Ethereum-compatible chain; `web3.py` writes and re-verifies a SHA-256 evidence fingerprint. Sepolia may be enabled later through configuration.
- No user accounts, database, web UI, private-platform scraping, or production deployment are in scope.

## Parallel module ownership

| Module | Owner | Responsibility | Contract dependencies |
| --- | --- | --- | --- |
| `identity` | TBD | Validate images and produce a face embedding/fingerprint | `contracts/domain.py`, `contracts/face.py` |
| `discovery` | TBD | Submit the authorized image to a provider and normalize matching public posts | `contracts/domain.py`, `contracts/discovery.py` |
| `ledger` | TBD | Fingerprint evidence, anchor it on-chain, and verify it | `contracts/domain.py`, `contracts/ledger.py` |

The shared CLI is an integration surface, not a fourth owned product module. See [BUILD_PROMPT.md](BUILD_PROMPT.md) for build order inside each module and the integration steps.

## Run locally (once implemented)

```powershell
uv sync --extra dev --extra face
Copy-Item .env.example .env
anvil
uv run facechain run --image .\samples\consented-subject.jpg
uv run facechain verify --evidence .\runs\<run-id>\evidence.json
```

Provide `SERPAPI_KEY` and an image of a consenting subject in `.env`. `run` must fail clearly if no real matching public post is found; it must never substitute a preselected result. See [PREREQUISITES.md](PREREQUISITES.md) for Day 0 setup and [REVIEW.md](REVIEW.md) before opening a pull request.
