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

### LEDGER-011 — Remove cache-v2 Drive data after representative v3 validation

- Status: Planned
- Type: Maintenance
- Layer: Google Drive saved data
- Evidence: Cache v3 is deliberately isolated from cache v2, and the older
  files have little current value, but deleting them during implementation
  would mix cleanup with validation of the replacement.
- Next check:
  - [ ] Run separately authorized representative live v3 trials.
  - [ ] Confirm that the new saved responses, material indexes, and request
        logs can be found and reused from a fresh Work session.
  - [ ] Inventory the exact cache-v2 Drive files without modifying them.
  - [ ] After the user approves that inventory, delete only those v2 files and
        verify that `YouTubeVideoWork` remains unchanged.
- Related document:
  [`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md)

### LEDGER-014 — Remove redundant timestamp-coordinate metadata

- Status: Completed
- Type: Design correction and implementation
- Layer: Gemini request metadata, response storage, material indexing, and
  search
- Evidence:
  - The first cache-v3 storage implementation accepted only video-start
    timestamps. A later negative search test used `clip_relative` only to prove
    that a different value would not match stored material; the system never
    implemented creation or conversion of that alternate coordinate.
  - The saved-material rewrite renamed the field to `timestampsRelativeTo` and
    allowed arbitrary non-empty values for generic reusable output, even though
    no supported workflow or output format defined another interpretation.
  - `sourceTimeRange` and `coveredTimeRanges` already express which partial
    interval was processed and retained. The extra field does not enable
    focused processing or partial reuse.
- Decision:
  - Define every millisecond time range as an offset from the beginning of the
    YouTube video.
  - Define `gemini-transcript` version `1` timestamp strings as offsets from the
    beginning of the same video.
  - Remove `timestampsRelativeTo`, `timestampBasis`,
    `TIMESTAMPS_FULL_VIDEO`, `--timestamps-relative-to`, and any renamed
    replacement. Do not preserve the mistake as a constant-valued field.
  - Save and index any checked partial interval immediately; processing the
    rest of the video is not a prerequisite.
  - Keep `languagePolicy` as a genuine material-search condition. This
    correction must not remove or weaken it.
- Required implementation:
  - [x] Correct the governing storage/search design before runtime work begins.
  - [x] Remove timestamp-coordinate metadata from the request-log fields,
        request construction APIs, CLI, validation, and immutable-metadata
        comparisons.
  - [x] Remove it from saved responses, saved-response identity, material-index
        entries, index rebuilding, material queries, filtering, returned search
        data, missing-range output, and chunk output.
  - [x] Make the transcript format contract and checker own the video-start
        timestamp rule without storing a separate coordinate label.
  - [x] Update `SKILL.md`, `references/contracts.md`, and active examples.
        Preserve completed historical ledger records.
  - [x] Add offline tests that save and reuse a focused nonzero interval, reject
        every removed field at public file and command boundaries, and prove
        that transcript checking still compares returned timestamps with the
        absolute requested interval.
  - [x] Run the complete offline suite and package validation without Gemini
        calls or live Drive writes.
- Outcome:
  - Commit `a0bde4d` removed the redundant metadata from runtime schemas,
    identities, APIs, commands, saved material, search, and tests.
  - Every numerical range now has one video-start interpretation, while
    `gemini-transcript` version `1` owns its corresponding textual timestamp
    contract.
  - Focused nonzero intervals remain immediately saveable and reusable, and
    `languagePolicy` remains a material-search condition.
  - All 81 offline tests and skill-package validation passed without Gemini or
    Drive mutation.
- Completion rule: Close this item only when the removed identifiers no longer
  occur in runtime code, current contracts, active examples, or tests; their
  appearance inside preserved historical evidence does not count as active
  support.
- Related document:
  [`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md)

## Completed refinements

### LEDGER-013 — Clarify documentation ownership and restore long-video planning

- Status: Completed
- Type: Refinement and regression correction
- Layer: Repository documentation and Gemini request planning
- Evidence:
  - `youtube-saved-work.md` combined whole-system routing, saved-response
    search, and request-history design under a misleading name.
  - `gemini-interactive-quota-pool.md` duplicated request-log rules.
  - Replacing the earlier cache implementation removed the deterministic
    `plan-chunks` command even though the runtime guidance still relied on it.
  - A real 2-hour-15-minute whole-video request failed while its
    `0s`–`1800s` clip succeeded, so bounded long-video planning remains an
    evidence-backed operating requirement.
