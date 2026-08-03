# Development backlog

This file is the actionable index for the repository's ongoing development,
feature, investigation, design, and refinement work.

## Active items

### LEDGER-001 — Run controlled clean-account installation trials

- Status: Planned
- Type: Investigation
- Layer: Cross-layer
- Evidence: One fresh account installed successfully, but its final answer
  omitted recoverable friction visible during execution.
- Next check:
  - [ ] Run trial `A2` against baseline commit `688642d`.
  - [ ] Run trial `A3` against the same commit.
  - [ ] Normalize both reports using the common incident schema.
  - [ ] Classify repeated incidents as deterministic, environment-dependent,
        transient, agent-path-dependent, or unconfirmed.
- Related document:
  [`investigations/chatgpt-work-installation-friction.md`](investigations/chatgpt-work-installation-friction.md)

### LEDGER-002 — Harden the npm cache path in fresh Work VMs

- Status: Worker implemented; acceptance pending
- Type: Work VM hardening
- Layer: Work VM/runtime
- Evidence:
  - Trial `A1` encountered a permission fault at `/root/.npm` and recovered by
    switching to a writable temporary cache.
  - The current installer still invokes both `npm ci` and `npm run build`
    without assigning a cache. In the current Work VM, npm still resolves its
    default cache to `/root/.npm`, so installation remains dependent on a path
    outside the writable Work storage.
  - The installer already creates a unique temporary build directory and
    removes it through its cleanup trap. An npm cache inside that directory
    changes no maintained installation path and leaves no persistent state.
- Decision:
  - Create one cache directory inside the installer's existing temporary build
    directory, for example `$build_root/npm-cache`.
  - Set `NPM_CONFIG_CACHE` explicitly to that directory for both `npm ci` and
    `npm run build`. Both commands must use the same isolated cache, including
    npm processes started by lifecycle scripts.
  - Do not inspect, create, repair, copy, or preserve `/root/.npm`. Do not use
    the user's home directory, a global npm configuration, the final portable
    installation, or the persistent credential directory for npm cache data.
  - Let the existing build-directory cleanup remove the cache after success or
    failure. Do not add migration, backup, or cache-reuse behavior.
  - Additional clean-account reproduction is no longer a prerequisite for
    this correction: the change removes a known external write assumption and
    has a bounded offline test plus a real clean-build acceptance check.
- Worker implementation:
  - [x] Update only the npm build portion of
        `scripts/ensure_youtube_mcp.sh`; do not alter the pinned MCP commit,
        Node version, maintained portable tree, credential handling, or MCP
        invocation path.
  - [x] Add a focused offline installer test with fake `git`, npm, and Node
        commands. Make the fake npm fail unless both npm invocations receive
        the same writable cache beneath the temporary build directory, and
        confirm that an inherited unusable npm-cache value cannot escape the
        installer override.
  - [x] Confirm that the temporary cache is absent after cleanup and never
        becomes an entry in `/workspace/youtube-mcp-portable`.
  - [x] Run the complete offline suite, shell and Python syntax checks,
        diff-integrity and active-reference scans, and credential-pattern
        checks. Do not replace the live MCP, access Drive, call Gemini, or
        update the installed skill.
- Worker outcome:
  - Commit `4f0f1e3` creates one npm cache inside the existing temporary build
    directory and exports it for both npm commands. The controlled fake-command
    test proves that the shared cache is writable, overrides an inherited
    unusable value, is removed by cleanup, and never enters the final portable
    tree.
  - All 94 offline tests passed under four hash seeds, together with shell and
    Python syntax, skill-package, diff-integrity, active-reference, and
    credential-pattern checks.
  - No live installation, Drive access, Gemini call, or installed-skill update
    was performed. The combined LEDGER-002/016/017 acceptance remains open.
- Main/user acceptance after implementation review and merge:
  - [ ] Run the single combined LEDGER-002/016/017 clean-install sequence.
  - [ ] Invoke the final installer while the caller's npm cache still resolves
        to the known unusable `/root/.npm` path; confirm that the installer
        builds successfully without creating or modifying that path.
  - [ ] Confirm that the temporary npm cache is removed and that the final
        portable tree contains only the directories and files defined by
        LEDGER-017.
  - [ ] Complete the MCP initialization and tool-enumeration handshake, then
        complete the persistent-credential checks in LEDGER-017.
- Completion rule: Keep LEDGER-002, LEDGER-016, and LEDGER-017 open until the
  same clean-install acceptance run proves the isolated npm build, final
  portable layout, MCP handshake, and persistent credential bootstrap.
- Related document:
  [`investigations/chatgpt-work-installation-friction.md`](investigations/chatgpt-work-installation-friction.md)

### LEDGER-003 — Characterize the account skill-save fallback

- Status: Hypothesis
- Type: Investigation
- Layer: ChatGPT skill platform
- Evidence: Trial `A1` received a validation-layer response on its first save,
  then succeeded after checking reconciliation and using a metadata-first,
  two-stage update.
- Next check:
  - [ ] Capture the exact observable response in another fresh account.
  - [ ] Determine whether the first request was rejected, asynchronously
        reconciled, or packaged incorrectly.
  - [ ] Encode conditional platform-installation guidance only after the
        behavior is sufficiently characterized.
- Related document:
  [`investigations/chatgpt-work-installation-friction.md`](investigations/chatgpt-work-installation-friction.md)

### LEDGER-011 — Remove cache-v2 Drive data after representative v3 validation

- Status: Planned
- Type: Maintenance
- Layer: Google Drive saved data
- Evidence: Cache v3 is deliberately isolated from cache v2, and the older
  files have little current value, but deleting them during implementation
  would mix cleanup with validation of the replacement.
- Next check:
  - [ ] Run separately authorized representative live v3 trials.
  - [ ] Confirm that the new saved responses, material indexes, and request
        logs can be found and reused from a fresh Work session.
  - [ ] Inventory the exact cache-v2 Drive files without modifying them.
  - [ ] After the user approves that inventory, delete only those v2 files and
        verify that `YouTubeVideoWork` remains unchanged.
