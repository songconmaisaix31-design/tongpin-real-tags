# QA-001 Acceptance Specification

## Objective

Provide an independent, offline-first acceptance layer for the RealTags
hackathon candidate. The layer exercises the product through Flask HTTP
requests, uses disposable SQLite databases, reports evidence without contacting
public services, and keeps implementation facts separate from assembly gaps.

## Completion criteria

1. The judge path reaches private tags, anonymous matching, a direct
   conversation, L4 demo progression, and a formed event group without network
   access.
2. Focused cases cover privacy, access control, invalid input, Public Live
   failure, explicit Fixture behavior, unavailable sources, and database
   side-effect boundaries.
3. Every case declares one failure category: `network`, `input`, `auth`,
   `route`, or `assertion`.
4. `tools/hackathon_acceptance.py` reports `PASS`, `FAIL`, and `SKIP`, preserves
   failure-category counts, uses a temporary database root, and exits nonzero
   when any case fails.
5. Target datasource cases are explicit `SKIP` results on this architecture-only
   branch. `--require-assembly` converts a missing target contract into a
   blocking failure for the integrated candidate.
6. The English submission package distinguishes Public Live, Fixture,
   Unavailable, and Roadmap statements and contains no unsupported deployment,
   user, revenue, score, approval, ownership, or live-success claim.
7. The runbook starts from a clean worktree, needs no credentials, and keeps
   live refresh outside the critical demo path.

## Constraints

- Write only under `tests/acceptance/**`, `tools/hackathon_acceptance.py`,
  `submission/**`, and `docs/qa/hackathon/acceptance/**`.
- Treat `docs/acceptance/P0_ACCEPTANCE_MATRIX.md` and
  `docs/contracts/DATA_SOURCE_CONTRACT.md` as frozen authority.
- Do not read credentials or `.env` files and do not make external requests.
- Do not patch application code from the QA track.
- Reuse Flask's test client, the application factory, SQLite, and the Python
  standard library; add no dependency.
- A skip is evidence of a named unavailable dependency, never a pass.

## Risks and controls

| Risk | User or judge impact | Control |
|---|---|---|
| Parallel datasource work is not present on this branch | A strict target test would make the worker gate unusable, while a permissive test could hide an integration gap | Detect the frozen target route and schema; report `SKIP` here and require `--require-assembly` on the assembled candidate |
| A test accidentally reaches the public internet | Results become flaky and may expose public profile data | Block socket creation in the acceptance runner and inject deterministic network failure in the Public Live case |
| Test data changes the developer database | Demo state becomes non-repeatable | Create one temporary root per run and one disposable SQLite database per case |
| A rejected request still mutates state | Privacy or authorization boundaries become cosmetic | Compare row counts or canonical source-tag snapshots before and after rejected requests |
| Fixture data is described as live | The trust claim becomes misleading | Assert Fixture provenance and maintain a claims ledger with mutually exclusive evidence classes |
| A runner hides why a case failed | Integration owners cannot route the defect | Attach one stable category and matrix control to every case and summarize failures by category |

## Planned test groups

| Group | Primary controls | Expected evidence on architecture base |
|---|---|---|
| Judge path | P0-09 through P0-17; demo acceptance 1-7 | `PASS` for the existing offline product path |
| Access and side effects | P0-10, P0-11, P0-14, P0-20 | `PASS` |
| Datasource boundary | STATE-03 through STATE-07 and STATE-10 | `SKIP` until the target sync route and provenance schema are assembled |
| Fixture contract | STATE-02; P0-07 and P0-08 | `SKIP` until the target provenance schema is assembled |
| Runner contract | QA-001 acceptance | `PASS` |

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/acceptance -v
.\.venv\Scripts\python.exe tools/hackathon_acceptance.py --dry-run
.\.venv\Scripts\python.exe tools/hackathon_acceptance.py
.\.venv\Scripts\python.exe -m compileall -q tests/acceptance tools/hackathon_acceptance.py
git diff --check
python scripts/gate.py check --run-checks
```

The integration owner additionally runs:

```powershell
.\.venv\Scripts\python.exe tools/hackathon_acceptance.py --require-assembly
```

That command remains offline. Any target-contract skip becomes a failure.
