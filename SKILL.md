---
name: work-with-youtube
description: Reproducible YouTube video research and analysis using a portable local YouTube MCP server, timestamp-cited transcripts, Gemini video understanding for captionless or visual material, timestamp chunking for long videos, persistent Google Drive credential recovery, and mandatory cache-first result reuse. Use for any request to inspect, summarize, query, compare, cite, or otherwise work with one or more YouTube URLs or videos, including requests made in a fresh Work Mode VM.
---

# Work with YouTube

Use a transcript-first, cache-first workflow. Rebuild missing local tooling automatically and recover Gemini credentials from the user's private Google Drive only when needed.

## Preserve these invariants

- Use the no-space installation name `youtube-mcp-portable`.
- Keep `materials/` and `workspace/` inside that installation.
- Never print, quote, summarize, log, or commit an API key.
- Never store a credential in a research cache record.
- Check persistent cache before every Gemini request.
- Record every Gemini attempt, including failures.
- Never repeat an identical failed request without a documented reason.
- Keep generated research separate from credentials.
- Keep Gemini video requests sequential; do not parallelize chunks across
  credentials.

Read [references/contracts.md](references/contracts.md) before using Google Drive or Gemini.

## Start or recover the local MCP

Set `skill_dir` to this skill directory. Run:

```sh
install=$(sh "$skill_dir/scripts/ensure_youtube_mcp.sh" \
  --search-root /workspace \
  --install-parent "$PWD")
```

Treat its printed path as the installation root. The script must discover and verify an existing compatible installation before rebuilding the pinned server.

Use the deterministic MCP caller:

```sh
"$install/runtime/bin/node" "$skill_dir/scripts/call_youtube_mcp.mjs" \
  --install "$install" --list-tools
```

Pass complex tool arguments through a JSON file in `$install/workspace/` instead of fragile shell quoting.

For `research-video` and `research-videos`, add `--structured-only` to avoid emitting the same result in both text and structured forms. For broad transcript reads, paginate `research-video` with `offset` and `maxSegments` instead of printing one oversized wrapper. Prefer a focused query whenever possible.

## Select the least expensive route

1. Normalize each URL to a YouTube video ID.
2. Use the MCP to inspect metadata and request the transcript.
3. Use `research-video` for focused transcript questions and timestamp-linked citations.
4. Use transcript results directly when they answer the request.
5. Use Gemini only when captions are absent, visual evidence matters, or the user requests whole-video understanding beyond the transcript.
6. For multiple videos, process and cache each video independently before comparison.

Do not assume a YouTube Data API key can retrieve unavailable captions. Its caption-download operation normally requires permission to edit the video.

## Request exact wording from Gemini

When captions are absent or inadequate and the task needs source wording, use
the tested transcript-only request instead of an analysis prompt:

```sh
python3 "$skill_dir/scripts/build_gemini_chunk_request.py" \
  --video-url VIDEO_URL \
  --start-seconds START \
  --end-seconds END \
  --transcript-only \
  --output REQUEST_JSON
```

This mode requests only audible linguistic content in the original language,
uses fixed full-video timestamp strings, and defaults to the tested
8192-token output allowance. For a long video, use the existing chunk planner
with 600-second chunks and a four-second overlap. Cache and route every chunk
through the normal Gemini workflow.

## Run a mandatory Gemini cache transaction

Perform these steps for every Gemini call, including chunk synthesis:

1. Build the exact request file.
2. Compute its SHA-256 fingerprint using `scripts/gemini_cache.py start`.
3. Search `YouTubeResearchCache` on Google Drive for the exact filename `<videoId>--<first16OfFingerprint>.json`.
4. If a successful record exists, reuse it. Do not call Gemini.
5. If an identical failed record exists, stop unless a permitted rerun condition below applies.
6. Create a local `pending` record with `gemini_cache.py start`.
7. Upload that pending record to `YouTubeResearchCache` before the network request.
8. Execute the request through `scripts/gemini_request.py`, which selects a
   healthy project bucket and writes safe routing metadata.