- Related document:
  [`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md)

### LEDGER-016 — Simplify the portable installation layout

- Status: Worker implemented; acceptance pending
- Type: Refinement
- Layer: Work VM/local portable installation
- Evidence:
  - The installer creates `bin/youtube-research-mcp` and
    `bin/youtube-research-http`, but the supported workflow uses
    `scripts/call_youtube_mcp.mjs`, which directly starts the pinned Node
    runtime and `app/dist/stdio-server.js`. No active workflow invokes either
    wrapper; the stdio wrapper remains referenced only by the installer's own
    verification check.
  - The installer creates and documents `materials/`, but no runtime code
    reads or writes it. MCP results are deliberately temporary, while reusable
    Gemini responses are stored on Drive.
  - `workspace/` is assigned both disposable argument and intermediate files
    and the future `gemini-keypool-state.json` path. Those two purposes should
    not share one vaguely named directory.
  - Naming an inner directory `workspace/` under
    `/workspace/youtube-mcp-portable` obscures the distinction between the
    mounted Work storage root and the installation's temporary files.
  - The current portable installation contains reproducible MCP source,
    dependencies, build output, and runtime files. Durable Gemini responses,
    material indexes, and request logs live on Drive; credentials can be
    restored from Drive; and no current Gemini routing state needs to be
    retained. Nothing in the old local installation warrants backup or data
    transfer.
- Decision:
  - Keep `/workspace/youtube-mcp-portable` as the exact installation path.
  - Keep `app/` and `runtime/` for the pinned MCP application and pinned Node
    runtime. The first LEDGER-016 implementation also retained `config/` as an
    interim credential location; LEDGER-017 superseded that choice before
    acceptance by moving credentials outside the replaceable installation.
  - Remove `bin/` and both generated launchers. Verify and invoke the MCP
    directly through the same Node executable and compiled stdio server used
    by `scripts/call_youtube_mcp.mjs`. Do not retain the unused HTTP entrypoint.
  - Remove `materials/` without introducing a renamed replacement.
  - Replace `workspace/` with `work/` for disposable local arguments,
    requests, responses, downloaded working copies, and intermediate JSON.
  - Reserve `state/gemini-keypool-state.json` for router state created by
    future Gemini use. The new installation starts with no state to transfer;
    the router creates the file when it first has state to write.
  - Implement only the maintained layout. Do not add code for backup,
    carry-over, conversion, or compatibility with the discarded pre-release
    layout.
  - After the LEDGER-017 correction, the maintained layout accepted by the
    combined test is exactly:

    ```text
    /workspace/youtube-mcp-portable/
      app/
      runtime/
      state/
      work/
      README.md
      VERSION
    ```

- Worker implementation:
  - [x] In the initial LEDGER-016 stage, change
        `scripts/ensure_youtube_mcp.sh` to create `app/`, `config/`, `runtime/`,
        `state/`, `work/`, `README.md`, and `VERSION`; LEDGER-017 subsequently
        removed the interim `config/` entry.
  - [x] Remove creation of `bin/youtube-research-mcp` and
        `bin/youtube-research-http`, their permission changes, their generated
        README entries, and the wrapper-only verification condition.
  - [x] Keep `verify_install()` focused on the maintained installation: require
        `VERSION`, the pinned MCP commit, the pinned Node executable and
        version, and `app/dist/stdio-server.js`; perform tool enumeration
        directly through `scripts/call_youtube_mcp.mjs`.
  - [x] Require `work/` and `state/` when recognizing an existing maintained
        installation. Do not recognize the former
        `bin/`/`materials/`/`workspace/` tree as current.
  - [x] If the exact destination already exists but fails current verification,
        stop with a clear replacement-required message. Do not delete, rename,
        back up, or modify it from the implementation script.
  - [x] Update `SKILL.md`, `references/contracts.md`, the generated portable
        `README.md`, and `.gitignore` to use only `work/` and `state/` for their
        defined purposes. Remove active references to the deleted directories
        and launchers; preserve historical ledger evidence unchanged.
  - [x] Change every operational path from `$install/workspace/` to
        `$install/work/`, and change the router-state path to
        `$install/state/gemini-keypool-state.json`. Credential handling remained
        unchanged only for this initial stage and was then corrected by
        LEDGER-017.
  - [x] Add focused repository checks for the maintained paths and removed
        launcher-generation code. Run shell syntax checks, the complete
        existing offline suite, active-reference scans, and skill-package
        validation. Do not install an MCP, call Gemini, access Drive, modify the
        installed skill, or alter `/workspace/youtube-mcp-portable`.
- Worker outcome:
  - The installer now recognizes only the complete maintained root tree,
    verifies the pinned runtime and compiled stdio server directly, and stops
    without changing an invalid exact destination.
  - Runtime instructions use `work/` only for disposable files and
    `state/gemini-keypool-state.json` only for Gemini router state.
  - Focused layout checks and all 85 offline tests passed under four hash seeds,
    together with shell syntax, active-reference, and skill-package checks.
  - No MCP installation, Gemini request, Drive operation, installed-skill
    update, or change to `/workspace/youtube-mcp-portable` was performed.
- Main/user acceptance after implementation review and merge:
  - [ ] Run these checks only after LEDGER-002 and LEDGER-017 are implemented.
        Use LEDGER-017's final credential location and portable tree; do not
        accept the interim `config/` directory as part of the maintained
        installation.
  - [ ] Delete the existing `/workspace/youtube-mcp-portable` installation.
  - [ ] Run the merged installer to build a fresh portable installation from
        the pinned source and dependencies.
  - [ ] Confirm the exact maintained tree and absence of the removed
        installation-root `bin/`, `materials/`, and `workspace/` directories.
  - [ ] Start the newly installed MCP locally and complete initialization plus
        tool enumeration. Do not access a video, Gemini, Drive, or a credential.
  - [ ] Confirm that a complex MCP argument file can be read from `work/` and
        that the configured future router-state path is under `state/`.
- Completion rule: The worker must leave this item open after implementation.
  Close LEDGER-002, LEDGER-016, and LEDGER-017 only after their combined
  main/user acceptance checks pass, the installed MCP handshake succeeds
  without launcher wrappers, and no active contract, procedure, script, or
  test refers to the removed installation-root `bin/`, `config/`, `materials/`,
  or former `workspace/` directory. The required Node executable remains
  `runtime/bin/node`.

### LEDGER-017 — Persist Gemini credentials independently of the MCP installation

- Status: Worker implemented; acceptance pending
- Type: Credential bootstrap correction
- Layer: Google Drive connector and mounted Work storage
- Evidence:
  - The current procedure writes `youtube-workbench-secrets.env` inside
    `/workspace/youtube-mcp-portable/config/`. That couples a persistent
    credential to a reproducible installation which is deliberately replaced
    as one unit.
  - The instruction to "materialize" the Drive file does not tell a fresh Work
    session how to move the credential from the connector result into the VM.
    This ambiguity has already caused Work sessions to hesitate or pursue
    inconsistent paths.
  - The maintained `work-vm-terminal-git` skill demonstrates the useful
    boundary: read the canonical Drive file as ordinary text, pass credential
    data through standard input to a deterministic local helper, and keep the
    protected local copy under `/workspace/.chatgpt-work-credentials/`.
    Git-specific configuration and credential-helper behavior do not apply to
    Gemini.
- Decision:
  - Store the local Gemini credential only at
    `/workspace/.chatgpt-work-credentials/youtube/youtube-workbench-secrets.env`.
    Set the directory mode to `0700` and the file mode to `0600`.
  - Keep credentials outside `/workspace/youtube-mcp-portable`. Remove
    `config/` from the portable installer, verifier, generated README, active
    contracts, and layout tests. The final maintained portable tree is:

    ```text
    /workspace/youtube-mcp-portable/
      app/
      runtime/
      state/
      work/
      README.md
      VERSION
    ```

  - Check and reuse the protected local file first. Read Drive only when that
    file is absent, empty, or invalid. An unrelated network, quota, request, or
    repository error is not a reason to read Drive again.
  - Use the existing canonical Drive location: folder `WorkModeCredentials`
    with ID `1q58TvI519TDgTePQG1h2Rof5EdA2jDJk`, and file
    `youtube-workbench-secrets.env` with ID
    `1rvfVswFWzIoqMOKsJttZgTsRkpbiKxNx`. Prefer the stable file ID; if it is
    unavailable, require one exact filename match inside the verified folder.
  - Fetch the Drive file as ordinary readable text. The connected Drive tool
    and the active Work session are authorized to read that plaintext. They
    must not reproduce it in commentary, final answers, terminal command
    arguments, or command output.
  - Pass the fetched text on standard input to one deterministic credential
    helper. Never shell-source the Drive response. The helper must accept only
    `GEMINI_API_KEY` and `GEMINI_API_KEY_FALLBACK`, require each exactly once
    with a non-empty distinct value, reject every other assignment or malformed
    line, and write a normalized two-assignment file atomically without
    printing either value.
  - Make the Gemini router read the normalized local file directly after it
    verifies the pending request binding. Do not require an agent to export or
    shell-source credentials, and do not accept credential values on command
    lines.
  - If Gemini explicitly rejects a configured credential, preserve the router
    result and stop. Automatic credential replacement and router-state reset
    are outside this initial bootstrap correction; do not mistake other
    failures for credential rejection.
- Worker implementation:
  - [x] Add one narrowly scoped credential helper with `install` and `check`
        operations. `install` reads the complete Drive text from standard input
        and writes only the fixed local path; `check` validates the fixed local
        file and its permissions without printing credential data.
  - [x] Change `scripts/gemini_request.py` to load the two buckets from the
        validated fixed local file instead of process environment variables.
        Preserve the rule that request-file and pending-run verification occurs
        before any credential is read.
  - [x] Remove `config/` from `scripts/ensure_youtube_mcp.sh` and every active
        description or test of the portable layout. Do not add migration,
        backup, compatibility, or credential-transfer behavior to the MCP
        installer.
  - [x] Replace the vague credential paragraph in `SKILL.md` with the exact
        local-first check, Drive text retrieval, standard-input install, and
        local-file router procedure. Update `references/contracts.md`, relevant
        design text, `.gitignore`, tests, and `REPOSITORY_MAP.md` without
        duplicating the runtime procedure.
  - [x] Add offline tests using fake credentials and temporary paths for exact
        parsing, rejection of missing/duplicate/unexpected/identical values,
        atomic replacement, `0700`/`0600` permissions, secret-free output,
        local-file bucket loading, and request verification before credential
        access. Ensure the final portable-layout tests reject `config/`.
  - [x] Run the complete offline suite, Python/shell/Node syntax checks,
        skill-package validation, active-path scans, credential-pattern scans,
        and diff-integrity checks. Do not access Drive, call Gemini, change the
        live credential directory, replace the installed MCP, or update the
        installed skill.
- Worker outcome:
  - Commit `d4e3099` added the fixed-path stdin credential helper, strict
    two-assignment validation, atomic normalized writes, protected permissions,
    and secret-free checks.
  - Commit `7fffe93` made the router load exactly two distinct local-file keys
    only after request and pending-run verification. Existing routing, retry,
    cooldown, and attempt-history behavior remains unchanged.
  - Commit `b4383d1` removed the credential directory from the portable MCP
    tree and made that former root entry fail current-layout recognition.
  - All 93 offline tests passed under four hash seeds, together with Python,
    shell, Node, skill-package, active-path, credential-pattern, and diff checks.
  - No Drive access, Gemini call, live credential change, MCP replacement, or
    installed-skill update was performed.
- Main/user acceptance after implementation review and merge:
  - [ ] Remove the existing portable installation and rebuild the final
        LEDGER-002/016/017 tree from the pinned MCP source.
  - [ ] Complete the MCP initialization and tool-enumeration handshake without
        root launcher scripts or a portable `config/` directory.
  - [ ] If the protected local credential is absent, retrieve the canonical
        Drive file once as readable text and install it through standard input.
        Verify the fixed path and permissions without displaying either key.
  - [ ] Repeat the credential check and MCP installer invocation using only the
        existing `/workspace` files; confirm that neither operation needs
        another Drive read or changes the credential file.
- Completion rule: Keep LEDGER-002, LEDGER-016, and LEDGER-017 open until the
  combined acceptance checks pass. Completion establishes an isolated npm
  build, persistent Drive-to-VM credential bootstrap, and a clean reproducible
  MCP installation; it does not claim that a Gemini key is accepted by the
  remote API. That live check remains part of the separately planned
  representative saved-work validation.

### LEDGER-018 — Reconcile requested and returned transcript end times

- Status: Planned from live evidence
- Type: Transcript validation and range-planning correction
- Layer: Gemini transcript checking, saved material, and missing-range planning
- Evidence:
  - During the first representative live test, YouTube exposed
    `I9tX-lFUTrw` with an integer duration of `198` seconds. A Gemini transcript
    request for `[0, 198000)` returned a coherent complete transcript whose
    declared end and completed-through time were `197000` milliseconds.
  - A changed request for `[0, 197000)` then returned a coherent complete
    transcript ending at `196892` milliseconds. The current checker classified
    both entire responses as `clip_mismatch` and retained none of their proven
    prefix as reusable material.
  - Treating either difference as an ignorable tolerance would risk hiding
    speech, music, noise, or other content at the video boundary. Repeatedly
    subtracting a rounded second also does not establish the actual source end.
- Required correction:
  - Do not require exact equality between a requested end and a shorter
    returned end as a condition for preserving all earlier valid transcript
    coverage. Validate the returned prefix mechanically and keep its exact
    completed-through time.
  - Keep the interval between that time and the requested end explicit. Do not
    round it away, silently call it covered, or discard the already validated
    prefix.
  - Establish a trustworthy way to obtain or reconcile precise source duration
    before declaring that an apparent tail lies beyond the video rather than
    remaining unprocessed. An integer YouTube duration and Gemini's own claim
    are not, individually, sufficient proof.
  - Distinguish an end-of-source discrepancy from an early stop inside an
    ordinary mid-video clip. Later-than-requested timestamps, invalid segment
    ordering, inconsistent completion flags, and content outside the returned
    bounds remain failures.
  - Prevent a decrement-and-retry loop. A changed request may be made only when
    the remaining range is real and the new request can obtain new evidence.
- Implementation acceptance:
  - [ ] Amend the transcript checker and range planner only after the precise
        source-duration boundary and its evidence are defined in the governing
        transcript contract.
  - [ ] Add secret-free offline cases for exact bounds, a shorter valid prefix,
        an actual source end between whole seconds, a genuine early stop in a
        mid-video clip, a later-than-requested end, inconsistent completion
        fields, and an unresolved final interval containing possible audio.
  - [ ] Prove that a valid prefix remains searchable while only the unresolved
        suffix is offered for further work.
  - [ ] Prove that neither whole-second rounding nor an arbitrary tolerance can
        mark an unexamined suffix as covered.
  - [ ] Use the two retained live responses only as observed evidence. Do not
        repeat either Gemini request during implementation or mutate its Drive
        record as part of offline validation.
- Completion rule: Close only after the corrected checker preserves proven
  coverage without making a false full-video claim, and a representative live
  acceptance run distinguishes true source end from an unprocessed tail.

## Completed refinements

### LEDGER-014 — Remove redundant timestamp-coordinate metadata

- Status: Completed
- Type: Design correction and implementation
- Layer: Gemini request metadata, response storage, material indexing, and
  search
- Evidence:
  - The first cache-v3 storage implementation accepted only video-start
    timestamps. A later negative search test used `clip_relative` only to prove
    that a different value would not match stored material; the system never
    implemented creation or conversion of that alternate coordinate.
  - The saved-material rewrite renamed the field to `timestampsRelativeTo` and
    allowed arbitrary non-empty values for generic reusable output, even though
    no supported workflow or output format defined another interpretation.
  - `sourceTimeRange` and `coveredTimeRanges` already express which partial
    interval was processed and retained. The extra field does not enable
    focused processing or partial reuse.
- Decision:
  - Define every millisecond time range as an offset from the beginning of the
    YouTube video.
  - Define `gemini-transcript` version `1` timestamp strings as offsets from the
    beginning of the same video.
  - Remove `timestampsRelativeTo`, `timestampBasis`,
    `TIMESTAMPS_FULL_VIDEO`, `--timestamps-relative-to`, and any renamed
    replacement. Do not preserve the mistake as a constant-valued field.
  - Save and index any checked partial interval immediately; processing the
    rest of the video is not a prerequisite.
  - Keep `languagePolicy` as a genuine material-search condition. This
    correction must not remove or weaken it.
- Required implementation:
  - [x] Correct the governing storage/search design before runtime work begins.
  - [x] Remove timestamp-coordinate metadata from the request-log fields,
        request construction APIs, CLI, validation, and immutable-metadata
        comparisons.
  - [x] Remove it from saved responses, saved-response identity, material-index
        entries, index rebuilding, material queries, filtering, returned search
        data, missing-range output, and chunk output.
  - [x] Make the transcript format contract and checker own the video-start
        timestamp rule without storing a separate coordinate label.
  - [x] Update `SKILL.md`, `references/contracts.md`, and active examples.
        Preserve completed historical ledger records.
  - [x] Add offline tests that save and reuse a focused nonzero interval, reject
        every removed field at public file and command boundaries, and prove
        that transcript checking still compares returned timestamps with the
        absolute requested interval.
  - [x] Run the complete offline suite and package validation without Gemini
        calls or live Drive writes.
- Outcome:
  - Commit `a0bde4d` removed the redundant metadata from runtime schemas,
    identities, APIs, commands, saved material, search, and tests.
  - Every numerical range now has one video-start interpretation, while
    `gemini-transcript` version `1` owns its corresponding textual timestamp
    contract.
  - Focused nonzero intervals remain immediately saveable and reusable, and
    `languagePolicy` remains a material-search condition.
  - All 81 offline tests and skill-package validation passed without Gemini or
    Drive mutation.
- Completion rule: Close this item only when the removed identifiers no longer
  occur in runtime code, current contracts, active examples, or tests; their
  appearance inside preserved historical evidence does not count as active
  support.
- Related document:
  [`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md)

