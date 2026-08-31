# Team workflow guide

This guide explains how three people can build this project together even if you have only used Git and GitHub alone before.

## What the project does

The program accepts an image from a person who has given consent. It confirms that there is exactly one face, creates a privacy-preserving face fingerprint, performs a genuine public visual search for a matching post, and normalizes the public result into evidence. It then hashes that evidence, records the hash on a local Ethereum-compatible blockchain, and verifies that the same evidence still matches the blockchain record.

The final demonstration must show: **consented image -> public post found through a real search -> blockchain record created -> verification succeeds**. Do not use private posts, a biometric database, a preselected result, or an image without consent. A no-match result is an honest failure, not something to hide.

## Git and GitHub in simple language

Git saves a history of your files. GitHub stores a shared copy of that history online. A **branch** is your own lane of work. Changes in your branch do not affect the shared project until they are merged. A **pull request** (PR) asks the team to merge your branch into the shared `main` branch; it shows the changes, runs checks, and gives teammates a place to approve or request edits.

Never work directly on `main`. Every small feature or bug fix gets its own branch and PR. This gives you a safety net: if something goes wrong, the shared working project stays intact.

### Words you will see often

- **Module:** one self-contained part of the program. This project has Identity, Discovery, and Ledger modules.
- **Integration:** the small amount of code that connects completed modules into one pipeline: Image -> Identity -> Discovery -> Ledger -> command-line result. Integration does not rebuild the modules; it makes their public services work together.
- **Module PR:** a pull request containing a focused change to one person's module, for example Person 1's "add face detector" PR.
- **Shared contract:** a file in `contracts/` that specifies the exact data format one module sends to another. It is what lets people build in parallel without waiting for each other's internal code.
- **CI (Continuous Integration):** GitHub automatically repeats the quality checks on every push/PR in a clean environment. A green check means the configured checks passed; a red X means something needs fixing before merge.

### The tools used by the checks

`uv` is the project's Python tool manager. It installs the agreed package versions and runs commands inside the project environment, so all teammates use compatible tools. `uv sync --extra dev --extra face` installs the project dependencies; `uv run <command>` runs a command using them.

`ruff` is a fast code-quality checker: it finds common mistakes such as unused imports and style problems. `mypy` is a type checker: it catches mismatched data shapes, such as supplying text where an integer is required. `pytest` runs the project's real automated tests. Run all three because they check different kinds of errors.

## Divide the project among three people

Assign one person to each module on Day 0. Write the actual names in `README.md`.

| Person | Owns | Their responsibility | What they pass onward |
| --- | --- | --- | --- |
| Person 1 | `src/facechain/identity/`, `tests/test_identity.py` | Validate a consented image, detect exactly one face, and make a face scan. | `FaceScan` |
| Person 2 | `src/facechain/discovery/`, `tests/test_discovery.py` | Use the approved public visual-search provider, normalize a public result, and make evidence. | `DiscoveryResult`, `EvidenceBundle` |
| Person 3 | `src/facechain/ledger/`, `tests/test_ledger.py` | Hash evidence, anchor it on Anvil, and verify it later. | `LedgerReceipt`, `VerificationResult` |

Integration is a rotating shared duty, not a fourth module. Once module PRs have merged, choose one person for a short integration task. That person may edit `src/facechain/pipeline/`, `src/facechain/cli.py`, and `tests/test_pipeline.py`, but does not rewrite the other modules.

## The shared contracts: read these first

All three people must read `contracts/` before coding. These files define the exact data each module gives another:

- `AuthorizedImage`: input path, image hash, and consent reference.
- `FaceScan`: face fingerprint, detector, exactly one face, and scan time.
- `PublicPost`: public source URL, platform, optional text/image details, and retrieval time.
- `EvidenceBundle`: the normalized public facts the ledger will hash.
- `LedgerReceipt` and `VerificationResult`: blockchain record and result of checking it.
- `PipelineEvent`: safe progress reporting; it must never contain raw image data, face embeddings, keys, or private URLs.

Treat contracts like the shape of a plug. Each person can build their own device independently if everyone keeps the plug shape. Do not change a contract field, name, or type without coordinating with everyone it affects.

## Day 0 setup: do this together

