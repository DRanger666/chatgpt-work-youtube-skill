# ChatGPT Work YouTube Skill

## Why this exists

I use YouTube for work, research, learning, hobbies, and entertainment. A
useful assistant should be able to work with the videos I already depend on:
verify claims, answer questions, summarize, synthesize ideas across videos,
translate unfamiliar languages, and point back to the relevant moments.

I previously relied on Gemini for much of that interaction. This skill brings
the same class of YouTube work into ChatGPT Work, so a YouTube URL can become
working material inside the environment where the rest of the research is
happening.

## How it works

The skill uses two complementary routes.

### 1. YouTube MCP for transcript research

The primary route is
[`coyaSONG/youtube-mcp-server`](https://github.com/coyaSONG/youtube-mcp-server).
It retrieves available captions and provides focused transcript research with
timestamp-linked YouTube citations. For captioned videos, this is usually the
fastest and least expensive way to answer a question.

The portable installation is pinned to:

- Upstream version: `1.2.0`
- Commit:
  [`06d5e7a83783f7a44498da88ade2ccaa42238747`](https://github.com/coyaSONG/youtube-mcp-server/commit/06d5e7a83783f7a44498da88ade2ccaa42238747)
- Node.js: `v24.14.0`

At the time of this README update, that commit is also the tip of upstream
`main`.

### 2. Gemini when transcripts are not enough

An MCP transcript cannot describe frames it cannot see, and some videos have
no usable captions. Gemini's
[YouTube video understanding](https://ai.google.dev/gemini-api/docs/generate-content/video-understanding)
fills that gap for captionless videos, visual verification, scene-level
questions, and whole-video understanding.

When exact source wording is needed, the request builder also has an explicit
transcript-only mode that prevents a broad audiovisual-analysis response.

Long videos are analyzed in timestamp-bounded chunks. Before constructing a
Gemini request, the skill searches a per-video material index for compatible
saved responses and verifies only the selected files. Only uncovered intervals
are generated.

Saved responses, material indexes, and Gemini request logs live in the
no-space `YouTubeVideoWork` Drive folder. The request log prevents blind
repetition without being used as a material-discovery key. This clean-slate
system does not import, migrate, or fall back to cache-v2 records.

For interactive continuity, the skill can use a second credential belonging to
a different Google Cloud project. It remains primary-first and sequential:
the fallback is used only when the primary project is cooling down or
unavailable. It does not blindly rotate keys or parallelize expensive video
chunks.

## Upstream maintenance

The skill does not blindly follow a moving branch. The pinned commit is the
reviewed and tested dependency.

Periodically:

1. Compare the pinned commit with upstream `main`.
2. Review upstream changes, releases, and dependency updates.
3. Rebuild the portable installation.
4. Run transcript, MCP handshake, captionless-video, and long-video chunking
   tests.
5. Advance the version and commit pin only after those checks pass.

This keeps installations reproducible while still allowing deliberate
upstream updates.

## Install in ChatGPT Work

Give ChatGPT Work this repository and explicitly ask it to install the skill
on the current account:

```text
Install the ChatGPT Work YouTube skill from:
https://github.com/DRanger666/chatgpt-work-youtube-skill
```

ChatGPT Work should clone the repository, validate `SKILL.md`, and install it
as a personal skill for the account where the request is made. Because the
repository is private, that account must have access through its connected
GitHub account or a privately supplied PAT.

No credentials belong in this repository. API keys and PATs should remain in
private user-owned credential storage and be materialized locally only for the
operation that needs them.

After installation, ordinary requests such as these should invoke the skill:

```text
Summarize this YouTube video and cite the important timestamps.

Compare these three videos and synthesize where they agree or disagree.

Translate and explain what is happening in this captionless video.
```

## What is in the repository

- `SKILL.md` — the canonical ChatGPT Work workflow.
- `scripts/ensure_youtube_mcp.sh` — restore and verify the pinned portable MCP.
- `scripts/call_youtube_mcp.mjs` — make deterministic MCP calls.
- `scripts/build_gemini_chunk_request.py` — build timestamp-clipped requests.
- `scripts/saved_gemini_responses.py` — save immutable reusable responses,
  maintain per-video material indexes, verify selected files, and plan missing
  coverage.
- `scripts/gemini_request_log.py` — preserve logical requests, separate
  authorized runs, router attempts, cooldowns, interruptions, and result
  references without overwriting history.
- `scripts/youtube_work_common.py` — shared file, identity, interval, format,
  and YouTube URL validation.
- `scripts/gemini_request.py` — route requests through healthy project
  credentials with bounded retries after verifying the highest pending run.
- `references/contracts.md` — version, credential, API, saved-response,
  material-index, and request-log contracts.
- `development-ledger/` — ongoing investigations, design notes, debugging
  records, and evidence-backed backlog items.
- `CONTRIBUTING.md` — repository and commit-history conventions.