- Outcome:
  - Added `REPOSITORY_MAP.md` with concern-specific ownership and a complete
    maintained-file map.
  - Split saved Gemini response storage/search from Gemini request execution;
    merged primary/fallback quota routing into the latter and removed the two
    misleading broad documents.
  - Kept `SKILL.md` as the sole runtime source-order authority: MCP material
    first, saved Gemini material second, and a new Gemini request only for the
    remaining gap.
  - Restored deterministic splitting of verified missing ranges, with the
    tested 1,800-second general default and the 600-second/four-second-overlap
    transcript policy preserved as distinct operating choices.
  - Preserved historical ledger entries instead of rewriting them around the
    new structure.
- Related documents:
  - [`../REPOSITORY_MAP.md`](../REPOSITORY_MAP.md)
  - [`../SKILL.md`](../SKILL.md)
  - [`../references/contracts.md`](../references/contracts.md)
  - [`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md)
  - [`design/gemini-request-execution.md`](design/gemini-request-execution.md)

### LEDGER-012 — Derive translations instead of storing them

- Status: Completed
- Type: Refinement
- Layer: Reusable video material
- Evidence: Translation can be produced on demand by ChatGPT from saved
  original-language transcripts or systematic onscreen text. Saving and
  searching a separate Gemini translation duplicates derived material without
  recovering information that ChatGPT otherwise lacks.
- Outcome:
  - Removed `translation` from the controlled reusable-output registry before
    any live v3 use.
  - Rejected translation in request logging, response saving, material-index
    admission, and search through the shared controlled registry.
  - Retained on-demand translation as a ChatGPT consumption step over saved
    source-language material.
- Related document:
  [`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md)

## Completed Gemini-response and video-material release corrections

