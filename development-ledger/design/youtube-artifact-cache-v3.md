# YouTube artifact cache v3

## Status

Design candidate. Implement only on a dedicated feature branch after the
artifact-search and manifest contracts below are reviewed together.

## Problem

Cache v2 hashes the exact request-file bytes and uses that fingerprint as the
primary lookup key. This reliably identifies one execution request, but it
conflates three separate problems:

1. discovering previously generated material that may satisfy the current
   task;
2. verifying the integrity of a stored transcript or analysis artifact; and
3. preventing an identical Gemini API execution from being repeated.

Prompt formulation, JSON formatting, URL form, token settings, or a schema
correction can change a request fingerprint even when an existing artifact
remains useful. Cache v2 therefore prevents byte-identical repetition but
cannot reliably answer whether the system already possesses sufficient
research material.

The cache-v3 principle is:

> Search by what an artifact represents and covers; audit by how it was
> produced.

## Design A — Artifact-first retrieval and coverage planning

Before constructing a Gemini request:

1. Normalize the YouTube URL to a video ID.
2. Load the artifact index for that video.
3. Select candidates by artifact kind, such as transcript, translation,
   visual analysis, or question-specific analysis.
4. Filter candidates by compatible contract version, timestamp basis,
   language policy, and completion state.
5. Compute the union of their valid coverage intervals.
6. Identify truncated regions, incompatible material, and uncovered gaps.
7. Reuse complete or composable artifacts and generate only the missing
   intervals.
8. Immediately before a network request, use a canonical execution
   fingerprint as an idempotency check.

An exact interval is not a transcript identity. A transcript covering
`0–1800s` can satisfy a request for `300–900s`, and multiple overlapping chunks
can jointly satisfy a larger interval.

Execution fingerprints remain provenance and duplicate-call guards. They do
not drive the initial artifact search.

### Acceptance cases

- One artifact exactly covers the requested interval.
- A larger compatible artifact contains the requested interval.
- Multiple compatible chunks jointly cover the requested interval.
- Overlapping chunks compose without turning the overlap into a gap.
- A truncated chunk contributes only its confirmed completed coverage.
- Incompatible contracts or language policies are not silently reused.
- Only uncovered intervals produce new Gemini requests.
- An identical pending or completed execution is not submitted twice.

## Design B — Per-video manifest and artifact storage

Google Drive is persistent storage, not a query database. Use one predictable
manifest per video:

```text
<videoId>--manifest.json
```

Treat the manifest as a mutable index. Keep transcript chunks and other
generated artifacts as separate records so they can be verified and reused
independently.

Each manifest entry should contain retrieval and provenance metadata such as:

- artifact ID and Drive file ID;
- artifact kind and contract version;
- timestamp basis and language policy;
- valid coverage intervals;
- completion, truncation, and gap information;
- integrity hash of the stored artifact;
- human-readable task description for analysis artifacts; and
- references to the executions that produced or extended it.

Never store credentials, authorization material, credential fragments, or
credential fingerprints in manifests or artifacts.

Transcript compatibility and interval coverage can be evaluated
mechanically. For arbitrary analyses, expose candidate artifacts and their task
descriptions so the agent can judge whether a result answers the new question.
Do not automatically equate paraphrased prompts or use aggressive semantic
normalization.

### Acceptance cases

- A manifest can be located deterministically from a video ID.
- Manifest coverage resolves every acceptance case in Design A.
- Missing or stale manifest entries do not destroy underlying artifacts.
- Updating a manifest does not rewrite immutable artifact content.
- Existing cache-v2 results become discoverable without another Gemini call.

## Cache-v2 migration

- Preserve existing v2 records.
- Extract their source, route, clip, completion, and result metadata into
  manifests without rerunning Gemini.
- Support read-through discovery of v2 records during transition.
- Retain existing request fingerprints as execution provenance rather than
  artifact identities.
- Avoid destructive or eager rewriting of prior records.

## Test direction

Do not add a byte-for-byte golden request or fixed request-hash regression test
merely to stabilize cache v2's coupling between request serialization and
artifact discovery.

Cache v3 should instead test:

- deterministic execution fingerprints;
- artifact identity and compatibility;
- interval coverage, composition, and gap detection;
- manifest lookup and update behavior; and
- cache-v2 discovery and migration.

## Non-goals

- No vector database or embedding service.
- No automatic equivalence between semantically similar analysis prompts.
- No cache-v3 implementation inside transcript-mode history.
- No destruction of cache-v2 records.
- No live Gemini quota consumption merely to test the index design.
