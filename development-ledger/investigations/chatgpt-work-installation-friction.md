# ChatGPT Work YouTube Skill Installation Investigation

## Purpose

This document defines a repeatable investigation for installing the ChatGPT
Work YouTube skill on fresh accounts.

The central question is not merely whether a capable agent eventually
succeeds. Modern reasoning agents often recover from faults autonomously and
omit resolved friction from their final answer. The investigation must
therefore capture the observable errors, retries, workarounds, fallback paths,
ambiguities, and extra work that occurred underneath a successful outcome.

The goal is to identify where repository improvements can reduce unnecessary
exploration and make future installations faster, simpler, and more
deterministic.

## Fixed test subject

- Repository:
  `https://github.com/DRanger666/chatgpt-work-youtube-skill`
- Baseline commit: `688642d459bdb75cde19a18bf7c6d1bb83bd2058`
- Skill name: `work-with-youtube`
- Upstream YouTube MCP version: `1.2.0`
- Upstream YouTube MCP commit:
  `06d5e7a83783f7a44498da88ade2ccaa42238747`

Keep the repository frozen at the baseline commit while collecting comparable
clean-account trials. Do not fix one observed problem between trials unless
intentionally beginning a new test round with a new recorded baseline.

## Operational-layer classification

Every issue must be assigned to the layer that owns the failing operation. The
layer determines where a fix or explanation belongs.

| Layer | Owns | Example failures | Likely fix location |
|---|---|---|---|
| ChatGPT skill platform | Account-level skill registration, validation, saving, reconciliation, persistence, and UI visibility | First save rejected; two-stage registration required; installed skill not immediately visible | Installation guidance, skill package metadata, or platform behavior |
| Repository/package | Skill manifest, directory layout, scripts, references, pins, checksums, and documentation | Missing file; inconsistent manifest; stale pin; source mismatch | GitHub repository |
| Work VM/runtime | Temporary filesystem, permissions, Node/npm, dependency build, proxy environment, and local MCP process | `/root/.npm` is unwritable; missing runtime; build or process launch failure | Bootstrap/runtime scripts, especially `ensure_youtube_mcp.sh` |
| YouTube MCP/upstream | MCP handshake, tool schemas, transcript and metadata implementation, and caption handling | Tool mismatch; transcript fetch bug; MCP protocol failure | Wrapper compatibility code or upstream MCP |
| Google Drive connector | Connector authorization, file discovery, credential retrieval, cache reads/writes, and Drive permissions | Credential file cannot be found; cache record cannot be written; connector disconnected | Connector procedure, Drive layout, or access configuration |
| Gemini API | Video ingestion, timestamp clipping, model behavior, quota, safety, and API limits | `INVALID_ARGUMENT`; quota failure; unsupported full-video request | Gemini request builder, chunking strategy, or model/API guidance |
| YouTube source | Availability and properties of the requested video | No captions; private video; regional restriction; unavailable language track | Route selection or user-facing limitation; not an installation fix |

### Important boundary: installation has two meanings

1. **Local runtime setup in the Work VM**: cloning or restoring the pinned MCP,
   installing dependencies, compiling, launching, and completing an MCP
   handshake.
2. **Account-level skill installation in the ChatGPT skill platform**:
   registering, validating, saving, reconciling, and exposing the skill to
   future chats.

These operations may happen in the same agent session, but they belong to
different systems and must not be reported as one undifferentiated
“installation” event.

### Classification rule

Classify an incident by the operation that failed, not by the tool the agent
happened to be using when it noticed the failure.

Examples:

- An npm cache permission error is a Work VM/runtime incident.
- A validation rejection from the account skill-saving service is a ChatGPT
  skill platform incident.
- Failure to fetch a credential file through the Drive connector is a Google
  Drive connector incident.
- A Gemini `INVALID_ARGUMENT` response after a valid credential was read is a
  Gemini API incident.
- A captionless video is a YouTube source condition, not an MCP installation
  failure.

