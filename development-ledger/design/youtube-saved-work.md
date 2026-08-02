# Saved Gemini responses and reusable YouTube material

## Contents

- [Status](#status)
- [Purpose](#purpose)
- [Names the release must actually use](#names-the-release-must-actually-use)
- [Files kept on Google Drive](#files-kept-on-google-drive)
- [Controlled reusable output types](#controlled-reusable-output-types)
- [Classify each Gemini request before sending it](#classify-each-gemini-request-before-sending-it)
- [Use Gemini as a video sensor](#use-gemini-as-a-video-sensor)
- [Normal workflow](#normal-workflow)
- [Finding and reusing saved work](#finding-and-reusing-saved-work)
- [Checking declared response formats](#checking-declared-response-formats)
- [Logging and sending a Gemini request](#logging-and-sending-a-gemini-request)
- [Interrupted runs](#interrupted-runs)
- [Same-video processing rule](#same-video-processing-rule)
- [No compatibility layer for the unmerged design](#no-compatibility-layer-for-the-unmerged-design)
- [Required tests](#required-tests)
- [Deliberately deferred work](#deliberately-deferred-work)

## Status

This document replaces the earlier cache-v3 and single-writer designs. The
reduced design, including LEDGER-012's removal of translation from saved and
searchable reusable outputs, is implemented on `feat/artifact-cache-v3` and
validated offline. The branch remains unmerged, the installed skill is
unchanged, and no live Drive files or Gemini requests were created during
implementation.

The audited code at `b8598e4` and the design correction at `f65a965` remain
useful development history. They are not the implementation specification.

The replacement uses the required scripts, commands, filenames, JSON fields,
and plain operational vocabulary without compatibility wrappers. Seventy-two
offline tests pass under four Python hash seeds, including 5,500 actual
material-planner interval cases per run. A representative live validation and
any later cache-v2 cleanup remain separately authorized work.

## Purpose

The system must let a new ChatGPT Work VM continue useful YouTube work without
needlessly repeating Gemini requests.

It must support these ordinary situations:

1. Find reusable transcripts, summaries, descriptions, and systematic visual
   records already saved for a video.
2. Decide whether that video material covers the user's current need and time
   range.
3. Process only missing time ranges.
4. Continue after Gemini returns an incomplete transcript.
5. Save every successful reusable-video-material response. Return
   task-specific observations and direct answers to the active conversation
   without writing their response text to Drive.
6. Avoid automatically repeating a request whose latest run is already known
   to be pending, successful, failed, or interrupted.
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
| One complete successful reusable-material response plus its run binding | Saved Gemini response |
| Per-video history of Gemini requests | Gemini request log |
| One deliberate execution of a logical request | Authorized run |
| One HTTP try made through a particular credential | Routing attempt |
| Portion of a video represented by saved work | Covered time range |
| Check that the logged request is the file being sent | Request-file verification |
| Run left pending by an unavailable session | Interrupted Gemini run |
| Script for saving responses and finding reusable material | `scripts/saved_gemini_responses.py` |
| Script for request history and retry decisions | `scripts/gemini_request_log.py` |
| Material-index filename | `<videoId>--video-material-index.json` |
| Saved-response filename | `<videoId>--gemini-response--<outputType>--<savedResponseId>.json` |
| Request-log filename | `<videoId>--gemini-requests.json` |

The implementation must remove or replace these public names:
`artifact_cache_v3.py`, `gemini_execution_journal_v3.py`,
`YouTubeArtifactCacheV3`, `--manifest.json`, `artifact`, `manifest`,
`execution journal`, `writer`, `lease`, `handoff`, and `reconciliation`.

Internal variable names, command names, and JSON fields must follow the same
vocabulary. Use `fileFormatVersion`, `materials`, `savedResponseId`,
`contentClass`, `outputType`, `outputFormat`, `coveredTimeRanges`, `requestId`,
`runs`, `runNumber`, and `runStatus`. Do not retain `schemaVersion`,
`artifacts`, `artifactId`, `savedOutputId`, `validCoverage`, a singular
top-level `requestStatus`, or the old writer-management commands in the
replacement files.

The saved-response script must expose plain command names equivalent to:
`save-response`, `init-material-index`, `add-to-material-index`,
`rebuild-material-index`, `find-material`, `verify-selected`, and
`plan-missing-ranges`. The request-log script must expose command names
equivalent to: `init-log`, `start-run`, `verify-run`, `finish-run`, and
`mark-run-interrupted`. Starting the same logical request again appends an
authorized run; it does not replace the request entry. For every run after the
first, `start-run` must record the user's authorization and append the pending
run in the same update. Do not create a separate request-level authorization
slot. The worker combines commands only when doing so removes duplicated input
or an unsafe intermediate step; it does not restore the old terminology.

## Files kept on Google Drive

The normal system keeps three kinds of files on Drive. Each answers a
different question.

For each normalized video ID, keep exactly one video material index, exactly
one Gemini request log, and zero or more saved Gemini response files. These are
three file types for one video, not a fixed three-file tuple: each successful
`video_material` call adds another saved response. Task-specific observations
and direct answers add no saved-response file.

Do not split one reusable-material success into a separate raw-result file and
a separate reusable-material file. The saved Gemini response below preserves
the exact response text together with the content classification declared
before the request. The material index points to eligible response files
instead of copying their contents.

### Saved Gemini response

Question answered: **What exactly did Gemini return?**

Create one self-contained JSON file for every successful `video_material`
response. Never create this file for `task_specific_observation` or
`direct_answer`. Build it by reading the actual request and response files and
the matching pending request-log run. It contains:

- `fileFormatVersion`;
- normalized `videoId`;
- `savedResponseId`;
- `requestId`, `runNumber`, and `exactRequestSha256`, copied from the verified
  pending run;
- predeclared `contentClass`;
- `outputType` and `outputFormat`;
- `sourceTimeRange`, copied from the matching request's requested range;
- `timestampsRelativeTo` and `languagePolicy` when applicable;
- mechanically derived `coveredTimeRanges` only when the registered structured
  format checker produces them;
- `formatCheck` exactly when the declared output format requires one;
- the complete safe router result returned for that run, including every
  routing attempt present in that result, its classification and cooldown, the
  terminal attempt time, and the router's `responseSha256`;
- `responseSha256`; and
- `responseJsonText`, containing the exact safe JSON text written by
  `gemini_request.py`.

`gemini_request.py` calculates `responseSha256` from the exact bytes of the
response file it writes and includes that hash in every successful safe router
result. The response-saving command rereads the response file without JSON
normalization, recalculates SHA-256 over those exact bytes, and requires
equality with the router's `responseSha256`. It then stores the exact response
file text as `responseJsonText` and the verified hash as `responseSha256`. Any
mismatch stops before a Drive file is written.

Calculate `savedResponseId` from a stable JSON representation of every
immutable saved-response field listed above except `savedResponseId` and
`responseJsonText`; use `responseSha256` to represent the exact response text.
One successful run therefore creates one self-identifying saved-response
record, and any change to its run binding, classified content metadata, format
check, safe router result, or returned content changes the ID. Two authorized
runs have different saved-response IDs even when Gemini returns identical
bytes; `responseSha256` still reveals that their returned content is
identical. Because controlled `outputType` and `outputFormat` are included in
the immutable saved fields, a transcript, summary, and systematic onscreen
text response for the same video range always receive different
saved-response IDs.

The response-saving command accepts the router result produced by
`gemini_request.py` and verifies that its request ID, run number, and exact
request hash match the pending run before writing the file. It verifies the
router's response hash against the exact response-file bytes as described
above. It must copy the content class, output type, output format, and source
range from the immutable logical request entry rather than accepting
replacements from the caller. A saved file whose run binding or response-byte
binding does not verify is rejected. It also validates and retains the
complete safe router result so a later session can restore every attempt
contained in that result and the original completion time if the final
request-log update was interrupted.

Write saved-response JSON in one deterministic format and hash the stored file
bytes separately when adding it to the video material index. Never edit an
existing saved-response file. If a checker changes what a structured response
means, introduce a new output-format version rather than reinterpreting the old
file.

Name the file
`<videoId>--gemini-response--<outputType>--<savedResponseId>.json` using the
verified controlled output type. The saved-response ID, not the readable type
segment, remains the file's unique record key.

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

### Controlled reusable output types

Every saved Gemini response and every video-material-index entry uses exactly
one `outputType` from this initial list:

| `outputType` | Reusable content |
|---|---|
| `transcript` | Spoken words in the source language, with the declared timestamp policy |
| `summary` | A reusable condensed account of the declared video range |
| `systematic_visual_description` | A chronological, reusable record of visible scenes, objects, and actions |
| `systematic_onscreen_text` | Reusable extraction of text shown on slides, boards, charts, captions, or other visible surfaces |

Translation is derived material. ChatGPT translates on demand from a saved
original-language transcript or systematic onscreen text; the system does not
save or search translation as a reusable Gemini output.

`outputType` is not an arbitrary caller-supplied category. A new reusable
output type enters this list only through a design update that defines its
meaning, required language and timestamp fields, compatible output formats,
search behavior, deterministic checker when structured, and offline tests.

The filename includes the controlled output type for human inspection. Code
reads and verifies the saved JSON instead of trusting filename text.

### Video material index

Question answered: **Which saved responses contain reusable source material
for this video?**

Use one predictable material-index file per normalized YouTube video ID. Its
top-level fields are `fileFormatVersion`, `videoId`, `materials`, and
`updatedAt`. Every entry represents a saved response whose predeclared
`contentClass` is `video_material`. Every eligible saved response has its own
entry. Each entry contains only information needed to find and reuse that
material:

- `savedResponseId`, `driveFileId`, `fileName`, and `fileSha256`;
- one controlled `outputType` from the list above;
- `outputFormat`, containing its name and version;
- `timestampsRelativeTo` and `languagePolicy` when applicable;
- verified `coveredTimeRanges`; and
- a short `materialDescription` only when the output type alone does not
  adequately describe the reusable material.

The material index does not contain prompts, task-specific observations,
direct answers, Gemini request status, request hashes, network attempts,
cooldowns, retry reasons, session IDs, or interruption history.

Index entries are identified by `savedResponseId`, never by video interval or
covered time. Adding a new saved-response ID appends its entry and preserves
every existing different ID, including entries with the same interval,
overlapping coverage, or another output type. Adding an existing ID verifies
that the stored entry and saved file are identical and then performs an
idempotent no-op. A matching interval, overlapping interval, or matching
output type never authorizes replacement or removal.

Search does not use `savedResponseId` as a semantic key. It opens the
predictable per-video index, filters entries by controlled output type, then
applies output-format version, language, timestamp policy, and covered-time
requirements. Only after selection does it use `savedResponseId`, Drive file
ID, and file hash to fetch and verify the exact saved response.

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
describes one logical Gemini request and contains immutable fields shared by
all deliberate executions of that request:

```text
Logical request
└── Authorized run
    └── Routing attempt
```

- `requestId`;
- normalized `videoId` and `requestedTimeRange`;
- the predeclared `contentClass`;
- `promptText`, copied exactly from the actual request file;
- the controlled `outputType` and `outputFormat` when `contentClass` is
  `video_material`; both fields are absent for the two one-time classes;
- `endpoint`, `model`, and `requestMethod`;
- `normalizedRequestSha256` for normalized request JSON;
- `runs`, an ordered list of authorized runs.

Each run contains:

- `runNumber`, starting at `1` and increasing by exactly one;
- `exactRequestSha256` for the exact request-file bytes used by that run;
- `startedAt` and `endedAt`, with `endedAt` set to `null` while pending;
- `runStatus`: `pending`, `succeeded`, `failed`, or `interrupted`;
- safe `routingAttempts` returned by `gemini_request.py` for that run, with
  `attemptNumber` starting at `1` and increasing without gaps, and with each
  attempt carrying its applicable `cooldownUntil` when one exists;
- `interruptionReason` when the user marks the run interrupted;
- `retryAuthorization` on every run after the first, recording `authorizedAt`,
  its plain reason, and `usedAt`; and
- `savedResponseId`, `savedResponseDriveFileId`, and
  `savedResponseFileSha256` when a `video_material` run succeeds;
- command-generated `responseNotSavedByPolicy: true` when a verified
  `task_specific_observation` or `direct_answer` run succeeds; and
- none of those success fields for `pending`, `failed`, or `interrupted`.

Create the request entry and run `1` together. Every later deliberate execution
appends run `N + 1` with a new consumed authorization. Credential fallback and
bounded transient retries performed by the router remain routing attempts
inside one run; they do not increment `runNumber`.

A request has at most one pending run, and it is the highest-numbered run. Do
not append another run until that run is terminal. Only that pending run
receives new routing attempts and then transitions to one terminal status.
Once terminal, a run is never rewritten or removed.
Previous runs, authorizations, attempts, cooldown evidence, and response
references or deliberate-non-storage markers remain distinguishable.

Do not store a separately writable request-level status, cooldown,
authorization, or saved-response reference. Calculate the current status from
the highest-numbered run, and enumerate all successful runs when retrieving
earlier results. A later pending, failed, or interrupted run never hides or
erases an earlier saved-response reference or deliberate-non-storage marker.

The exact prompt is retained so a later Work session can understand what the
request asked Gemini to observe or answer. The request log supports duplicate
prevention and resuming the same known request. It is not a semantic search
index for future tasks and does not answer whether a response is reusable video
material. That decision belongs to the video material index.

For `video_material`, the relationship is recorded in both directions: the
successful run contains the saved-response reference, and the saved response
contains the verified request ID, run number, and exact request hash. For either
one-time class, the successful run contains only the required
`responseNotSavedByPolicy: true` marker. Neither form puts request history in
the video material index.

## Classify each Gemini request before sending it

Every Gemini request must declare exactly one `contentClass` before request
construction and before any network call:

| `contentClass` | Intended content | Required storage behavior |
|---|---|---|
| `video_material` | One controlled reusable output type | Save the complete run-linked response; add every eligible response to the material index |
| `task_specific_observation` | Narrow sensory evidence requested for the active ChatGPT task, such as text on one board, values in one chart, or actions in one short scene | Return it to the active conversation; write no response file and no material-index entry |
| `direct_answer` | Gemini's own reasoning or answer to a question | Return it to the active conversation; write no response file and no material-index entry |

The class describes why the request is being made, not whether the returned
text later looks impressive. Bind it into the logical request entry before its
first run, but do not make this local classification part of request identity.
For `video_material`, the response-saving command copies it from that entry and
does not accept a replacement class from the caller. Never promote a
task-specific observation or direct answer into `video_material` after seeing
the response.

A purpose-specific builder fixes the class when the mode determines it; the
transcript builder fixes `video_material`. A generic prompt builder requires an
explicit class and never defaults to `video_material` or `direct_answer`.
Every `video_material` request also supplies one controlled `outputType` and
one compatible `outputFormat`; a named builder supplies them, otherwise the
caller supplies them explicitly. The two one-time classes contain neither
field in the request log and never create arbitrary output categories.

Preserve and link the exact successful response only for `video_material`.
For either one-time class, return the response to the active conversation and
finish the run through the verified one-time-success procedure below; the
response text is not written to Drive. `finish-run` writes
`responseNotSavedByPolicy: true` itself after verification. It never accepts
that Boolean from the caller. The required marker distinguishes deliberate
non-storage from a missing saved-response write. A later identical request
reports the earlier success and deliberate non-storage, then requires a new
explicit authorization before another run.

Do not add a task index, automatic semantic promotion, retention policy, or
cleanup subsystem in this release. To retain a sensory record for future use,
classify the request as `video_material` before sending it and use
`systematic_visual_description` or `systematic_onscreen_text`.

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
question is a `task_specific_observation`. ChatGPT consumes the latter in the
active conversation; the system does not save or index it.

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
8. Declare the request's `contentClass`. For `video_material`, also declare one
   controlled `outputType` and compatible `outputFormat`. Construct a Gemini
   request only for the identified gap.
9. Read the exact request file and prompt into the Gemini request log. Create
   the logical request if needed and append its next authorized `pending` run.
10. Verify the same request file, declared class, request ID, and run number
    immediately before Gemini credentials are loaded.
11. Send one Gemini request at a time.
12. For `video_material`, save the complete successful response after
    verifying that the router result and pending run have the same request ID,
    run number, and exact request hash, and that the router's response hash
    equals a fresh hash of the exact response-file bytes. Include the required
    format-check result and finish the run with the saved-response reference.
13. Add every eligible saved `video_material` response to the index after the
    applicable structured check or free-form review.
14. For either one-time class, give `finish-run` the actual successful router
    result and response file. After it verifies the request ID, run number,
    exact request hash, terminal success, response hash, and attempt history,
    it copies the routing attempts and original terminal time into the run,
    writes `responseNotSavedByPolicy: true`, and leaves no response file on
    Drive. Give the verified live response to ChatGPT for the active task.

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

Task-specific observations and direct answers have no Drive response files or
index entries. If existing `video_material` reveals a remaining visual gap,
issue a narrow `task_specific_observation`, let Gemini report the sensory facts
to the active conversation, and reason over those facts in ChatGPT.

If the material index is missing, list that video's saved-response files and
consider only files whose predeclared class is `video_material`. Recalculate
each response ID and response hash. Rerun the registered checker for a
structured format; inspect a free-form response before admitting it again.
Create an empty index only after confirming that no saved `video_material`
response can be indexed. Rebuilding adds every eligible distinct
`savedResponseId`; it never collapses transcript, summary, systematic visual
description, or systematic onscreen text merely because their source
intervals match or overlap.

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

The initial registry is deliberately asymmetric. Timestamped transcript
generation has already shown that it needs a machine-checked structure and
mechanically derived covered time. No comparable structural need has been
observed for the other three reusable output types, so they share one minimal
free-form format:

| `outputType` | Required `outputFormat` | Kind |
|---|---|---|
| `transcript` | `gemini-transcript` version `1` | Structured |
| `summary` | `gemini-free-form-text` version `1` | Free-form |
| `systematic_visual_description` | `gemini-free-form-text` version `1` | Free-form |
| `systematic_onscreen_text` | `gemini-free-form-text` version `1` | Free-form |

`gemini-free-form-text` version `1` means that Gemini's generated content is
ordinary text without a promised machine-readable response structure. It has
no deterministic checker, and its saved response must not contain
`formatCheck`. ChatGPT reads it once before material-index admission and
records only conservative covered-time metadata inside the declared source
range. The controlled output type and the existing language, timestamp, and
covered-time index fields retain the meaning needed for later search.

Reject an unregistered format name or version and any type-format combination
not listed above. Do not add a dedicated structured format for summary,
systematic visual description, or systematic onscreen text until an observed
need defines the structure, checker, search effect, and offline tests.

A format check validates only the declared structure and internal consistency:
required fields and types, timestamp syntax and ordering, requested clip
bounds, and completion flags where applicable. It does not judge factual
accuracy, reasoning quality, usefulness, or whether Gemini perceived the
video correctly.

A failed check prevents automatic use under that structured format. The exact
response remains available for inspection, but ChatGPT must not treat its
fields, time range, or completion claim as validated.

Run the required checker for every structured `video_material` response before
finishing its saved-response file. Passing is required for admission. For
free-form `video_material`, ChatGPT reads the response once; adding it to the
index records the acceptance without inventing a `passed` format status. The
two one-time classes create no saved response and therefore no durable
`formatCheck`.

### Gemini transcript version 1

The JSON format requested from Gemini is an instruction, not proof that Gemini
obeyed it. `scripts/saved_gemini_responses.py` must run the registered
`gemini-transcript` version `1` checker before a transcript can enter the
material index.

For transcript format `gemini-transcript` version `1`:

1. Extract the generated JSON from the Gemini response.
2. Require exactly the documented fields and types.
3. Parse all timestamps as full-video `MM:SS.mmm`; the minute part accepts
   values above `99`.
4. Require the returned clip start and end to match the request file.
5. Require every segment to have increasing start and end timestamps inside
   the returned clip. Permit overlapping speech, but require segments to be
   ordered by start time.
6. Check `completed_through_timestamp`, `transcription_complete`,
   `truncation_detected`, and Gemini's finish reason together.
7. Derive the covered time range from the requested clip start through the
   verified completed-through timestamp.

Callers cannot supply or override transcript covered time. A complete
transcript covers the full requested clip. A valid incomplete transcript
covers only its verified portion, and the remaining range is processed with a
smaller or otherwise changed request. A malformed response remains saved in
full with a failed format check but contributes no covered time.

Do not repeat an identical successful run automatically merely because its
response failed its format check. Show the saved response and require the user
to approve another run or change the request.

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

`contentClass` remains immutable metadata on every request entry. Controlled
`outputType` and declared `outputFormat` are also immutable for
`video_material` and are absent for the two one-time classes. These local
fields do not create a different request ID. If an existing request ID is
presented with conflicting local metadata, stop and show the earlier entry;
never use relabelling to permit the same Gemini call again. A genuinely broader
material request uses meaningfully different prompt or other request content.

For this purpose, normalize the request by parsing the JSON, replacing every
supported YouTube URL with the normalized video ID representation, sorting
object keys, and writing JSON without insignificant whitespace. Do not reorder
arrays or rewrite prompt text.

The pending run stores the exact request-file SHA-256. Immediately before
loading a Gemini credential, `gemini_request.py` must verify:

- the exact request-file hash;
- the normalized request hash and request ID;
- the expected `runNumber`;
- the video ID in every supplied YouTube URI;
- the start and end offsets;
- the declared content class;
- the controlled output type and output format for `video_material`, or their
  required absence for either one-time class;
- the endpoint, model, and method; and
- that this is the request entry's highest-numbered run and its `runStatus` is
  still `pending`.

Any mismatch stops before network access.

One logged Gemini request contains exactly one normalized YouTube video ID.
For comparisons, process each video separately and compare the saved responses
afterward; do not place a multi-video request inside one per-video log.

Before appending another run, calculate the current status from the
highest-numbered run. Surface every saved response from earlier successful
`video_material` runs and every deliberate-non-storage marker from earlier
one-time runs, then apply these rules:

- `pending`: do not send another copy;
- `succeeded`: use the saved response for `video_material`; for a one-time
  class, report that its response was deliberately not retained. Either form
  requires a new explicit authorization before an identical later run;
- `failed`: require a new authorization with a recorded reason, respect every
  unexpired saved cooldown, and never repeat an unchanged terminal request
  error; and
- `interrupted`: require a new explicit authorization with a recorded reason.

Attach that authorization to the new run. The first run has no
`retryAuthorization`; every later run must have exactly one, and one
authorization cannot start two runs.

Preserve each safe primary, fallback, and bounded transient attempt returned
by the router inside the run that made it. Bind the router's result to both
`requestId` and `runNumber`. A successful router result also contains the
exact request hash and `responseSha256`. Validate attempt numbers, timestamp
order, HTTP status, classification, selected credential alias, final routing
status, and response hash before saving them. Never store credential values or
fingerprints.

When `gemini_request.py` returns a terminal safe router result, that result
contains the complete ordered attempt list for the run, not merely attempts
missing from the request log. Retain every safe attempt in that result before
making another Gemini call. When `finish-run` or an interrupted-completion
operation encounters attempts already stored on the pending run, those stored
attempts must equal the same-length prefix of the router result in attempt
number and every safe field. Append only the missing suffix. An equal full list
is an idempotent no-op. A mismatch, gap, duplicate, reordering, stored list
longer than the router result, or terminal attempt that is not the router
result's final attempt stops without changing the run.

The system does not claim visibility into an invocation that ends before its
terminal safe router result becomes available to the active session or is
durably retained. In that state, the request log remains pending and contains
no inferred network attempt. Whether Gemini received the request is unknown.
Follow the interrupted-run procedure; do not invent a missing attempt, infer
success or failure, or retry automatically.

### Finishing a one-time run

`responseNotSavedByPolicy: true` is a storage-policy marker, not evidence of
Gemini success. For `task_specific_observation` and `direct_answer`,
`finish-run` requires the actual safe router result and response file produced
by `gemini_request.py`. It verifies all of the following before changing the
pending run:

- router status is successful and its final numbered attempt has the matching
  successful HTTP classification;
- router `requestId`, `runNumber`, and `exactRequestSha256` match the logical
  request and highest pending run;
- a fresh SHA-256 of the exact response-file bytes equals the router's
  `responseSha256`;
- all attempt numbers, timestamps, classifications, cooldowns, and selected
  credential aliases are valid; and
- attempts already stored on the pending run satisfy the exact-prefix rule
  above.

After every check passes, `finish-run` appends only the missing routing
attempts, sets `endedAt` from the router's final successful attempt, sets
`runStatus` to `succeeded`, and writes `responseNotSavedByPolicy: true` in the
same request-log update. It does not accept caller-supplied status, completion
time, routing attempts, or policy marker. It writes no saved-response fields
and uploads no response file to Drive. A missing, failed, incomplete,
mismatched, or internally inconsistent router result leaves the run unchanged.

## Interrupted runs

A run is eligible to be marked `interrupted` when it remains `pending` but the
Work session that started it cannot be confirmed as active. Elapsed time alone
does not prove that the session stopped. The durable log proves that the
request was prepared but does not prove whether Gemini received it or returned
a response.

When a later session encounters such a run:

1. stop before calling Gemini;
2. for `video_material`, search that video's saved-response files for the exact
   request ID, run number, and exact request hash, then verify every candidate's
   router-declared response hash against the embedded exact response bytes,
   stored-file hash, and immutable request metadata;
3. for either one-time class, perform no response-file search because the
   storage policy creates no such file;
4. show the user the video, requested time range, start time, request ID, run
   number, routing evidence, and all available saved-response evidence;
5. ask the user to confirm that the earlier session is no longer doing this
   work;
6. for `video_material`, when one exact saved response exists, finish the
   existing run as `succeeded` without another Gemini call;
7. when no exact reusable-material response exists, or when the request belongs
   to a one-time class, ask whether to mark the run `interrupted`, record the
   user's decision and reason, and permit another run only after explicit
   authorization and every saved cooldown; and
8. stop for investigation when multiple files claim the same request and run
   or any binding or integrity check fails.

An independently verified unlinked reusable-material response remains
available for separate material-index admission. It never completes the
pending run. Show it as evidence during the user's decision, but use only an
exact verified run-linked response and its retained safe router result to
finish that run. Do not add a two-phase response-upload protocol, invent
missing network attempts, infer that the request failed, or claim exactly-once
processing.

When a later session finishes a run from an exact saved response, set
`endedAt` from the bound successful router attempt. Do not use the later repair
time as the run's completion time; the request log's `updatedAt` records when
the later Drive update occurred. Reconcile any attempts already stored on the
pending run with the retained complete router history using the exact-prefix
rule above; never replace or duplicate them.

The normal write orders are:

```text
video_material:
append pending run → call Gemini → save response → finish run → update index

task_specific_observation or direct_answer:
append pending run → call Gemini → verify router success and response bytes →
finish run as deliberately not saved
```

A VM can disappear between those steps. That rare ambiguity is accepted and
resolved by the user, not by an automatic crash-handling system.

## Same-video processing rule

Do not intentionally process the same video in two write-capable Work sessions
at the same time. Concurrent read-only use of saved responses is allowed, and
different videos are processed independently.

Google Drive cannot acquire a lock and replace a file as one indivisible
operation. Therefore the system does not implement session ownership,
expiry-based takeover, handoff commands, or automatic takeover. A pending run
blocks later sequential work, but two truly simultaneous sessions can still
race. The run list is append-only as a data rule; Drive still replaces the JSON
file during each update and does not provide an atomic append. State this
limitation plainly rather than claiming mutual exclusion.

## No compatibility layer for the unmerged design

No live files from the unmerged cache-v3 implementation have been created, so
the implementation can adopt the new names without migration or compatibility
aliases.

The new Drive folder and all three file formats start at file-format version
`1`. Normal code must not import, search, migrate, or fall back to cache-v2
files.
Old cache-v2 records remain temporarily as read-only comparison evidence. They
are deleted separately after representative validation.

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
- transcript, summary, systematic visual description, and systematic onscreen
  text for the same interval all remain indexed;
- adding a distinct saved-response ID preserves every existing entry even when
  intervals or output types match or overlap;
- adding the same ID is an idempotent verified no-op, while the same ID with
  different content stops;
- search filters explicit index fields and uses `savedResponseId` only after
  selection for direct retrieval and verification;
- task-specific observations and direct answers have no response files or
  material-index entries; and
- complete isolation from cache v2.

### Content classification and response preservation

- all three content classes are declared before request construction and bound
  immutably to the request entry without changing request identity;
- relabelling an existing request cannot permit another Gemini call;
- the logical request's class cannot be replaced while saving a
  `video_material` run's response;
- the exact prompt is retained in the request log;
- every successful `video_material` response is preserved and linked from its
  request run;
- successful task-specific observations and direct answers write no response
  file and receive a command-generated `responseNotSavedByPolicy: true` only
  after verified router success;
- the controlled output-type list rejects arbitrary categories;
- `video_material` requires controlled `outputType` and compatible
  `outputFormat`, while both fields are absent for the one-time classes;
- the format registry accepts `gemini-transcript` version `1` only for
  `transcript`, accepts `gemini-free-form-text` version `1` only for the other
  three reusable output types, and rejects every other pairing;
- reusable saved filenames contain their verified controlled output type;
- identical response text from different source time ranges receives distinct
  saved-response identities;
- only `video_material` enters the material index;
- every structured saved `video_material` response runs its registered
  checker;
- a free-form format never contains a fabricated format-check result;
- free-form material cannot claim indexed time outside its source range;
- systematic OCR can enter material search while an otherwise similar
  one-slide task-specific observation cannot.

### Authorized-run history

- run numbers start at `1`, increase without gaps, and are unique within the
  logical request;
- at most one run is pending, it is highest-numbered, and no later run is
  appended before it becomes terminal;
- run `1` has no retry authorization, while every later run has exactly one
  consumed authorization that cannot be reused;
- the exact request-file hash is stored and verified separately for each run;
- `endedAt` is `null` while pending and present when the run becomes terminal;
- router attempts are bound to the correct request ID and run number;
- successful router results contain a response SHA-256 that the response saver
  independently recomputes from the exact response-file bytes;
- a correct run binding paired with different response bytes is rejected;
- credential failover and bounded transient retries remain attempts inside one
  run;
- terminal runs are immutable, and appending another run preserves every
  earlier authorization, attempt, cooldown, saved-response reference, and
  deliberate-non-storage marker;
- two successful authorized `video_material` runs retain two separately
  verifiable response references;
- each saved response verifies back to exactly one request ID, run number, and
  exact request hash;
- each saved response retains the validated safe router result needed to
  restore every routing attempt contained in that result and the original run
  completion time;
- existing pending-run attempts must be an exact prefix of retained router
  history; only the missing suffix is appended, and conflicting, reordered,
  duplicated, gapped, or extra attempts are rejected;
- a pending run with one exact verified response can be finished after the
  user confirms the earlier session has stopped, without another network call;
- an unlinked response cannot finish a pending run, and multiple claimants or
  any binding mismatch stop for investigation;
- a succeeded `video_material` run requires its complete response reference; a
  succeeded one-time run requires verified router success, copied routing
  attempts and terminal time, and command-generated
  `responseNotSavedByPolicy: true`; other statuses contain neither form;
- a bare caller-supplied policy Boolean, failed router result, mismatched
  request or run binding, mismatched response hash, or conflicting attempt
  history cannot finish a one-time run;
- a later failed run does not hide an earlier successful response or
  deliberate-non-storage marker;
- current status is calculated from the highest-numbered run; and
- no request-level status, cooldown, authorization, or response summary is
  persisted as separately writable truth.

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
  highest pending run stops before credential loading;
- successful, failed, pending, and interrupted latest-run handling;
- explicit retry reasons and cooldown enforcement;
- unchanged terminal request failure rejection;
- routing-attempt consistency; and
- no credential material in any saved file.

### Interruption behavior

- a pending run from an unavailable session stops;
- an invocation interrupted before its terminal safe router result is retained
  leaves the run pending with an unknown network outcome; no missing attempt or
  outcome is invented;
- exact run-linked response discovery, integrity verification, user-confirmed
  session cessation, and completion without another Gemini call;
- one-time pending runs perform no response-file search and require the user's
  interrupted-run decision;
- no automatic retry or claim that an unlinked response completed a run;
- `endedAt` restored from the bound router result rather than the later log
  update;
- explicit user authorization is attached before another run starts; and
- no writer, lease, handoff, reconciliation, or two-phase-upload interface
  remains.

## Deliberately deferred work

Do not add any of the following without observed need and a new design review:

- treating an unlinked saved response as proof that a pending run completed;
- two-phase response commits;
- automatic reconstruction of unknown network outcomes;
- cross-session atomic locking or an external coordination service;
- semantic search across task-specific observations or direct answers;
- automatic promotion of either class into reusable video material;
- response-retention or cleanup machinery without observed storage pressure;
- batch Gemini processing;
- parallel Gemini video requests; or
- permanent cache-v2 compatibility.
