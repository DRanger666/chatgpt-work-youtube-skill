# Development backlog

This file is the actionable index for the repository's ongoing development,
feature, investigation, design, and refinement work.

## Active items

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

### LEDGER-010 — Restore Gemini execution requirements in cache v3

- Status: Completed
- Type: Design correction and implementation
- Layer: Gemini execution lifecycle and persistent research state
- Evidence:
  - LEDGER-004 requires every Gemini network attempt to remain observable,
    identical failed requests to require a documented retry reason, and prior
    attempt history to survive retries.
  - Commit `763d4cf` removed the workflow that consumed `ROUTING_JSON`, required
    documented authorization for identical failed retries, and preserved
    appended attempt history.
  - The initial v3 implementation stores pending and failed execution state only
    in the artifact manifest. Completed provenance is also copied into
    artifacts, but manifest reconstruction still cannot recover pending or
    failed execution-only history.
  - Drive replacement exposes no atomic compare-and-set operation, so leases
    cannot enforce mutual exclusion across Work sessions.
- Goal: Add a native v3 Gemini execution journal without restoring cache-v2
  schemas, filenames, lookup, migration, or fallback behavior. Keep every
  execution-oriented field in this separate data structure and link successful
  executions to produced artifact IDs only in the execution-to-artifact
  direction. Support one write-capable session per normalized video ID and
  describe that boundary as an operating policy rather than a Drive-enforced
  concurrency guarantee.
- Completed work:
  - [x] Stored pending, completed, and failed executions separately from the
        artifact-discovery manifest.
  - [x] Consumed and persisted safe `ROUTING_JSON` attempts for success and
        failure.
  - [x] Required a documented permitted reason before an identical failed
        request can run again.
  - [x] Preserved attempt history and numbering through retries, independently
        of artifact-manifest reconstruction.
  - [x] Added pending expiry and reconciliation without claiming unsupported
        cross-session atomicity.
  - [x] Blocked another session's same-video write path while active pending
        ownership exists while continuing to permit read-only artifact reuse.
  - [x] Treated expiry as a reconciliation trigger, not automatic takeover, and
        preserved explicit writer handoff or abandonment evidence.
  - [x] Permitted different normalized video IDs to have independent concurrent
        writers.
  - [x] Kept the artifact manifest byte-stable across every execution-only
        state change that produces no searchable artifact.
  - [x] Stored produced artifact IDs on execution records without adding
        execution back-references to artifacts or manifests.
  - [x] Re-ran LEDGER-004 routing, failure, cooldown, and retry-history tests
        against the native v3 execution lifecycle.
  - [x] Summarized the dedicated single-writer policy in `SKILL.md` and
        `references/contracts.md` without redefining it.
- Outcome:
  - The native journal consumes unmodified `gemini_request.py` routing output
    and preserves individual primary, fallback, failure, cooldown, and retry
    records without importing cache v2.
  - The per-video writer lifecycle supports renewal, release, handoff,
    expiry reconciliation, and abandonment while explicitly retaining Drive's
    non-atomic concurrency limitation.
- Implementation commits: `49416da`, `2fd89bd`, `44244aa`.
- Related documents:
  - [`design/gemini-interactive-quota-pool.md`](design/gemini-interactive-quota-pool.md)
  - [`design/youtube-artifact-cache-v3.md`](design/youtube-artifact-cache-v3.md)
  - [`design/youtube-artifact-cache-v3-single-writer-policy.md`](design/youtube-artifact-cache-v3-single-writer-policy.md)

### LEDGER-009 — Correct per-video artifact manifests

- Status: Completed
- Type: Design and implementation
- Layer: Google Drive research storage
- Problem: Drive cache records named by execution-request fingerprints could
  not deterministically enumerate the reusable transcript and analysis
  material associated with one video.
- Goal: Add one predictable per-video manifest in a clean v3 Drive namespace
  that indexes immutable artifacts, compatibility metadata, valid coverage,
  integrity hashes, and analysis task descriptions when required for review,
  without inheriting cache-v2 schemas or lookup behavior. Keep the manifest
  exclusively optimized for artifact discovery, compatibility filtering,
  coverage planning, and integrity verification.