### LEDGER-015 — Remove language-policy metadata

- Status: Completed
- Type: Design correction and implementation
- Layer: Gemini request metadata, response storage, material indexing, and
  search
- Evidence:
  - `languagePolicy` was introduced to distinguish source-language material
    from saved translations. LEDGER-012 subsequently removed translation as a
    saved and searchable output because ChatGPT can translate source material
    on demand.
  - The remaining validator accepts any non-empty object, while material
    search compares those objects for exact equality. No controlled set of
    keys or values gives that comparison a stable meaning.
  - Transcript mode already requires original spoken language and native
    script. Its segment-level `language` values record observed content; the
    additional top-level policy does not alter or clarify that content.
  - Systematic onscreen text should preserve the text and script visible in
    the video. A translated rendering is derived material and must not become
    a separately saved search variant.
- Decision:
  - Save source-language material only. Preserve original spoken language in
    transcripts and original visible text in systematic onscreen-text output.
  - Translate saved source material on demand in ChatGPT. Do not save, index,
    or search translated variants.
  - Remove `languagePolicy`, `sourceLanguage`, `--language-policy`, and any
    renamed replacement from active storage, identity, indexing, search,
    request logging, and planning interfaces.
  - Do not add a constant-valued replacement or a video-wide language label
    merely to restate the source-language rule. Multilingual and code-switching
    evidence remains in the saved content itself, including transcript
    segment-level language values.
  - Do not divide summaries or systematic visual descriptions into separate
    search entries according to the language of their generated prose. When a
    different presentation language is needed, ChatGPT derives it from the
    saved material at use time.
