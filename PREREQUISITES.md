# Day 0 setup

## Required tools

- Git 2.45+ and a GitHub account.
- Python 3.11.x (do not use 3.12 until InsightFace support is confirmed).
- `uv` 0.5+ (`winget install astral-sh.uv`); run `uv sync --extra dev --extra face` after cloning.
- Foundry with `anvil` 1.0+ (`foundryup` from the official installer).
- A SerpAPI account/key with Google Lens access, or another provider implemented behind `DiscoveryProvider`.
- VS Code with OpenCode. Each contributor needs an isolated clone or worktree.

## Repository controls

Create `main` on GitHub and enable: required pull request, one approval, required `CI / test`, require branches to be up to date, and disallow force pushes and direct pushes. Add the three contributors with write access; keep secrets only in GitHub Actions secrets and local `.env` files. Enable secret scanning and push protection where available.

## Day 0 module-decomposition session

Meet once before coding, read the four files in `contracts/`, and record agreement in the first PR. The module map is:

| Module | Starts after agreeing | Exposes | Consumes |
| --- | --- | --- | --- |
| Identity | `domain.py`, `face.py` | `FaceScan` | `AuthorizedImage` |
| Discovery | `domain.py`, `discovery.py` | `DiscoveryResult` | `AuthorizedImage`, `FaceScan` metadata |
| Ledger | `domain.py`, `ledger.py` | `LedgerReceipt`, `VerificationResult` | `EvidenceBundle` |

Identity and Discovery agree on `domain.py`; Discovery and Ledger agree on the canonical `EvidenceBundle`; all three agree on `events.py`. Once these contracts are committed, implementations can proceed simultaneously. Contract changes require the process in [BUILD_PROMPT.md](BUILD_PROMPT.md).

## End-of-Day-0 repository tree

```text
.
├── .github/workflows/ci.yml
├── .opencode/command/{review,explain,contract-check}.md
├── contracts/{domain,face,discovery,ledger,events}.py
├── src/facechain/{cli.py,config.py,contracts.py,identity/,discovery/,ledger/,pipeline/}
├── tests/{contract,test_identity,test_discovery,test_ledger,test_pipeline}.py
├── .env.example
├── .gitignore
├── AGENTS.md
├── BUILD_PROMPT.md
├── GIT_WORKFLOW.md
├── OPENCODE_SKILLS.md
├── PREREQUISITES.md
├── README.md
├── REVIEW.md
├── SKILLS.md
└── pyproject.toml
```

Do not commit real face images, provider keys, private URLs, transaction private keys, or generated `runs/` evidence.
