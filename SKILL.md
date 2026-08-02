---
name: work-with-youtube
description: Reproducible YouTube video research using a portable local YouTube MCP server, timestamp-cited captions, saved Gemini video material, transcript-only generation for captionless sources, long-video chunking, and private Google Drive credential recovery. Use for any request to inspect, summarize, query, compare, cite, translate, transcribe, or otherwise work with one or more YouTube URLs or videos, including in a fresh Work Mode VM.
---

# Work with YouTube

Use captions first, saved work second, and Gemini only for material that is
still missing. Read [references/contracts.md](references/contracts.md) before
using Google Drive or Gemini.

## Preserve these rules

- Keep the portable MCP installation name `youtube-mcp-portable` and keep its
  `materials/` and `workspace/` directories inside that installation.
- Never print, quote, summarize, log, or commit an API key.
- Search saved video material before constructing a Gemini request or loading
  Gemini credentials.
- Use only the `YouTubeVideoWork` Drive folder and file format version `1`.
  Do not search, import, migrate, or fall back to cache-v2 files.
- Never edit a saved Gemini response. The per-video material index is only a
  searchable list; the per-video request log is the complete request history.
- Never submit an identical pending request or silently repeat a terminal run.
  Require a recorded reason for every deliberate repeat and reject unchanged
  terminal request failures and requests whose cooldown has not expired.
- Preserve every safe Gemini attempt returned by the router. If the router
  stops without returning a terminal result, leave the run pending and invent
  no attempt or outcome.
- Do not intentionally run two Work sessions that can write for the same
  video. Different videos can be processed concurrently; Drive does not lock
  simultaneous same-video updates.
- Keep Gemini chunks sequential.

## Start or recover the local MCP

Set `skill_dir` to this skill directory, then run:

```sh
install=$(sh "$skill_dir/scripts/ensure_youtube_mcp.sh" \
  --search-root /workspace \
  --install-parent "$PWD")
```

The script discovers and verifies an existing compatible installation before
rebuilding the pinned server. Call it deterministically:

```sh
"$install/runtime/bin/node" "$skill_dir/scripts/call_youtube_mcp.mjs" \
  --install "$install" --list-tools
```

Put complex MCP arguments in a JSON file under `$install/workspace/`. For
`research-video` and `research-videos`, use `--structured-only`. Paginate broad
transcript reads with `offset` and `maxSegments`; prefer a focused query.

## Choose the least expensive route

1. Normalize the URL to a YouTube video ID.
2. Check YouTube captions through the MCP. Use usable captions for transcript
   work without calling Gemini.
3. Locate the video's material index and saved responses in
   `YouTubeVideoWork`. Search compatible index entries and verify only the
   selected response files.
4. Reuse sufficient verified material. Construct requests only for returned
   missing time ranges.
5. Use Gemini when captions and saved material are inadequate, visual evidence
   matters, or the user requests whole-video understanding.
6. Process each video independently before comparing several videos.

A YouTube Data API key does not grant access to unavailable captions; caption
download normally requires permission to edit the video.

## Search saved video material

The three durable Drive filenames are:

- `<videoId>--video-material-index.json`
- `<videoId>--gemini-response--<outputType>--<savedResponseId>.json`
- `<videoId>--gemini-requests.json`

Use `scripts/saved_gemini_responses.py`.

1. Run `locate --video VIDEO` and find the exact material-index filename.
2. If it is absent, enumerate that video's saved-response filenames. Run
   `rebuild-material-index` when responses exist. Run `init-material-index
   --confirmed-no-saved-responses` only after confirming none exist.
3. Create a query containing the video, controlled output type, compatible
   output format, requested half-open millisecond ranges, and applicable
   language or timestamp policy. Run `find-material` against the local index.
4. Download only files listed in `savedResponseIdsToFetch`, then run
   `verify-selected`. If selected files are missing, stale, or invalid, fetch
   only any replacements in the new plan and verify again.
5. Run `plan-missing-ranges` only on a verified plan. Build no Gemini request
   for covered time.

The controlled reusable outputs are `transcript`, `summary`,
`systematic_visual_description`, and `systematic_onscreen_text`. Transcript
uses `gemini-transcript` version `1`; the other three use
`gemini-free-form-text` version `1`. Free-form material enters the index only
after ChatGPT reviews it and supplies conservative covered time within the
requested source range.

Do not save or search translations as reusable Gemini output. Translate on
demand in ChatGPT from saved original-language transcripts or systematic
onscreen text.

During rebuilding, the `--free-form-admissions` JSON records `admitted: true`
with covered time for material accepted after review, or only
`admitted: false` for a reviewed response that should remain unindexed. A
failed structured response also remains saved but is skipped by rebuilding.

## Request exact wording from Gemini

When captions are absent or inadequate and source wording matters, build the
tested transcript-only request:

