# QA-001 Acceptance Coverage

## Executable cases

| Control | Case | Category | Boundary | Architecture-base result |
|---|---|---|---|---|
| `DEMO-01` | Full private-tags -> match -> L4 conversation -> formed group path | route | Runs with socket creation blocked and a disposable database | PASS |
| `STATE-10` | Searching and L0 omit identity/source/algorithm fields | assertion | Rendered HTML | PASS |
| `STATE-10/CORE-001` | L0 omits the internal candidate identifier | assertion | Rendered HTML and action URLs | SKIP: CORE-001 not assembled |
| `AUTH-01` | Guest and nonmember writes are rejected | auth | HTTP plus unchanged row counts | PASS |
| `INPUT-01` | Invalid event, oversized message, and stale attempt write nothing | input | HTTP plus unchanged row counts | PASS |
| `STATE-10` | Connection UI removes fake authorization and secret inputs | auth | Target HTML and removed legacy route | SKIP: datasource contract not assembled |
| `AUTH-02` | Public sync requires a signed-in session | auth | Redirect plus unchanged tag/connection counts | SKIP: datasource contract not assembled |
| `STATE-03` | Unavailable source has no active POST behavior | route | 404 plus unchanged tag/connection counts | SKIP: datasource contract not assembled |
| `STATE-05` | Invalid handle returns before transport | input | Zero socket calls, stable tags, bounded state | SKIP: datasource contract not assembled |
| `STATE-04` | Deterministic timeout is retryable and preserves last success | network | Simulated timeout, exact tag snapshot, bounded error | SKIP: datasource contract not assembled |
| `STATE-07` | Deterministic network failure preserves last success | network | Simulated socket failure, exact tag snapshot, bounded error | SKIP: datasource contract not assembled |
| `STATE-02/P0-07` | Offline Fixture has the required 21-key vocabulary and provenance | assertion | SQLite plus self-profile copy | SKIP: datasource contract not assembled |
| `STATE-02/DS-012` | Fixture reload is deterministic and production rejects it | assertion | Repeated demo POST plus production-mode app | SKIP: datasource contract not assembled |
| `RUNNER-01` through `RUNNER-04` | Exit code, category preservation, temp isolation, deterministic dry-run | assertion | Synthetic nested suites | PASS |

## Runner semantics

- `PASS` means the case executed and met its assertions.
- `FAIL` means the case executed or was required and did not meet its boundary.
- `SKIP` means a named dependency is absent; it is never counted as a pass.
- `--dry-run` validates and prints the stable manifest without executing tests.
- A normal run blocks external socket creation and creates one temporary root
  plus one case database per test.
- `--require-assembly` turns the DATA-001 and CORE-001 dependency skips into
  failures. The final integrated candidate must report `FAIL=0 SKIP=0`.

## Failure routing

| Category | Typical owner | Examples |
|---|---|---|
| `network` | Datasource transport/state | timeout or upstream error is unbounded, snapshot is lost, Fixture fallback occurs |
| `input` | Route/service validation | invalid handle opens transport, invalid form writes state |
| `auth` | Session/membership/source authorization | guest or nonmember mutation, secret-bearing form returns |
| `route` | Flask composition/product flow | endpoint absent, wrong method/status, judge path breaks |
| `assertion` | Cross-cutting contract/invariant | privacy leak, Fixture provenance drift, runner contract failure |

The category identifies the violated boundary. The full traceback remains
available with `--verbose`; categories are not collapsed into one generic test
failure count.
