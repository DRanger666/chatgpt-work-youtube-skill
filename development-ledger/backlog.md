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

## Active Gemini-response and video-material release corrections

The earlier implementation remains useful evidence, but its public names and
its automatic crash-handling design are not the release specification. The
three reopened items below are governed by
[`design/youtube-saved-work.md`](design/youtube-saved-work.md).

### LEDGER-008 — Find and reuse video material before Gemini

- Status: Reopened — release blocker
- Type: Design correction and implementation
- Layer: Video-material search and request planning
- Problem: A request-file hash can identify an earlier Gemini request, but it
  cannot answer whether reusable transcripts or other source material already
  satisfy the user's present need.
- Goal: Search the video material index by video ID, output type, output
  format, language, timestamp policy, and verified covered time. Construct a
  Gemini request only for material or visual evidence that remains missing.
- Evidence retained from the earlier implementation:
  - Exact, containing, combined, overlapping, incomplete, incompatible, stale,
    and missing time-range planning worked offline.
  - Selected-file-only downloading and replanning after stale files worked.
  - Commits `9bff861`, `763d4cf`, `61a60ef`, `2fd89bd`, and `44244aa` preserve
    that history.
- Why it remains open:
  - Checkpoint `b8598e4` allowed caller-supplied transcript time ranges without
    checking the returned transcript.
  - The old public interface still describes saved work as artifacts and the
    per-video list as a manifest.
- Required release work:
  - [ ] Replace `scripts/artifact_cache_v3.py` with
        `scripts/saved_gemini_responses.py`; do not leave a compatibility
        wrapper.
  - [ ] Plan from `<videoId>--video-material-index.json`, then download and
        verify only the selected saved-response files.
  - [ ] Derive transcript covered time mechanically from the checked Gemini
        response and its actual requested clip. Never accept it from a caller.
  - [ ] Exclude `task_specific_observation` and `direct_answer` responses from
        ordinary material search, regardless of prompt similarity.
  - [ ] When reusable material leaves a visual-sensory gap, request a narrowly
        scoped `task_specific_observation` and let ChatGPT reason over it.
  - [ ] Return only missing time ranges for new request construction.
  - [ ] Re-run the full material-search matrix, including malformed,
        incomplete, mismatched-clip, excluded-class, and systematic-OCR
        responses.

### LEDGER-009 — Maintain a video material index and saved Gemini responses

- Status: Reopened — release blocker
- Type: Design correction and implementation
- Layer: Google Drive response and material files
- Problem: Request-hash filenames cannot enumerate useful work for one video,
  while the earlier replacement used generic file names and split information
  in a way that made its promised index rebuilding unreliable.
- Goal: Keep one predictable per-video material index and separate,
  never-edited saved-response files. Every successful response is preserved,
  while only predeclared `video_material` may enter ordinary search.
- Evidence retained from the earlier implementation:
  - Per-video lookup, separate output files, file-integrity checking, and index
    rebuilding worked offline under the earlier names.
  - Commits `7b8a8ef`, `763d4cf`, `61a60ef`, `2fd89bd`, and `44244aa` preserve
    that history.
- Why it remains open:
  - Checkpoint `b8598e4` could index malformed transcript content as complete.
  - Commit `f65a965` correctly separated saved-work search from Gemini request
    history, but its stronger crash-reconstruction rules are no longer part of
    the governing design.
- Required release work:
  - [ ] Use the `YouTubeVideoWork` Drive folder,
        `<videoId>--video-material-index.json`, and
        `<videoId>--gemini-response--<savedResponseId>.json`.
  - [ ] Use file-format field names defined in `youtube-saved-work.md`; remove
        the old artifact, manifest, contract, and valid-coverage field names.
  - [ ] Keep request status, attempts, cooldowns, retry reasons, and session
        information out of the video material index, saved-response file, and
        saved-response identity.
  - [ ] Save every successful Gemini response in full, including a malformed
        structured response and every task-specific observation or direct
        answer.
  - [ ] Copy the requested source time range into each saved response and its
        identity so identical text from different video intervals cannot
        collapse into one record.
  - [ ] Remove the global `reusable` and `unusableReason` fields. Treat material
        index admission as the reuse decision; do not replace them with general
        `contentCheckStatus` or `contentCheckFailure` fields.
  - [ ] Run a deterministic format checker exactly when the declared output
        format requires it. A free-form format must not receive a fabricated
        check status.
  - [ ] Add only `video_material` to the index. A malformed transcript must
        contribute no covered time even though its response remains saved.
  - [ ] Rebuild a missing index from saved responses whose predeclared class is
        `video_material`. Do not create an empty index until response
        enumeration confirms that no qualifying file can be admitted.
  - [ ] Keep normal operation completely separate from cache-v2 files; add no
        migration, fallback, validator, or permanent compatibility path.