1. Create the GitHub repository and invite all three team members.
2. Protect the `main` branch in GitHub: require a PR, one approval, and the `CI / test` check. Disable force pushes and direct pushes.
3. Each person installs Git, Python 3.11, `uv`, Foundry/Anvil, VS Code, and OpenCode as listed in `PREREQUISITES.md`.
4. Each person clones the repo, opens PowerShell in it, and runs `uv sync --extra dev --extra face`.
5. Each person copies `.env.example` to `.env` locally. `.env` contains secrets and must never be committed.
6. Read `AGENTS.md`, `SKILLS.md`, `BUILD_PROMPT.md`, this guide, and every contract together. Confirm which person owns each module and choose a group chat for quick questions.
7. If a real requirement is missing, make a tiny contract-only PR, get acknowledgement from all affected owners, and merge it before implementations begin.

## Every work session, for every person

### 1. Update the shared baseline

Open PowerShell in the project and run:

```powershell
git status
git switch main
git pull --ff-only
```

`git status` tells you whether you have unfinished edits. Do not delete edits just to make it clean: finish, commit, or ask for help. `git pull --ff-only` downloads work already merged by teammates.

### 2. Create a branch before editing

Use `codex/<module>/<short-description>`:

```powershell
git switch -c codex/identity/validate-input-image
```

Other examples are `codex/discovery/serpapi-adapter`, `codex/ledger/verify-evidence`, and `codex/integration/cli-pipeline`. One branch should do one small coherent job.

`codex/` is simply this repository's agreed branch-name prefix. It makes team branches easy to recognize and group in GitHub; Git does not require that word specifically. The remainder names the module and the task.

Do **not** normally keep one permanent branch per module. A person owns a module, but creates a new branch for each small feature/phase in it. For example, the Identity owner might make `codex/identity/input-validation`, then `codex/identity/face-provider`, then `codex/identity/error-handling`. This makes PRs easier to review and merge.

If one feature takes several days, continue using the same branch every day. You do not create it again. Save progress with additional commits and pushes, then create the next branch only after the current feature's PR is merged (or after you intentionally stop that feature).

### 3. Work inside your boundary

Read the matching contract and your module section in `BUILD_PROMPT.md`. Work only in your module folder and its matching test file. Use OpenCode for one phase at a time, explicitly naming the allowed folder and contract. Do not ask it to build the entire project in one change.

### 4. Test before committing

The identity owner runs the following; discovery and ledger owners change the final test filename:

```powershell
uv run ruff check .
uv run mypy src
uv run pytest tests/test_identity.py
```

Tests must use fakes/mocks; they must not need the internet, Anvil, or real provider keys. In OpenCode, also run `/contract-check` and `/review`. Fix important findings before making a PR. `/explain` can translate your change into plain English for a teammate.

### 5. Commit and upload your work

Inspect the changed files with `git status` and `git diff`. Stage only files relevant to the current feature, then create a clear checkpoint:

```powershell
git add src/facechain/identity tests/test_identity.py
git commit -m "feat(identity): validate authorized input images"
git push -u origin codex/identity/validate-input-image
```

`git add` selects files; it does not upload them. `git commit` saves a snapshot locally. `git push` uploads the branch to GitHub. Use messages such as `feat(discovery): normalize public search results` or `fix(ledger): reject altered evidence`.

### 6. Open and finish a pull request

On GitHub, use **Compare & pull request** and target `main`. Describe: what changed, which contracts were followed, tests run, any provider assumption, and confirmation that no secret, real face image, raw embedding, or private URL was committed. Request review from a teammate.

If the reviewer asks for changes, edit the same branch, rerun checks, commit, and push. The PR updates by itself. When CI is green and one teammate approves, merge using the agreed option (squash merge is a good default). Then return to `main`, pull, and begin the next branch.

## Module work, in order

### Person 1: identity

Person 1 starts by creating `codex/identity/input-validation`. They paste the first Identity phase from `BUILD_PROMPT.md` into OpenCode, after adding: "Read `AGENTS.md`, `SKILLS.md`, `contracts/domain.py`, and `contracts/face.py` first. Stay only in the permitted folders." They then inspect the changed files, test, commit, push, open a PR, get it approved, and merge it.