## Investigation design

### Why use fresh accounts

A fresh account provides a clean test of whether the repository contains
enough information for an autonomous ChatGPT Work agent to install and prepare
the skill without relying on previous chat context or an already-installed
account skill.

Do not uninstall the successful installation from an existing account merely
to repeat the test. Use another fresh account when available. This avoids
uncertain residual state and preserves the successful installation as
evidence.

### Controlled variables

For comparable trials:

- Use the same two-sentence prompt.
- Use the same repository baseline commit.
- Request setup and readiness verification without analyzing a video.
- Use the same model and reasoning setting where possible.
- Begin from an account on which this skill has not previously been installed.
- Record the account only by an anonymous trial label such as `A1`, `A2`, or
  `A3`.
- Record start time, finish time, and approximate total duration.
- Do not give the agent hints about previously observed npm or two-stage-save
  issues.

Not mentioning known issues is deliberate: the test should reveal whether the
repository guides the agent onto an efficient path by itself.

## Clean-account investigation prompt

> Install the ChatGPT Work YouTube skill from
> https://github.com/DRanger666/chatgpt-work-youtube-skill on this account, set
> it up completely, and confirm it is ready without analyzing a video. During
> the work, keep an observable installation-friction log and, after success,
> report every error, retry, workaround, fallback path, ambiguity, or source
> change encountered—even if resolved—then recommend concrete repository
> improvements without exposing credentials or private chain-of-thought.

This prompt asks for observable execution facts, not hidden reasoning or
private chain-of-thought. The distinction matters: the useful evidence is what
failed, what the agent did next, and what extra cost resulted.

## Required post-install report

The fresh-account session should report the following even when the final
result is successful.

### 1. Outcome

- Was the account-level skill installed and visible?
- Was the local MCP runtime restored and compiled?
- Did the MCP handshake pass?
- Were credentials and persistent cache locations verified without exposing
  secrets?
- Was any video, transcript, or Gemini request accessed despite the instruction
  not to analyze a video?

### 2. Friction log

Use one record per incident:

| Field | Required content |
|---|---|
| Trial | Anonymous trial identifier |
| Sequence | Order in which the incident occurred |
| Layer | One operational layer from the taxonomy |
| Stage | Precise operation in progress |
| Observable failure | Exact error or concise factual description |
| First attempted path | What the installer initially tried |
| Recovery taken | Retry, workaround, fallback, or changed path |
| Outcome | Recovered, partially recovered, or unresolved |
| Extra cost | Additional commands, retries, source inspection, rebuilds, or time |
| Source changed? | Whether repository or installed files were modified |
| Recommended fix | Concrete improvement |
| Fix location | Repository file, installation guidance, connector setup, upstream project, or platform |
| Confidence | Confirmed, probable, or uncertain |

Preferred compact notation:

`Layer → Stage → Observable failure → Recovery taken → Extra cost → Recommended fix location`

### 3. Clean-path reconstruction

After reporting incidents, the session should describe the shortest path it
believes would have worked in that exact environment if the discovered
information had been available from the beginning.

This is not a request for private reasoning. It is an operational
reconstruction made from observed commands, responses, and successful recovery
steps.

### 4. Suggested repository changes

Each recommendation should state:

- which observed incident it addresses;
- which file should change;
- whether it changes behavior or only documentation;
- whether it is safe to apply immediately;
- whether it should wait for reproduction in another clean account.

## Evidence collection

Save or manually transcribe:

- the final answer;
- intermediate messages that disclose errors or recovery actions;
- exact observable error text where available;
- screenshots showing important platform or connector responses;
- total elapsed time;
- whether the agent changed any source or installed files;
- the resulting skill name and readiness checks.

Do not collect or reproduce:

- Gemini API keys;
- GitHub PATs;
- complete credential-file contents;
- authentication headers;
- private chain-of-thought.

## Trial record template

Copy this section for each new account.

