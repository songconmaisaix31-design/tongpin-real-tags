# API Interface Validation Workspace

## Scope

- Validate API interfaces supplied in `All_API_Interfaces_2026-08-22.zip`.
- Keep generated scripts, sanitized evidence, and reports inside this workspace.
- Treat the source archive as read-only.

## Safety

- Never read or print credential files, `.env` files, private keys, tokens, or secret values.
- Redact authorization headers, cookies, query secrets, and sensitive response fields from evidence.
- Start with non-mutating checks. Do not exercise create, update, delete, payment, messaging, or other side-effecting operations without explicit scope and safe test data.
- Use bounded timeouts, no automatic retries for non-idempotent requests, and no TLS verification bypass.

## Implementation

- Prefer Python standard-library tooling unless the provided example requires an already-declared dependency.
- Keep endpoint definitions in one explicit contract source.
- Validate untrusted archive content and extracted paths before use.
- Use English for code, comments, filenames, reports, and technical documentation.

## Verification

- Use the detailed result taxonomy defined in `API_TEST_SPEC.md`; never collapse authentication, input rejection, route failure, and network failure into one unavailable state.
- Record request method, sanitized target, status code, latency, and a bounded/redacted response summary.
- Distinguish network reachability from authenticated functional correctness.
- Run syntax checks and a representative dry run before live probes.
