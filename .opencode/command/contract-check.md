---
description: Check a module's code and tests against the shared contracts.
---

Identify the module touched by the current diff. Read its matching file(s) in `contracts/`, plus `contracts/domain.py` and `contracts/events.py`. Compare each public function, Pydantic model, serialized payload, event, and error path with the contract. Flag field-name/type/optionalness differences, non-canonical evidence hashing, cross-module internal imports, undocumented contract changes, and tests that do not validate the boundary. Do not propose edits outside the touched module or `contracts/`; state the exact contract owner(s) that must be consulted for a shared change.
