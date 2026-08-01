# YouTube workflow contracts

## Contents

- [Local installation](#local-installation)
- [Google Drive](#google-drive)
- [Gemini clipped request](#gemini-clipped-request)
- [Interactive Gemini quota pool](#interactive-gemini-quota-pool)
- [Artifact cache v3](#artifact-cache-v3)
- [Validated behavior](#validated-behavior)
- [Primary documentation](#primary-documentation)

## Local installation

Use this exact no-space layout:

```text
youtube-mcp-portable/
  app/
  bin/
  config/
  materials/
  runtime/
  workspace/
  VERSION
```

Pinned implementation:

- Repository: `https://github.com/coyaSONG/youtube-mcp-server.git`
- Version: `1.2.0`
- Commit: `06d5e7a83783f7a44498da88ade2ccaa42238747`
- Node: `v24.14.0`
- Platform: `linux-x86_64`

## Google Drive

Use private Drive files. Do not create public links.

Credential location:

- Folder: `WorkModeCredentials`
- Folder ID: `1q58TvI519TDgTePQG1h2Rof5EdA2jDJk`
- File: `youtube-workbench-secrets.env`
- File ID: `1rvfVswFWzIoqMOKsJttZgTsRkpbiKxNx`

Native research artifact cache:

- Folder: `YouTubeArtifactCacheV3`
- Manifest name: `<videoId>--manifest.json`
- Artifact name: `<videoId>--<kind>--<artifactId>.json`
- Gemini execution journal name: `<videoId>--gemini-executions.json`

The v3 folder has no stable ID until its first controlled creation. Locate it
by exact name and require one unambiguous private folder. Record and verify its
stable ID after creation. Do not search `YouTubeResearchCache` or any cache-v2
record when a v3 manifest is absent.

Prefer stable IDs after they are established. Fall back to exact-name search
when an ID no longer resolves, and verify the parent folder before use.

Retrieve credentials in code mode so the connector result is not surfaced. Compare bytes or hashes without printing content. Materialize locally with mode `0600`.

Credential variables:

- `GEMINI_API_KEY`: primary Gemini project credential.
- `GEMINI_API_KEY_FALLBACK`: optional credential from a different Google Cloud
  project.

Gemini quota is project-level. Multiple keys from the same project must not be
treated as separate quota buckets.

## Gemini clipped request

Use the Generate Content endpoint:

`POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent`

Send requests through `scripts/gemini_request.py`. It authenticates with the
selected credential using the `x-goog-api-key` header without writing the
credential to routing state or cache.

Use this input structure:

```json
{
  "contents": [{
    "role": "user",
    "parts": [
      {
        "fileData": {
          "fileUri": "https://www.youtube.com/watch?v=VIDEO_ID",
          "mimeType": "video/*"
        },
        "videoMetadata": {
          "startOffset": "0s",
          "endOffset": "1800s"
        }
      },
      {
        "text": "Analyze only this supplied interval and use full-video timestamps."
      }
    ]
  }],
  "generationConfig": {
    "responseMimeType": "application/json",
    "maxOutputTokens": 2048
  }
}
```

Google documents `startOffset` and `endOffset` as seconds ending in `s`. Keep the prompt after the video part.

### Transcript-only request

Pass `--transcript-only` to `scripts/build_gemini_chunk_request.py` when the
workflow needs Gemini to transcribe rather than analyze a supplied interval.
The builder uses the prompt and strict JSON schema validated in the July 2026
captionless-video trials and defaults to `8192` output tokens.
Timestamp minutes contain at least two digits and may exceed `99`, so clips
after 7,200 seconds can retain full-video `MM:SS.mmm` timestamps.

For long transcripts, use the existing planner with
`--chunk-seconds 600 --overlap-seconds 4`. Keep the generated full-video
timestamps when reconciling the overlap.

Treat a transcript response as incomplete when `transcription_complete` is
false, `truncation_detected` is true, `completed_through_timestamp` does not
cover the requested interval, or the API finish reason reports output
truncation. Finish and retain its normal cache record, but do not treat that
record as complete coverage. Request the unfinished interval in smaller clips;
the changed clip bounds produce new fingerprints. Do not repeat or reopen the
identical request for truncation recovery.

## Interactive Gemini quota pool

The pool contains at most two aliases:

- `primary` from `GEMINI_API_KEY`;
- `fallback` from `GEMINI_API_KEY_FALLBACK`.

Keep at most one request in flight. Prefer `primary`; use `fallback` only when
the primary bucket is cooling down or unavailable. On `429
RESOURCE_EXHAUSTED`, respect a server-provided retry delay when present, add
jitter, and cool down the entire project bucket. Bound transient retries. Do
not rotate on `400 INVALID_ARGUMENT`.

Store session-local health at:

`$install/workspace/gemini-keypool-state.json`

The state may contain bucket aliases, cooldown times, disabled flags, and
failure classifications. It must not contain credential values or
fingerprints.

## Artifact cache v3

Use `scripts/artifact_cache_v3.py` for reusable material and
`scripts/gemini_execution_journal_v3.py` for Gemini lifecycle. Native
artifacts, manifests, and execution journals each start at schema version `1`;
the numeral `3` identifies the cache-system generation. Production v3 code
does not import, search, validate, migrate, or fall back to cache v2.

Represent coverage as normalized half-open integer-millisecond intervals:

```json
{"startMs": 0, "endMs": 600000}
```

Match transcript-like artifacts mechanically by exact artifact kind, contract
name and version, timestamp basis, and structured language policy. Native
artifacts use the `full_video` timestamp basis and expose only verified
`validCoverage`. Compute current gaps from requested coverage minus the union
of compatible valid coverage. Keep requested execution coverage and produced
artifact references in the execution journal; do not persist truncation events
or derived request gaps in artifact-search records.

The mutable `<videoId>--manifest.json` contains:

- `schemaVersion`, `cacheSystem`, `videoId`, and `updatedAt`;
- artifact entries with artifact and Drive file IDs, deterministic filename,
  kind, contract, timestamp basis, language policy, valid coverage, and exact
  stored-byte SHA-256 integrity;
- a human-readable `taskDescription` only when an analysis artifact requires
  explicit agent review.

The manifest contains no execution IDs, fingerprints, provenance, lifecycle,
attempts, routing, retry reasons, leases, cooldowns, requested execution
coverage, stored request gaps, or truncation events. Modify it only when the
searchable artifact set or content-side index metadata changes.

Each immutable artifact contains reusable generated content and the
compatibility metadata required to interpret and validate it. Derive
`artifactId` from that canonical reusable record without execution provenance.
The same reusable material therefore retains the same identity when a
different execution produces or verifies it. Never replace an existing
artifact file; upload a new artifact before adding its entry to the manifest.

Plan from manifest metadata before downloading artifact content. Download and
integrity-check only selected reuse or analysis-review candidates. Replan
around missing, stale, or invalid selected files before constructing any new
Gemini request.

If a manifest is missing, enumerate native artifacts for that video first.
Reconstruct the manifest from verified artifact files and Drive file IDs when
any exist. Initialize an empty manifest only after enumeration confirms that no
native artifacts exist. Manifest recovery never reads, rewrites, erases, or
resets the execution journal.

### Gemini execution journal

The deterministic `<videoId>--gemini-executions.json` journal owns:

- normalized video identity and canonical execution fingerprints;
- route, model, and requested coverage;
- pending, completed, failed, and reconciled abandonment history;
- session-specific writer ownership and lease expiry;
- every safe network attempt present in retained `ROUTING_JSON`;
- selected bucket, retry delay, backoff, cooldown, failure classification, and
  earliest available cooldown when present;
- documented authorization for each identical failed or abandoned retry;
- reconciliation, handoff, and abandonment evidence; and
- one-way references from completed executions to produced artifact IDs.

Artifacts and manifests never point back to executions. Rebuilding a manifest
does not change execution history or attempt numbering.

Before credential selection, acquire the supported per-video writer, reread
the latest manifest, and repeat artifact planning and selected-file
verification. Build the request only for still-uncovered work, start its
execution, save the pending journal to Drive, and only then invoke
`gemini_request.py`. Finalize both successes and failures with the exact safe
routing metadata. Preserve primary, fallback, and bounded transient attempts
as separate entries. A failure caused by no healthy bucket may contain zero
network attempts but must retain its earliest cooldown.

If the router invocation ends before `ROUTING_JSON` is retained, the journal
remains pending with an unknown network outcome and no inferred attempt. Never
invent the missing history or infer an outcome; stop for the user's
interrupted-run decision before another Gemini call.

An identical pending or completed execution blocks submission. An identical
failed or abandoned execution requires a non-empty recorded retry reason.
Never retry `INVALID_ARGUMENT` or another terminal request failure unchanged.

### Single-writer operating contract

The initial release supports one write-capable Work session per normalized
YouTube video ID. Writing includes Gemini submission, journal mutation,
artifact publication, and manifest creation, replacement, repair, or removal.
Concurrent sessions may inspect and reuse the same video's artifacts read-only.
Different normalized video IDs may have independent writers.

An active different owner blocks the same video's write path. Lease expiry
triggers reconciliation; it does not grant ownership or prove the old writer
stopped. When termination is uncertain, require human confirmation before
recording reconciliation, handoff, or abandonment and proceeding.

Drive replacement supplies no atomic compare-and-set. Do not claim
Drive-enforced mutual exclusion, safe concurrent same-video writes,
cross-session at-most-once execution, or exactly-once execution. This is a
supported-use constraint. A future atomic coordinator may replace it without
changing artifact identity or manifest search fields.

Never store:

- API keys
- authorization headers
- raw credential files
- credential fragments or fingerprints
- unrelated personal information

## Validated behavior

- Transcript MCP works on captioned Bengali videos and returns timestamp-linked citations.
- A public captionless 2h15m Hindi movie failed as a single whole-video Gemini request.
- The same movie succeeded when clipped to `0s`–`1800s`.
- Native v3 coverage tests handle exact, containing, composite, overlapping,
  partial-valid, incompatible, stale, and missing material without v2 fixtures.
- Manifest-first planning downloads only selected artifacts and replans around
  verification failures.
- Native journals preserve router attempts, retry authorization, pending
  recovery, handoff, abandonment, and one-way artifact references independently
  of manifest recovery.
- Canonical execution guards prevent duplicate pending and completed calls,
  require reasons for failed retries, and reject unchanged terminal failures.
- Existing offline Gemini-router tests cover primary success, project cooldown,
  fallback, bounded transient retry, terminal request errors, and credential
  failure.

## Primary documentation

- Gemini video understanding: `https://ai.google.dev/gemini-api/docs/generate-content/video-understanding`
- Gemini Generate Content API: `https://ai.google.dev/api/generate-content`
- YouTube captions download: `https://developers.google.com/youtube/v3/docs/captions/download`
