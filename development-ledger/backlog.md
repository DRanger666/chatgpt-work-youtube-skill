# Development backlog

This file is the actionable index for the repository's ongoing development,
feature, investigation, design, and refinement work.

## Active items

### LEDGER-006 — Add Gemini transcript-only mode

- Status: In progress
- Type: Feature
- Layer: Gemini request construction
- Problem: Gemini normally describes and interprets a supplied video. In two
  captionless-video trials, an explicit transcript-only prompt and constrained
  JSON response made it transcribe instead.
- Goal: Add an explicit transcript request mode to the existing Gemini
  pipeline.
- Required work:
  - [ ] Add the tested transcript-only prompt and response schema to the
        existing request builder.
  - [ ] Expose transcript mode without changing existing prompt-driven
        requests.
  - [ ] Document the minimal invocation, including the tested output budget
        and use of the existing chunk planner for long videos.
  - [ ] Test the generated request contract and unchanged default behavior.
  - [ ] Re-run all existing Gemini routing and cache tests.
- Constraints:
  - Reuse the existing caption-first workflow, cache v2, Gemini project
    routing, credential handling, and chunk planner.
  - Do not add translation, transliteration, diarization, subtitle export,
    alternative ASR, cache redesign, routing changes, or unrelated
    refactoring.
- Completion rule: Every changed line must be necessary to build, invoke,
  document, or test transcript-only requests.
- Related evidence: July 2026 Raaz and Haal-e-Dil captionless-video trials.

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
