# Development backlog

This file is the actionable index for the repository's ongoing development,
feature, investigation, design, and refinement work.

## Active items

### LEDGER-009 — Add per-video artifact manifests

- Status: Planned
- Type: Design and implementation
- Layer: Google Drive research storage
- Problem: Drive cache records are named by execution-request fingerprints, so
  the agent cannot deterministically enumerate the reusable transcript and
  analysis material associated with one video.
- Goal: Add one predictable per-video manifest in a clean v3 Drive namespace
  that indexes immutable artifacts, compatibility metadata, valid coverage,
  integrity hashes, and execution provenance without inheriting cache-v2
  schemas or lookup behavior.
- Next check:
  - [ ] Finalize native manifest schema version `1` and update semantics.
  - [ ] Fix the separate no-space v3 Drive namespace and deterministic lookup.
  - [ ] Define recovery from missing or stale manifest entries.
  - [ ] Prove clean-slate operation without cache-v2 data or fixtures.
  - [ ] If useful, isolate v2 comparison in a disposable read-only validator
        that production v3 code cannot import.
- Related document:
  [`design/youtube-artifact-cache-v3.md`](design/youtube-artifact-cache-v3.md)

### LEDGER-008 — Search artifacts before constructing requests

- Status: Planned
- Type: Design and implementation
- Layer: Research artifact retrieval
- Problem: An exact request fingerprint can prevent a byte-identical API call,
  but it cannot determine whether existing artifacts already provide usable
  or composable coverage for the current task.
- Goal: Search by video, artifact kind, compatibility, and interval coverage;
  construct Gemini requests only for uncovered material.
- Next check:
  - [ ] Define transcript compatibility and interval-union rules.
  - [ ] Define handling for overlaps, truncation, and partial coverage.
  - [ ] Keep execution fingerprints as last-moment idempotency guards.
  - [ ] Keep v3 retrieval free of cache-v2 fallback and compatibility paths.
  - [ ] Test exact, containing, composite, incompatible, and incomplete
        coverage cases.
- Related document:
  [`design/youtube-artifact-cache-v3.md`](design/youtube-artifact-cache-v3.md)

### LEDGER-001 — Run controlled clean-account installation trials

- Status: Planned
- Type: Investigation
- Layer: Cross-layer
- Evidence: One fresh account installed successfully, but its final answer
  omitted recoverable friction visible during execution.
- Next check:
  - [ ] Run trial `A2` against baseline commit `688642d`.
  - [ ] Run trial `A3` against the same commit.
  - [ ] Normalize both reports using the common incident schema.
  - [ ] Classify repeated incidents as deterministic, environment-dependent,
        transient, agent-path-dependent, or unconfirmed.
- Related document:
  [`investigations/chatgpt-work-installation-friction.md`](investigations/chatgpt-work-installation-friction.md)

### LEDGER-002 — Harden the npm cache path in fresh Work VMs

- Status: Hypothesis
- Type: Debugging
- Layer: Work VM/runtime
- Evidence: Trial `A1` encountered a permission fault at `/root/.npm` and
  recovered by switching to a writable temporary cache.
- Next check:
  - [ ] Determine whether trials `A2` and `A3` reproduce the permission fault.
  - [ ] Confirm that setting an isolated writable cache unconditionally is
        harmless across fresh VMs.
  - [ ] If confirmed, update `scripts/ensure_youtube_mcp.sh` and test a clean
        build.
- Related document:
  [`investigations/chatgpt-work-installation-friction.md`](investigations/chatgpt-work-installation-friction.md)

### LEDGER-003 — Characterize the account skill-save fallback

- Status: Hypothesis
- Type: Investigation
- Layer: ChatGPT skill platform
- Evidence: Trial `A1` received a validation-layer response on its first save,
  then succeeded after checking reconciliation and using a metadata-first,
  two-stage update.
- Next check:
  - [ ] Capture the exact observable response in another fresh account.
  - [ ] Determine whether the first request was rejected, asynchronously
        reconciled, or packaged incorrectly.
  - [ ] Encode conditional platform-installation guidance only after the
        behavior is sufficiently characterized.