### LEDGER-010 — Log Gemini requests and prevent blind repetition

- Status: Reopened — release blocker
- Type: Design correction and implementation
- Layer: Gemini requests and persistent request history
- Problem: The first cache-v3 implementation discarded request-attempt and
  retry safeguards from LEDGER-004. The later repair restored them but added
  session ownership, expiry, handoff, and automatic crash-handling machinery
  that the interactive workflow does not justify.
- Goal: Keep a plain per-video Gemini request log. Verify that the exact request
  file recorded as pending is the one sent, preserve routing attempts and
  cooldowns, and stop for the user's decision when an earlier request has an
  uncertain outcome.
- Evidence:
  - Commit `763d4cf` stopped consuming `ROUTING_JSON` and removed documented
    retry authorization and attempt preservation.
  - Audit checkpoint `b8598e4` proved that the recorded request could differ
    from the file and endpoint sent to the router. It also exposed missing
    cooldown enforcement and contradictory request history.
  - Commits `49416da`, `2fd89bd`, and `44244aa` contain useful attempt-log and
    routing-validation work, but their writer-management interface is rejected.
  - Commit `f65a965` is a diagnostic checkpoint, not the implementation
    specification.
- Required release work:
  - [ ] Replace `scripts/gemini_execution_journal_v3.py` with
        `scripts/gemini_request_log.py`; do not leave a compatibility wrapper.
  - [ ] Build each pending entry by reading the actual request file. Store its
        exact prompt, exact-file hash, normalized-request hash, video ID, clip,
        endpoint, model, method, predeclared `contentClass`, `outputType`, and
        `outputFormat`.
  - [ ] Make `gemini_request.py` verify that same information and the pending
        request status before loading a credential.
  - [ ] Bind content class, output type, and output format immutably to the
        pending entry without adding local classification to request identity.
        Reject conflicting metadata for an existing request ID and reject a
        caller's attempt to replace it after the call.
  - [ ] Let a purpose-specific builder fix an unambiguous class, including
        `video_material` for transcript mode. Require the generic prompt route
        to declare its class explicitly; do not supply a silent default.
  - [ ] Use `fileFormatVersion` and the plain request-log field names in the
        request log, routing metadata, and local bucket-state file; update the
        operational documents and tests in the same implementation commit.
  - [ ] Persist every safe primary, fallback, transient, failed, and successful
        routing attempt. Preserve earlier attempts through an authorized retry.
  - [ ] Enforce saved cooldowns and reject unchanged terminal request errors.
  - [ ] Require a saved-response reference before marking any successful
        request `succeeded`, including a failed-format response,
        task-specific observation, or direct answer. Retain its Drive file ID
        and file SHA-256 so non-indexed responses remain directly retrievable
        and verifiable.
  - [ ] Use only `pending`, `succeeded`, `failed`, and `interrupted` request
        states. An old pending request must stop and ask the user; elapsed time
        alone must not authorize another call.
  - [ ] Remove writer, lease, renewal, release, handoff, takeover, and automatic
        reconciliation commands and tests.
  - [ ] State the supported same-video rule plainly: do not intentionally use
        two write-capable sessions for one video; Drive cannot guarantee a
        lock between truly simultaneous sessions.
  - [ ] Add offline tests for request-file mismatch, all duplicate states,
        explicit retry reasons, cooldowns, interrupted-request decisions,
        routing consistency, immutable pre-call classification, relabelling
        that cannot bypass duplicate prevention, exact prompt retention, and
        absence of credentials in saved files.
- Related documents:
  - [`design/youtube-saved-work.md`](design/youtube-saved-work.md)
  - [`design/gemini-interactive-quota-pool.md`](design/gemini-interactive-quota-pool.md)

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
