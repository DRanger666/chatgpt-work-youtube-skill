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
  - [ ] Accept only `transcript`, `translation`, `summary`,
        `systematic_visual_description`, and `systematic_onscreen_text` as
        initial reusable output types. Reject arbitrary categories.
  - [ ] Enforce the deliberately asymmetric initial format registry:
        `transcript` uses structured `gemini-transcript` version `1`; the other
        four reusable output types use minimal `gemini-free-form-text` version
        `1`. Reject unregistered formats and incompatible type-format pairs.
  - [ ] Search explicit index fields in that order: controlled output type,
        output-format version, language, timestamp policy, and covered time.
        Use `savedResponseId` only after selection to retrieve and verify the
        chosen file.
  - [ ] Derive transcript covered time mechanically from the checked Gemini
        response and its actual requested clip. Never accept it from a caller.
  - [ ] Exclude `task_specific_observation` and `direct_answer` responses from
        Drive response storage and ordinary material search, regardless of
        prompt similarity.
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
  never-edited saved-response files. Every successful `video_material`
  response is preserved; every eligible one is indexed after its required
  validation or review. The two one-time classes write no response files.
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
        `<videoId>--gemini-response--<outputType>--<savedResponseId>.json`.
  - [ ] Use file-format field names defined in `youtube-saved-work.md`; remove
        the old artifact, manifest, contract, and valid-coverage field names.
  - [ ] Keep request status, attempts, cooldowns, retry reasons, and session
        information out of the video material index. Keep the saved response's
        verified request ID, run number, and exact request hash out of material
        search fields while retaining them in the saved file and its identity.
  - [ ] Save every successful `video_material` response in full, including a
        malformed structured response. Never write a saved-response file for
        a task-specific observation or direct answer.
  - [ ] Copy the requested source time range into each saved response and its
        content metadata. Calculate saved-response identity from every
        immutable saved field, including video ID, request ID, run number,
        exact request hash, safe router result, and response hash, so every
        successful run has one self-identifying response record.
  - [ ] Remove the global `reusable` and `unusableReason` fields. Treat material
        index admission as the reuse decision; do not replace them with general
        `contentCheckStatus` or `contentCheckFailure` fields.
  - [ ] Run a deterministic format checker exactly when the declared output
        format requires it. A free-form format must not receive a fabricated
        check status.
  - [ ] Treat `gemini-free-form-text` version `1` as ordinary generated text
        without a machine-readable response contract. Add no dedicated
        structured format for a reusable output type until observed need
        defines its checker, search effect, and offline tests.
  - [ ] Add only `video_material` to the index. A malformed transcript must
        contribute no covered time even though its response remains saved.
  - [ ] Identify index entries only by `savedResponseId`. Append every new ID
        without replacing entries that share an interval, overlap, or use the
        same output type; treat an identical existing ID as a verified
        idempotent no-op.
  - [ ] Keep transcript, translation, summary, systematic visual description,
        and systematic onscreen text entries together when they describe the
        same source interval.
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
  file recorded for a pending run is the one sent, preserve every authorized
  run and its routing attempts, and stop for the user's decision when an
  earlier run has an uncertain outcome.
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
  - Commit `36b3ae3` still represented status, authorization, and response
    reference as singular request-level fields while allowing authorized
    repeats. A later run could therefore overwrite the history of an earlier
    one.