9. Finish the same local record with `gemini_cache.py finish
   --routing-metadata ROUTING_JSON`, whether the call succeeded or failed.
10. Replace the same Drive file in place. Verify its status, fingerprint, and
    appended attempt history.

Permit a new call only when at least one condition is explicit:

- The new question cannot be answered from cached results.
- The prompt, clip, source, model, or processing route materially changed.
- The cached failure was transient, such as rate limiting or a network failure.
- The user requested a refresh.
- Independent verification is justified and identified as such.

Do not classify an `INVALID_ARGUMENT` response as transient. Do not retry it unchanged.

When a prior failed record qualifies for a new attempt, reopen it with
`gemini_cache.py start --retry-reason REASON`. Preserve its existing
`attempts` history.

## Route Gemini requests conservatively

Use the primary credential normally and the fallback only when the primary
project is cooling down, rate-limited, transiently unavailable after bounded
retries, or credential-invalid.

Run:

```sh
python3 "$skill_dir/scripts/gemini_request.py" \
  --request REQUEST_JSON \
  --response RESPONSE_JSON \
  --routing-metadata ROUTING_JSON \
  --state "$install/workspace/gemini-keypool-state.json"
```

The router permits only one request at a time. It handles:

- quota exhaustion by cooling the project bucket and trying the other healthy
  bucket once;
- `408` and transient `5xx` responses with bounded exponential backoff and
  jitter;
- credential failures by disabling that bucket for the run;
- terminal request errors without rotating keys.

If every configured bucket is unavailable, stop and report the cooldown rather
than looping. Record only the aliases `primary` and `fallback`; never record a
key or key fingerprint.

## Chunk long or rejected videos

Use timestamp clipping when a whole-video request exceeds limits or returns an ingestion error. Gemini accepts `videoMetadata.startOffset` and `endOffset` on YouTube inputs.

Plan 30-minute chunks:

```sh
python3 "$skill_dir/scripts/gemini_cache.py" plan \
  --duration-seconds VIDEO_DURATION \
  --chunk-seconds 1800
```

Use a small overlap only when boundary continuity is material; the default is no overlap to avoid duplicate usage. Build each request with:

```sh
python3 "$skill_dir/scripts/build_gemini_chunk_request.py" \
  --video-url VIDEO_URL \
  --start-seconds START \
  --end-seconds END \
  --prompt PROMPT \
  --output REQUEST_JSON
```

Require timestamps relative to the complete YouTube video. Cache every chunk separately. Synthesize from cached chunk outputs; if Gemini performs the synthesis, cache that request and result as another transaction.

Start with one representative chunk. Expand to all chunks only after that chunk succeeds.
Process chunks sequentially.

## Recover Gemini credentials privately

Use the connected Google Drive app and the exact credential contract in `references/contracts.md`.

Fetch the raw credential file without displaying its bytes. Materialize it as:

`$install/config/youtube-workbench-secrets.env`

Set mode `0600`, then load it into the process environment. Never place it in `materials/`, `workspace/`, a prompt, a tool argument, source control, or a cache record.

The credential file may contain:

- `GEMINI_API_KEY` for the primary Google Cloud project.
- `GEMINI_API_KEY_FALLBACK` for a separately provisioned fallback project.

Gemini quotas are project-level. Do not expect two keys from the same project
to add capacity. The router collapses duplicate credential values to one
bucket.

If Drive requires connection or authorization, stop and ask the user to connect it. Do not create a Gemini request before credential retrieval succeeds.

## Deliver research

- Cite transcript claims with MCP timestamp links.
- Label Gemini-derived claims as video-model analysis and include timestamps when available.
- Distinguish observed facts, model inference, and uncertainty.
- State when only part of a long video has been analyzed.
- Mention cache reuse when it prevented a new Gemini call.
