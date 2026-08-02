# Gemini request execution and history

## Scope and authority

This document defines how one Gemini request is recorded, verified, routed,
finished, and deliberately repeated. It owns the per-video Gemini request log,
numbered authorized runs, credential-pool routing, interruption decisions, and
the same-video write limitation.

It does not define MCP use, whole-system source order, saved-material search,
or final research synthesis. [`SKILL.md`](../../SKILL.md) is the sole runtime
workflow authority. The running skill reaches this design only after the MCP
path and saved-Gemini-material search leave an actual need for a new Gemini
request.

Saved responses and the material index are defined in
[`gemini-response-storage-and-search.md`](gemini-response-storage-and-search.md).
Exact current commands and file fields are summarized in
[`references/contracts.md`](../../references/contracts.md).

## Status

The initial implementation was validated offline. The supported workflow uses
one write-capable Work session per normalized video ID and at most two
independently provisioned Gemini project credentials.

This design deliberately excludes batch processing, round-robin rotation,
parallel Gemini video calls, external locks, automatic crash reconstruction,
and permanent cache-v2 compatibility.

## Request log

Use one `<videoId>--gemini-requests.json` file per normalized video ID. Its
top-level fields are `fileFormatVersion`, `videoId`, `requests`, and
`updatedAt`.

Each request entry contains immutable information read from the actual request
file:

- `requestId`, normalized `videoId`, and `requestedTimeRange`;
- exact `promptText`;
- predeclared `contentClass`;
- controlled `outputType` and `outputFormat` only for `video_material`;
- endpoint, model, and request method;
- `normalizedRequestSha256`; and
- an ordered `runs` list.

The request log is not a material search index. It answers whether the same
Gemini request was deliberately run before and what is known about each run.
It never determines whether an old response satisfies a new task.

### Request identity

Derive `requestId` from normalized request JSON plus endpoint, model, method,
video ID, and requested interval. Normalize supported YouTube URL spellings,
object-key order, and insignificant JSON whitespace. Do not rewrite prompt
text, reorder arrays, or normalize generation choices that change the call.

Store the exact request-file SHA-256 separately on every run. Formatting-only
changes can preserve logical request identity while still producing a
different exact-file hash that the router must verify.

The local `contentClass` and reusable-output declaration do not create another
request identity. If an existing request ID is presented with conflicting
classification, stop instead of relabelling the same request to bypass repeat
protection.

### Authorized runs

Create the logical request and run `1` together. Every deliberate later
execution appends run `N + 1`; no run or prior outcome is overwritten.

Each run contains:

- sequential `runNumber`, starting at `1` without gaps;
- `exactRequestSha256`;
- `startedAt`, nullable `endedAt`, and `runStatus`;
- an ordered `routingAttempts` list;
- applicable cooldown evidence;
- `interruptionReason` when marked interrupted;
- `retryAuthorization` on every run after `1`; and
- exactly one applicable success outcome: a complete saved-response reference
  for `video_material`, or command-generated
  `responseNotSavedByPolicy: true` for either one-time class.

Allowed statuses are `pending`, `succeeded`, `failed`, and `interrupted`.
`endedAt` is null only while pending. At most one run in a video's request log
is pending, it is the highest-numbered run, and no later run can be appended
until it becomes terminal.

Do not store a separately writable request-level status, authorization,
cooldown, or response summary. Calculate current status from the highest run
and enumerate earlier successes when retrieving history.

Every run after the first contains a new user authorization with its reason,
authorization time, and use time. One authorization cannot start two runs.
Never repeat an unchanged terminal request failure, and respect every durable
cooldown before an authorized new run.

## Verification before network access

Append the pending run to Drive before loading a Gemini credential. The router
then rereads the request file and request log and verifies:

- exact and normalized request hashes;
- request ID and highest pending run number;
- every supplied YouTube URI resolves to the logged video ID;
- requested start and end offsets;
- prompt, endpoint, model, and method;
- declared content class; and
- controlled output type and format for `video_material`, or their absence for
  either one-time class.

Any mismatch stops before credential loading or network access. One logged
request contains exactly one normalized YouTube video ID; process videos
separately before comparison.

## Interactive credential pool

Use at most two aliases:

- `primary`: `GEMINI_API_KEY`;
- `fallback`: `GEMINI_API_KEY_FALLBACK` from a separately provisioned project.

If both values are identical, collapse them to one bucket. Persist aliases and
safe health state only; never store key values, fragments, or fingerprints.

Keep one Gemini request in flight. Route one run as follows:

1. Select `primary` unless it is disabled or cooling down.
2. On success, return the response and complete safe attempt history.
3. On `429 RESOURCE_EXHAUSTED`, derive a conservative cooldown from available
   retry information and try the other healthy bucket once.
4. On `408` or selected transient `5xx`, use bounded exponential backoff with
   jitter, then consider the other healthy bucket.
5. On a credential-specific authentication or permission failure, disable that
   bucket for the run and try the other healthy bucket once.
