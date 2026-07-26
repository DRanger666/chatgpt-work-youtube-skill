# YouTube workflow contracts

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

Use `scripts/artifact_cache_v3.py`. Both manifests and artifacts use native
schema version `1`; the numeral `3` identifies the cache-system generation.
Production v3 code does not import, search, validate, migrate, or fall back to
cache v2.

Represent coverage as normalized half-open integer-millisecond intervals:

```json
{"startMs": 0, "endMs": 600000}
```

Match transcript-like artifacts mechanically by exact artifact kind, contract
name and version, timestamp basis, and structured language policy. Native
artifacts use the `full_video` timestamp basis. A `complete` artifact has no
gaps. `partial` and `truncated` artifacts contribute only `validCoverage`;
compute missing work from requested coverage minus the union of verified valid
coverage.

The mutable `<videoId>--manifest.json` contains:

- `schemaVersion`, `cacheSystem`, `videoId`, and `updatedAt`;
- artifact entries with artifact and Drive file IDs, deterministic filename,
  kind, contract, timestamp basis, language policy, requested and valid
  coverage, completion state, gaps, SHA-256 integrity, and execution IDs;
- safe execution records with canonical fingerprint, pending/completed/failed
  status, route, model, requested coverage, timestamps, and artifact IDs.

Each immutable artifact contains the same native identity and compatibility
metadata, its generated content, and safe execution provenance. Its
content-derived artifact ID excludes only the `artifactId` field. The manifest
integrity value hashes the exact stored JSON bytes. Never replace an existing
artifact file; upload a new artifact before adding its entry to the manifest.

Arbitrary analysis artifacts require a human-readable `taskDescription`.
Expose compatible descriptions for agent review and reuse an analysis artifact
only after explicit approval of its artifact ID. Do not infer equivalence from
similar wording.

Before a network call, fingerprint the canonical execution specification,
including normalized video identity, route, model, requested coverage, and
request JSON. Store only the fingerprint and safe provenance. An identical
pending or completed execution blocks submission. A failed execution remains
in provenance but may create a separately identified guarded attempt; never
loop automatically.

If a manifest is missing or stale, reconstruct it from verified native
artifact files and their Drive file IDs. This recovers durable artifacts and
completed execution provenance without modifying artifact bytes. Pending or
failed execution-only history cannot be reconstructed from artifacts alone.

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
  truncated, incompatible, stale, and missing material without v2 fixtures.
- Canonical execution guards prevent duplicate pending and completed calls
  without making fingerprints an artifact-discovery key.
- Existing offline Gemini-router tests cover primary success, project cooldown,
  fallback, bounded transient retry, terminal request errors, and credential
  failure.

## Primary documentation

- Gemini video understanding: `https://ai.google.dev/gemini-api/docs/generate-content/video-understanding`
- Gemini Generate Content API: `https://ai.google.dev/api/generate-content`
- YouTube captions download: `https://developers.google.com/youtube/v3/docs/captions/download`
