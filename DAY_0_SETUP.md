# Day 0 setup checklist

Complete this checklist together before anybody starts their first module branch. Day 0 is successful when all three people can run the checks locally, GitHub protects `main`, module ownership is clear, and the shared contracts are agreed. Do not start implementation prompts until the final sign-off section is complete.

## 1. Appoint two temporary team roles

Choose these roles for Day 0. They can rotate later.

| Role | What they do on Day 0 |
| --- | --- |
| Repository administrator | Creates/configures the GitHub repository and adds collaborators. They do not become the only person allowed to merge forever. |
| Setup checker | Helps each teammate run the local setup commands and records any blocker in GitHub Issues or the team chat. |

Also decide how you will communicate: use GitHub PR comments for code-specific discussions and one group-chat channel for quick coordination. Do not send API keys, private keys, or real images in either place.

## 2. Create and configure the GitHub repository

The repository administrator does the following in GitHub:

1. Create a repository named `FaceID + Blockchain` (or use this existing repository) under the account/organisation the team will submit from.
2. Set its visibility according to your submission requirements. Private is safest while developing; make it public only when the submission requires it and after checking it contains no sensitive data.
3. Add the other two people as collaborators with write access. Every contributor needs their own GitHub account; do not share an account.
4. Confirm the repository contains this project's files and that the `main` branch exists.
5. In **Settings -> Branches -> Add branch protection rule**, protect `main` with these settings:
   - Require a pull request before merging.
   - Require at least one approving review.
   - Require review of new changes after approval, if GitHub offers this setting.
   - Require the `CI / test` status check once it appears after the first CI run.
   - Require the branch to be up to date before merging.
   - Block force pushes.
   - Block direct pushes to `main`.
6. In **Settings -> Security**, enable secret scanning and push protection if those options are available.
7. Open the repository's **Actions** tab and confirm GitHub Actions are allowed. The existing `.github/workflows/ci.yml` is the automatic check configuration.

### What not to put on GitHub

Never commit or upload:

- `.env` files, API keys, Anvil private keys, passwords, or tokens.
- Real face images, face embeddings, or generated evidence from a real person.
- Private social-media URLs, private posts, or anything downloaded from a private account.

The `.gitignore` file protects common cases, but it cannot protect a file that is deliberately staged with Git. Always inspect `git status` and `git diff --staged` before committing.

## 3. Each person sets up their computer

Every team member completes this section on their own computer. Do not use one person's environment for all three people.

### Required accounts and software

1. Sign in to GitHub in a browser and accept the repository invitation.
2. Install Git 2.45 or newer.
3. Install Python 3.11.x. Use Python 3.11, not Python 3.12, until the team has confirmed that the face-recognition dependency works with 3.12.
4. Install `uv` 0.5 or newer. On Windows, this may be done with:

   ```powershell
   winget install astral-sh.uv
   ```

5. Install VS Code and the OpenCode extension/tool you will use for coding assistance.
6. Install Foundry and confirm its local blockchain tool, `anvil`, is available. Follow Foundry's official installation instructions for your operating system, then run its update/setup command if the installer asks you to.
7. Person 2 creates or obtains an approved visual-search-provider account/key with Google Lens access (the planned provider is SerpAPI). The key is needed for the eventual real demo, not for unit tests. Keep it private.

### Configure your Git identity once

In PowerShell, set the name and email that should appear on your commits. Use your own details, not someone else's:

```powershell
git config --global user.name "Your Name"
git config --global user.email "your-github-email@example.com"
git config --global init.defaultBranch main
```

Check that Git is installed:

```powershell
git --version
```

## 4. Clone the repository and install project dependencies

Each person chooses a normal local work folder, opens PowerShell there, and clones the repository using the **Code** button's HTTPS URL (or SSH URL if they already use SSH keys):

```powershell
git clone <repository-url>
cd "FaceID + Blockchain"
```

Check the remote and branch state:

```powershell
git remote -v
git branch --show-current
git status
```

The remote should point to the team repository, the branch should be `main`, and `git status` should say the working tree is clean. Then install project dependencies:

```powershell
uv sync --extra dev --extra face
```

This creates the project's isolated Python environment and installs the project, developer tools, and face-recognition extras. It can take a while on the first machine because model/runtime packages may be downloaded.

Confirm the basic tools work:

```powershell
uv --version
uv run python --version
uv run ruff --version
uv run mypy --version
uv run pytest --version
anvil --version
```

If a command is not found, fix that installation before proceeding. Record the operating system and error message in the team chat/issue so all three people do not debug the same problem separately.