- Required implementation:
  - [x] Correct the governing storage/search design before changing runtime
        code.
  - [x] Remove the field from request-log fields, request construction APIs,
        command-line arguments, validators, and immutable-metadata checks.
  - [x] Remove it from saved responses, saved-response identity,
        material-index entries, index rebuilding, material queries, filtering,
        returned search data, missing-range output, and chunk output.
  - [x] Keep original-language transcript and onscreen-text requirements in
        their output instructions or format contract rather than representing
        them as stored search metadata.
  - [x] Update `SKILL.md`, `references/contracts.md`, active design material,
        examples, and tests. Preserve completed historical ledger records.
  - [x] Add offline tests that reject the removed field at public file and
        command boundaries, retain transcript segment language content, save
        source onscreen text without language-policy metadata, and perform
        material search without language-based fragmentation.
  - [x] Run the complete offline suite and skill-package validation without
        Gemini calls or live Drive writes.
- Outcome:
  - Commit `e360e8f` removed language metadata from the governing saved-material
    model before runtime changes.
  - Commit `d8c2fe4` removed the validator, Python and command interfaces,
    request-log field, saved-response and identity field, material-index field,
    query condition, and language-fragmented compatibility check.
  - Transcript requests retain the tested original-language prompt, transcript
    segment `language` values remain stored content, and source onscreen text
    is saved and reused without a top-level language label.
  - Removed metadata is rejected at every tested request-log, saved-response,
    material-index, query, search-plan, missing-range, and chunk boundary.
  - All 81 offline tests and skill-package validation passed without Gemini or
    Drive mutation.
