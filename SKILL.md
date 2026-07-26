---
name: work-with-youtube
description: Reproducible YouTube video research and analysis using a portable local YouTube MCP server, timestamp-cited transcripts, artifact-first cache retrieval, Gemini video understanding for captionless or visual material, timestamp chunking for long videos, and persistent Google Drive storage and credential recovery. Use for any request to inspect, summarize, query, compare, cite, or otherwise work with one or more YouTube URLs or videos, including requests made in a fresh Work Mode VM.
---

# Work with YouTube

Use a transcript-first, cache-first workflow. Rebuild missing local tooling automatically and recover Gemini credentials from the user's private Google Drive only when needed.

## Preserve these invariants

- Use the no-space installation name `youtube-mcp-portable`.
- Keep `materials/` and `workspace/` inside that installation.
- Never print, quote, summarize, log, or commit an API key.
- Never store a credential in a research cache record.
- Search native v3 artifacts before constructing a Gemini request.
- Use `YouTubeArtifactCacheV3`; never fall back to cache v2.
- Keep artifact files immutable and the per-video manifest search-only.
- Keep Gemini lifecycle in the separate native execution journal.
- Record every Gemini attempt, including failures.
- Never submit an identical pending or completed execution.
- Never repeat an identical failed execution without a documented permitted
  reason; never repeat a terminal request failure unchanged.
- Permit only one write-capable Work session per normalized video ID.
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
2. Search the native v3 manifest and verified artifacts for compatible coverage.
3. Reuse sufficient artifacts before invoking either transcript or video-model
   generation.
4. Use the MCP to inspect metadata and request captions for uncovered transcript
   material.
5. Use `research-video` for focused caption questions and timestamp-linked
   citations.
6. Use Gemini only when captions are absent, visual evidence matters, or the
   user requests whole-video understanding beyond the available artifacts.
7. For multiple videos, process and store each video independently before
   comparison.

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
with 600-second chunks and a four-second overlap. Store and route every chunk
through the native v3 workflow.

Store an incomplete or truncated response as an immutable artifact, but index
only its confirmed valid coverage. Search again and process the unfinished
interval with smaller clips and new execution fingerprints. Never recover by
repeating the identical request.

## Search and update artifact cache v3

Read the native schemas and file lifecycle in
[references/contracts.md](references/contracts.md). Use
`scripts/artifact_cache_v3.py` for artifact discovery and
`scripts/gemini_execution_journal_v3.py` for Gemini execution state.

Before constructing a Gemini request:

1. Run `locate --video VIDEO` and find the exact
   `<videoId>--manifest.json` file in `YouTubeArtifactCacheV3`.
2. If the manifest is absent, enumerate the video's native artifact files.
   Download and run `rebuild-manifest` when any exist. Run `init-manifest
   --confirmed-no-artifacts` only after confirming that none exist. Do not
   initialize empty state merely because the manifest is missing.
3. Write a query describing artifact kind, contract, full-video interval,
   timestamp basis, and language policy; then run `search`. This first phase
   reads manifest metadata only.
4. Inspect analysis review candidates and approve only artifacts that answer
   the current question. Download only the Drive files listed in
   `artifactIdsToFetch`.
5. Run `verify-search` against those selected files. If verification reports
   stale material and selects replacements, download only the new
   `artifactIdsToFetch` and repeat verification.
6. Reuse only a verified plan. Pass only its `newRequestIntervals` to
   `plan-chunks`; construct no request for covered intervals.

Immediately before each unavoidable network execution:

1. Establish the supported single writer for the normalized video ID. Other
   sessions may reuse artifacts read-only but must not call Gemini, mutate the
   journal, publish an artifact, or update that video's manifest.
2. Locate `<videoId>--gemini-executions.json`. Initialize it with
   `init-journal --confirmed-no-journal` only after exact-name lookup confirms
   that no journal exists. Use a new session-specific owner ID and
   `acquire-writer`, then replace the Drive journal with the acquired state.
3. Stop if another owner is active. Expiry triggers reconciliation; it never
   grants ownership automatically. Require human confirmation when the prior
   writer's termination is uncertain, and preserve handoff or abandonment
   evidence.
4. After acquiring ownership, reread the latest manifest and repeat its
   metadata search and selected-artifact verification. Stop if it now covers
   the work; this closes the handoff window between read-only planning and
   writer acquisition.
5. Build the request and canonical execution-spec JSON only for verified
   uncovered work. Run journal `start-execution`, supplying `--retry-reason`
   only for an identical non-terminal failed or abandoned execution.
6. Replace the Drive journal with the pending state before selecting a Gemini
   credential or sending the request.
7. Run `scripts/gemini_request.py` sequentially and retain its
   `ROUTING_JSON`. On failure, run journal `finish-execution --status failed`
   with that metadata and replace the Drive journal, even when no bucket was
   available. Store no artifact and leave the manifest byte-stable.
8. On success, create and upload the immutable artifact without execution
   provenance. Run journal `finish-execution --status completed` with
   `ROUTING_JSON` and its artifact ID, replace the Drive journal, add the
   artifact to the manifest using its Drive file ID, and replace the manifest.
9. After all pending work is finalized and durable, run `release-writer` with
   the completion or handoff reason and replace the Drive journal.

If an artifact upload succeeds but the manifest update fails, retain the
artifact and rebuild the manifest from native artifact files and verified Drive
file IDs. If any post-request journal update fails, reconcile the pending
execution from its saved routing metadata and artifacts; do not repeat Gemini.
Never rewrite immutable artifact content. Execution fingerprints identify
execution specifications for audit and duplicate-call prevention only; they do
not identify or discover reusable artifacts.

The single-writer rule is per normalized video ID, not global. Different videos
may have independent writers. Drive replacement does not enforce mutual
exclusion, exactly-once execution, or safe concurrent same-video writes. Leases
support recovery and diagnosis only; an expired lease does not prove that the
old writer stopped.

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

Plan chunks from the search plan's uncovered intervals:

```sh
python3 "$skill_dir/scripts/artifact_cache_v3.py" plan-chunks \
  --search-plan SEARCH_PLAN_JSON \
  --chunk-seconds 1800 \
  --output CHUNK_PLAN_JSON
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

Require timestamps relative to the complete YouTube video. Store every chunk
as an independent artifact. Synthesize from reusable artifacts; if Gemini
performs the synthesis, store that result and execution as another artifact.

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
