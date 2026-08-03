# Repository map

This file maps the maintained repository and assigns one owner to each kind of
information. Update it in the same commit whenever a file is added, removed,
renamed, or given a different role. Ordinary content edits that do not change
a file's role do not require a map edit.

## Authority by concern

| Concern | Owning source |
|---|---|
| Project purpose, rationale, installation, and high-level architecture | [`README.md`](README.md) |
| Runtime source order and agent procedure | [`SKILL.md`](SKILL.md) |
| Exact current paths, pins, filenames, commands, fields, and operating values | [`references/contracts.md`](references/contracts.md) |
| Executable behavior | `scripts/`, guarded by `tests/` |
| Design rationale and deliberately supported boundaries | `development-ledger/design/` |
| Work status, historical decisions, and future checks | [`development-ledger/backlog.md`](development-ledger/backlog.md) |
| Repeatable investigation methods and collected evidence | `development-ledger/investigations/` |
| Contribution and commit-history rules | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

There is no blanket rule that one document outranks all others. Ownership is
by concern. A design note cannot redefine runtime source order; a historical
ledger entry is not a current interface contract; and a reference contract
must not invent behavior absent from the scripts. If two owning sources
conflict, stop and correct the contradiction rather than silently selecting
one.

## Root files

| Path | Role |
|---|---|
| [`.gitignore`](.gitignore) | Excludes credentials, common local runtime directories, caches, and build products from version control. |
| [`README.md`](README.md) | Explains why the skill exists, its high-level MCP-first architecture, installation, and upstream maintenance. |
| [`REPOSITORY_MAP.md`](REPOSITORY_MAP.md) | Maps repository ownership and every maintained file. |
| [`SKILL.md`](SKILL.md) | Installed ChatGPT Work skill and sole owner of runtime route order and operating procedure. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Defines documentation maintenance, commit structure, validation, and publishing conventions. |

## Agent metadata and runtime reference

| Path | Role |
|---|---|
| [`agents/openai.yaml`](agents/openai.yaml) | ChatGPT product metadata and the default invocation prompt; summarizes but does not redefine `SKILL.md`. |
| [`references/contracts.md`](references/contracts.md) | Compact current contract read by the skill: installation pin, private Drive locations, Gemini request and chunk values, saved-response/index formats, request-log rules, and validated behavior. |

## Runtime scripts

| Path | Role |
|---|---|
| [`scripts/ensure_youtube_mcp.sh`](scripts/ensure_youtube_mcp.sh) | Finds or restores the pinned portable YouTube MCP installation and verifies it. |
| [`scripts/call_youtube_mcp.mjs`](scripts/call_youtube_mcp.mjs) | Performs deterministic MCP handshakes, tool enumeration, and tool calls. |
| [`scripts/build_gemini_chunk_request.py`](scripts/build_gemini_chunk_request.py) | Builds one timestamp-clipped Gemini request, including structured transcript mode. |
| [`scripts/saved_gemini_responses.py`](scripts/saved_gemini_responses.py) | Saves reusable Gemini responses, maintains and searches per-video material indexes, verifies selected files, finds missing time ranges, and splits those ranges into deterministic long-video chunks. |
| [`scripts/gemini_request_log.py`](scripts/gemini_request_log.py) | Maintains per-video logical requests and append-only authorized runs, including retry, interruption, attempt, and result evidence. |
| [`scripts/gemini_request.py`](scripts/gemini_request.py) | Verifies the highest pending run, loads the protected local credential file, and routes one request through the primary/fallback Gemini pool. |
| [`scripts/youtube_credentials.py`](scripts/youtube_credentials.py) | Installs and validates the protected local Gemini credential file without exposing its values. |
| [`scripts/youtube_work_common.py`](scripts/youtube_work_common.py) | Holds shared constants and validation for YouTube IDs, files, output types, hashes, timestamps, and time ranges. |

## Tests

| Path | Role |
|---|---|
| [`tests/test_portable_layout.py`](tests/test_portable_layout.py) | Verifies recognition of the exact maintained portable-installation layout, rejection without replacement, and absence of discarded launcher generation. |
| [`tests/test_transcript_request.py`](tests/test_transcript_request.py) | Verifies ordinary and transcript-only Gemini request construction. |
| [`tests/test_saved_gemini_responses.py`](tests/test_saved_gemini_responses.py) | Verifies saved responses, transcript checks, material-index search, missing-range planning, and deterministic chunk planning. |
| [`tests/test_gemini_request_log.py`](tests/test_gemini_request_log.py) | Verifies logical requests, numbered runs, retry authorization, interruptions, and result binding. |
| [`tests/test_gemini_routing.py`](tests/test_gemini_routing.py) | Verifies request-to-router binding, safe primary/fallback routing, failures, cooldowns, and returned attempt history. |
| [`tests/test_youtube_credentials.py`](tests/test_youtube_credentials.py) | Verifies strict Gemini credential parsing, atomic protected installation, local validation, and secret-free command output. |

## Development ledger

[`development-ledger/README.md`](development-ledger/README.md) is the
directory-local index and maintenance guide for this area.

| Path | Role |
|---|---|
| [`development-ledger/backlog.md`](development-ledger/backlog.md) | Stable ledger IDs, current work state, acceptance checks, completed refinements, and preserved development history. |
| [`development-ledger/design/gemini-response-storage-and-search.md`](development-ledger/design/gemini-response-storage-and-search.md) | Governing rationale for retained Gemini responses, reusable material types, per-video indexes, validation, search, and index rebuilding. It does not own MCP routing or request execution. |
| [`development-ledger/design/gemini-request-execution.md`](development-ledger/design/gemini-request-execution.md) | Governing rationale for Gemini request identity, numbered runs, request verification, primary/fallback routing, interruption decisions, and the same-video write limit. It does not own material search or the whole YouTube workflow. |
| [`development-ledger/investigations/chatgpt-work-installation-friction.md`](development-ledger/investigations/chatgpt-work-installation-friction.md) | Layer-aware clean-account installation trial method, report format, evidence, and unresolved platform/VM/Drive questions. |
