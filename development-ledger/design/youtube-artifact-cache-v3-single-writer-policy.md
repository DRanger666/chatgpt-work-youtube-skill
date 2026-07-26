# YouTube artifact cache v3 single-writer policy

## Status

Approved initial-release operating policy for LEDGER-010. It defines the
supported concurrency boundary; it does not claim that Drive supplies a lock or
that the runtime enforces mutual exclusion across Work sessions.

## Reason

The connected Drive workflow exposes read and replacement operations but no
atomic compare-and-set. Two sessions can read the same state, both decide that
writing is permitted, and overwrite one another. A lease written through the
same path supports recovery and diagnosis; it cannot make acquisition atomic.

## Ownership scope

Use the repository's normalized YouTube video ID as the ownership key. URL
spelling, query parameters, and shortened versus full URLs must not create
different keys for the same video.

All writes for one video form one consistency domain, even when they concern
different intervals or artifact kinds. Permit only one write-capable Work
session for that video at a time. Different video IDs may have independent
writers and proceed concurrently.

## What counts as writing

A session is a writer for a video if it:

- submits a Gemini request;
- reserves, renews, reconciles, retries, finalizes, or otherwise mutates an
  execution-journal record;
- uploads a new immutable artifact or removes an invalid one; or
- creates, replaces, repairs, or removes the artifact manifest or an entry.

Never replace immutable artifact content in place. Keep writer ownership,
leases, handoffs, and abandonment in the execution journal, never in artifacts
or the manifest.

## Concurrent read-only sessions

Concurrent sessions may read the manifest, fetch and integrity-check artifacts,
inspect execution history, plan coverage locally, and answer from available
artifacts.

A read-only session must not call Gemini, mutate an execution, publish an
artifact, or repair the manifest. It reports stale or invalid state and leaves
repair to the established writer.

## Active pending work

An active pending execution or writer record blocks every other session from
that video's write path. Other sessions may continue read-only work but must
not steal, replace, or race the writer.

The established writer may resume or renew its own work after rereading the
latest execution state. Generate its owner identifier through the journal tool
with at least 128 bits of randomness. Reject an identifier already present in
that video's writer history; a later session must never reuse it.

## Lease expiry and reconciliation

Expiry makes pending work eligible for reconciliation; it does not prove that
the previous writer stopped. Before another writer proceeds:

1. Reread the complete execution record and inspect referenced artifacts and
   the current manifest.
2. Determine whether the prior work completed, failed, or was abandoned.
3. If the previous session's termination remains uncertain, require human
   confirmation that it will no longer write.
4. Append the reconciliation outcome, evidence, and reason while preserving
   attempt numbering, router history, retry reasons, and cooldowns.
5. Begin new work only after reconciliation and, for an identical failed
   request, a documented permitted retry reason.

Never convert expiry directly into permission to call Gemini.

## Writer handoff and abandonment

For a clean handoff, the outgoing writer must confirm that no Gemini call
remains in flight, persist all attempt, result, and artifact state, finish or
release pending work, and record the handoff. The incoming writer rereads that
durable state before recording ownership. A handoff names exactly one incoming
owner and reserves the next acquisition for that owner. A different owner may
proceed only through explicit reconciliation that preserves and supersedes the
handoff.

After a crash or lost VM, record abandonment only through reconciliation.
When the network outcome cannot be reconstructed, record it as unknown rather
than failed. Never delete or overwrite the abandoned writer's history, invent
missing router attempts, or automatically retry ambiguous work.

## Supported guarantees

- Serialized same-video mutation by sessions complying with this policy.
- Automatic identical-call blocking unless a retry is explicitly authorized.
- Durable attempt history, retry authorization, and crash reconciliation.
- Concurrent same-video reads and concurrent different-video writers.

## Explicitly unsupported guarantees

- Drive-enforced cross-session mutual exclusion.
- At-most-once execution when concurrent sessions violate the policy.
- Exactly-once execution.
- Safe concurrent same-video artifact, manifest, or journal mutation.
- Any inference that expiry proves the previous writer stopped.

## Future atomic-coordination extension

A future coordinator may replace the convention if it supplies atomic
acquisition keyed by normalized video ID, renewal and release, and fencing that
prevents a stale writer from mutating state after ownership changes. That
extension must not alter artifact identity, artifact content, or manifest
search fields.

## Implementation obligation

Summarize this policy in `SKILL.md` and `references/contracts.md`; do not
reinterpret it there. Test same-video blocking, read-only concurrency,
different-video independence, generated non-reused owner IDs,
recipient-constrained handoff, chronological event history, expiry
reconciliation, unknown outcomes, and abandonment without claiming
Drive-backed atomic exclusion.