### Trial `A?`

- Date:
- Model and reasoning setting:
- Fresh account confirmed:
- Repository baseline:
- Start time:
- Finish time:
- Duration:
- Final outcome:
- Skill visible:
- MCP handshake:
- Number of exposed tools:
- Credential location verified:
- Cache location verified:
- Video accessed:
- Repository files changed:
- Installed skill files changed:

#### Incident 1

- Layer:
- Stage:
- Observable failure:
- First attempted path:
- Recovery taken:
- Outcome:
- Extra cost:
- Source changed:
- Recommended fix:
- Fix location:
- Confidence:

#### Clean-path reconstruction

-

#### Agent recommendations

-

#### Investigator notes

-

## Preliminary evidence from the first fresh-account trial

The first trial succeeded in approximately 12 minutes 58 seconds and installed
the skill. It restored the pinned MCP, completed its handshake, verified
private Gemini credential and cache locations, and did not analyze a video.

Two resolved incidents were visible during execution but were omitted from the
success-focused final report:

| Observed incident | Classification | Recovery observed | Current status |
|---|---|---|---|
| First runtime build encountered an npm-cache permission fault at `/root/.npm` | Work VM/runtime | Retried with a writable temporary npm cache | Confirmed in one trial; needs reproduction |
| First account skill-save request received a validation-layer rejection | ChatGPT skill platform | Checked reconciliation, then used a two-stage save path: metadata registration followed by scripts/references attached as an update to the same skill | Confirmed in one trial; exact platform rule needs reproduction |

These are hypotheses for improvement, not yet universal installation
requirements.

## Cross-trial analysis

After at least two additional clean-account trials, classify each incident:

| Classification | Meaning | Action |
|---|---|---|
| Deterministic | Reproduced consistently under the same conditions | Encode a direct fix or mandatory path |
| Environment-dependent | Reproduced only with a particular VM, account state, connector state, or platform response | Add detection and conditional recovery |
| Transient | Disappeared on an unchanged retry and lacks a stable trigger | Document retry bounds; avoid forcing a permanent workaround |
| Agent-path-dependent | Triggered by an avoidable first choice rather than the environment itself | Improve instructions so the efficient path is preferred |
| Unconfirmed | Observed once with incomplete evidence | Preserve as a hypothesis and gather another trial |

### Decision standard for repository changes

Apply a change when:

- the incident is reproducible or the fix is harmless and removes a known
  environmental assumption;
- ownership of the failure is clear;
- the proposed change does not blur operational layers;
- the change can be tested without consuming unnecessary Gemini requests.

Examples:

- A bootstrap script using its own writable npm cache is likely a harmless
  VM-hardening change.
- Declaring two-stage skill saving mandatory should wait until the platform
  behavior is reproduced or precisely characterized.
- A Drive connector failure should not trigger an MCP rebuild.
- A Gemini API failure should not be treated as evidence that account skill
  installation failed.

## Recommended development sequence after investigation

1. Complete clean-account trials against the frozen baseline.
2. Normalize all incident records using the common schema.
3. Separate deterministic failures from transient or agent-path-dependent
   friction.
4. Map every accepted improvement to its owning layer and repository file.
5. Implement improvements as modular commits with descriptive commit bodies.
6. Begin a new test round against the new commit hash.
7. Compare completion time, retry count, fallback count, and source exploration
   with the baseline.

## Success criteria

The repository is working well when a fresh ChatGPT Work account can:

- infer the intended account-level installation;
- install the skill without prior conversational context;
- restore the pinned MCP in a fresh VM;
- work around no hidden permission assumptions because the bootstrap path is
  already portable;
- verify Drive-held credentials and cache locations safely;
- complete readiness checks without processing a video;
- avoid unnecessary retries, source modifications, or broad solution-space
  exploration;
- clearly report any remaining friction even when it ultimately succeeds.

Successful installation is necessary. Efficient, deterministic, observable
installation is the stronger target.
