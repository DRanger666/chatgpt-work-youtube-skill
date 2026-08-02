# Gemini response storage and search

## Scope and authority

This document defines only the Google Drive files used to preserve, index,
find, and verify reusable Gemini video material. It does not define the full
YouTube workflow, MCP tool use, Gemini credential routing, or final research
response.

[`SKILL.md`](../../SKILL.md) is the sole authority for runtime source order.
The skill tries the YouTube MCP first and uses sufficient MCP output directly.
MCP output is temporary and is not written into the Gemini material index.
This design is entered only when the MCP path leaves information missing.

Gemini request execution and request history are defined separately in
[`gemini-request-execution.md`](gemini-request-execution.md). Exact commands,
paths, and current file fields are summarized for the running skill in
[`references/contracts.md`](../../references/contracts.md).

## Status

The initial implementation was validated offline before any live files were
created in `YouTubeVideoWork` or any Gemini generation quota was consumed.

LEDGER-014 blocks live use until the redundant per-record timestamp-coordinate
field is removed from request logging, saved responses, material indexes, and
search. Video-start time is a system and output-format rule, not stored or
queried as variable metadata.

The design replaces the request-byte lookup and the later artifact/manifest
model. Cache-v2 files remain outside this system and are not imported,
searched, migrated, or used as fallback data.

## Purpose

The saved-material system answers two questions:

1. Which reusable Gemini responses already exist for one YouTube video?
2. Do those responses provide compatible material for the requested time
   range, or must the skill request missing material from Gemini?

Prompt wording and request-file serialization are not material search keys.
The system searches by video, controlled output type, output format, applicable
language requirements, and checked covered time.

## Drive files

Use the private `YouTubeVideoWork` Drive folder. For each normalized video ID,
this design owns:

- exactly one `<videoId>--video-material-index.json`; and
- zero or more
  `<videoId>--gemini-response--<outputType>--<savedResponseId>.json` files.

The separate `<videoId>--gemini-requests.json` file is owned by the Gemini
request-execution design. Request history never belongs in the material index.

### Saved Gemini response

One successful `video_material` run creates one never-edited, self-contained
saved-response file. Successful `task_specific_observation` and
`direct_answer` runs create no Drive response file.

A saved response contains:

- `fileFormatVersion` and normalized `videoId`;
- `savedResponseId`;
- the verified `requestId`, `runNumber`, and `exactRequestSha256`;
- fixed `contentClass`, controlled `outputType`, and compatible
  `outputFormat`;
- the exact requested `sourceTimeRange`;
- applicable `languagePolicy`;
- the complete safe `routerResult` retained from the matching run;
- `responseSha256` and the exact UTF-8 response text in `responseJsonText`;
- `formatCheck` exactly when the registered output format has a deterministic
  checker; and
- mechanically derived `coveredTimeRanges` only when that checker produces
  them.

The saver reads the actual pending request, router result, and response file.
It copies classification and source fields from the request log instead of
accepting replacements from the caller. It independently hashes the exact
response bytes and requires equality with the router's `responseSha256` before
writing a file.

Calculate `savedResponseId` from deterministic JSON containing every immutable
saved field except `savedResponseId` and the repeated `responseJsonText`;
`responseSha256` already represents those exact bytes. A different authorized
run therefore creates a different saved-response ID even when Gemini returns
identical bytes. The response hash still reveals identical returned content.

Hash the complete stored file separately when adding it to the material index.
Never edit an existing saved response. A changed response contract uses a new
output-format version rather than reinterpreting old files.

### Video material index

The index answers: **Which saved Gemini responses contain reusable material
for this video?**

Its top-level fields are `fileFormatVersion`, `videoId`, `materials`, and
`updatedAt`. Each entry contains only fields used to find and verify material:

- `savedResponseId`, Drive file ID, predictable filename, and stored-file
  SHA-256;
- controlled `outputType` and `outputFormat`;
- checked `coveredTimeRanges`;
- applicable language policy; and
- a concise `materialDescription` when the output type alone is insufficient.

The index never contains prompts, request IDs, run numbers, Gemini status,
routing attempts, cooldowns, retry reasons, session information, or response
text. Those fields would make a search structure carry request history it does
not need.

Entries are identified by `savedResponseId`, not by interval. Add every new
ID while preserving existing entries with the same or overlapping interval or
another output type. Adding an existing ID is an idempotent no-op only after
the stored entry and saved file verify as identical.

## Which Gemini responses are retained

Every Gemini request declares one `contentClass` before the network call:

| `contentClass` | Meaning | Drive response storage |
|---|---|---|
| `video_material` | Reusable source material of one controlled type | Save the complete run-linked response; index it only after the required check or review |
| `task_specific_observation` | Narrow sensory evidence for the active ChatGPT task | Do not save response text or add an index entry |
| `direct_answer` | Gemini's own task-specific reasoning or answer | Do not save response text or add an index entry |

Classification is fixed in the logical request before execution. Never promote
a one-time response to `video_material` after seeing its contents. The request
log records deliberate non-storage for a verified one-time success so it
cannot be confused with a failed Drive write.

The reusable output registry is intentionally small:

| `outputType` | Required `outputFormat` | Admission rule |
|---|---|---|
| `transcript` | `gemini-transcript` version `1` | Deterministic transcript check must pass |
| `summary` | `gemini-free-form-text` version `1` | ChatGPT review before indexing |
| `systematic_visual_description` | `gemini-free-form-text` version `1` | ChatGPT review before indexing |
| `systematic_onscreen_text` | `gemini-free-form-text` version `1` | ChatGPT review before indexing |