```sh
python3 "$skill_dir/scripts/build_gemini_chunk_request.py" \
  --video-url VIDEO_URL \
  --start-seconds START \
  --end-seconds END \
  --transcript-only \
  --output REQUEST_JSON
```

This mode requests only audible linguistic content in the original language,
uses full-video timestamps, and defaults to 8192 output tokens. Timestamp
minutes have at least two digits and may exceed 99.

Use approximately 600-second transcript clips with four-second overlap for
long material. If a response is incomplete or truncated, save it normally and
index only mechanically validated covered time. Request its unfinished range
with smaller clips, creating a new request. Never repeat the identical request
as truncation recovery.

## Run one Gemini request safely

Classify the response before starting:

- `video_material`: reusable source material; declare a controlled output type
  and format and save the response.
- `task_specific_observation`: evidence for the current question only; return
  it to the conversation and do not save the response text.
- `direct_answer`: a current-task answer only; return it and do not save its
  text.

Use `scripts/gemini_request_log.py` and replace the corresponding Drive file
after every successful local log update.

1. Locate `<videoId>--gemini-requests.json`. Run `init-log
   --confirmed-no-log` only after exact-name lookup confirms it is
   absent.
2. Recheck the material index immediately before an unavoidable request.
3. Build the exact request file, then run `start-run`. Use `--transcript` for a
   transcript-only request; otherwise declare `--content-class` and, for
   reusable material, its controlled output fields. Record `--retry-reason`
   only when the user deliberately authorizes another run.
4. Upload the pending request log before selecting credentials.
5. Run the router with the same request-log path, request ID, run number,
   endpoint, model, and method:

```sh
python3 "$skill_dir/scripts/gemini_request.py" \
  --request REQUEST_JSON \
  --response RESPONSE_JSON \
  --router-result ROUTER_RESULT_JSON \
  --request-log REQUEST_LOG_JSON \
  --request-id REQUEST_ID \
  --run-number RUN_NUMBER \
  --state "$install/workspace/gemini-keypool-state.json"
```

The router verifies the exact pending request before loading credentials. It
uses `primary` first, bounded retries for transient failures, and `fallback`
only when the primary project is unavailable. It never rotates on a terminal
request error. Keep only bucket aliases in saved state.

6. On failure, run `finish-run` with the returned router result and upload the
   updated request log. Do not create a saved response.
7. On successful `video_material`, run `save-response`. Upload the immutable
   response to Drive, run `finish-run` with its local path and Drive file ID,
   then add an eligible response to the material index. Upload the request log
   before uploading the updated material index.
8. On successful one-time content, run `finish-run` with the router result and
   exact response file. It verifies success and records
   `responseNotSavedByPolicy`; do not upload the response text.

The request log keeps one stable request entry with numbered runs beneath it;
each run keeps its own authorization, attempts, cooldown, status, and result
reference. Earlier runs are never overwritten.

## Handle an interrupted pending run

Do not infer an outcome from elapsed time.

- Ask the user to confirm that the earlier session stopped.
- For reusable video material, enumerate all saved responses for that video.
  If exactly one valid file identifies the same request ID, run number, and
  exact request hash, call `finish-run` with every candidate path plus
  `--confirmed-session-stopped --confirmed-response-enumeration`; this finishes
  the existing run without another Gemini call.
- If no exact saved response exists, or the interrupted run was one-time
  content, use `mark-run-interrupted` only after user confirmation. A later run
  still needs explicit retry authorization.
- If multiple responses claim the same run or any binding fails, stop and
  investigate.

## Chunk other long requests

Build requests only for verified missing ranges. Start with one representative
clip and expand sequentially after it succeeds:

```sh
python3 "$skill_dir/scripts/build_gemini_chunk_request.py" \
  --video-url VIDEO_URL \
  --start-seconds START \
  --end-seconds END \
  --prompt PROMPT \
  --output REQUEST_JSON
```

Use full-video timestamps. Save each reusable response separately; synthesize
from reused material in ChatGPT unless a distinct reusable Gemini output is
actually needed.

## Recover Gemini credentials privately

Use the connected Google Drive app and the exact credential contract in
`references/contracts.md`. Retrieve the file without displaying its bytes and
materialize it as `$install/config/youtube-workbench-secrets.env` with mode
`0600`. Never place it in a prompt, tool argument, saved response, request log,
material index, repository, `materials/`, or `workspace/`.

The file can contain `GEMINI_API_KEY` and a separately provisioned
`GEMINI_API_KEY_FALLBACK`. Gemini quota is project-level; duplicate values are
one bucket. If Drive authorization is unavailable, stop and ask the user to
connect it.

## Deliver research

- Cite caption claims with timestamped YouTube links.
- Label Gemini-derived claims and include timestamps when available.
- Distinguish observation, inference, and uncertainty.
- State when only part of a long video was processed.
- Mention saved-material reuse when it prevented a Gemini call.