- Initial implementation evidence:
  - [x] Fixed native manifest and artifact schema version `1`.
  - [x] Fixed the no-space `YouTubeArtifactCacheV3` namespace and deterministic
        `<videoId>--manifest.json` lookup.
  - [x] Initially indexed immutable artifacts together with coverage,
        completion, and execution provenance; the completed corrections below
        supersede that rejected boundary.
  - [x] Added native recovery from missing or stale manifests without rewriting
        artifact content.
  - [x] Proved clean-slate operation without cache-v2 data or fixtures.
  - [x] Rejected the optional v2 validator because native offline evidence was
        sufficient.
- Completed corrections:
  - [x] Kept execution provenance outside immutable artifact content and
        artifact identity.
  - [x] Restricted manifest entries to artifact and Drive IDs, artifact kind,
        contract version, timestamp basis, language policy, valid coverage,
        integrity hash, and an analysis task description when review requires
        it.
  - [x] Removed execution references, lifecycle state, attempts, retry data,
        leases, cooldowns, requested execution coverage, truncation history,
        and persisted request gaps from the artifact-discovery manifest.
  - [x] Replaced initial tests that require manifest execution references,
        completion state, truncation history, or stored request gaps with
        search-only manifest contract tests.
  - [x] Updated the manifest only when the searchable artifact set or its
        content-side indexing metadata changes.
  - [x] Rebuilt a missing manifest from existing native artifacts before
        initializing an empty manifest.
  - [x] Reconstructed the manifest from native artifacts without reading or
        rewriting Gemini execution records.
- Initial implementation commits: `7b8a8ef`, `763d4cf`.
- Correction commits: `61a60ef`, `2fd89bd`, `44244aa`.
- Related document:
  [`design/youtube-artifact-cache-v3.md`](design/youtube-artifact-cache-v3.md)

### LEDGER-008 — Correct artifact-first request planning

- Status: Completed
- Type: Design and implementation
- Layer: Research artifact retrieval
- Problem: An exact request fingerprint could prevent a byte-identical API
  call, but it could not determine whether existing artifacts already provided
  usable or composable coverage for the current task.
- Goal: Search by video, artifact kind, compatibility, and interval coverage;
  construct Gemini requests only for uncovered material.
- Verified initial work:
  - [x] Defined exact contract, timestamp-basis, and language-policy
        compatibility with normalized half-open millisecond intervals.
  - [x] Implemented exact, containing, composite, overlapping, truncated,
        incompatible, stale, and missing coverage planning.
  - [x] Returned only uncovered intervals for new request construction.
  - [x] Required explicit agent approval before reusing arbitrary analysis
        artifacts by task description.
  - [x] Kept canonical execution fingerprints as provenance and last-moment
        pending/completed duplicate guards.
  - [x] Kept production v3 retrieval free of cache-v2 imports, fallbacks,
        migration, and legacy fixtures.
- Completed corrections:
  - [x] Planned candidate coverage from the per-video manifest before
        downloading artifact files.
  - [x] Fetched and integrity-checked only selected reuse or analysis-review
        candidates, then replan around stale material.
  - [x] Consulted the separate Gemini execution journal only after artifact
        coverage planning and before credential selection.
  - [x] Re-ran exact, containing, composite, overlapping, truncated,
        incompatible, stale, and missing-coverage tests through the corrected
        two-phase workflow.
- Initial implementation commits: `9bff861`, `763d4cf`.
- Correction commits: `61a60ef`, `2fd89bd`, `44244aa`.
- Related document:
  [`design/youtube-artifact-cache-v3.md`](design/youtube-artifact-cache-v3.md)

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
- Related commits: `caee5b6`, `f7a7289`.

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
    in `caee5b6` changed the prompt and response schema, so branch-tip requests
    have new fingerprints and do not reuse those original trial cache records.
  - Fourteen offline tests pass: three transcript-builder tests and eleven
    existing routing and cache tests.
  - Caption routing, cache v2, Gemini project routing, credential handling,
    chunk planning, and prompt-driven analysis behavior remain unchanged.
- Implementation commits: `d62c964`, `6306991`.

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