## 5. Create your local secret configuration

Each person creates a private `.env` file from the template:

```powershell
Copy-Item .env.example .env
```

Open `.env` locally. Do not add it to Git. Initially it can retain blank secret values. For the eventual live demo, the responsible teammate will add:

- `SERPAPI_KEY`: the visual-search-provider key.
- `ANVIL_RPC_URL`: normally `http://127.0.0.1:8545` for local Anvil.
- `ANVIL_PRIVATE_KEY`: a test-only Anvil account private key.
- `CHAIN_ID`: `31337` for the local Anvil chain.
- `DISCOVERY_MODE`: `real` for the real demo.

Do not use real cryptocurrency funds or a personal wallet. Anvil is a local, disposable development chain. Restarting it resets its data unless the team deliberately configures persistence.

## 6. Run the starting quality checks

From the repository root, every person runs:

```powershell
uv run ruff check .
uv run mypy src
uv run pytest
```

At the beginning, these checks validate the scaffold and available tests. Later they validate actual code. If they pass, write "local setup passed" in the group chat. If they fail, do not begin module implementation until the setup checker understands whether the problem is a local installation issue or a repository issue.

What the commands mean:

- `uv` installs/runs the exact Python tools required by the project.
- `ruff` checks common code mistakes and style problems.
- `mypy` checks type/data-shape mistakes.
- `pytest` runs automated tests.
- GitHub CI repeats these same checks automatically for every PR.

## 7. Hold the contract and ownership meeting

Meet for 30-45 minutes. Share your screen and read these files together:

```text
README.md
AGENTS.md
SKILLS.md
BUILD_PROMPT.md
TEAM_WORKFLOW_GUIDE.md
contracts/domain.py
contracts/face.py
contracts/discovery.py
contracts/ledger.py
contracts/events.py
```

Decide and record the following in the first GitHub issue or a short Day 0 PR:

| Decision | Record |
| --- | --- |
| Ownership | Name assigned to Identity, Discovery, and Ledger. |
| Reviews | Who reviews whose PRs; a simple rotation is Person 1 reviews Person 2, Person 2 reviews Person 3, Person 3 reviews Person 1. |
| Integration | Initial rotating integrator and when to start integration. |
| Provider | Confirm SerpAPI Google Lens or document an approved replacement. |
| Consent | How the test participant gives consent and where the reference is stored without putting personal information in Git. |
| Demo | Who supplies a consented image, who operates Anvil, and who records the final screen demonstration. |

### Contract agreement checklist

Confirm that everyone understands:

- Identity produces `FaceScan` from `AuthorizedImage`.
- Discovery accepts permitted input/scan metadata and produces `DiscoveryResult` plus `EvidenceBundle`.
- Ledger consumes only `EvidenceBundle` and produces receipt/verification models.
- Integration connects those public services without importing another module's internals.
- `PipelineEvent` never contains biometric material or secrets.

If a contract needs changing, create a **contract-only PR**, get acknowledgement from affected owners, merge that first, then update each module separately. Do not start a module based on an unagreed interface.

## 8. Make the first planning record

The repository administrator or setup checker creates a GitHub Issue named `Day 0 team agreement`. It contains:

- The three owners and their module folders.
- The review rotation.
- The selected provider and its account owner (not its key).
- Confirmation that all three local setup checks passed.
- Any current blocker and who owns the next action.

Optionally make a small Day 0 documentation PR that adds the names to the ownership table in `README.md`. This must not contain secrets or private consent information.

## 9. Final Day 0 sign-off

Do not start the implementation workflow until every box below is true:

- [ ] All three people accepted the GitHub invitation and can clone/push a branch.
- [ ] `main` is protected with PR review and CI requirements.
- [ ] Each person installed Git, Python 3.11, `uv`, VS Code/OpenCode, and Anvil.
- [ ] Each person ran `uv sync --extra dev --extra face` successfully.
- [ ] Each person ran Ruff, mypy, and pytest successfully.
- [ ] Each person has a private untracked `.env` file.
- [ ] No secrets or real personal images are in Git history or the current working tree.
- [ ] Identity, Discovery, and Ledger each have an owner.
- [ ] Everyone read and agreed to the shared contracts.
- [ ] The provider, consent approach, reviewer rotation, and initial integration plan are written in the Day 0 team agreement issue.

Once all boxes are checked, each owner follows `TEAM_WORKFLOW_GUIDE.md`: update `main`, create their first small branch, paste only their relevant phase prompt from `BUILD_PROMPT.md` into OpenCode, test locally, and open a PR.
