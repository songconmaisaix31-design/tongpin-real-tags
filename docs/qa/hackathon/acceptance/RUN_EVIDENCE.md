# QA-001 Worker Run Evidence

## Scope and provenance

| Item | Value |
|---|---|
| Date | 2026-08-23 |
| Logical task | `QA-001` |
| Branch | `songconmaisaix31-design/trk-qa-qa-001` |
| Frozen dependency | `origin/songconmaisaix31-design/trk-architecture-arch-001@eddb9dd3add3d898db1b5e6a419e835d48bda400` |
| Network policy | External socket creation blocked; no public API probe |
| Database policy | Temporary root per runner and disposable SQLite database per acceptance case |

The final pushed SHA is carried by the worker completion receipt rather than
embedded here, which avoids a self-referential commit. This record applies only
to the QA worker branch; the integration owner must rerun every final gate on
the exact assembled candidate SHA.

## Results

| Command or gate | Result |
|---|---|
| `.venv\Scripts\python.exe -m unittest discover -s tests/acceptance -v` | PASS: 17 tests, 0 failures, 9 explicit assembly skips |
| `.venv\Scripts\python.exe tools/hackathon_acceptance.py --dry-run` | PASS: manifest `PASS=1 FAIL=0 SKIP=17` |
| `.venv\Scripts\python.exe tools/hackathon_acceptance.py` | PASS: executed `PASS=8 FAIL=0 SKIP=9` |
| Controlled `--require-assembly` run | Expected exit 1: `PASS=8 FAIL=9 SKIP=0`; failure categories `NETWORK=2 INPUT=1 AUTH=2 ROUTE=1 ASSERTION=3` |
| `.venv\Scripts\python.exe -m unittest discover -s tests -v` | PASS: 45 tests, 0 failures, 9 explicit assembly skips |
| `.venv\Scripts\python.exe tools/harness_cli.py --no-color` | PASS: 6/6 stages |
| `node --test tests/match_flow.test.mjs` | PASS: 4/4 tests |
| `.venv\Scripts\python.exe -m compileall -q app tests tools` | PASS |
| `python scripts/gate.py check --run-checks` | PASS: all changed files stayed inside the QA allowlist and both required checks passed |
| `git diff --check` | PASS |

## Interpretation

The eight executed acceptance passes support the existing offline judge path,
privacy assertions that are available on the frozen base, rejected side-effect
checks, and the runner contract. The nine assembly-dependent cases do not
support a success claim; they cover the target datasource route/schema and the
CORE-001 internal candidate-ID boundary and remain explicit `SKIP` results on
this branch.

The controlled strict run proves that any `FAIL` returns a nonzero process code
and that network, input, auth, route, and assertion failures remain separately
counted. On the final integrated candidate, the same strict command must report
`FAIL=0 SKIP=0` before the submission pack can promote assembly-dependent
claims.

## Evidence not produced

- No current Public Live success, availability, or latency evidence.
- No deployment, production, user, partner, revenue, conversion, retention,
  match-quality, judging score, approval, ranking, or award evidence.
- No final-candidate desktop or 390x844 screenshot evidence.
- No proof that a public handle belongs to a RealTags user.

`MEMORY.md` was not updated because it is outside the QA-001 write allowlist.
