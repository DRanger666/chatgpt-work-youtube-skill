# YouTube artifact cache v3

## Status

Approved clean-slate direction with a release correction required. The initial
feature-branch implementation must not be merged or used for live v3 data until
the artifact-search, manifest, and Gemini execution contracts satisfy this
corrected design together.

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
4. Persist every Gemini network attempt, including bucket alias, timestamps,
   HTTP status, classification, error status, retry delay, cooldown, and
   backoff when present.
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

Cache v3 uses three persisted data structures with non-overlapping ownership:

| Data structure | Owns | Must not own |
|---|---|---|
| Immutable artifact record | Reusable generated material and the content-side metadata required to identify, interpret, and validate that material | Gemini execution IDs, lifecycle, attempts, routing, retries, leases, cooldowns, or provenance references |
| Per-video artifact manifest | The minimal index needed to locate artifacts and plan compatible, integrity-checked coverage | Gemini execution lifecycle, history, routing, retry, concurrency, or provenance data |
| Gemini execution journal | Canonical execution identity, requested work, lifecycle, routing attempts, retry authorization, reconciliation, and one-way references to produced artifact IDs | Artifact discovery or coverage-search responsibilities |

Do not duplicate execution fields in either the immutable artifact or the
per-video manifest for convenience. If execution history changes without
creating a new reusable artifact, neither artifact-side data structure changes.

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
8. Immediately before a network request, consult the durable Gemini execution
   journal using a canonical execution fingerprint.

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
- pending, completed, failed, abandoned, or retry lifecycle state;
- network attempts, retry reasons, leases, cooldowns, or credential-bucket
  routing;
- requested execution coverage; or
- truncation history or request gaps that can be derived by comparing the
  current requested interval with indexed valid coverage.

An artifact produced by a truncated Gemini response contributes only the
coverage that the artifact verifies as valid. The manifest does not preserve
the truncation event. Gap planning is a query-time calculation from the current
requested interval and the union of compatible valid coverage; gaps are not
persisted as manifest state.

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

## Design C — Durable Gemini execution journal

Use a separate durable Gemini execution data structure. The per-video artifact
manifest must contain no execution lifecycle, history, routing, retry, lease,
cooldown, or provenance fields and must not reference this execution data
structure.

Use separate native v3 execution records for:

- the canonical execution fingerprint and requested coverage;
- pending, completed, and failed lifecycle state;
- pending ownership, expiry, and reconciliation evidence;
- the documented reason for an identical failed-request retry;
- every safe router attempt emitted through `ROUTING_JSON`;
- final status, selected bucket alias, model and usage metadata when present;
  and
- references to any artifacts produced by the execution.

The relationship is one-way: an execution record may list the artifact IDs it
produced, but neither the immutable artifact nor its manifest entry points back
to an execution. Provenance remains available from the execution records
without burdening the artifact-search index with execution-oriented fields or
updates.

Artifact-manifest reconstruction must not erase or reset execution records,
failed attempts, retry reasons, or attempt numbering. Reconstruct artifact
discovery exclusively from native artifacts and their content-side metadata.
Recover Gemini execution history exclusively from its separate native
execution records. Neither recovery procedure depends on or rewrites the other
data structure.

Do not include execution provenance in immutable artifact content or artifact
identity. Derive an artifact ID from the reusable artifact material and its
compatibility metadata. Keep execution-to-artifact references only in the
execution records so the same reusable artifact does not receive a different
identity merely because it was produced or verified by another execution.

Before calling Gemini, complete this order:

1. Plan coverage from manifest metadata.
2. Fetch and integrity-check only the artifacts selected for reuse or explicit
   analysis review.
3. Replan if a selected artifact is missing, stale, or invalid.
4. Consult and update the durable execution journal.
5. Select a Gemini credential and execute only the remaining uncovered work.

If a manifest is missing, enumerate and verify native artifacts for the video
before initializing an empty manifest. Initialize an empty manifest only when
no native artifacts exist. Do not read execution records to reconstruct an
artifact manifest.

Raw Drive-file replacement currently provides no atomic compare-and-set
operation through the connected workflow. The initial release therefore adopts
the explicit
[single-writer-per-video policy](youtube-artifact-cache-v3-single-writer-policy.md).
Treat it as a supported-use constraint, not technical mutual exclusion. Leases
support crash recovery and reconciliation but do not make writer acquisition
atomic or prove that an expired writer stopped.

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
- Fingerprint a canonical execution specification only after artifact search.
  Store its lifecycle and router attempts in the separate native v3 execution
  journal. Block identical pending or completed executions, and require a
  documented permitted reason before retrying an identical failed execution.
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

## Test direction

Do not add a byte-for-byte golden request or fixed request-hash regression test
merely to stabilize cache v2's coupling between request serialization and
artifact discovery.

Cache v3 should instead test:

- clean-slate operation with no v2 records or fixtures;
- deterministic execution fingerprints;
- artifact identity that remains stable across different execution provenance;
- artifact compatibility;
- interval coverage, composition, and gap detection;
- manifest-first planning followed by selected-artifact verification;
- missing-manifest reconstruction before empty initialization;
- durable router-attempt history and failed-retry authorization;
- pending expiry and reconciliation;
- same-video writer blocking, read-only concurrency, different-video
  independence, writer handoff, and abandonment under the documented
  single-writer policy;
- execution-journal recovery independent of manifest recovery;
- manifest entries restricted to artifact-discovery, compatibility, coverage,
  and integrity fields;
- byte-stable manifests across execution-only pending, failure, fallback,
  retry, cooldown, abandonment, and no-artifact completion changes;
- one-way execution-to-artifact references with no artifact or manifest
  back-reference;
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
- No deletion of cache-v2 data as part of the v3 feature branch; retire it
  separately after validation.
- No live Gemini quota consumption merely to test the index design.