- Completion rule: Close this item only when the removed active identifiers no
  longer occur in runtime code, current contracts, active examples, or tests;
  their appearance inside preserved historical evidence does not count as
  active support.
- Related documents:
  - [`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md)
  - [`../references/contracts.md`](../references/contracts.md)

### LEDGER-013 — Clarify documentation ownership and restore long-video planning

- Status: Completed
- Type: Refinement and regression correction
- Layer: Repository documentation and Gemini request planning
- Evidence:
  - `youtube-saved-work.md` combined whole-system routing, saved-response
    search, and request-history design under a misleading name.
  - `gemini-interactive-quota-pool.md` duplicated request-log rules.
  - Replacing the earlier cache implementation removed the deterministic
    `plan-chunks` command even though the runtime guidance still relied on it.
  - A real 2-hour-15-minute whole-video request failed while its
    `0s`–`1800s` clip succeeded, so bounded long-video planning remains an
    evidence-backed operating requirement.
- Outcome:
  - Added `REPOSITORY_MAP.md` with concern-specific ownership and a complete
    maintained-file map.
  - Split saved Gemini response storage/search from Gemini request execution;
    merged primary/fallback quota routing into the latter and removed the two
    misleading broad documents.
  - Kept `SKILL.md` as the sole runtime source-order authority: MCP material
    first, saved Gemini material second, and a new Gemini request only for the
    remaining gap.
  - Restored deterministic splitting of verified missing ranges, with the
    tested 1,800-second general default and the 600-second/four-second-overlap
    transcript policy preserved as distinct operating choices.
  - Preserved historical ledger entries instead of rewriting them around the
    new structure.
- Related documents:
  - [`../REPOSITORY_MAP.md`](../REPOSITORY_MAP.md)
  - [`../SKILL.md`](../SKILL.md)
  - [`../references/contracts.md`](../references/contracts.md)
  - [`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md)
  - [`design/gemini-request-execution.md`](design/gemini-request-execution.md)

### LEDGER-012 — Derive translations instead of storing them

- Status: Completed
- Type: Refinement
- Layer: Reusable video material
- Evidence: Translation can be produced on demand by ChatGPT from saved
  original-language transcripts or systematic onscreen text. Saving and
  searching a separate Gemini translation duplicates derived material without
  recovering information that ChatGPT otherwise lacks.
- Outcome:
  - Removed `translation` from the controlled reusable-output registry before
    any live v3 use.
  - Rejected translation in request logging, response saving, material-index
    admission, and search through the shared controlled registry.
  - Retained on-demand translation as a ChatGPT consumption step over saved
    source-language material.