- Related document:
  [`investigations/chatgpt-work-installation-friction.md`](investigations/chatgpt-work-installation-friction.md)

## Closed items

### LEDGER-007 — Correct transcript-mode edge cases

- Status: Completed
- Type: Refinement
- Layer: Gemini transcript requests
- Problem:
  - The timestamp schema accepted exactly two minute digits, so it rejected
    full-video timestamps at or beyond 100 minutes.
  - The transcript workflow did not state how to recover when Gemini returned
    only part of a requested interval.
- Goal: Correct these two blind spots without expanding transcript-mode scope.
- Completed work:
  - [x] Accepted `MM:SS.mmm` timestamps whose minute component has at least two
        digits, and tested a clip after 7,200 seconds.
  - [x] Required incomplete or truncated responses to remain cached while the
        unfinished interval is processed with smaller clips and new
        fingerprints.
  - [x] Re-ran all transcript, cache, and routing tests.
- Outcome:
  - The timestamp test accepts `120:00.000` and rejects a one-digit minute
    component.
  - Fifteen offline tests pass.
  - MCP behavior, cache semantics, Gemini routing, credential handling, and
    unrelated code remain unchanged.
- Related commits: `112bbe3`, `988a076`.

### LEDGER-006 — Add Gemini transcript-only mode

- Status: Completed
- Type: Feature
- Layer: Gemini request construction
- Problem: Gemini normally describes and interprets a supplied video. In two
  captionless-video trials, an explicit transcript-only prompt and constrained
  JSON response made it transcribe instead.
- Goal: Add an explicit transcript request mode to the existing Gemini
  pipeline.
- Completed work:
  - [x] Added the tested transcript-only prompt and response schema to the
        existing request builder.
  - [x] Exposed transcript mode without changing existing prompt-driven
        requests.
  - [x] Documented the minimal invocation, tested output budget, and use of
        the existing chunk planner for long videos.
  - [x] Tested the generated request contract and unchanged default behavior.
  - [x] Re-ran all existing Gemini routing and cache tests.
- Outcome:
  - At initial completion, generated requests exactly matched the successful
    cached Raaz and Haal-e-Dil trial requests. The later timestamp correction
    in `112bbe3` changed the prompt and response schema, so branch-tip requests
    have new fingerprints and do not reuse those original trial cache records.
  - Fourteen offline tests pass: three transcript-builder tests and eleven
    existing routing and cache tests.
  - Caption routing, cache v2, Gemini project routing, credential handling,
    chunk planning, and prompt-driven analysis behavior remain unchanged.
- Implementation commits: `3cc3f3f`, `16da400`.

### LEDGER-005 — Confirm independent Gemini project ownership

- Status: Completed
- Type: Refinement
- Layer: Gemini API
- Evidence: The user confirmed that the primary and fallback credentials were
  created under different Google accounts in separately created Google AI
  Studio projects, rather than in an imported or shared project. Both
  credentials also authenticate successfully.
- Outcome:
  - [x] Treat `primary` and `fallback` as independent project quota buckets.
  - [x] Keep account names, project identifiers, and credentials out of the
        repository.
  - [x] Do not exhaust either project merely to prove quota independence.
- Related document:
  [`design/gemini-interactive-quota-pool.md`](design/gemini-interactive-quota-pool.md)

### LEDGER-004 — Add interactive Gemini quota-pool routing

- Status: Completed
- Type: Feature
- Layer: Gemini API
- Evidence: Implemented by
  [`223380b`](https://github.com/DRanger666/chatgpt-work-youtube-skill/commit/223380bf7b508bf2536b91b07f617500f2ef3316).
- Completed checks:
  - [x] Added the private fallback-key credential contract.
  - [x] Implemented primary-first failover with project cooldowns.
  - [x] Preserved retries in one request-fingerprint cache record.
  - [x] Mocked quota, transient, terminal, and credential failures.
  - [x] Validated each credential through Gemini model metadata without
        generating content or approaching quota.
  - [x] Kept all long-video chunks sequential by default.
- Related document:
  [`design/gemini-interactive-quota-pool.md`](design/gemini-interactive-quota-pool.md)
