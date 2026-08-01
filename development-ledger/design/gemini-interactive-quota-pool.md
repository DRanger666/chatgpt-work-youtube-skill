# Interactive Gemini quota-pool design

## Decision

Use two independently provisioned Gemini project credentials as a conservative
primary-and-fallback pool for interactive ChatGPT Work video analysis.

Do not use Gemini Batch API. The workflow is human-in-the-loop, expects results
inside the active conversation, and is not driven by background automation.
Batch submission, polling, delayed retrieval, and extra bookkeeping would add
complexity without serving that interaction model.

Do not add an external proxy, Redis, a dashboard, parallel chunk execution, or
per-request round-robin rotation.

## Goals

- Preserve interactive continuity when one Gemini project is temporarily
  rate-limited or unavailable.
- Avoid draining both projects merely because two credentials exist.
- Respect project-level cooldowns and server-provided retry information.
- Search saved video outputs before every request and keep every network
  attempt observable.
- Never expose, log, save, or commit credential material.
- Remain portable across fresh ChatGPT Work VMs.

## Preconditions

Gemini quota is applied per Google Cloud project rather than per API key. The
two credentials provide additional capacity only if they belong to different
projects.

Configure the pool as:

- `GEMINI_API_KEY`: primary project credential.
- `GEMINI_API_KEY_FALLBACK`: separately provisioned fallback project
  credential.

If both variables contain the same value, collapse them to one bucket. Record
only the aliases `primary` and `fallback`; do not derive or persist key
fingerprints.

## Request routing

1. Complete the saved-video-output search before selecting a credential.
2. Select `primary` unless it is disabled or cooling down.
3. Keep at most one Gemini video request in flight.
4. On success, return the response and keep the selected bucket healthy.
5. On a quota-related `429 RESOURCE_EXHAUSTED`:
   - parse `Retry-After`, `google.rpc.RetryInfo.retryDelay`, or a retry delay in
     the error message;
   - fall back to a conservative default when no delay is supplied;
   - add small jitter;
   - cool down the entire project bucket;
   - try the other healthy bucket once without sleeping on the exhausted
     bucket.
6. On `408` or transient `5xx`, retry with bounded exponential backoff and
   jitter, then consider the other healthy bucket.
7. On a credential-specific authentication or permission failure, disable that
   bucket for the run and try the other bucket once.
8. On `400 INVALID_ARGUMENT` or another request error, stop without rotation.
9. When no bucket is healthy, save the failed attempt history and report the
   earliest cooldown time instead of busy-looping.

## Long videos

- Keep the established 30-minute timestamp chunks.
- Test one representative chunk first.
- Process additional chunks sequentially.
- Let project cooldown and failover happen between requests.
- Never create parallel calls merely to consume both projects.
- Synthesize from saved chunk outputs whenever possible.

## State

Keep short-lived bucket health in a local JSON state file under the portable
installation's `workspace/` directory:

```json
{
  "fileFormatVersion": 1,
  "buckets": {
    "primary": {
      "cooldownUntil": null,
      "disabled": false,
      "reason": null
    },
    "fallback": {
      "cooldownUntil": null,
      "disabled": false,
      "reason": null
    }
  }
}
```

Rate-limit windows are short. Do not introduce a separate persistent quota
database unless real cross-session evidence later justifies it.

## Gemini request log

Keep request history in the per-video Gemini request log defined in
[`youtube-saved-work.md`](youtube-saved-work.md). The log is separate from the
video output index. A request entry preserves the router's safe attempt data:

```json
{
  "fileFormatVersion": 1,
  "requestStatus": "succeeded",
  "routingAttempts": [
    {
      "bucket": "primary",
      "httpStatus": 429,
      "classification": "rate_limited",
      "cooldownUntil": "..."
    },
    {
      "bucket": "fallback",
      "httpStatus": 200,
      "classification": "success"
    }
  ]
}
```

An identical failed request may run again only when the log contains a
documented permitted retry reason. Preserve prior attempts during that retry.
Never include a key, authorization header, key fragment, or key fingerprint.

## Error policy

| Response | Classification | Action |
|---|---|---|
| `2xx` | Success | Return and save the response |
| `429 RESOURCE_EXHAUSTED` | Project rate limit | Cool down bucket; try other healthy bucket |
| `408`, `500`, `502`, `503`, `504` | Transient | Bounded backoff with jitter; then fail over |
| `401` or credential-specific `403` | Credential failure | Disable bucket for run; try other bucket |
| API-key-invalid error | Credential failure | Disable bucket for run; try other bucket |
| `400 INVALID_ARGUMENT` | Request failure | Stop; do not rotate |
| Other `4xx` | Request failure | Stop unless explicitly classified as credential-specific |

## Validation

Use deterministic local HTTP fixtures before live use:

- primary success;
- primary `429` followed by fallback success;
- both buckets rate-limited;
- transient `503` followed by success;
- terminal `400` with no fallback call;
- invalid primary credential followed by fallback success;
- cooldown persistence without secret material;
- request-log retry authorization and preservation of earlier attempts.

After offline tests pass, make one inexpensive validation request per
credential. Do not stress-test quota or deliberately provoke throttling.

## Historical implementation outcome

Implemented in
[`223380b`](https://github.com/DRanger666/chatgpt-work-youtube-skill/commit/223380bf7b508bf2536b91b07f617500f2ef3316).

- Eleven offline tests covered routing, cooldown, retry, terminal failure,
  duplicate credentials, secret-free state, cache reopening, and legacy
  migration at that historical checkpoint. LEDGER-010 now requires the routing
  behavior to use the plain Gemini request log and removes the legacy cache
  attachment.
- Both credentials returned HTTP 200 from the Gemini model-metadata endpoint.
- No generation request or quota stress test was used for credential
  validation.
- The user confirmed that the credentials were created in separately created
  Google AI Studio projects under different accounts, not in a shared or
  imported project. Treat them as independent quota buckets without attempting
  a quota-exhaustion probe.

## Sources

- Gemini rate limits:
  `https://ai.google.dev/gemini-api/docs/rate-limits`
- Gemini retry guidance:
  `https://ai.google.dev/gemini-api/docs/troubleshooting`
- Gemini API-key behavior:
  `https://ai.google.dev/gemini-api/docs/api-key`
- Bucket-aware rotation discussion:
  `https://github.com/openclaw/openclaw/issues/28847`
