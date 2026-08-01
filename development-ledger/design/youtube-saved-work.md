# Saved Gemini responses and reusable YouTube material

## Contents

- [Status](#status)
- [Purpose](#purpose)
- [Names the release must actually use](#names-the-release-must-actually-use)
- [Files kept on Google Drive](#files-kept-on-google-drive)
- [Classify each Gemini request before sending it](#classify-each-gemini-request-before-sending-it)
- [Use Gemini as a video sensor](#use-gemini-as-a-video-sensor)
- [Normal workflow](#normal-workflow)
- [Finding and reusing saved work](#finding-and-reusing-saved-work)
- [Checking declared response formats](#checking-declared-response-formats)
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

1. Find reusable transcripts, translations, summaries, descriptions, and
   systematic visual records already saved for a video.
2. Decide whether that video material covers the user's current need and time
   range.
3. Process only missing time ranges.
4. Continue after Gemini returns an incomplete transcript.
5. Save every successful Gemini response during the normal workflow, including
   narrowly task-specific observations and direct answers that must not enter
   ordinary material search.
6. Avoid automatically repeating a request that is already known to be
   pending, successful, failed, or interrupted.
7. Rebuild a missing per-video material index by inspecting saved-response
   files.

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
| Per-video list of reusable source material | Video material index |
| One complete successful Gemini response plus its classification | Saved Gemini response |
| Per-video history of Gemini requests | Gemini request log |
| Portion of a video represented by saved work | Covered time range |
| Check that the logged request is the file being sent | Request-file verification |
| Request left pending by an unavailable session | Interrupted Gemini request |
| Script for saving responses and finding reusable material | `scripts/saved_gemini_responses.py` |
| Script for request history and retry decisions | `scripts/gemini_request_log.py` |
| Material-index filename | `<videoId>--video-material-index.json` |
| Saved-response filename | `<videoId>--gemini-response--<savedResponseId>.json` |
| Request-log filename | `<videoId>--gemini-requests.json` |

The implementation must remove or replace these public names:
`artifact_cache_v3.py`, `gemini_execution_journal_v3.py`,
`YouTubeArtifactCacheV3`, `--manifest.json`, `artifact`, `manifest`,
`execution journal`, `writer`, `lease`, `handoff`, and `reconciliation`.

Internal variable names, command names, and JSON fields must follow the same
vocabulary. Use `fileFormatVersion`, `materials`, `savedResponseId`,
`contentClass`, `outputType`, `outputFormat`, `coveredTimeRanges`, `requestId`,
and `requestStatus`. Do not retain `schemaVersion`, `artifacts`, `artifactId`,
`savedOutputId`, `validCoverage`, or the old writer-management commands in the
replacement files.

The saved-response script must expose plain command names equivalent to:
`save-response`, `init-material-index`, `add-to-material-index`,
`rebuild-material-index`, `find-material`, `verify-selected`, and
`plan-missing-ranges`. The request-log script must expose command names
equivalent to: `init-log`, `start-request`, `verify-request`, `finish-request`,
`mark-interrupted`, and `authorize-retry`. The worker may combine commands when
that removes duplicated input or an unsafe intermediate step, but it must not
restore the old terminology.

## Files kept on Google Drive

The normal system keeps three kinds of files on Drive. Each answers a
different question.

For each normalized video ID, keep exactly one video material index, exactly
one Gemini request log, and zero or more saved Gemini response files. These are
three file types for one video, not a fixed three-file tuple: each successful
Gemini call can add another saved response.

Do not split one Gemini success into a separate raw-result file and a separate
reusable-material file. The saved Gemini response below preserves the exact
response text together with the content classification declared before the
request. The material index points to selected response files instead of
copying their contents.

### Saved Gemini response

Question answered: **What exactly did Gemini return?**

Create one self-contained JSON file for every successful Gemini response in
the normal workflow. Build it by reading the actual request and response
files and the matching pending request-log entry. It contains:

- `fileFormatVersion`;
- normalized `videoId`;
- `savedResponseId`;
- predeclared `contentClass`;
- `outputType` and `outputFormat`;
- `sourceTimeRange`, copied from the matching request's requested range;
- `timestampsRelativeTo` and `languagePolicy` when applicable;
- mechanically derived `coveredTimeRanges` only when the registered structured
  format checker produces them;
- `formatCheck` exactly when the declared output format requires one;
- `responseSha256`; and
- `responseJsonText`, containing the exact safe JSON text written by
  `gemini_request.py`.

Calculate `responseSha256` from the exact UTF-8 bytes of `responseJsonText`.
Calculate `savedResponseId` from a stable JSON representation of `videoId`,
`contentClass`, `outputType`, `outputFormat`, `sourceTimeRange`, applicable
checked content metadata, and `responseSha256`. The source range prevents
identical text returned for different parts of one video from being treated as
the same saved response. Do not include request ID, prompt, model, credential
choice, routing attempts, or other request-run history. An identical
classified response for the same source range therefore has the same identity
regardless of which Gemini request run produced it.

Write saved-response JSON in one deterministic format and hash the stored file
bytes separately when adding it to the video material index. Never edit an
existing saved-response file. If a checker changes what a structured response
means, introduce a new output-format version rather than reinterpreting the old
file.

There is no global `reusable` field and no `unusableReason`. Reuse is a
relationship between a response and a later need, not an intrinsic truth about
all Gemini text. Admission to the video material index is the durable decision
that a response is reusable source material. A malformed structured response
is still preserved in full, with a failed `formatCheck`, but cannot enter that
index.

Do not add general `contentCheckStatus` or `contentCheckFailure` fields. A
deterministic `formatCheck` exists only for a declared format contract;
free-form material review is represented solely by admission to the material
index.

The file contains no API key, authorization header, credential fragment,
credential fingerprint, or routing-bucket secret.

### Video material index

Question answered: **Which saved responses contain reusable source material
for this video?**

Use one predictable material-index file per normalized YouTube video ID. Its
top-level fields are `fileFormatVersion`, `videoId`, `materials`, and
`updatedAt`. Every entry represents a saved response whose predeclared
`contentClass` is `video_material`. Each entry contains only information needed
to find and reuse that material:

- `savedResponseId`, `driveFileId`, `fileName`, and `fileSha256`;
- `outputType`, such as transcript, translation, summary, visual description,
  or systematic slide text;
- `outputFormat`, containing its name and version;
- `timestampsRelativeTo` and `languagePolicy` when applicable;
- verified `coveredTimeRanges`; and
- a short `materialDescription` only when the output type alone does not
  adequately describe the reusable material.

The material index does not contain prompts, task-specific observations,
direct answers, Gemini request status, request hashes, network attempts,
cooldowns, retry reasons, session IDs, or interruption history.

For a structured output, its required deterministic format check must pass
before admission. For a free-form `video_material` response, ChatGPT must read
it once and decide whether it is suitable reusable source material. The index
entry records that admission; do not add another content-review state to the
saved response. During that review, any indexed covered time must be a
conservative subset of the response's `sourceTimeRange`. It is index metadata,
not a fabricated mechanically checked field in the free-form response file.

### Gemini request log

Question answered: **Was this Gemini request already sent, and what is known
about it?**

Use one request-log file per normalized video ID. Its top-level fields are
`fileFormatVersion`, `videoId`, `requests`, and `updatedAt`. Each request entry
contains:

- `requestId`;
- normalized `videoId` and `requestedTimeRange`;
- the predeclared `contentClass`;
- `promptText`, copied exactly from the actual request file;
- `outputType` and `outputFormat`;
- `endpoint`, `model`, and `requestMethod`;
- `exactRequestSha256` for the exact request-file bytes;
- `normalizedRequestSha256` for normalized request JSON;
- `requestStatus`: `pending`, `succeeded`, `failed`, or `interrupted`;
- `startedAt` and `updatedAt`;
- safe `routingAttempts` and `cooldownUntil` information returned by
  `gemini_request.py`;
- `savedResponseId`, `savedResponseDriveFileId`, and
  `savedResponseFileSha256` after success; and
- `retryAuthorization` with its reason when required.

A retry authorization applies to one `requestId`, records `authorizedAt`, its
plain reason, and `usedAt`, and is consumed by one retry. Retrying does not
create a different request ID merely to evade the earlier history; it appends
the new routing attempts to the same request entry.

The exact prompt is retained so a later Work session can understand what the
request asked Gemini to observe or answer. The request log supports duplicate
prevention and resuming the same known request. It is not a semantic search
index for future tasks and does not answer whether a response is reusable video
material. That decision belongs to the video material index.

## Classify each Gemini request before sending it

Every Gemini request must declare exactly one `contentClass` before request
construction and before any network call:

| `contentClass` | Intended content | Material-index rule |
|---|---|---|
| `video_material` | Broadly reusable transcript, translation, summary, description, systematic visual record, or systematic OCR | May enter after the required format check or one free-form content review |
| `task_specific_observation` | Narrow sensory evidence requested for the current ChatGPT task, such as text on one board, values in one chart, or actions in one short scene | Never enters ordinary material search |
| `direct_answer` | Gemini's own reasoning or answer to a question | Never enters ordinary material search; use only deliberately |

The class describes why the request is being made, not whether the returned
text later looks impressive. Bind it into the pending request-log entry, but do
not make this local classification part of request identity. The
response-saving command must copy it from that entry and must not accept a
replacement class from the caller. Do not silently promote a task-specific
observation or direct answer into `video_material` after seeing the response.

A purpose-specific builder may fix a class when there is no ambiguity; the
transcript builder fixes `video_material`. A generic prompt builder must require
an explicit class and must not silently default to `video_material` or
`direct_answer`. Apply the same rule to `outputType` and `outputFormat` whenever
the builder cannot derive them from a named mode.

Preserve the exact successful response for all three classes and link it from
the request log. Only `video_material` may be added to the material index.
Task-specific observations and direct answers remain available through the
known request that produced them, which is sufficient for the current task and
for preventing an identical repeat without bloating later material searches.
This preservation is required: a request must not be marked `succeeded` and
thereby block repetition while its returned content is unavailable to a fresh
Work VM.

Do not add a separate task index, automatic semantic promotion, retention
policy, or cleanup subsystem in this release. Saved JSON responses are small;
introduce cleanup only after observed storage pressure establishes a real need.

## Use Gemini as a video sensor

ChatGPT remains responsible for reasoning. Use Gemini when the task requires
video perception that ChatGPT does not possess directly: reading boards or
slides, extracting chart values, identifying visible objects, describing
actions, or locating a visual change.

Prefer prompts such as:

- "Transcribe the text visible on the board from 12:10 to 12:35."
- "Report the labels and values shown in this chart; do not interpret them."
- "Describe the observable actions in this scene in chronological order."

Avoid asking Gemini which interpretation is correct, whether evidence proves
an argument, or what conclusion should be drawn. ChatGPT should obtain the
sensory facts and perform that reasoning itself. If Gemini's own conclusion is
specifically wanted, declare `direct_answer` so it cannot be confused with
source material.

Classify by the work requested, not by grammar. "What text is visible on this
slide?" is still a `task_specific_observation`; a question mark does not make
it a `direct_answer`.

Scope determines the class. Systematically reading every slide in a lecture is
reusable `video_material`; reading one slide to resolve the user's present
question is a `task_specific_observation`. The latter may be consumed
immediately by ChatGPT but is deliberately absent from ordinary future search.

## Normal workflow

For each video:

1. Normalize the URL to a video ID.
2. Find or rebuild the video material index.
3. Find material compatible with the requested output type, format,
   language, timestamp policy, and time range.
4. Download and verify only the selected saved-response files.
5. Compute missing time ranges.
6. Use YouTube MCP captions where they can supply the missing transcript.
7. Identify any remaining material or visual-sensory gap.
8. Declare the request's `contentClass`, `outputType`, and `outputFormat`, then
   construct a Gemini request only for that gap.
9. Read the exact request file and prompt into the Gemini request log and save
   its `pending` entry to Drive.
10. Verify the same request file and declared class immediately before Gemini
    credentials are loaded.
11. Send one Gemini request at a time.
12. Save the complete successful response, including a required format-check
    result when the declared format has a checker.
13. Finish the request-log entry with the saved-response reference.
14. If and only if the class is `video_material`, add the response to the video
    material index after the applicable structured check or free-form review.
15. Give task-specific observations to ChatGPT for reasoning without indexing
    them.

Do not select a Gemini credential or construct a request for a material type
and time range already covered by compatible saved material. Transcript
coverage does not, by itself, satisfy a missing visual observation.

## Finding and reusing saved work

Search by what the user needs, not by the wording or serialization of an old
Gemini request.

Represent each covered time range as integer milliseconds with `startMs`
included and `endMs` excluded. Reject negative, empty, or reversed ranges.
Sort ranges and merge overlaps or touching boundaries before saving or
planning combined work.

For transcript-like material:

1. Select material-index entries with the same video ID, output type,
   output-format version, timestamp policy, and language requirements.
2. Combine their verified covered time ranges.
3. Determine whether one response contains the requested range or several
   saved responses jointly cover it.
4. Treat incomplete responses as covering only the verified portion.
5. Download only the files selected to satisfy the request.
6. Verify each downloaded file against its recorded SHA-256 before using it.
7. Recalculate missing ranges if a selected file is absent or invalid.

Do not search task-specific observations or direct answers when answering a new
question. If existing `video_material` reveals a remaining visual gap, issue a
narrow `task_specific_observation`, let Gemini report the sensory facts, and
reason over those facts in ChatGPT.

If the material index is missing, list that video's saved-response files and
consider only files whose predeclared class is `video_material`. Recalculate
each response ID and response hash. Rerun the registered checker for a
structured format; inspect a free-form response before admitting it again.
Create an empty index only after confirming that no saved `video_material`
response can be indexed.

## Checking declared response formats

`formatCheck` is not optional at agent discretion. Its presence is determined
solely by a fixed output-format registry in the implementation:

- A registered structured format must have a deterministic checker. Its saved
  response must contain `formatCheck.name` and `formatCheck.status`, whose value
  is `passed` or `failed`. A failure also contains one short deterministic
  `failure` value.
- A registered free-form format has no deterministic checker and its saved
  response must not contain `formatCheck`.
- Adding another structured format requires adding its checker and offline
  tests before live use. A caller cannot supply, omit, or choose the checker.

A format check validates only the declared structure and internal consistency:
required fields and types, timestamp syntax and ordering, requested clip
bounds, and completion flags where applicable. It does not judge factual
accuracy, reasoning quality, usefulness, or whether Gemini perceived the
video correctly.

A failed check prevents automatic use under that structured format. The exact
response remains available for inspection, but ChatGPT must not treat its
fields, time range, or completion claim as validated.

Run the required checker regardless of content class. Passing does not make a
`task_specific_observation` or `direct_answer` eligible for the material index.
For structured `video_material`, passing is required for admission. For
free-form `video_material`, ChatGPT reads the response once; adding it to the
index records the acceptance without inventing a `passed` format status.

### Gemini transcript version 1

The JSON format requested from Gemini is an instruction, not proof that Gemini
obeyed it. `scripts/saved_gemini_responses.py` must run the registered
`gemini-transcript` version `1` checker before a transcript can enter the
material index.

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
smaller or otherwise changed request. A malformed response remains saved in
full with a failed format check but contributes no covered time.

Do not repeat an identical successful request automatically merely because its
response failed its format check. Show the saved response and require the user
to approve an identical retry or change the request.

## Logging and sending a Gemini request

The request-log tool must build the request entry by reading the actual
request file. Do not require an agent to copy the request into a second
request-description file.

Request ID is derived from normalized request JSON together with the endpoint,
model, method, normalized video ID, and requested time range. It identifies the
actual Gemini call, not the local purpose assigned to it. JSON whitespace,
object-key order, and equivalent YouTube URL spelling must not create a new
request ID. Prompt wording, model, generation settings, response schema, video
ID, or clip bounds remain meaningful request differences because they change
the request sent to Gemini.

`contentClass`, `outputType`, and the declared `outputFormat` remain immutable
metadata on that request entry. They do not create a different request ID. If
an existing request ID is presented with conflicting local metadata, stop and
show the earlier entry; never use relabelling to permit the same Gemini call
again. A genuinely broader material request must use a meaningfully different
prompt or other content in the request sent to Gemini.

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
- the declared content class, output type, and output format;
- the endpoint, model, and method; and
- that the matching request-log entry is still `pending`.

Any mismatch stops before network access.

One logged Gemini request may contain only one normalized YouTube video ID.
For comparisons, process each video separately and compare the saved responses
afterward; do not place a multi-video request inside one per-video log.

Before starting a request, apply these rules:

- `pending`: do not send another copy;
- `succeeded`: use the linked saved response; an identical retry requires
  explicit user authorization;
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

An independently verified saved response may still contain useful video
material, because material identity does not depend on knowing which request
produced it. Do not, however, automatically claim that an unlinked response
completed the pending request. Show it as evidence during the user's decision.
Do not add a two-phase response-upload protocol, invent missing network
attempts, infer that the request failed, or claim exactly-once processing.

The normal write order remains:

```text
save pending request → call Gemini → save response → finish request log
```

A VM can disappear between those steps. That rare ambiguity is accepted and
resolved by the user, not by an automatic crash-handling system.

## Same-video processing rule

Do not intentionally process the same video in two write-capable Work sessions
at the same time. Concurrent read-only use of saved responses is allowed, and
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

### Video-material search

- exact, containing, combined, overlapping, incomplete, incompatible, and
  missing covered time ranges;
- material-index rebuilding from saved responses whose class is
  `video_material`;
- empty-index refusal until saved-response enumeration is confirmed;
- selected-file-only download planning and replanning after a missing or
  invalid file;
- complete exclusion of task-specific observations and direct answers from
  material search; and
- complete isolation from cache v2.

### Content classification and response preservation

- all three content classes are declared before request construction and bound
  immutably to the request entry without changing request identity;
- relabelling an existing request cannot permit another Gemini call;
- the pending request's class cannot be replaced while saving its response;
- the exact prompt is retained in the request log;
- every successful response is preserved and linked from its request;
- identical response text from different source time ranges receives distinct
  saved-response identities;
- only `video_material` can enter the material index;
- a structured format always runs its registered checker, regardless of
  content class;
- a free-form format never contains a fabricated format-check result; and
- free-form material cannot claim indexed time outside its source range;
- systematic OCR can enter material search while an otherwise similar
  one-slide task-specific observation cannot.

### Transcript checking

- complete and incomplete transcripts;
- truncation flag and finish-reason consistency;
- malformed or missing fields;
- segment and clip-bound ordering;
- timestamps beyond 99 minutes;
- request/response clip mismatch; and
- failed-format response saved without material-index covered time.

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
- no automatic retry or claim that an unlinked response completed a request;
- explicit user authorization is recorded before another request; and
- no writer, lease, handoff, reconciliation, or two-phase-upload interface
  remains.

## Deliberately deferred work

Do not add any of the following without observed need and a new design review:

- automatically treating an unlinked saved response as proof that a pending
  request completed;
- two-phase response commits;
- automatic reconstruction of unknown network outcomes;
- cross-session atomic locking or an external coordination service;
- semantic search across task-specific observations or direct answers;
- automatic promotion of either class into reusable video material;
- response-retention or cleanup machinery without observed storage pressure;
- batch Gemini processing;
- parallel Gemini video requests; or
- permanent cache-v2 compatibility.
