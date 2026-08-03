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

The runtime source order is deliberate:

1. Ask the YouTube MCP for every relevant item it can provide.
2. If the MCP material is sufficient, use it directly and stop.
3. Otherwise, search previously saved Gemini material for the missing need.
4. Make a new Gemini request only for information that neither earlier source
   supplies.

### YouTube MCP first

The primary route is
[`coyaSONG/youtube-mcp-server`](https://github.com/coyaSONG/youtube-mcp-server).
It retrieves available captions and provides focused transcript research with
timestamp-linked YouTube citations, plus other applicable information exposed
by the server. For captioned videos, this is usually the fastest and least
expensive way to answer a question. MCP results remain temporary because they
can be retrieved again without consuming Gemini quota; they are not copied
into the saved-Gemini material index.

The portable installation is pinned to:

- Upstream version: `1.2.0`
- Commit:
  [`06d5e7a83783f7a44498da88ade2ccaa42238747`](https://github.com/coyaSONG/youtube-mcp-server/commit/06d5e7a83783f7a44498da88ade2ccaa42238747)
- Node.js: `v24.14.0`

### Gemini only for remaining gaps

An MCP transcript cannot describe frames it cannot see, and some videos have
no usable captions. Gemini's
[YouTube video understanding](https://ai.google.dev/gemini-api/docs/generate-content/video-understanding)
fills that gap for captionless videos, visual verification, scene-level
questions, and whole-video understanding.

When exact source wording is needed, the request builder also has an explicit
transcript-only mode that prevents a broad audiovisual-analysis response.

Before constructing a Gemini request, the skill searches a per-video material
index for compatible saved Gemini responses and verifies only the selected
files. Only uncovered intervals are generated.

Long videos are processed in deterministic timestamp-bounded chunks. General
video analysis uses a tested 30-minute conservative default with no overlap;
transcript-only work uses approximately 10-minute clips with four-second
overlap. The 30-minute default comes from a real whole-video failure followed
by a successful `0s`–`1800s` request. It is an operating default, not a claim
about Gemini's absolute video limit.

Saved responses, material indexes, and Gemini request logs live in the
no-space `YouTubeVideoWork` Drive folder. The request log prevents blind
repetition without being used as a material-discovery key. This clean-slate
system does not import, migrate, or fall back to cache-v2 records.

Translations are derived on demand in ChatGPT from saved original-language
transcripts or systematic onscreen text. They are not stored or searched as a
separate reusable Gemini output.

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

No credentials belong in this repository or the replaceable MCP installation.
API keys and PATs remain in private user-owned storage and protected mounted
workspace credential files.

After installation, ordinary requests such as these should invoke the skill:

```text
Summarize this YouTube video and cite the important timestamps.

Compare these three videos and synthesize where they agree or disagree.

Translate and explain what is happening in this captionless video.
```

## Repository guide

[`REPOSITORY_MAP.md`](REPOSITORY_MAP.md) identifies every maintained file,
which document owns each concern, and the rule for resolving contradictions.
Keep that map current whenever a file is added, removed, renamed, or assigned a
different role.
