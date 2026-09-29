# API Interface Availability Test Specification

## Objective

Verify the concrete external interfaces described by
`All_API_Interfaces_2026-08-22.zip` without reading credential files, using
real user credentials, or triggering business side effects.

The source archive is identified by SHA-256:
`88A3CA61F6539F82637B362510CF61D955134CF2952DC4D3D38184736F4909FF`.

## Scope

The executable contract covers:

- Duolingo and LeetCode public endpoints already implemented in this workspace,
  because the archive declares those adapters but omits concrete URLs.
- Keep login and activity endpoints.
- Steam Web API endpoints listed in the research document.
- GitHub REST and GraphQL endpoints listed in the research document.
- NetEase Cloud Music local-service endpoints, including the invalid `300300`
  port exactly as documented.
- WeRead MCP tool names, assumed local HTTP paths, and internal HTTP paths.

TypeScript adapter methods and mock-only methods are code contracts, not remote
interfaces, so they are outside the live HTTP probe.

## Non-goals

- Do not prove authenticated business success without a dedicated test account.
- Do not read `credentials.json`, `.env`, cookies, tokens, passwords, or private
  keys.
- Do not log raw response bodies or personal data.
- Do not install, start, or configure third-party local services.
- Do not call login, check-in, mutation, upload, payment, notification, or other
  side-effecting operations with their documented method.

## Safety Model

Each contract item declares its documented method and a separate probe action.

- Public read-only HTTP endpoints use a bounded `GET` or a read-only GraphQL
  `POST` with synthetic input.
- Authentication and potentially state-changing `POST` endpoints use `OPTIONS`.
- MCP tools are recorded as `NOT_TESTED_PREREQUISITE` when no configured MCP
  server is available; HTTP paths are not treated as equivalent to MCP tools.
- Invalid URLs are classified without opening a socket.
- Redirects are not followed, TLS verification remains enabled, response reads
  are capped at 4096 bytes, and each request has a bounded timeout.

## Result Semantics

| Label | Meaning |
|---|---|
| `AVAILABLE` | A safe functional request returned the expected 2xx response shape. |
| `AUTH_REQUIRED` | The route responded but requires valid authentication. |
| `REQUEST_REJECTED` | The route responded with input or contract validation failure. |
| `RESOURCE_NOT_FOUND` | The route exists, but the synthetic resource was not found. |
| `ROUTE_NOT_FOUND` | The documented path appears absent. |
| `METHOD_NOT_ALLOWED` | The safe probe method is unsupported; availability is inconclusive. |
| `RATE_LIMITED` | The service is reachable but currently throttling requests. |
| `INCONCLUSIVE_SAFE_PROBE` | `HEAD`/`OPTIONS` succeeded; this does not prove business success. |
| `PREREQUISITE_MISSING` | A required local service is not running. |
| `NOT_TESTED_PREREQUISITE` | The interface requires an MCP server or credentials not in scope. |
| `CONTRACT_INVALID` | The documented URL or port is syntactically invalid. |
| `SERVICE_ERROR` | The server returned a 5xx response. |
| `NETWORK_ERROR` | DNS, TLS, connection, or timeout failure. |
| `UNEXPECTED_RESPONSE` | The response does not fit the expected contract. |

`401`, `403`, `400`, and `422` prove route reachability, not authenticated
functional correctness. A successful `OPTIONS` response also does not prove the
documented operation works.

## Acceptance Criteria

1. Every concrete interface has a stable contract ID and source reference.
2. Unsafe operations are never sent with their documented method.
3. The probe never imports or calls the project's credential loader.
4. Results contain only method, sanitized target, status, latency, bounded schema
   metadata, label, and reason.
5. JSON and Markdown reports are reproducible from one command.
6. Contract, classification, redaction, and safety invariants have offline tests.
7. The live run completes with TLS verification enabled and no raw body dump.

## Verification Commands

```powershell
python -m unittest tests.test_endpoint_probe -v
python -m py_compile endpoint_probe.py tests/test_endpoint_probe.py
python endpoint_probe.py --json reports/api-interface-validation-2026-08-22.json --markdown reports/api-interface-validation-2026-08-22.md
```