- Related document:
  [`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md)

## Completed Gemini-response and video-material release corrections

The earlier implementation remains useful evidence, but its public names and
its automatic crash-handling design are not the release specification.
LEDGER-008 and LEDGER-009 are governed by
[`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md);
LEDGER-010 is governed by
[`design/gemini-request-execution.md`](design/gemini-request-execution.md).

### LEDGER-008 — Find and reuse video material before Gemini

- Status: Completed
- Type: Design correction and implementation
- Layer: Video-material search and request planning
- Problem: A request-file hash can identify an earlier Gemini request, but it
  cannot answer whether reusable transcripts or other source material already
  satisfy the user's present need.
- Goal: Search the video material index by video ID, output type, output
  format, language, timestamp policy, and verified covered time. Construct a
  Gemini request only for material or visual evidence that remains missing.
- Evidence retained from the earlier implementation:
  - Exact, containing, combined, overlapping, incomplete, incompatible, stale,
    and missing time-range planning worked offline.
  - Selected-file-only downloading and replanning after stale files worked.
  - Commits `cec862d`, `1e72955`, `da14941`, `bee56d7`, and `0c7a74d` preserve
    that history.
- Correction resolved:
  - Checkpoint `a9ab341` allowed caller-supplied transcript time ranges without
    checking the returned transcript.
  - The old public interface described saved work as artifacts and the
    per-video list as a manifest; the replacement now uses concrete filenames
    and video-material terms.
- Completed release work:
  - [x] Replaced `scripts/artifact_cache_v3.py` with
        `scripts/saved_gemini_responses.py`; do not leave a compatibility
        wrapper.
  - [x] Plan from `<videoId>--video-material-index.json`, then download and
        verify only the selected saved-response files.
  - [x] Accept only `transcript`, `translation`, `summary`,
        `systematic_visual_description`, and `systematic_onscreen_text` as
        initial reusable output types. Reject arbitrary categories.
  - [x] Enforce the deliberately asymmetric initial format registry:
        `transcript` uses structured `gemini-transcript` version `1`; the other
        four reusable output types use minimal `gemini-free-form-text` version
        `1`. Reject unregistered formats and incompatible type-format pairs.
  - [x] Search explicit index fields in that order: controlled output type,
        output-format version, language, timestamp policy, and covered time.
        Use `savedResponseId` only after selection to retrieve and verify the
        chosen file.
  - [x] Derive transcript covered time mechanically from the checked Gemini
        response and its actual requested clip. Never accept it from a caller.
  - [x] Exclude `task_specific_observation` and `direct_answer` responses from
        Drive response storage and ordinary material search, regardless of
        prompt similarity.
  - [x] When reusable material leaves a visual-sensory gap, request a narrowly
        scoped `task_specific_observation` and let ChatGPT reason over it.
  - [x] Return only missing time ranges for new request construction.
  - [x] Re-ran the full material-search matrix, including malformed,
        incomplete, mismatched-clip, excluded-class, and systematic-OCR
        responses.
- Outcome:
  - `scripts/saved_gemini_responses.py` plans from readable index fields and
    verifies only selected response files before exposing missing ranges.
  - The actual planner matches interval-union results across 5,500
    deterministic randomized cases under each validation seed.
  - Implementation commits: `35b95bb`, `aaeb9c5`, and `69a0e8b`.

### LEDGER-009 — Maintain a video material index and saved Gemini responses

- Status: Completed
- Type: Design correction and implementation
- Layer: Google Drive response and material files
- Problem: Request-hash filenames cannot enumerate useful work for one video,
  while the earlier replacement used generic file names and split information
  in a way that made its promised index rebuilding unreliable.
- Goal: Keep one predictable per-video material index and separate,
  never-edited saved-response files. Every successful `video_material`
  response is preserved; every eligible one is indexed after its required
  validation or review. The two one-time classes write no response files.
- Evidence retained from the earlier implementation:
  - Per-video lookup, separate output files, file-integrity checking, and index
    rebuilding worked offline under the earlier names.
  - Commits `904c14e`, `1e72955`, `da14941`, `bee56d7`, and `0c7a74d` preserve
    that history.
- Correction resolved:
  - Checkpoint `a9ab341` could index malformed transcript content as complete.
  - Commit `186c9d2` correctly separated saved-work search from Gemini request
    history, but its stronger crash-reconstruction rules are no longer part of
    the governing design.
- Completed release work:
  - [x] Use the `YouTubeVideoWork` Drive folder,
        `<videoId>--video-material-index.json`, and
        `<videoId>--gemini-response--<outputType>--<savedResponseId>.json`.
  - [x] Use file-format field names defined in `youtube-saved-work.md`; remove
        the old artifact, manifest, contract, and valid-coverage field names.
  - [x] Keep request status, attempts, cooldowns, retry reasons, and session
        information out of the video material index. Keep the saved response's
        verified request ID, run number, and exact request hash out of material
        search fields while retaining them in the saved file and its identity.
  - [x] Save every successful `video_material` response in full, including a
        malformed structured response. Never write a saved-response file for
        a task-specific observation or direct answer.
  - [x] Copy the requested source time range into each saved response and its
        content metadata. Calculate saved-response identity from every
        immutable saved field, including video ID, request ID, run number,
        exact request hash, safe router result, and response hash, so every
        successful run has one self-identifying response record.
  - [x] Remove the global `reusable` and `unusableReason` fields. Treat material
        index admission as the reuse decision; do not replace them with general
        `contentCheckStatus` or `contentCheckFailure` fields.
  - [x] Run a deterministic format checker exactly when the declared output
        format requires it. A free-form format must not receive a fabricated
        check status.
  - [x] Treat `gemini-free-form-text` version `1` as ordinary generated text
        without a machine-readable response contract. Add no dedicated
        structured format for a reusable output type until observed need
        defines its checker, search effect, and offline tests.
  - [x] Add only `video_material` to the index. A malformed transcript must
        contribute no covered time even though its response remains saved.
  - [x] Identify index entries only by `savedResponseId`. Append every new ID
        without replacing entries that share an interval, overlap, or use the
        same output type; treat an identical existing ID as a verified
        idempotent no-op.
  - [x] Keep transcript, translation, summary, systematic visual description,
        and systematic onscreen text entries together when they describe the
        same source interval.
  - [x] Rebuild a missing index from saved responses whose predeclared class is
        `video_material`. Do not create an empty index until response
        enumeration confirms that no qualifying file can be admitted.
  - [x] Keep normal operation completely separate from cache-v2 files; add no
        migration, fallback, validator, or permanent compatibility path.
