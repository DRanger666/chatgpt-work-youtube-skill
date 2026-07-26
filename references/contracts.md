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

Research cache:

- Folder: `YouTubeResearchCache`
- Folder ID: `1BVqRlmyVCVsEFhXblmbbSMPIvQ4xoGlB`
- Record name: `<videoId>--<first16OfRequestSha256>.json`

Prefer stable IDs. Fall back to exact-name search when an ID no longer resolves, and verify the parent folder before use.

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

## Cache record lifecycle

Create `pending` before the API call. Replace it in place with `succeeded` or
`failed` afterward. Use schema version 2 and retain all network attempts in one
record.

Required fields:

- `schemaVersion`
- `videoId`
- `videoUrl`
- `requestFingerprint`
- `route`
- `model`
- `prompt`
- `status`
- `attemptStartedAt`
- `retrySameRequest`
- `attempts`

Each `attempts` entry may contain:

- `bucket`
- `startedAt`
- `finishedAt`
- `httpStatus`
- `classification`
- `errorStatus`
- `retryDelaySeconds`
- `cooldownUntil`
- `backoffSeconds`

Add clip bounds, finish time, final HTTP status, selected bucket alias, model
version, usage metadata, parsed result, error, and conclusion when applicable.
Reopen an identical failed record only with a documented permitted retry
reason. Preserve prior attempts.

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
- Treat each clip and prompt as a separate fingerprinted cache item.
- Offline routing tests cover primary success, project cooldown, fallback,
  bounded transient retry, terminal request errors, credential failure, and
  legacy cache migration.

## Primary documentation

- Gemini video understanding: `https://ai.google.dev/gemini-api/docs/generate-content/video-understanding`
- Gemini Generate Content API: `https://ai.google.dev/api/generate-content`
- YouTube captions download: `https://developers.google.com/youtube/v3/docs/captions/download`
