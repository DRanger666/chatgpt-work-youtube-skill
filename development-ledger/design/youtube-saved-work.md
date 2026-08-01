# Saved YouTube work

## Contents

- [Status](#status)
- [Purpose](#purpose)
- [Names the release must actually use](#names-the-release-must-actually-use)
- [Files kept on Google Drive](#files-kept-on-google-drive)
- [Normal workflow](#normal-workflow)
- [Finding and reusing saved work](#finding-and-reusing-saved-work)
- [Checking a Gemini transcript](#checking-a-gemini-transcript)
- [Logging and sending a Gemini request](#logging-and-sending-a-gemini-request)
- [Interrupted requests](#interrupted-requests)
- [Same-video processing rule](#same-video-processing-rule)
- [No compatibility layer for the unmerged design](#no-compatibility-layer-for-the-unmerged-design)
- [Required tests](#required-tests)
- [Deliberately deferred work](#deliberately-deferred-work)

## Status

This document replaces the earlier cache-v3 and single-writer designs. The
feature branch remains blocked from merge and must not create live saved-work
files until the worker implements and validates this reduced design.

The audited code at `b8598e4` and the design correction at `f65a965` remain
useful development history. They are not the implementation specification.

This commit changes the governing documents only. The old scripts and the
operational instructions that describe them remain temporarily visible so the
worker can replace and test them together. Do not run this feature branch as a
live saved-work system until that replacement is complete.

## Purpose

The system must let a new ChatGPT Work VM continue useful YouTube work without
needlessly repeating Gemini requests.

It must support these ordinary situations:

1. Find transcripts and analyses already saved for a video.
2. Decide whether the saved work covers the user's current question or time
   range.
3. Process only missing time ranges.
4. Continue after Gemini returns an incomplete transcript.
5. Save every successful Gemini response during the normal workflow.
6. Avoid automatically repeating a request that is already known to be
   pending, successful, failed, or interrupted.
7. Rebuild a missing per-video output index by inspecting saved-output files.

The system does not need to reconstruct every possible interruption between
two Google Drive writes. When the evidence is incomplete, it must stop and ask
the user instead of inventing certainty or retrying automatically.

## Names the release must actually use

These are the names the implementation, command-line interfaces, tests, skill
instructions, and Drive files must use. Do not retain the older generic names
as public aliases or compatibility wrappers.

| Purpose | Required name |
|---|---|
| Private Drive folder | `YouTubeVideoWork` |
| Per-video list of reusable saved work | Video output index |
| One saved Gemini response plus checked content information | Saved video output |
| Per-video history of Gemini requests | Gemini request log |
| Portion of a video represented by saved work | Covered time range |
| Check that the logged request is the file being sent | Request-file verification |
| Request left pending by an unavailable session | Interrupted Gemini request |
| Script for saving, finding, and checking outputs | `scripts/saved_video_outputs.py` |
| Script for request history and retry decisions | `scripts/gemini_request_log.py` |
| Output-index filename | `<videoId>--output-index.json` |
| Saved-output filename | `<videoId>--saved-output--<savedOutputId>.json` |
| Request-log filename | `<videoId>--gemini-requests.json` |

The implementation must remove or replace these public names:
`artifact_cache_v3.py`, `gemini_execution_journal_v3.py`,
`YouTubeArtifactCacheV3`, `--manifest.json`, `artifact`, `manifest`,
`execution journal`, `writer`, `lease`, `handoff`, and `reconciliation`.

Internal variable names, command names, and JSON fields must follow the same
vocabulary. Use `fileFormatVersion`, `savedOutputs`, `savedOutputId`,
`outputType`, `outputFormat`, `coveredTimeRanges`, `requestId`, and
`requestStatus`. Do not retain `schemaVersion`, `artifacts`, `artifactId`,
`validCoverage`, or the old writer-management commands in the replacement
files.

The saved-work script must expose plain command names equivalent to:
`init-index`, `save-output`, `add-to-index`, `rebuild-index`, `find-outputs`,
`verify-selected`, and `plan-missing-ranges`. The request-log script must
expose command names equivalent to: `init-log`, `start-request`,
`verify-request`, `finish-request`, `mark-interrupted`, and `authorize-retry`.
The worker may combine commands when that removes duplicated input or an
unsafe intermediate step, but it must not restore the old terminology.

## Files kept on Google Drive

The normal system keeps three kinds of files on Drive. Each answers a
different question.

Do not split one Gemini success into a separate raw-result file and a separate
reusable-output file. The saved video output below preserves both the exact
response text and the checked content information. That keeps index rebuilding
possible without creating another file relationship to maintain.

### Saved video output

Questions answered: **What did Gemini return, and what useful video material
can be verified from that response?**

Create one self-contained JSON file for every successful Gemini response in
the normal workflow. Build it by reading the actual request and response
files. Do not let an agent supply a covered time range or an output format that
contradicts those files. It contains:

- `fileFormatVersion`;
- normalized `videoId`;
- `savedOutputId`;
- `outputType` and `outputFormat`;
- `timestampsRelativeTo` and `languagePolicy`;
- mechanically checked `coveredTimeRanges`;
- `taskDescription` when later analysis review needs it;
- `reusable` and, when false, a plain `unusableReason`;
- `responseSha256`; and
- `responseJsonText`, containing the exact safe JSON text written by
  `gemini_request.py`.

Calculate `responseSha256` from the exact UTF-8 bytes of `responseJsonText`.
Calculate `savedOutputId` from a stable JSON representation of `videoId`,
`outputType`, `outputFormat`, `timestampsRelativeTo`, `languagePolicy`,
`coveredTimeRanges`, `taskDescription` when present, `reusable`,
`unusableReason` when present, and `responseSha256`. Do not include request ID,
prompt, model, credential choice, routing attempts, or other request-run
history in `savedOutputId`.

Write saved-output JSON in one deterministic format and hash the stored file
bytes separately when adding it to the video output index. This distinguishes
three things without creating three records: the exact Gemini response, the
identity of the saved video material, and the integrity of the Drive file.

The saved-output file is never edited. A malformed response is still saved
with `reusable` set to false and no covered time range, but it is not added to
the video output index. If checking rules later change, create a new
saved-output file with a new output-format version instead of rewriting the
old one.

For a structured output such as `gemini-transcript` version `1`, `reusable`
means the named checker passed. For a free-form analysis, it means the response
is readable and can be shown as a candidate together with its task
description; it does not mean that the analysis automatically answers a later
question. Formats without a deterministic checker always require content
review before reuse.

The file contains no API key, authorization header, credential fragment,
credential fingerprint, or routing-bucket secret.

### Video output index

Question answered: **Which saved outputs are useful for this video?**

Use one predictable output-index file per normalized YouTube video ID. Its
top-level fields are `fileFormatVersion`, `videoId`, `savedOutputs`, and
`updatedAt`. Each `savedOutputs` entry contains only information needed to
find and reuse a saved output:

- `savedOutputId`, `driveFileId`, `fileName`, and `fileSha256`;
- `outputType`, such as transcript, translation, visual analysis, or an answer
  to a specific question;
- `outputFormat`, containing its name and version;
- `timestampsRelativeTo`;
- `languagePolicy`;
- verified `coveredTimeRanges`; and
- `taskDescription` when an analysis requires human or agent review.

The output index does not contain Gemini request status, request hashes,
network attempts, cooldowns, retry reasons, session IDs, or interruption
history.

Only a checked, reusable saved output may be listed. Never edit a saved output
to correct it. Save a new output and update the index.

### Gemini request log

Question answered: **Was this Gemini request already sent, and what is known
about it?**

Use one request-log file per normalized video ID. Its top-level fields are
`fileFormatVersion`, `videoId`, `requests`, and `updatedAt`. Each request entry
contains:

- `requestId`;
- normalized `videoId` and `requestedTimeRange`;
- `endpoint`, `model`, and `requestMethod`;
- `exactRequestSha256` for the exact request-file bytes;
- `normalizedRequestSha256` for normalized request JSON;
- `requestStatus`: `pending`, `succeeded`, `failed`, or `interrupted`;
- `startedAt` and `updatedAt`;
- safe `routingAttempts` and `cooldownUntil` information returned by
  `gemini_request.py`;
- `savedOutputId` after success;
- `savedOutputReusable` and, when false, `savedOutputUnusableReason`; and
- `retryAuthorization` with its reason when required.

A retry authorization applies to one `requestId`, records `authorizedAt`, its
plain reason, and `usedAt`, and is consumed by one retry. Retrying does not
create a different request ID merely to evade the earlier history; it appends
the new routing attempts to the same request entry.

The request log does not answer whether saved material covers a later task.
That decision belongs to the video output index.

## Normal workflow

For each video:

1. Normalize the URL to a video ID.
2. Find or rebuild the video output index.
3. Find saved outputs compatible with the requested output type, format,
   language, timestamp policy, and time range.
4. Download and verify only the selected saved-output files.
5. Compute missing time ranges.
6. Use YouTube MCP captions where they can supply the missing transcript.
7. Construct a Gemini request only for work still missing.
8. Read the exact request file into the Gemini request log and save its
   `pending` entry to Drive.
9. Verify the same request file immediately before Gemini credentials are
   loaded.
10. Send one Gemini request at a time.
11. Check the successful Gemini response and save the resulting saved-output
    file to Drive, including an unusable record when checking fails.
12. Finish the request-log entry with the saved-output reference.
13. Add the saved output to the video output index only when it is reusable.

Do not select a Gemini credential or construct requests for time ranges already
covered by verified saved work.

## Finding and reusing saved work

Search by what the user needs, not by the wording or serialization of an old
Gemini request.

Represent each covered time range as integer milliseconds with `startMs`
included and `endMs` excluded. Reject negative, empty, or reversed ranges.
Sort ranges and merge overlaps or touching boundaries before saving or
planning combined work.

For transcript-like work:

1. Select output-index entries with the same video ID, output type,
   output-format version, timestamp policy, and language requirements.
2. Combine their verified covered time ranges.
3. Determine whether one response contains the requested range or several
   saved outputs jointly cover it.
4. Treat incomplete responses as covering only the verified portion.
5. Download only the files selected to satisfy the request.
6. Verify each downloaded file against its recorded SHA-256 before using it.
7. Recalculate missing ranges if a selected file is absent or invalid.

For arbitrary analyses, show the task description and relevant time range.
Require human or agent review before deciding that an earlier analysis answers
a new question. Do not automatically equate paraphrased prompts.

If the output index is missing, list that video's saved-output files, check
them, and rebuild the index from files marked reusable. Arbitrary analyses
remain candidates requiring task-description review; rebuilding the index
does not declare them equivalent to a new question. Create an empty index only
after confirming that no saved output for the video can be indexed.

Rebuilding must not trust a stored `reusable` flag or covered time by itself.
Recalculate the saved-output ID and response hash, rerun the named checker for
structured formats, and compare the recalculated content information with the
stored fields before adding an entry.

## Checking a Gemini transcript

The JSON format requested from Gemini is an instruction, not proof that Gemini
obeyed it. `scripts/saved_video_outputs.py` must check transcript responses
before they can enter the output index.

For transcript format `gemini-transcript` version `1`:

1. Extract the generated JSON from the Gemini response.
2. Require exactly the documented fields and types.
3. Parse all timestamps as full-video `MM:SS.mmm`; the minute part may exceed
   `99`.
4. Require the returned clip start and end to match the request file.
5. Require every segment to have increasing start and end timestamps inside
   the returned clip. Permit overlapping speech, but require segments to be
   ordered by start time.
6. Check `completed_through_timestamp`, `transcription_complete`,
   `truncation_detected`, and Gemini's finish reason together.
7. Derive the covered time range from the requested clip start through the
   verified completed-through timestamp.

No caller may supply or override transcript covered time. A complete
transcript covers the full requested clip. A valid incomplete transcript
covers only its verified portion, and the remaining range is processed with a
smaller or otherwise changed request. A malformed response remains saved with
`reusable` set to false but contributes no covered time.

Do not repeat an identical successful request automatically merely because its
saved output was unusable. Show the saved output and require the user to approve
an identical retry or change the request.

## Logging and sending a Gemini request

The request-log tool must build the request entry by reading the actual
request file. Do not require an agent to copy the request into a second
request-description file.

Request ID is derived from normalized request JSON together with the endpoint,
model, method, normalized video ID, and requested time range. JSON whitespace,
object-key order, and equivalent YouTube URL spelling must not create a new
request ID. Prompt wording, model, generation settings, video ID, or clip
bounds remain meaningful request differences.

For this purpose, normalize the request by parsing the JSON, replacing every
supported YouTube URL with the normalized video ID representation, sorting
object keys, and writing JSON without insignificant whitespace. Do not reorder
arrays or rewrite prompt text.

The pending entry also stores the exact request-file SHA-256. Immediately
before loading a Gemini credential, `gemini_request.py` must verify:

- the exact request-file hash;
- the normalized request hash and request ID;
- the video ID in every supplied YouTube URI;
- the start and end offsets;
- the endpoint, model, and method; and
- that the matching request-log entry is still `pending`.

Any mismatch stops before network access.

One logged Gemini request may contain only one normalized YouTube video ID.
For comparisons, process each video separately and compare the saved outputs
afterward; do not place a multi-video request inside one per-video log.

Before starting a request, apply these rules:

- `pending`: do not send another copy;
- `succeeded`: reuse the saved output; an identical retry requires explicit
  user authorization;
- `failed`: require a recorded retry reason, respect the saved cooldown, and
  never repeat an unchanged terminal request error; and
- `interrupted`: require explicit user authorization and a recorded reason.

Preserve each safe primary, fallback, and bounded transient attempt returned
by the router. Validate timestamp order, HTTP status, classification, selected
credential alias, and final routing status before saving them. Never store
credential values or fingerprints.

## Interrupted requests

A request may be interrupted when its Drive entry remains `pending` but the
Work session that started it cannot be confirmed as active. Elapsed time alone
does not prove that the session stopped. The system may know that the request
was prepared; it may not know whether Gemini received it or returned a
response.

When a later session encounters such an entry:

1. stop before calling Gemini;
2. show the user the video, requested time range, start time, request ID, and
   any saved attempt or response evidence;
3. ask the user to confirm that the earlier session is no longer doing this
   work and whether to mark the request `interrupted`;
4. record the user's decision and reason; and
5. retry only after explicit authorization and any saved cooldown.

An independently verified saved output may still be useful, because useful
video material does not depend on knowing which request produced it. Do not,
however, automatically claim that an unlinked saved output completed the
pending request. Show it as evidence during the user's decision. Do not add a
two-phase response-upload protocol, invent missing network attempts, infer
that the request failed, or claim exactly-once processing.

The normal write order remains:

```text
save pending request → call Gemini → save output → finish request log
```

A VM can disappear between those steps. That rare ambiguity is accepted and
resolved by the user, not by an automatic crash-handling system.

## Same-video processing rule

Do not intentionally process the same video in two write-capable Work sessions
at the same time. Concurrent read-only use of saved outputs is allowed, and
different videos may be processed independently.

Google Drive cannot acquire a lock and replace a file as one indivisible
operation. Therefore the system does not implement session ownership,
expiry-based takeover, handoff commands, or automatic takeover. A pending
request blocks later sequential work, but two truly simultaneous sessions can
still race. State this limitation plainly rather than claiming mutual
exclusion.

## No compatibility layer for the unmerged design

No live files from the unmerged cache-v3 implementation have been created, so
the implementation can adopt the new names without migration or compatibility
aliases.

The new Drive folder and all three file formats start at file-format version
`1`. Normal code must not import, search, migrate, or fall back to cache-v2
files.
Old cache-v2 records may remain temporarily as read-only comparison evidence
and may be deleted separately after representative validation.

The implementation must replace the old script names, tests, Drive folder,
filenames, command names, JSON fields, skill instructions, contracts, and
README descriptions together. Do not leave a mixed vocabulary in the release.

## Required tests

All tests are offline unless a later controlled Drive check is explicitly
approved.

### Saved-work search

- exact, containing, combined, overlapping, incomplete, incompatible, and
  missing covered time ranges;
- output-index rebuilding from saved outputs;
- empty-index refusal until saved-output enumeration is confirmed;
- selected-file-only download planning and replanning after a missing or
  invalid file;
- arbitrary-analysis review by task description; and
- complete isolation from cache v2.

### Transcript checking

- complete and incomplete transcripts;
- truncation flag and finish-reason consistency;
- malformed or missing fields;
- segment and clip-bound ordering;
- timestamps beyond 99 minutes;
- request/response clip mismatch; and
- unusable response saved without output-index covered time.

### Gemini request safety

- request JSON formatting changes preserve request ID but change exact-file
  hash;
- mismatched request file, video URI, time range, endpoint, model, method, or
  pending entry stops before credential loading;
- successful, failed, pending, and interrupted duplicate handling;
- explicit retry reasons and cooldown enforcement;
- unchanged terminal request failure rejection;
- routing-attempt consistency; and
- no credential material in any saved file.

### Interruption behavior

- a pending request from an unavailable session stops;
- no automatic retry or claim that an unlinked output completed a request;
- explicit user authorization is recorded before another request; and
- no writer, lease, handoff, reconciliation, or two-phase-upload interface
  remains.

## Deliberately deferred work

Do not add any of the following without observed need and a new design review:

- automatically treating an unlinked saved output as proof that a pending
  request completed;
- two-phase response commits;
- automatic reconstruction of unknown network outcomes;
- cross-session atomic locking or an external coordination service;
- vector search or automatic semantic equivalence for analyses;
- batch Gemini processing;
- parallel Gemini video requests; or
- permanent cache-v2 compatibility.