- Outcome:
  - Saved responses are immutable and self-identifying; the material index is
    search-only and can be rebuilt from eligible saved files and explicit
    free-form review decisions.
  - Failed structured responses and rejected free-form responses remain saved
    but do not create false coverage.
  - Implementation commits: `35b95bb` and `69a0e8b`.

### LEDGER-010 — Log Gemini requests and prevent blind repetition

- Status: Completed
- Type: Design correction and implementation
- Layer: Gemini requests and persistent request history
- Problem: The first cache-v3 implementation discarded request-attempt and
  retry safeguards from LEDGER-004. The later repair restored them but added
  session ownership, expiry, handoff, and automatic crash-handling machinery
  that the interactive workflow does not justify.
- Goal: Keep a plain per-video Gemini request log. Verify that the exact request
  file recorded for a pending run is the one sent, preserve every authorized
  run and every safe routing attempt returned to the active workflow, and stop
  for the user's decision when an earlier run has an uncertain outcome.
- Evidence:
  - Commit `1e72955` stopped consuming `ROUTING_JSON` and removed documented
    retry authorization and attempt preservation.
  - Audit checkpoint `a9ab341` proved that the recorded request could differ
    from the file and endpoint sent to the router. It also exposed missing
    cooldown enforcement and contradictory request history.
  - Commits `d13127f`, `bee56d7`, and `0c7a74d` contain useful attempt-log and
    routing-validation work, but their writer-management interface is rejected.
  - Commit `186c9d2` is a diagnostic checkpoint, not the implementation
    specification.
  - Commit `3744de4` still represented status, authorization, and response
    reference as singular request-level fields while allowing authorized
    repeats. A later run could therefore overwrite the history of an earlier
    one.
- Completed release work:
  - [x] Replaced `scripts/gemini_execution_journal_v3.py` with
        `scripts/gemini_request_log.py`; do not leave a compatibility wrapper.
  - [x] Expose run-oriented operations such as `start-run`, `verify-run`,
        `finish-run`, and `mark-run-interrupted`. For run numbers above `1`,
        record authorization and append the pending run in the same update.
  - [x] Build each logical request entry by reading the actual request file.
        Store its exact prompt, normalized-request hash, video ID, clip,
        endpoint, model, method, and predeclared `contentClass` as immutable
        request-level fields. Require controlled `outputType` and compatible
        `outputFormat` only for `video_material`; forbid both fields for the
        two one-time classes.
  - [x] Store an ordered `runs` list under that request. Start `runNumber` at
        `1`, increment without gaps, and keep exact request-file hash, times,
        status, routing attempts, cooldown, authorization, and the applicable
        successful outcome fields inside the corresponding run.
  - [x] Permit at most one pending run per request, require it to be the
        highest-numbered run, and forbid appending another run before it is
        terminal.
  - [x] Remove separately writable request-level status, authorization,
        cooldown, and saved-response fields. Calculate current status from the
        highest-numbered run and enumerate each successful run's saved-response
        reference or deliberate-non-storage marker when retrieving results.
  - [x] Make `gemini_request.py` verify the immutable request information,
        exact hash, request ID, run number, and highest pending run before
        loading a credential.
  - [x] Bind content class and the applicable reusable output fields immutably
        to the logical request entry without adding local classification to
        request identity. Reject conflicting metadata for an existing request
        ID and reject a caller's attempt to replace it after the call.
  - [x] Let a purpose-specific builder fix an unambiguous class, including
        `video_material` for transcript mode. Require the generic prompt route
        to declare its class explicitly; do not supply a silent default. For
        `video_material`, require one controlled reusable output type and its
        compatible format.
  - [x] Use `fileFormatVersion` and the plain request-log field names in the
        request log, routing metadata, and local bucket-state file; update the
        operational documents and tests in the same implementation commit.
  - [x] Persist every safe primary, fallback, transient, failed, and successful
        routing attempt returned to the active workflow inside the run that
        made it. Bind routing output to both request ID and run number. If an
        invocation ends before a terminal safe router result is retained,
        leave the run pending with an unknown network outcome; never fabricate
        missing attempts or infer success or failure.
  - [x] Keep bounded router retries and credential failover inside one run.
        Every later deliberate execution must append another run with one new,
        consumed user authorization; never overwrite an earlier run.
  - [x] Enforce saved cooldowns and reject unchanged terminal request errors.
  - [x] Require a complete saved-response reference before marking a
        `video_material` run `succeeded`, including a failed-format response.
        For a task-specific observation or direct answer, require `finish-run`
        to verify the actual successful router result and response-file hash,
        copy routing attempts and terminal time, generate
        `responseNotSavedByPolicy: true`, and forbid saved-response fields.
        Never accept that Boolean, status, attempts, or completion time from
        the caller.
  - [x] Require the response-saving command to verify the router result's
        request ID, run number, and exact request hash against the pending run,
        recompute SHA-256 over the exact response-file bytes, require equality
        with the router result's `responseSha256`, then write that binding and
        the complete safe router result into the saved response.
  - [x] When a later session finds one exact verified saved response for a
        pending run, require user confirmation that the earlier session has
        stopped and finish that existing run without another Gemini call. Use
        the retained router result to restore every attempt contained in that
        result and its terminal attempt time for `endedAt`.
  - [x] Number router attempts from `1` without gaps and require each successful
        router result to contain the run's complete ordered attempt history.
        Existing pending-run attempts must match an exact prefix; append only
        the missing suffix and reject conflicts, duplicates, gaps, reordering,
        extra stored attempts, or a non-final terminal attempt.
  - [x] Never finish a pending run from an unlinked response. Stop for
        investigation when multiple responses claim one run or any binding or
        integrity check fails.
  - [x] Use only `pending`, `succeeded`, `failed`, and `interrupted` run states.
        Keep `endedAt` null while pending and require it for a terminal run. An
        old pending run must stop and ask the user; elapsed time alone must not
        authorize another call.
  - [x] Remove writer, lease, renewal, release, handoff, takeover, and automatic
        reconciliation commands and tests.
  - [x] State the supported same-video rule plainly: do not intentionally use
        two write-capable sessions for one video; Drive cannot guarantee a
        lock between truly simultaneous sessions.
  - [x] Added offline tests for request-file mismatch, all duplicate states,
        explicit retry reasons, cooldowns, interrupted-run decisions,
        routing consistency, immutable pre-call classification, relabelling
        that cannot bypass duplicate prevention, exact prompt retention,
        controlled output-type rejection, deliberate non-storage markers,
        bare-marker rejection, one-time failed and mismatched router-result
        rejection, one-time response-byte verification, copied one-time attempt
        history and terminal time, monotonic run numbering, multiple successful
        reusable response references, saved-response back-links,
        interrupted-write completion without a new network call, response-byte
        hash mismatch, attempt-prefix reconciliation, unlinked and conflicting
        response rejection, router interruption with an unknown network outcome
        and no invented attempt, append-only terminal history, derived current
        status, and absence of credentials in saved files.