1. In that first branch, validate the image, calculate its hash, require a consent reference, and create `AuthorizedImage`. Test valid and invalid input.
2. After that PR merges, create `codex/identity/face-provider`. Paste the second Identity phase prompt. Add InsightFace/OpenCV behind a provider boundary. Exactly one face is valid; unreadable, zero-face, and multiple-face input are typed errors.
3. Return the contract's `FaceScan`. Never log or store a raw embedding.
4. After the provider PR merges, create `codex/identity/quality-gate`. Paste the third prompt, run all checks, and fix only Identity issues. Test success and all failure paths with safe fixtures/fakes. Do not commit real images of people.

The Discovery and Ledger owners follow exactly the same branch -> prompt -> inspect -> test -> commit -> push -> PR -> merge cycle for their own phases.

### Person 2: discovery

1. Add a `DiscoveryProvider` boundary with fake-provider tests.
2. Implement the real SerpAPI Google Lens adapter using a key from `.env`, with timeout/retry handling.
3. Normalize one qualifying public result into `PublicPost`, then build `EvidenceBundle` exactly as contracted.
4. Return `NoMatchFoundError` if there is no public match. Never return a saved post to make a demo appear to work.

### Person 3: ledger

1. Canonically serialize the `EvidenceBundle`: UTF-8, sorted keys, compact separators, then SHA-256 lowercase hex. Test that key order does not change the hash.
2. Use `web3.py` and Anvil to anchor only the evidence hash and timestamp. Read credentials from `.env`, never output them.
3. Recalculate and compare the hash during verification. Changed evidence returns `matched=false`; an unreachable chain returns a typed error.
4. Test success, transaction failure, wrong chain ID, and altered evidence using fakes.

## Integration workflow

1. Pick a rotating integrator and create an integration branch from current `main`.
2. In the pipeline, call identity, pass allowed metadata to discovery, pass `EvidenceBundle` to ledger, then verify.
3. Add CLI commands such as `run --image ...` and `verify --evidence ...`. Expected errors should be understandable and return non-zero exit codes.
4. Emit safe progress events.
5. Add mocked end-to-end tests for success, no match, chain failure, and changed evidence.
6. Open an integration PR and ask all three owners to review the boundaries.

## Changing a contract mid-project

Never silently edit `contracts/`.

1. Explain the problem in GitHub or group chat: which field/type must change, why it is needed, and who is affected.
2. Make a small contract-only PR. Do not mix it with module code.
3. Get acknowledgement from every affected owner.
4. Merge the contract PR first.
5. Each owner updates their own module in a separate PR. Integration waits until those updates merge.

## Git problems you will see

### Someone merged while I was working

Before merging your PR, run:

```powershell
git fetch origin
git merge origin/main
```

Run tests again and push. If Git reports a conflict, two people edited the same nearby lines.

### I have a merge conflict

Git marks both versions using `<<<<<<<`, `=======`, and `>>>>>>>`. Read both, produce the intended combined code, and delete all marker lines. Then run `git add <resolved-file>` and commit the resolution. Run tests. If the conflict is in `contracts/`, stop and ask the affected owners rather than guessing.

### I accidentally staged a secret or real image

Check `git diff --staged` before committing. If it is not committed, use `git restore --staged <file>` and move it outside the repository. If it was pushed, revoke the key immediately, tell the team, and remove it in a new commit. Deleting a pushed secret does not make it safe.

## Final demo checklist

1. All module and integration PRs are merged; `main` has green CI.
2. Use a consenting person and a public result genuinely found by the provider.
3. Put actual local values only in `.env`; do not show keys in the recording.
4. Start Anvil and run the full pipeline.
5. Show image input, one-face scan, real public source result, blockchain transaction hash, and successful verification.
6. If possible, alter a harmless evidence field in a copy and show `matched=false`.
7. Record the screen, upload it, test the link in an incognito/private window, and submit it.
8. Update `README.md` with the real provider, blockchain, commands, and limitations. Confirm GitHub contains no `.env`, real images, generated evidence runs, or secrets.

## The rules that prevent confusion

- One branch has one small purpose.
- Each owner edits their module, not another module's internals.
- Contracts are agreed first and changed openly.
- Run tests before every PR; require CI and one approval before merging.
- Keep `main` safe for any teammate to pull and run.
- Ask early when unclear.
- Protect people as well as code: consent only, public content only, no biometric database, no secrets in Git, and honest failures rather than fabricated results.