- Required release work:
  - [ ] Replace `scripts/gemini_execution_journal_v3.py` with
        `scripts/gemini_request_log.py`; do not leave a compatibility wrapper.
  - [ ] Expose run-oriented operations such as `start-run`, `verify-run`,
        `finish-run`, and `mark-run-interrupted`. For run numbers above `1`,
        record authorization and append the pending run in the same update.
  - [ ] Build each logical request entry by reading the actual request file.
        Store its exact prompt, normalized-request hash, video ID, clip,
        endpoint, model, method, and predeclared `contentClass` as immutable
        request-level fields. Require controlled `outputType` and compatible
        `outputFormat` only for `video_material`; forbid both fields for the
        two one-time classes.
  - [ ] Store an ordered `runs` list under that request. Start `runNumber` at
        `1`, increment without gaps, and keep exact request-file hash, times,
        status, routing attempts, cooldown, authorization, and the applicable
        successful outcome fields inside the corresponding run.
  - [ ] Permit at most one pending run per request, require it to be the
        highest-numbered run, and forbid appending another run before it is
        terminal.
  - [ ] Remove separately writable request-level status, authorization,
        cooldown, and saved-response fields. Calculate current status from the
        highest-numbered run and enumerate each successful run's saved-response
        reference or deliberate-non-storage marker when retrieving results.
  - [ ] Make `gemini_request.py` verify the immutable request information,
        exact hash, request ID, run number, and highest pending run before
        loading a credential.
  - [ ] Bind content class and the applicable reusable output fields immutably
        to the logical request entry without adding local classification to
        request identity. Reject conflicting metadata for an existing request
        ID and reject a caller's attempt to replace it after the call.
  - [ ] Let a purpose-specific builder fix an unambiguous class, including
        `video_material` for transcript mode. Require the generic prompt route
        to declare its class explicitly; do not supply a silent default. For
        `video_material`, require one controlled reusable output type and its
        compatible format.
  - [ ] Use `fileFormatVersion` and the plain request-log field names in the
        request log, routing metadata, and local bucket-state file; update the
        operational documents and tests in the same implementation commit.
  - [ ] Persist every safe primary, fallback, transient, failed, and successful
        routing attempt inside the run that made it. Bind routing output to
        both request ID and run number.
  - [ ] Keep bounded router retries and credential failover inside one run.
        Every later deliberate execution must append another run with one new,
        consumed user authorization; never overwrite an earlier run.
  - [ ] Enforce saved cooldowns and reject unchanged terminal request errors.
  - [ ] Require a complete saved-response reference before marking a
        `video_material` run `succeeded`, including a failed-format response.
        For a task-specific observation or direct answer, require `finish-run`
        to verify the actual successful router result and response-file hash,
        copy routing attempts and terminal time, generate
        `responseNotSavedByPolicy: true`, and forbid saved-response fields.
        Never accept that Boolean, status, attempts, or completion time from
        the caller.
  - [ ] Require the response-saving command to verify the router result's
        request ID, run number, and exact request hash against the pending run,
        recompute SHA-256 over the exact response-file bytes, require equality
        with the router result's `responseSha256`, then write that binding and
        the complete safe router result into the saved response.
  - [ ] When a later session finds one exact verified saved response for a
        pending run, require user confirmation that the earlier session has
        stopped and finish that existing run without another Gemini call. Use
        the retained router result to restore every attempt and its terminal
        attempt time for `endedAt`.
  - [ ] Number router attempts from `1` without gaps and require each successful
        router result to contain the run's complete ordered attempt history.
        Existing pending-run attempts must match an exact prefix; append only
        the missing suffix and reject conflicts, duplicates, gaps, reordering,
        extra stored attempts, or a non-final terminal attempt.
  - [ ] Never finish a pending run from an unlinked response. Stop for
        investigation when multiple responses claim one run or any binding or
        integrity check fails.
  - [ ] Use only `pending`, `succeeded`, `failed`, and `interrupted` run states.
        Keep `endedAt` null while pending and require it for a terminal run. An
        old pending run must stop and ask the user; elapsed time alone must not
        authorize another call.
  - [ ] Remove writer, lease, renewal, release, handoff, takeover, and automatic
        reconciliation commands and tests.
  - [ ] State the supported same-video rule plainly: do not intentionally use
        two write-capable sessions for one video; Drive cannot guarantee a
        lock between truly simultaneous sessions.
  - [ ] Add offline tests for request-file mismatch, all duplicate states,
        explicit retry reasons, cooldowns, interrupted-run decisions,
        routing consistency, immutable pre-call classification, relabelling
        that cannot bypass duplicate prevention, exact prompt retention,
        controlled output-type rejection, deliberate non-storage markers,
        bare-marker rejection, one-time failed and mismatched router-result
        rejection, one-time response-byte verification, copied one-time attempt
        history and terminal time, monotonic run numbering, multiple successful
        reusable response references, saved-response back-links,
        interrupted-write completion without a new network call, response-byte
        hash mismatch, attempt-prefix reconciliation, unlinked and conflicting
        response rejection, append-only terminal history, derived current
        status, and absence of credentials in saved files.
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
