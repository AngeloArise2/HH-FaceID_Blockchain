# OpenCode commands and session loop

Commands live in `.opencode/command/` and are invoked from OpenCode as `/review`, `/explain`, and `/contract-check`.

Use this loop for every focused session: read the assigned module prompt in [BUILD_PROMPT.md](BUILD_PROMPT.md), implement only that module, run its tests, use `/contract-check` to compare code with its shared schema, use `/review` on the diff, and use `/explain` before handing off if a teammate needs a plain-English summary. Commands are review aids, not substitutes for tests or human approval.

`/review` checks conventions, privacy safeguards, tests, and a diff. `/explain` translates the latest diff without exposing personal data. `/contract-check` checks models, payload fields, and canonicalization against `contracts/`.
