# Git workflow

Create branches from current `main` using `codex/<module>/<short-description>`, for example `codex/identity/face-provider`, `codex/discovery/serpapi-adapter`, or `codex/ledger/anvil-verify`. Integration work uses `codex/integration/<short-description>`.

Daily loop:

```powershell
git switch main
git pull --ff-only
git switch -c codex/identity/face-provider
# edit, then test
git add src/facechain/identity tests/test_identity.py
git commit -m "feat(identity): add face provider adapter"
git push -u origin codex/identity/face-provider
```

Open a PR, request review, merge only after required checks and approval, then delete the remote branch. Rebase/merge updates only as team convention permits; never force-push `main`.

## Merge conflicts in plain English

A conflict means Git found two edits to the same lines and cannot safely choose. Read both changes and preserve the intended behavior, especially the shared contract. Remove the `<<<<<<<`, `=======`, and `>>>>>>>` markers, run tests, then `git add <resolved-file>` and commit the resolution. If the conflict is in `contracts/`, stop and coordinate with the affected module owner rather than guessing.
