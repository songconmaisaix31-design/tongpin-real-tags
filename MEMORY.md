# Project Memory

## Purpose

This workspace contains reproducible, security-conscious validation artifacts for the API interface package dated 2026-08-22.

## Durable Decisions

- The original ZIP in `C:\Users\DW\Downloads` remains read-only.
- Availability checks default to non-mutating requests and bounded timeouts.
- Authentication material is never copied into this workspace or included in reports.
- A reachable authentication or validation error proves endpoint availability, but not successful authenticated functionality.

## Current Source Package

- `C:\Users\DW\Downloads\All_API_Interfaces_2026-08-22.zip`
- Detected contents: Markdown interface research and one Python integration example.

## 2026-08-22 Live Validation Baseline

- A credential-free probe covers 37 HTTP/MCP contract items in `endpoint_probe.py`.
- Live result: 6 `AVAILABLE`, 7 `AUTH_REQUIRED`, 3 `REQUEST_REJECTED`, 3 `ROUTE_NOT_FOUND`, 2 `RESOURCE_NOT_FOUND`, 11 `PREREQUISITE_MISSING`, 3 `NOT_TESTED_PREREQUISITE`, 1 `INCONCLUSIVE_SAFE_PROBE`, and 1 `CONTRACT_INVALID`.
- `reports/API_VALIDATION_SUMMARY_2026-08-22.md` is the human-readable decision record; JSON and per-item Markdown evidence are in the same folder.
- Do not run the existing `run_probe.py` with real credentials: it loads `credentials.json` unconditionally and can print or persist unredacted private response data.
- Retire Keep `/pd/v3/stats/records`, WeRead `/user/reading/statistics`, and WeRead `/note/getList` from the current contract unless later authenticated evidence disproves the observed 404 results.
- The NetEase research dependency is archived, and the documented `300300` QR-check port is invalid.
- The official-domain WeRead Skill page is reachable, while the `weread-mcp` npm package identifies itself as unofficial; model them as separate products and transports.

## 2026-08-22 Keep Authenticated Probe

- The official Keep web sign-in entry is `https://keep.com/kts/home`; an unauthenticated browser is redirected to Keep's unified login on `open.gotokeep.com`.
- A successful browser login proves only the Keep web session and sports-profile UI are authorized; it does not by itself prove that the separate bearer-authenticated API probe is authorized.
- `keep_authenticated_probe.py` is the only approved authenticated Keep workflow in this workspace; do not add credentials to `run_probe.py` or adapter configuration.
- It accepts only an existing temporary bearer token through hidden interactive TTY input after dedicated-test-account confirmation.
- Its network allowlist contains exactly two requests: `GET https://api.gotokeep.com/pd/v3/stats/detail` for `running` and `cycling` aggregate summaries.
- Reports contain fixed capability labels and booleans only; response field names, response values, identity values, and credentials are not persisted.
- Offline security verification passed 20 tests on 2026-08-22, including per-request Cookie disposal. Live authenticated evidence is still pending user input and must not be claimed until a sanitized report exists.