6. On `400 INVALID_ARGUMENT` or another terminal request error, stop without
   rotation.
7. If no bucket is healthy, return failure and the earliest cooldown instead
   of sleeping or looping indefinitely.

Keep short-lived bucket health in a local file under the portable
installation's `workspace/` directory. Do not create a persistent quota
database without observed cross-session need.

| Response | Classification | Router action |
|---|---|---|
| `2xx` | Success | Return response hash and complete safe attempts |
| `429 RESOURCE_EXHAUSTED` | Project rate limit | Cool down bucket; try other healthy bucket |
| `408`, `500`, `502`, `503`, `504` | Transient | Bounded backoff, then fail over |
| Credential-specific `400`, `401`, or `403` | Credential failure | Disable bucket for the run; try other healthy bucket |
| `400 INVALID_ARGUMENT` | Request failure | Stop without rotation |
| Other terminal `4xx` | Request failure | Stop unless specifically classified as credential failure |

## Routing attempts

Each network try is one routing attempt inside the current run. Attempts start
at `1` without gaps and retain safe start/finish times, bucket alias, HTTP
status, classification, and applicable cooldown or backoff information.

A terminal router result contains the complete ordered attempt list for that
run, its request ID, run number, exact request hash, final status, and on
success `responseSha256` calculated from the exact response-file bytes.

Attempts already stored on a pending run must equal the same-length prefix of
the returned list in every safe field. Append only the missing suffix. Reject
gaps, duplicates, reordering, conflicts, extra stored attempts, or a terminal
attempt that is not last.

If the active session never receives or durably retains a terminal safe router
result, the network outcome is unknown. Preserve only attempts actually
returned to the session; never invent missing attempts or infer success or
failure.

## Finishing a run

`finish-run` accepts only a router result bound to the exact highest pending
run. Completion time comes from the final router attempt, not the later Drive
update.

### Reusable `video_material`

The response-saving command independently verifies `responseSha256`, writes
the run-linked saved response, and uploads it before the request log becomes
successful. The finished run records saved-response ID, Drive file ID, and
stored-file hash. Material-index admission happens afterward and never changes
request history.

### One-time content

For `task_specific_observation` or `direct_answer`, `finish-run` requires the
actual successful router result and response file. It verifies request ID, run
number, exact request hash, response hash, and complete attempts, then writes
`responseNotSavedByPolicy: true` itself. Caller-supplied status, attempts,
completion time, or policy marker are not success evidence. No response text
is uploaded to Drive.

## Interrupted pending runs

Elapsed time does not prove that an earlier session stopped. When a later
session finds a pending run:

1. stop before another Gemini call;
2. show the known request, run, time range, and retained attempt evidence;
3. ask the user to confirm that the earlier session has stopped;
4. for `video_material`, enumerate saved responses for one exact match on
   request ID, run number, and exact request hash;
5. when exactly one fully verified match exists, restore only missing attempt
   suffixes and finish that same run without another Gemini call;
6. when no match exists, or the request was one-time content, mark the run
   `interrupted` only after user confirmation and require new authorization
   before another run; and
7. stop for investigation on multiple claimants or any identity, byte, or
   attempt-history conflict.

The system does not infer that an unlinked response completed a run, reconstruct
unknown network activity, or claim exactly-once processing.

## Same-video write limit

Do not intentionally use two write-capable Work sessions for the same video.
Concurrent read-only use is allowed, and different videos can be processed
independently.

Google Drive does not provide atomic compare-and-set replacement for these
files. A pending run blocks later sequential work, but truly simultaneous
sessions can still race. Do not add session ownership, leases, expiry-based
takeover, handoff commands, or an external coordination service without a new
requirement and design review.

## Required offline validation

- request identity normalization and per-run exact-file hashes;
- request, video, interval, endpoint, model, method, and highest-pending
  mismatches stopping before credentials or network;
- monotonic numbered runs and immutable earlier outcomes;
- explicit retry authorization, durable cooldowns, and rejection of unchanged
  terminal request failures;
- primary success, primary rate limit with fallback success, both buckets
  unavailable, transient retry, credential failure, and terminal request error;
- sequential, complete, prefix-consistent routing-attempt history;
- successful response hashes bound to exact bytes;
- complete saved-response references for reusable success;
- verified deliberate non-storage for both one-time classes;
- interrupted-run decisions, exact saved-response completion without another
  call, and unknown network outcomes without invented attempts;
- same-video single-writer limitation stated without a false lock guarantee;
  and
- absence of credentials and credential fingerprints from every saved file.

After offline tests pass, live validation uses at most one inexpensive request
per credential. Do not exhaust quota merely to prove rate-limit behavior.

## Sources

- Gemini rate limits: `https://ai.google.dev/gemini-api/docs/rate-limits`
- Gemini retry guidance: `https://ai.google.dev/gemini-api/docs/troubleshooting`
- Gemini API-key behavior: `https://ai.google.dev/gemini-api/docs/api-key`
