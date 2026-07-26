# YouTube artifact cache v3

## Contents

- [Status](#status)
- [Problem and clean-slate boundary](#problem)
- [Retained Gemini requirements](#gemini-execution-requirements-retained-from-ledger-004)
- [Persistent data structures](#persistent-data-structure-boundary)
- [Artifact-first retrieval](#design-a--artifact-first-retrieval-and-coverage-planning)
- [Manifest and artifact storage](#design-b--per-video-manifest-and-artifact-storage)
- [Bound execution and durable results](#design-c--bound-gemini-execution-and-durable-result)
- [Implementation and tests](#implementation-decisions)
- [Non-goals](#non-goals)

## Status

Approved clean-slate architecture with a second release correction specified
and implementation pending. Preserve the audited feature-branch tip
`b8598e4` as the pre-correction checkpoint. Do not merge the branch or create
live v3 data until request binding, durable result storage, transcript
validation, and journal-state invariants satisfy this design together.

## Problem

Cache v2 hashes the exact request-file bytes and uses that fingerprint as the
primary lookup key. This reliably identifies one execution request, but it
conflates three separate problems:

1. discovering previously generated material that may satisfy the current
   task;
2. verifying the integrity of a stored transcript or analysis artifact; and
3. preventing an identical Gemini API execution from being repeated.

Prompt formulation, JSON formatting, URL form, token settings, or a schema
correction can change a request fingerprint even when an existing artifact
remains useful. Cache v2 therefore prevents byte-identical repetition but
cannot reliably answer whether the system already possesses sufficient
research material.

The cache-v3 principle is:

> Search by what an artifact represents and covers; audit by how it was
> produced.

## Clean-slate boundary

Design cache v3 independently of cache v2:

- Use a separate no-space Drive namespace for native v3 manifests and
  artifacts.
- Start the new manifest and artifact contracts at their own schema version
  `1`; “v3” names the system generation, not an inherited record schema.
- Do not add v2 fields, filename rules, lookup fallbacks, migration markers, or
  compatibility branches to normal v3 code.
- Do not search v2 when a v3 manifest is absent.
- Do not require v2 data or fixtures for native v3 tests.
- Regenerate the small amount of useful prior material natively in v3 when
  that is simpler or safer than preserving compatibility.

Cache-v2 records may remain temporarily as read-only validation evidence. They
impose no requirements on v3 schemas, filenames, artifact lookup, migration,
fallback, or native record representation.

This clean-slate boundary does not cancel the Gemini execution requirements
established by LEDGER-004. Those requirements govern whether and how Gemini may
be called; they remain necessary even though their first implementation shared
the cache-v2 request record.

## Gemini execution requirements retained from LEDGER-004

The v3 workflow must retain these exact Gemini requirements:

1. Complete artifact discovery before selecting a Gemini credential.
2. Keep at most one Gemini video request in flight within a workflow.
3. Consume the safe routing metadata emitted by `gemini_request.py`.
4. Persist every Gemini network attempt returned in terminal router metadata,
   including bucket alias, timestamps, HTTP status, classification, error
   status, retry delay, cooldown, and backoff when present. If a process or VM
   disappears before terminal metadata becomes durable, preserve the pending
   execution as an unknown network outcome rather than inventing attempt
   details or treating it as a confirmed failure.
5. Preserve prior attempt history across primary/fallback routing and every
   later retry.
6. Permit an identical failed Gemini request to run again only when a
   documented retry reason is supplied.
7. Do not retry `INVALID_ARGUMENT` or another terminal request failure
   unchanged.
8. Persist the failed attempt history and earliest cooldown when no Gemini
   project bucket is available.
9. Finalize every pending Gemini execution as completed or failed using the
   router metadata; do not replace detailed attempt history with only a
   logical status.

These are Gemini execution requirements, not cache-v2 compatibility
requirements. Cache v3 must implement them through native v3 records without
importing or calling `gemini_cache.py`.

## Persistent data-structure boundary

Cache v3 uses four persisted data structures with non-overlapping ownership:

| Data structure | Owns | Must not own |
|---|---|---|
| Immutable execution-result record | The exact safe Gemini response bytes and their integrity identity | Artifact compatibility, reusable coverage, manifest indexing, writer lifecycle, routing history, or credentials |
| Immutable artifact record | Reusable generated material and the content-side metadata required to identify, interpret, and validate that material | Gemini execution IDs, lifecycle, attempts, routing, retries, leases, cooldowns, or provenance references |
| Per-video artifact manifest | The minimal index needed to locate artifacts and plan compatible, integrity-checked coverage | Gemini execution lifecycle, history, routing, retry, concurrency, result-record, or provenance data |
| Gemini execution journal | Bound request identity, requested work, lifecycle, routing attempts, retry authorization, reconciliation, and one-way references to its durable result and any produced artifact IDs | Artifact discovery or coverage-search responsibilities |

Do not duplicate execution or result fields in either the immutable artifact
or the per-video manifest for convenience. A successful network result does
not become a reusable artifact merely because it was persisted. If execution
history or result evidence changes without creating a validated reusable
artifact, neither artifact-side data structure changes.

## Design A — Artifact-first retrieval and coverage planning

Before constructing a Gemini request:

1. Normalize the YouTube URL to a video ID.
2. Load the artifact index for that video.
3. Select candidates by artifact kind, such as transcript, translation,
   visual analysis, or question-specific analysis.
4. Filter candidates by compatible contract version, timestamp basis, and
   language policy, then use only their recorded valid coverage.
5. Compute the union of their valid coverage intervals.
6. Identify incompatible material and uncovered gaps.
7. Reuse complete or composable artifacts and generate only the missing
   intervals.
8. Build and validate one bound execution from the exact request file and
   endpoint that the router will receive.
9. Immediately before credential selection, consult and reserve the durable
   Gemini execution journal using that bound execution fingerprint.

An exact interval is not a transcript identity. A transcript covering
`0–1800s` can satisfy a request for `300–900s`, and multiple overlapping chunks
can jointly satisfy a larger interval.

Execution fingerprints identify canonical execution specifications for audit
and duplicate-call prevention. They do not drive the initial artifact search
or identify reusable artifacts.

### Acceptance cases

- One artifact exactly covers the requested interval.
- A larger compatible artifact contains the requested interval.
- Multiple compatible chunks jointly cover the requested interval.
- Overlapping chunks compose without turning the overlap into a gap.
- An artifact produced from a truncated result contributes only its confirmed
  valid coverage.
- Incompatible contracts or language policies are not silently reused.
- Only uncovered intervals produce new Gemini requests.
- The router refuses any request file or endpoint that differs from the
  reserved pending execution.
- An identical pending or completed execution is not submitted twice.
- An identical failed execution is not submitted again without a documented
  permitted retry reason.

## Design B — Per-video manifest and artifact storage

Google Drive is persistent storage, not a query database. Use one predictable
manifest per video:

```text
<videoId>--manifest.json
```

Treat the manifest exclusively as the mutable artifact-discovery index. Keep
transcript chunks and other generated artifacts as separate immutable records
so they can be verified and reused independently. The manifest is not a Gemini
execution record, execution-history store, or provenance index.

Apart from the manifest format version and video ID needed to identify and
interpret the index, each manifest entry must contain only:

- artifact ID and Drive file ID;
- artifact kind and contract version;
- timestamp basis and language policy;
- valid coverage intervals;
- integrity hash of the stored artifact; and
- human-readable task description when an analysis artifact requires agent
  review.

Do not put any of the following in the manifest:

- an executions array, execution IDs, execution fingerprints, or execution
  provenance references;
- execution-result IDs, response bodies, or result-record Drive references;
- pending, completed, failed, abandoned, or retry lifecycle state;
- network attempts, retry reasons, leases, cooldowns, or credential-bucket
  routing;
- requested execution coverage; or
- truncation history or request gaps that can be derived by comparing the
  current requested interval with indexed valid coverage.

A validated artifact produced from a truncated Gemini response contributes
only the coverage derived by its contract adapter. The immutable execution
result remains durable even when validation produces no reusable artifact.
The manifest does not preserve the truncation event or index an invalid
result. Gap planning is a query-time calculation from the current requested
interval and the union of compatible valid coverage; gaps are not persisted as
manifest state.

Modify a manifest only when the searchable artifact set or its indexing
metadata changes: for example, when adding a verified artifact, removing an
invalid entry, repairing a Drive file reference, or correcting compatibility,
coverage, or integrity metadata. A Gemini attempt, fallback, failure, retry,
abandonment, cooldown, or completion that produces no new searchable artifact
must leave the manifest unchanged.

Never store credentials, authorization material, credential fragments, or
credential fingerprints in manifests or artifacts.

Transcript compatibility and interval coverage can be evaluated
mechanically. For arbitrary analyses, expose candidate artifacts and their task
descriptions so the agent can judge whether a result answers the new question.
Do not automatically equate paraphrased prompts or use aggressive semantic
normalization.

### Acceptance cases

- A manifest can be located deterministically from a video ID.
- Manifest coverage resolves the artifact-reuse and gap-planning acceptance
  cases in Design A.
- Missing or stale manifest entries do not destroy underlying artifacts.
- Updating a manifest does not rewrite immutable artifact content.
- Execution-only lifecycle changes do not rewrite the manifest.
- A clean v3 namespace works correctly when no cache-v2 data exists.
- Manifests and artifacts contain no legacy-only compatibility fields.
- Manifests contain no Gemini execution lifecycle, history, routing, or
  provenance fields.
- The same reusable artifact content retains the same artifact ID regardless of
  which Gemini execution produced or verified it.

## Design C — Bound Gemini execution and durable result

Use the separate per-video Gemini execution journal for execution state. The
artifact manifest must contain no request binding, result reference, lifecycle,
history, routing, retry, lease, cooldown, or provenance fields.

### Request-to-router binding

Create a pending execution from the exact request file and endpoint that the
router will receive. Do not ask an agent to reproduce the request inside an
independent execution-spec file. The binding must contain:

- normalized video ID;
- requested half-open millisecond coverage;
- route and HTTP method;
- endpoint and model identity;
- SHA-256 of the exact request-file bytes;
- SHA-256 of the canonical parsed request JSON; and
- a canonical execution fingerprint derived from the video, coverage, route,
  model, endpoint identity, and canonical request JSON.

The exact-byte digest binds the reserved execution to the transport file. The
canonical digest and execution fingerprint make irrelevant JSON whitespace and
object-key ordering immaterial to duplicate detection. Neither digest is an
artifact-discovery key.

For the initial YouTube workflow, require exactly one video input. Normalize
every embedded `fileUri` and require it to match the journal video ID. Parse
its `videoMetadata.startOffset` and `endOffset`, convert them to the repository's
millisecond interval representation, and require exact agreement with requested
coverage. Derive or verify the model and route from an allowed Gemini endpoint;
do not trust independently typed labels.

After the pending binding is durable, the router must recompute both request
digests from the file it is about to read and verify the endpoint, model, route,
and pending execution identity before loading a credential or performing
network I/O. A missing, stale, or mismatched binding must fail closed.

### Immutable execution-result records

Persist every successful Gemini response before marking its execution
completed. Store the exact safe `RESPONSE_JSON` bytes as an immutable
content-addressed result record named:

```text
<videoId>--gemini-result--<resultId>.json
```

Derive `resultId` from the exact response bytes. The journal stores the result
ID, deterministic filename, Drive file ID, and integrity digest. The result
record contains no credential, authorization header, bucket secret, artifact
compatibility claim, or reusable coverage.

A successful response remains durable even when it is malformed, truncated,
or unsuitable for reuse. Such a result is evidence of what Gemini returned; it
does not become a transcript or analysis artifact merely because the HTTP
request succeeded. A completed execution must reference its durable result.
Artifact references remain optional because validation may correctly produce
none.

The relationships remain one-way:

- the execution journal references its immutable result and any validated
  reusable artifacts;
- a reusable artifact and its manifest entry do not reference the execution or
  result; and
- an execution result is never indexed in the artifact manifest.

### Transcript-v1 result adapter

Create a `gemini-transcript` version `1` artifact only through a deterministic
adapter that reads a bound execution and its verified immutable result. The
adapter must:

1. extract the generated JSON from the successful Gemini response envelope;
2. require exactly the transcript-v1 fields and their documented types;
3. parse every full-video timestamp and enforce the
   `MM:SS.mmm`-with-unbounded-minutes syntax;
4. require returned clip bounds to equal the bound request interval;
5. require each segment to have positive, in-range bounds and nondecreasing
   start order, while allowing genuine overlapping speech;
6. validate `completed_through_timestamp`, `transcription_complete`,
   `truncation_detected`, and the Gemini finish reason as one consistent state;
   and
7. derive valid coverage mechanically from the bound clip start through the
   verified completed-through timestamp.

Caller-supplied coverage must never enter a transcript artifact. A complete
result covers the full bound interval. A valid incomplete result may create a
partial transcript artifact and leaves the remainder uncovered. A malformed or
internally inconsistent result creates no reusable transcript artifact and
claims no coverage.

Do not automatically repeat a completed execution whose result was malformed
or unusable. Preserve the result, expose the uncovered interval and blocking
execution, and require either a changed request or an explicitly documented
human-authorized retry.

### Journal state-machine invariants

Use native v3 execution records for:

- the bound request identity and requested coverage;
- pending, completed, failed, and unknown-outcome lifecycle state;
- pending ownership, expiry, and reconciliation evidence;
- the documented reason for every permitted identical retry;
- every safe router attempt emitted through terminal `ROUTING_JSON`;
- final status, selected bucket, result reference, and artifact references;
  and
- model and usage metadata when present.

Enforce these invariants:

- a pending execution has one current writer and one immutable request binding;
- a completed execution has terminal success routing metadata and one durable
  result reference;
- a failed execution has terminal failure metadata and no fabricated result;
- an unchanged terminal request failure cannot be retried;
- an identical failed, abandoned, unknown-outcome, or explicitly approved
  unusable-result execution cannot retry without a recorded reason;
- a retry cannot begin before the applicable durable cooldown expires;
- attempt start and finish times, execution times, lease times, retry
  authorizations, and writer events are chronologically consistent;
- HTTP status, classification, selected bucket, and terminal routing status are
  mutually consistent; and
- writer history, current ownership, pending ownership, handoff target, and
  lease state describe the same lifecycle.

Generate a fresh high-entropy session owner ID through the journal tool. Reject
an owner ID already present in that video's history. A recorded handoff reserves
the next acquisition for its named recipient; another owner cannot acquire
without explicit reconciliation.

Artifact-manifest reconstruction must not erase or reset results, execution
records, failed attempts, retry reasons, cooldowns, or attempt numbering.
Result recovery follows journal references and deterministic result filenames.
Artifact recovery uses only validated reusable artifacts. Neither recovery path
rewrites the other data structure.

### Ordered write procedure

Before calling Gemini:

1. plan coverage from manifest metadata;
2. fetch and verify only selected reusable artifacts;
3. replan around stale or invalid selections;
4. acquire the supported per-video writer and reread artifact state;
5. create the binding from the exact router request and endpoint;
6. reserve the pending execution and make the journal durable; and
7. let the router verify that binding before credential selection.

After the router returns:

1. on failure, finalize the journal with its exact terminal routing metadata;
2. on success, upload the immutable execution result first;
3. run the applicable deterministic result adapter;
4. upload any validated reusable artifact;
5. finalize the journal with its result reference, router metadata, and any
   artifact IDs; and
6. update the artifact manifest only for validated reusable artifacts.

If a result or artifact upload succeeds but a later mutable update fails,
recover from the immutable files and pending binding; do not repeat Gemini.

If the process or VM disappears after a network attempt but before terminal
routing metadata and the result become durable, the external call and Drive
replacement cannot be made atomic. Preserve the pending execution as an
unknown network outcome. Reconciliation must record that uncertainty and must
not infer failure, reconstruct unavailable attempt details, or authorize an
automatic retry.

If a manifest is missing, enumerate and verify native artifacts for the video
before initializing an empty manifest. Do not read execution or result records
to reconstruct an artifact manifest.

Raw Drive-file replacement provides no atomic compare-and-set operation. The
initial release therefore adopts the explicit
[single-writer-per-video policy](youtube-artifact-cache-v3-single-writer-policy.md).
Treat it as a supported-use constraint, not technical mutual exclusion. Leases
support recovery and reconciliation but do not make writer acquisition atomic
or prove that an expired writer stopped.

## Optional disposable cache-v2 validator

If comparison with prior results is useful, keep it outside the v3 runtime:

- Read v2 records without modifying them.
- Compare their source, interval, completion, and result information with
  native v3 artifacts.
- Produce validation reports only; do not create v3 manifests or artifacts
  from v2 records.
- Keep the dependency one-way: a disposable validator may inspect v3, but
  production v3 code must never import or call the validator.
- Remove the validator together with the remaining v2 data after
  representative transcript, analysis, persistence, coverage, truncation, and
  idempotency behavior is verified in v3.

The validator is optional. Do not create it unless it provides concrete value
during controlled validation.

## Implementation decisions

- Fix the private Drive namespace as `YouTubeArtifactCacheV3`. Its stable folder
  ID will be recorded only after controlled live creation; implementation and
  offline validation do not invent one.
- Represent requested, valid, covered, and missing ranges as normalized
  half-open integer-millisecond intervals.
- Treat contract name/version, timestamp basis, and structured language policy
  as exact mechanical compatibility dimensions. Do not silently coerce them.
- Require analysis artifacts to carry a task description and require explicit
  agent approval of an artifact ID before automatic interval reuse.
- Derive artifact IDs from canonical reusable artifact content and
  compatibility metadata. Keep execution provenance outside immutable artifact
  content and the manifest. Store a separate SHA-256 of the exact immutable
  JSON bytes in the manifest.
- Upload an immutable artifact before replacing the mutable manifest. Rebuild a
  missing or stale manifest from verified native artifacts and Drive file IDs.
- Update the manifest only for changes to the searchable artifact set or its
  content-side indexing metadata. Do not update it for execution-only state
  transitions.
- Construct the execution binding from the actual request file and endpoint
  only after artifact search. Preserve both exact-byte and canonical request
  digests; use the canonical execution fingerprint for duplicate control.
- Persist the exact successful response as an immutable result before
  completing the journal. Never substitute an artifact ID for a missing result
  record or infer reusable coverage from network success.
- Permit transcript artifacts only through the transcript-v1 adapter. Derive
  coverage from validated output and the bound clip rather than metadata
  supplied to a generic artifact builder.
- Block identical pending or completed executions by default. Require
  documented authorization before any permitted retry of a failed, abandoned,
  unknown-outcome, or completed-but-unusable execution.
- Enforce the supported single-writer-per-normalized-video workflow described
  in the dedicated policy. Keep writer ownership, leases, handoffs, and
  abandonment in the execution journal rather than the artifact manifest.
- Do not implement the optional v2 validator. Native offline fixtures cover the
  required storage, retrieval, truncation, integrity, and idempotency evidence
  without introducing a disposable dependency.

The initial implementation deviated from this corrected design by using the
artifact manifest as the only durable store for pending and failed execution
state, not consuming `ROUTING_JSON`, allowing identical failed executions to
restart without a reason, losing pending and failed history during manifest
reconstruction, placing execution-oriented metadata and references in the
artifact manifest, and including execution provenance in artifact identity.
These are release blockers, not accepted design changes.

The audited checkpoint `b8598e4` corrected those storage boundaries but left a
second set of release blockers: the reserved execution is not bound to the
router's actual request file and endpoint; a completed execution may contain no
durable result; the generic artifact builder accepts unvalidated transcript
content and caller-asserted coverage; durable cooldowns are not enforced; and
writer, attempt, and routing histories accept contradictory states. Correct
these boundaries without moving execution fields back into artifacts or the
manifest.

## Test direction

Do not add a byte-for-byte golden request or fixed request-hash regression test
merely to stabilize cache v2's coupling between request serialization and
artifact discovery.

Cache v3 should instead test:

- clean-slate operation with no v2 records or fixtures;
- formatting-independent canonical execution fingerprints plus exact-byte
  transport binding;
- rejection of mismatched request files, video URIs, clip bounds, endpoints,
  models, routes, and absent pending bindings before credential selection;
- immutable result identity, Drive reference, integrity verification, and
  recovery after a mutable-update failure;
- rejection of completed executions without a durable result reference;
- transcript-v1 extraction, timestamp and clip-bound validation, completion
  and truncation consistency, and mechanically derived valid coverage;
- preservation without reuse of malformed successful results;
- artifact identity that remains stable across different execution provenance;
- artifact compatibility;
- interval coverage, composition, and gap detection;
- manifest-first planning followed by selected-artifact verification;
- missing-manifest reconstruction before empty initialization;
- durable router-attempt history, cooldown enforcement, and retry
  authorization;
- pending expiry, unknown-outcome reconciliation, and no automatic retry after
  an ambiguous crash window;
- same-video writer blocking, read-only concurrency, different-video
  independence, unique owner generation, recipient-constrained handoff,
  chronological writer history, and abandonment under the documented
  single-writer policy;
- chronological execution and attempt history plus consistent HTTP status,
  classification, selected bucket, and terminal routing state;
- execution-journal recovery independent of manifest recovery;
- manifest entries restricted to artifact-discovery, compatibility, coverage,
  and integrity fields;
- byte-stable manifests across execution-only pending, failure, fallback,
  retry, cooldown, abandonment, result-only completion, and malformed-result
  preservation;
- one-way execution-to-result and execution-to-artifact references with no
  result, artifact, or manifest back-reference;
- replacement of tests that currently require manifest execution references
  or other execution-derived manifest fields;
- manifest lookup and update behavior; and
- isolation from legacy lookup and schema assumptions.

If the disposable validator is implemented, test it separately for read-only
behavior and removable isolation from production v3 code.

## Non-goals

- No vector database or embedding service.
- No automatic equivalence between semantically similar analysis prompts.
- No cache-v3 implementation inside transcript-mode history.
- No cache-v2 compatibility, import, migration, or fallback path in production
  v3 code.
- No claim of Drive-backed cross-session mutual exclusion, at-most-once
  execution when the single-writer policy is violated, or exactly-once
  execution.
- No claim that Drive can reconstruct an HTTP attempt or response lost when a
  process or VM disappears before terminal router output becomes durable.
- No deletion of cache-v2 data as part of the v3 feature branch; retire it
  separately after validation.
- No live Gemini quota consumption merely to test the index design.
