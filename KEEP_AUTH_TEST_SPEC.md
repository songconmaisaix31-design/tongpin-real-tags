# Keep Authenticated Read-Only Probe Specification

## Objective

Verify whether a temporary Keep bearer token can access the aggregate personal
sport summaries exposed by `GET /pd/v3/stats/detail` without disclosing the
token or the returned personal data.

## Authorized Scope

- Use a dedicated test account only.
- Accept an existing temporary bearer token through an interactive TTY prompt.
- Probe only the fixed `running` and `cycling` aggregate summary requests.
- Keep TLS verification enabled, disable redirects and environment proxies,
  use bounded timeouts, perform no retries, cap each response read, and discard
  any response Cookie before the next request.
- Write one sanitized JSON report under the workspace `reports/` directory.

## Explicitly Prohibited

- No account password, SMS code, Cookie, refresh token, or token file.
- No secret in chat, command-line arguments, environment variables, clipboard
  automation, `credentials.json`, `.env`, stdout, stderr, reports, or errors.
- No login request, session creation, logout, check-in, mutation, upload, or
  any other write operation.
- No `stats/records`, running log, cycling log, route points, heart rate,
  cadence, raw response dump, tag values, arbitrary response keys, or identity
  values.
- No main account. The operator must explicitly confirm a dedicated test
  account before the token prompt appears.

## Result Semantics

| Label | Meaning |
|---|---|
| `AUTHENTICATED_AVAILABLE` | HTTP 2xx, Keep success envelope, and a data object were returned. |
| `AUTH_INVALID_OR_EXPIRED` | The token was missing, invalid, expired, or rejected. |
| `PERMISSION_INSUFFICIENT` | Authentication was recognized but access was forbidden. |
| `REQUEST_REJECTED` | Keep rejected the fixed query contract or its input. |
| `PRIVACY_RESTRICTED` | The endpoint was reachable but no personal data object was exposed. |
| `RATE_LIMITED` | The authenticated route is currently throttled. |
| `ROUTE_NOT_FOUND` | The fixed aggregate path returned 404. |
| `SERVICE_ERROR` | Keep returned a 5xx response. |
| `NETWORK_ERROR` | DNS, TLS, connection, or timeout failure. |
| `UNEXPECTED_RESPONSE` | The response did not match the bounded Keep envelope contract. |

The report may state only whether a data object exists and whether it is empty.
It must not contain any returned field names or values.

## Known Limitation

The aggregate endpoint does not provide a verified identity binding in the
current contract. A successful result proves that the supplied token can read
a Keep data envelope, but not that the token belongs to a separately asserted
account identifier.

## Acceptance Criteria

1. The program refuses non-TTY input and has no token/password/cookie CLI flag.
2. The token is held only in process memory and removed from session headers
   before process exit.
3. Runtime code has an exact HTTPS host, method, path, and query-name allowlist.
4. Only two GET requests are possible: aggregate `running` and `cycling`.
5. Each request remains bearer-only; response Cookies are cleared after every
   success or failure and cannot flow into the next request.
6. Sentinel secrets and arbitrary response content cannot reach result objects,
   JSON reports, stdout, stderr, or exception messages.
7. Offline tests cover transport policy, token validation, response labels,
   response truncation, and report redaction before a live token is accepted.

## Verification

```powershell
python -m unittest tests.test_keep_authenticated_probe -v
python -m py_compile keep_authenticated_probe.py tests\test_keep_authenticated_probe.py
python keep_authenticated_probe.py
```