The earlier implementation remains useful evidence, but its public names and
its automatic crash-handling design are not the release specification.
LEDGER-008 and LEDGER-009 are governed by
[`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md);
LEDGER-010 is governed by
[`design/gemini-request-execution.md`](design/gemini-request-execution.md).

### LEDGER-008 — Find and reuse video material before Gemini

- Status: Completed
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
  - Commits `cec862d`, `1e72955`, `da14941`, `bee56d7`, and `0c7a74d` preserve
    that history.
- Correction resolved:
  - Checkpoint `a9ab341` allowed caller-supplied transcript time ranges without
    checking the returned transcript.
  - The old public interface described saved work as artifacts and the
    per-video list as a manifest; the replacement now uses concrete filenames
    and video-material terms.
- Completed release work:
  - [x] Replaced `scripts/artifact_cache_v3.py` with
        `scripts/saved_gemini_responses.py`; do not leave a compatibility
        wrapper.
  - [x] Plan from `<videoId>--video-material-index.json`, then download and
        verify only the selected saved-response files.
  - [x] Accept only `transcript`, `translation`, `summary`,
        `systematic_visual_description`, and `systematic_onscreen_text` as
        initial reusable output types. Reject arbitrary categories.
  - [x] Enforce the deliberately asymmetric initial format registry:
        `transcript` uses structured `gemini-transcript` version `1`; the other
        four reusable output types use minimal `gemini-free-form-text` version
        `1`. Reject unregistered formats and incompatible type-format pairs.
  - [x] Search explicit index fields in that order: controlled output type,
        output-format version, language, timestamp policy, and covered time.
        Use `savedResponseId` only after selection to retrieve and verify the
        chosen file.
  - [x] Derive transcript covered time mechanically from the checked Gemini
        response and its actual requested clip. Never accept it from a caller.
  - [x] Exclude `task_specific_observation` and `direct_answer` responses from
        Drive response storage and ordinary material search, regardless of
        prompt similarity.
  - [x] When reusable material leaves a visual-sensory gap, request a narrowly
        scoped `task_specific_observation` and let ChatGPT reason over it.
  - [x] Return only missing time ranges for new request construction.
  - [x] Re-ran the full material-search matrix, including malformed,
        incomplete, mismatched-clip, excluded-class, and systematic-OCR
        responses.
- Outcome:
  - `scripts/saved_gemini_responses.py` plans from readable index fields and
    verifies only selected response files before exposing missing ranges.
  - The actual planner matches interval-union results across 5,500
    deterministic randomized cases under each validation seed.
  - Implementation commits: `35b95bb`, `aaeb9c5`, and `69a0e8b`.

### LEDGER-009 — Maintain a video material index and saved Gemini responses

- Status: Completed
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
  - Commits `904c14e`, `1e72955`, `da14941`, `bee56d7`, and `0c7a74d` preserve
    that history.
- Correction resolved:
  - Checkpoint `a9ab341` could index malformed transcript content as complete.
  - Commit `186c9d2` correctly separated saved-work search from Gemini request
    history, but its stronger crash-reconstruction rules are no longer part of
    the governing design.
- Completed release work:
  - [x] Use the `YouTubeVideoWork` Drive folder,
        `<videoId>--video-material-index.json`, and
        `<videoId>--gemini-response--<outputType>--<savedResponseId>.json`.
  - [x] Use file-format field names defined in `youtube-saved-work.md`; remove
        the old artifact, manifest, contract, and valid-coverage field names.
  - [x] Keep request status, attempts, cooldowns, retry reasons, and session
        information out of the video material index. Keep the saved response's
        verified request ID, run number, and exact request hash out of material
        search fields while retaining them in the saved file and its identity.
  - [x] Save every successful `video_material` response in full, including a
        malformed structured response. Never write a saved-response file for
        a task-specific observation or direct answer.
  - [x] Copy the requested source time range into each saved response and its
        content metadata. Calculate saved-response identity from every
        immutable saved field, including video ID, request ID, run number,
        exact request hash, safe router result, and response hash, so every
        successful run has one self-identifying response record.
  - [x] Remove the global `reusable` and `unusableReason` fields. Treat material
        index admission as the reuse decision; do not replace them with general
        `contentCheckStatus` or `contentCheckFailure` fields.
  - [x] Run a deterministic format checker exactly when the declared output
        format requires it. A free-form format must not receive a fabricated
        check status.
  - [x] Treat `gemini-free-form-text` version `1` as ordinary generated text
        without a machine-readable response contract. Add no dedicated
        structured format for a reusable output type until observed need
        defines its checker, search effect, and offline tests.
  - [x] Add only `video_material` to the index. A malformed transcript must
        contribute no covered time even though its response remains saved.
  - [x] Identify index entries only by `savedResponseId`. Append every new ID
        without replacing entries that share an interval, overlap, or use the
        same output type; treat an identical existing ID as a verified
        idempotent no-op.
  - [x] Keep transcript, translation, summary, systematic visual description,
        and systematic onscreen text entries together when they describe the
        same source interval.
  - [x] Rebuild a missing index from saved responses whose predeclared class is
        `video_material`. Do not create an empty index until response
        enumeration confirms that no qualifying file can be admitted.
  - [x] Keep normal operation completely separate from cache-v2 files; add no
        migration, fallback, validator, or permanent compatibility path.
- Outcome:
  - Saved responses are immutable and self-identifying; the material index is
    search-only and can be rebuilt from eligible saved files and explicit
    free-form review decisions.
  - Failed structured responses and rejected free-form responses remain saved
    but do not create false coverage.
  - Implementation commits: `35b95bb` and `69a0e8b`.

### LEDGER-010 — Log Gemini requests and prevent blind repetition

- Status: Completed
- Type: Design correction and implementation
- Layer: Gemini requests and persistent request history
- Problem: The first cache-v3 implementation discarded request-attempt and
  retry safeguards from LEDGER-004. The later repair restored them but added
  session ownership, expiry, handoff, and automatic crash-handling machinery
  that the interactive workflow does not justify.
- Goal: Keep a plain per-video Gemini request log. Verify that the exact request
  file recorded for a pending run is the one sent, preserve every authorized
  run and every safe routing attempt returned to the active workflow, and stop
  for the user's decision when an earlier run has an uncertain outcome.
- Evidence:
  - Commit `1e72955` stopped consuming `ROUTING_JSON` and removed documented
    retry authorization and attempt preservation.
  - Audit checkpoint `a9ab341` proved that the recorded request could differ
    from the file and endpoint sent to the router. It also exposed missing
    cooldown enforcement and contradictory request history.
  - Commits `d13127f`, `bee56d7`, and `0c7a74d` contain useful attempt-log and
    routing-validation work, but their writer-management interface is rejected.
  - Commit `186c9d2` is a diagnostic checkpoint, not the implementation
    specification.
  - Commit `3744de4` still represented status, authorization, and response
    reference as singular request-level fields while allowing authorized
    repeats. A later run could therefore overwrite the history of an earlier
    one.
- Completed release work:
  - [x] Replaced `scripts/gemini_execution_journal_v3.py` with
        `scripts/gemini_request_log.py`; do not leave a compatibility wrapper.
  - [x] Expose run-oriented operations such as `start-run`, `verify-run`,
        `finish-run`, and `mark-run-interrupted`. For run numbers above `1`,
        record authorization and append the pending run in the same update.
  - [x] Build each logical request entry by reading the actual request file.
        Store its exact prompt, normalized-request hash, video ID, clip,
        endpoint, model, method, and predeclared `contentClass` as immutable
        request-level fields. Require controlled `outputType` and compatible
        `outputFormat` only for `video_material`; forbid both fields for the
        two one-time classes.
  - [x] Store an ordered `runs` list under that request. Start `runNumber` at
        `1`, increment without gaps, and keep exact request-file hash, times,
        status, routing attempts, cooldown, authorization, and the applicable
        successful outcome fields inside the corresponding run.
  - [x] Permit at most one pending run per request, require it to be the
        highest-numbered run, and forbid appending another run before it is
        terminal.
  - [x] Remove separately writable request-level status, authorization,
        cooldown, and saved-response fields. Calculate current status from the
        highest-numbered run and enumerate each successful run's saved-response
        reference or deliberate-non-storage marker when retrieving results.
  - [x] Make `gemini_request.py` verify the immutable request information,
        exact hash, request ID, run number, and highest pending run before
        loading a credential.
  - [x] Bind content class and the applicable reusable output fields immutably
        to the logical request entry without adding local classification to
        request identity. Reject conflicting metadata for an existing request
        ID and reject a caller's attempt to replace it after the call.
  - [x] Let a purpose-specific builder fix an unambiguous class, including
        `video_material` for transcript mode. Require the generic prompt route
        to declare its class explicitly; do not supply a silent default. For
        `video_material`, require one controlled reusable output type and its
        compatible format.
  - [x] Use `fileFormatVersion` and the plain request-log field names in the
        request log, routing metadata, and local bucket-state file; update the
        operational documents and tests in the same implementation commit.
  - [x] Persist every safe primary, fallback, transient, failed, and successful
        routing attempt returned to the active workflow inside the run that
        made it. Bind routing output to both request ID and run number. If an
        invocation ends before a terminal safe router result is retained,
        leave the run pending with an unknown network outcome; never fabricate
        missing attempts or infer success or failure.
  - [x] Keep bounded router retries and credential failover inside one run.
        Every later deliberate execution must append another run with one new,
        consumed user authorization; never overwrite an earlier run.
  - [x] Enforce saved cooldowns and reject unchanged terminal request errors.
  - [x] Require a complete saved-response reference before marking a
        `video_material` run `succeeded`, including a failed-format response.
        For a task-specific observation or direct answer, require `finish-run`
        to verify the actual successful router result and response-file hash,
        copy routing attempts and terminal time, generate
        `responseNotSavedByPolicy: true`, and forbid saved-response fields.
        Never accept that Boolean, status, attempts, or completion time from
        the caller.
  - [x] Require the response-saving command to verify the router result's
        request ID, run number, and exact request hash against the pending run,
        recompute SHA-256 over the exact response-file bytes, require equality
        with the router result's `responseSha256`, then write that binding and
        the complete safe router result into the saved response.
  - [x] When a later session finds one exact verified saved response for a
        pending run, require user confirmation that the earlier session has
        stopped and finish that existing run without another Gemini call. Use
        the retained router result to restore every attempt contained in that
        result and its terminal attempt time for `endedAt`.
  - [x] Number router attempts from `1` without gaps and require each successful
        router result to contain the run's complete ordered attempt history.
        Existing pending-run attempts must match an exact prefix; append only
        the missing suffix and reject conflicts, duplicates, gaps, reordering,
        extra stored attempts, or a non-final terminal attempt.
  - [x] Never finish a pending run from an unlinked response. Stop for
        investigation when multiple responses claim one run or any binding or
        integrity check fails.
  - [x] Use only `pending`, `succeeded`, `failed`, and `interrupted` run states.
        Keep `endedAt` null while pending and require it for a terminal run. An
        old pending run must stop and ask the user; elapsed time alone must not
        authorize another call.
  - [x] Remove writer, lease, renewal, release, handoff, takeover, and automatic
        reconciliation commands and tests.
  - [x] State the supported same-video rule plainly: do not intentionally use
        two write-capable sessions for one video; Drive cannot guarantee a
        lock between truly simultaneous sessions.
  - [x] Added offline tests for request-file mismatch, all duplicate states,
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
        response rejection, router interruption with an unknown network outcome
        and no invented attempt, append-only terminal history, derived current
        status, and absence of credentials in saved files.
- Outcome:
  - The router verifies the exact highest pending request before credential
    loading and validates every result before writing it.
  - Numbered authorized runs retain distinct outcomes, safe routing attempts,
    cooldowns, exact response bindings, and user-mediated interruption
    decisions without session-ownership machinery.
  - Implementation commits: `5ccbe33`, `35b95bb`, `a3bb2bd`, and `aaeb9c5`.
- Related documents:
  - [`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md)
  - [`design/gemini-request-execution.md`](design/gemini-request-execution.md)

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
  [`design/gemini-request-execution.md`](design/gemini-request-execution.md)

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
  [`design/gemini-request-execution.md`](design/gemini-request-execution.md)
