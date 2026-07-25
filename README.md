# ChatGPT Work YouTube Skill

A reproducible, cache-first YouTube research skill built specifically for
ChatGPT Work.

The skill restores a pinned portable YouTube MCP server when necessary, uses
caption transcripts before paid model calls, analyzes captionless or visual
content with Gemini, splits long videos into timestamp-bounded chunks, and
stores reusable Gemini results in a persistent cache.

## Core behavior

- Discover or rebuild `youtube-mcp-portable`.
- Preserve the no-space `materials/` and `workspace/` layout.
- Use transcript research with timestamp-linked YouTube citations.
- Use Gemini only when transcripts are insufficient.
- Split long videos into fingerprinted 30-minute requests.
- Check persistent cache before every Gemini call.
- Record every Gemini success, failure, and usage total.
- Refuse unjustified repetition of an identical failed request.
- Recover credentials privately without including them in this repository.

## Repository layout

```text
SKILL.md
agents/
  openai.yaml
references/
  contracts.md
scripts/
  build_gemini_chunk_request.py
  call_youtube_mcp.mjs
  ensure_youtube_mcp.sh
  gemini_cache.py
```

`SKILL.md` is the canonical workflow. The scripts provide deterministic MCP
setup, MCP calls, Gemini chunk construction, and cache-record lifecycle
handling.

## Credentials

This repository contains no API keys, PATs, authorization headers, or cached
video analyses. Credentials remain in private user-owned storage and are
materialized locally only when required.

## Validated scenarios

- Captioned Bengali videos with focused timestamp citations.
- Captionless long-form Hindi video analysis.
- Gemini timestamp clipping through `startOffset` and `endOffset`.
- Cache creation before a Gemini call and in-place completion afterward.
- Recovery of an existing portable MCP installation in a fresh workspace.
