# Contribution conventions

Keep the repository history useful as long-term development documentation.

## Commit structure

- Put one coherent concern in each commit.
- Separate workflow documentation, MCP/runtime behavior, Gemini/cache
  behavior, and repository maintenance when they can stand independently.
- Use an imperative, descriptive subject.
- Include a commit body for every non-trivial change.

Each commit body should explain:

1. What changed.
2. Why the change was needed.
3. How it was validated.
4. Any compatibility, migration, credential, caching, or operational impact.

Do not use vague subjects such as `update`, `fix`, or `changes`.

## Publishing

- Use ordinary `git` over HTTPS.
- Do not use GitHub CLI (`gh`) for this repository.
- Load the GitHub PAT from private credential storage only for the active
  network operation.
- Never place a PAT in a remote URL, repository configuration, commit,
  generated file, terminal log, or documentation.

## Before committing

- Inspect the exact staged diff.
- Stage only files belonging to the commit's stated concern.
- Run the narrowest relevant validation.
- Scan staged content for credential patterns.
- Confirm generated caches, runtime binaries, materials, and workspaces remain
  untracked.

Suggested message shape:

```text
Imperative summary of the coherent change

Explain the problem or need and the chosen implementation.

Validation:
- relevant check
- relevant scenario

Operational impact:
- migration, cache, credential, or compatibility notes
```