- Outcome:
  - The router verifies the exact highest pending request before credential
    loading and validates every result before writing it.
  - Numbered authorized runs retain distinct outcomes, safe routing attempts,
    cooldowns, exact response bindings, and user-mediated interruption
    decisions without session-ownership machinery.
  - Implementation commits: `5ccbe33`, `35b95bb`, `a3bb2bd`, and `aaeb9c5`.
- Related documents:
  - [`design/gemini-response-storage-and-search.md`](design/gemini-response-storage-and-search.md)
  - [`design/gemini-request-execution.md`](design/gemini-request-execution.md)

## Closed items

### LEDGER-007 — Correct transcript-mode edge cases

- Status: Completed
- Type: Refinement
- Layer: Gemini transcript requests
- Problem:
  - The timestamp schema accepted exactly two minute digits, so it rejected
    full-video timestamps at or beyond 100 minutes.
  - The transcript workflow did not state how to recover when Gemini returned
    only part of a requested interval.
- Goal: Correct these two blind spots without expanding transcript-mode scope.
- Completed work:
  - [x] Accepted `MM:SS.mmm` timestamps whose minute component has at least two
        digits, and tested a clip after 7,200 seconds.
  - [x] Required incomplete or truncated responses to remain cached while the
        unfinished interval is processed with smaller clips and new
        fingerprints.
  - [x] Re-ran all transcript, cache, and routing tests.
- Outcome:
  - The timestamp test accepts `120:00.000` and rejects a one-digit minute
    component.
  - Fifteen offline tests pass.
  - MCP behavior, cache semantics, Gemini routing, credential handling, and
    unrelated code remain unchanged.
- Related commits: `112bbe3`, `988a076`.

### LEDGER-006 — Add Gemini transcript-only mode

- Status: Completed
- Type: Feature
- Layer: Gemini request construction
- Problem: Gemini normally describes and interprets a supplied video. In two
  captionless-video trials, an explicit transcript-only prompt and constrained
  JSON response made it transcribe instead.
- Goal: Add an explicit transcript request mode to the existing Gemini
  pipeline.
- Completed work:
  - [x] Added the tested transcript-only prompt and response schema to the
        existing request builder.
  - [x] Exposed transcript mode without changing existing prompt-driven
        requests.
  - [x] Documented the minimal invocation, tested output budget, and use of
        the existing chunk planner for long videos.
  - [x] Tested the generated request contract and unchanged default behavior.
  - [x] Re-ran all existing Gemini routing and cache tests.
- Outcome:
  - At initial completion, generated requests exactly matched the successful
    cached Raaz and Haal-e-Dil trial requests. The later timestamp correction
    in `112bbe3` changed the prompt and response schema, so branch-tip requests
    have new fingerprints and do not reuse those original trial cache records.
  - Fourteen offline tests pass: three transcript-builder tests and eleven
    existing routing and cache tests.
  - Caption routing, cache v2, Gemini project routing, credential handling,
    chunk planning, and prompt-driven analysis behavior remain unchanged.
- Implementation commits: `3cc3f3f`, `16da400`.

### LEDGER-005 — Confirm independent Gemini project ownership

- Status: Completed
- Type: Refinement
- Layer: Gemini API
- Evidence: The user confirmed that the primary and fallback credentials were
  created under different Google accounts in separately created Google AI
  Studio projects, rather than in an imported or shared project. Both
  credentials also authenticate successfully.
- Outcome:
  - [x] Treat `primary` and `fallback` as independent project quota buckets.
  - [x] Keep account names, project identifiers, and credentials out of the
        repository.
  - [x] Do not exhaust either project merely to prove quota independence.
- Related document:
  [`design/gemini-request-execution.md`](design/gemini-request-execution.md)

### LEDGER-004 — Add interactive Gemini quota-pool routing

- Status: Completed
- Type: Feature
- Layer: Gemini API
- Evidence: Implemented by
  [`223380b`](https://github.com/DRanger666/chatgpt-work-youtube-skill/commit/223380bf7b508bf2536b91b07f617500f2ef3316).
- Completed checks:
  - [x] Added the private fallback-key credential contract.
  - [x] Implemented primary-first failover with project cooldowns.
  - [x] Preserved retries in one request-fingerprint cache record.
  - [x] Mocked quota, transient, terminal, and credential failures.
  - [x] Validated each credential through Gemini model metadata without
        generating content or approaching quota.
  - [x] Kept all long-video chunks sequential by default.
- Related document:
  [`design/gemini-request-execution.md`](design/gemini-request-execution.md)
