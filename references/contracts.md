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

## Gemini clipped request

Use the Generate Content endpoint:

`POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent`

Authenticate with the `x-goog-api-key` header from `GEMINI_API_KEY`.

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

## Cache record lifecycle

Create `pending` before the API call. Replace it in place with `succeeded` or `failed` afterward.

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

Add clip bounds, finish time, HTTP status, model version, usage metadata, parsed result, error, and conclusion when applicable.

Never store:

- API keys
- authorization headers
- raw credential files
- unrelated personal information

## Validated behavior

- Transcript MCP works on captioned Bengali videos and returns timestamp-linked citations.
- A public captionless 2h15m Hindi movie failed as a single whole-video Gemini request.
- The same movie succeeded when clipped to `0s`–`1800s`.
- Treat each clip and prompt as a separate fingerprinted cache item.

## Primary documentation

- Gemini video understanding: `https://ai.google.dev/gemini-api/docs/generate-content/video-understanding`
- Gemini Generate Content API: `https://ai.google.dev/api/generate-content`
- YouTube captions download: `https://developers.google.com/youtube/v3/docs/captions/download`
