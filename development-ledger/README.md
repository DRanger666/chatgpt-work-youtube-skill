# Development ledger

This directory preserves the engineering memory behind the skill: unfinished
work, feature ideas, refinement opportunities, investigations, design
decisions, and debugging evidence.

The Git history explains changes that were made. This ledger also records work
that has not yet been done, why it matters, and what evidence should determine
the eventual decision.

## Contents

- [`backlog.md`](backlog.md) is the actionable index of open, deferred,
  completed, rejected, and superseded work.
- `investigations/` contains repeatable test plans, trial evidence, and
  cross-trial conclusions.
- Future design or debugging documents should remain inside this directory and
  be linked from the backlog.

## Status vocabulary

| Status | Meaning |
|---|---|
| Hypothesis | Observed or proposed, but not sufficiently reproduced |
| Confirmed | Supported by enough evidence to act on |
| Planned | Accepted and waiting for implementation |
| In progress | Currently being implemented or tested |
| Completed | Implemented and validated |
| Rejected | Considered and deliberately not pursued |
| Superseded | Replaced by a later decision or implementation |

## Working rules

1. Give each ledger item a stable identifier.
2. Link the item to its investigation, design note, debug record, issue, or
   implementation commit.
3. Distinguish observed evidence from interpretation.
4. Assign a problem to the operational layer that owns the failing operation.
5. Record the validation needed before changing a hypothesis to confirmed.
6. Do not delete completed, rejected, or superseded items; preserve their
   outcome so the same question does not need to be rediscovered.
7. Keep credentials, generated video analyses, and private connector contents
   out of the repository.

## Adding an item

Use this minimum record:

```markdown
### LEDGER-000 — Short descriptive title

- Status:
- Type: Feature | Refinement | Investigation | Design | Debugging
- Layer:
- Evidence:
- Next check:
- Related documents or commits:
```

Detailed work can live in a separate document. The backlog entry should remain
the concise index and lifecycle record.

## Investigation index

| Document | Scope |
|---|---|
| [`investigations/chatgpt-work-installation-friction.md`](investigations/chatgpt-work-installation-friction.md) | Layer-aware clean-account installation testing and friction reporting |
| [`design/gemini-interactive-quota-pool.md`](design/gemini-interactive-quota-pool.md) | Conservative two-project Gemini routing for interactive video analysis |
| [`design/youtube-artifact-cache-v3.md`](design/youtube-artifact-cache-v3.md) | Artifact-first retrieval, manifest storage, and durable Gemini execution requirements |