Reject every unregistered type, format, or type-format pairing. Translation is
derived on demand by ChatGPT from original-language transcripts or systematic
onscreen text; it is not saved, indexed, or searched as a Gemini output.

`gemini-free-form-text` promises ordinary text, not a machine-readable
structure. It has no `formatCheck`. ChatGPT reads it once before admission and
supplies only conservative covered time inside the response's declared source
range. Do not manufacture a format-check result for prose.

## Time representation

Every `startMs` and `endMs` value in this system is an offset from the beginning
of the YouTube video. The `gemini-transcript` version `1` format defines its
`MM:SS.mmm` strings the same way. This is one fixed interpretation, not a
per-response choice or a search condition.

Partial processing remains independently reusable. For example, a response
created from minutes 10 through 20 records `sourceTimeRange` and checked
coverage between `600000` and `1200000`, while its transcript labels run from
`10:00.000` through `20:00.000`. Save and index that response immediately;
minutes 0 through 10 do not need to exist first.

Do not store or accept `timestampsRelativeTo`, `timestampBasis`, or a renamed
equivalent in a request-log entry, saved response, material-index entry, or
material query. If a future output genuinely requires another coordinate
system, normalize it to video-start offsets before storage or define a new
output-format version through a separate design decision.

## Searching saved Gemini material

The caller supplies normalized video identity, controlled output type,
compatible output format, requested half-open millisecond ranges, and any
applicable language requirement.

Search in this order:

1. Open the predictable per-video material index.
2. Filter entries by output type and output-format version.
3. Apply the declared language requirement when one exists.
4. Calculate exact, containing, or combined coverage from the readable index.
5. Select the smallest suitable set of entries and return their saved-response
   IDs plus any missing ranges.
6. Download only selected files and verify each stored-file hash, response ID,
   response hash, and immutable metadata.
7. Replan around any missing, stale, or invalid selected file.
8. Expose missing ranges for new Gemini request construction only after the
   selected files have been verified.

The missing-range output is the only input accepted by the deterministic
chunk planner. The planner splits each missing range independently and never
fills a gap that search already classified as covered. `SKILL.md` owns the
runtime choice of chunk size and overlap; `references/contracts.md` records
the exact command and the observed long-video evidence behind those defaults.

Use `savedResponseId` for direct retrieval and verification only after
semantic fields select a response. Never use a request hash or response ID as
the primary answer to whether compatible material exists.

Represent time as integer milliseconds with `startMs` included and `endMs`
excluded. Reject negative, empty, or reversed ranges. Sort ranges and merge
overlapping or touching boundaries before calculating missing coverage.

Transcript coverage does not satisfy a visual-information requirement. A
summary does not displace a transcript, visual description, or onscreen-text
record merely because their intervals match.

## Transcript format check

The Gemini response schema is an instruction to Gemini, not proof that the
returned transcript obeys it. Before a `gemini-transcript` version `1`
response can enter the index, the registered checker must:

1. extract the generated JSON from the Gemini response envelope;
2. require exactly the documented transcript and segment fields and types;
3. parse `MM:SS.mmm` timestamps as offsets from the beginning of the YouTube
   video, with a minute part of at least two digits that can exceed `99`;
4. require returned clip bounds to equal the requested clip;
5. require ordered, in-range segment times and valid controlled values;
6. check `completed_through_timestamp`, `transcription_complete`,
   `truncation_detected`, and Gemini's finish reason together; and
7. derive coverage from requested clip start through the verified completed
   timestamp.

Callers never supply transcript coverage. A complete response covers the full
requested clip. A valid incomplete response covers only its verified portion.
A malformed response remains preserved with a failed `formatCheck` and no
covered time, so it cannot enter the index.

An incomplete transcript is continued with a smaller or otherwise changed
request for its unfinished interval. Do not automatically repeat the identical
successful request because its returned format was incomplete or malformed.

## Rebuilding a missing index

If the material index is absent, enumerate that video's saved-response files.
For each candidate:

- verify its filename, stored bytes, response ID, response hash, video ID, and
  request binding;
- rerun the registered checker for structured output;
- require a fresh ChatGPT review and explicit admission decision for free-form
  output; and
- add every eligible distinct response without collapsing equal intervals.

Create an empty index only after confirming that no saved `video_material`
response can be admitted. A failed structured response or a reviewed but
rejected free-form response remains saved and unindexed.

## Supported limits

- Drive replacement is not an atomic append or compare-and-set operation.
- Concurrent reads are allowed, but the runtime must not intentionally use two
  write-capable sessions for the same video.
- The system does not provide semantic search across one-time observations or
  direct answers because their response text is deliberately not stored.
- Cache-v2 discovery, migration, fallback, and permanent compatibility are
  excluded.

Do not add two-phase response commits, automatic promotion of one-time output,
or response-retention machinery without observed need and a new design review.

## Required offline validation

- all four registered reusable output types and rejection of every other type;
- exact, containing, combined, overlapping, incomplete, incompatible, and
  missing coverage;
- preservation of distinct outputs sharing one interval;
- selected-file-only verification and replanning around stale files;
- index rebuilding and refusal to initialize empty before enumeration;
- free-form review, source-range bounds, and absence of fabricated checks;
- complete, partial, truncated, malformed, and long-timestamp transcripts;
- independent saving and reuse of a focused partial interval whose time values
  remain offsets from the beginning of the video;
- request/response clip mismatch and false-coverage rejection;
- rejection of every removed timestamp-coordinate field at request-log,
  saved-response, material-index, and material-query boundaries;
- response-byte, saved-response identity, and stored-file integrity checks;
- no saved response or index entry for either one-time content class; and
- complete isolation from cache v2.
