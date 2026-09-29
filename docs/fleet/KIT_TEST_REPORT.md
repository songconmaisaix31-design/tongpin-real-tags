# Test Report

Source report generated: 2026-08-22

## Passed

- Python syntax compilation for all automation scripts and tests.
- 9 unit/integration tests:
  - UTF-8 subprocess output decoding on Windows;
  - directory glob matching;
  - ownership containment and overlap detection;
  - example Wave plan validation;
  - concurrent write-overlap rejection;
  - clean two-parent no-ff integration merges accepted;
  - direct integration edits to Worker-owned paths rejected;
  - manually edited/conflicting merge trees rejected.
- Clean temporary Git repository smoke test:
  - example plan validated;
  - coordinator dry-run created a Run state;
  - only the dependency-free foundation Wave was dispatched;
  - dependent Waves remained planned.
- Normal Worker end-to-end test with a fake Orca transport:
  - task context initialized;
  - allowed Web path passed;
  - API path modification was rejected;
  - commit + push/upstream verification passed;
  - `worker_done` was emitted once;
  - duplicate completion for the same Dispatch was rejected.
- Integration Worker end-to-end test with a fake Orca transport:
  - exact dependency SHAs were merged with clean no-ff commits;
  - merge trees were recomputed and matched;
  - integration-owned README change passed;
  - first-parent commit IDs were checked;
  - pushed integration branch emitted `worker_done` successfully.

## Original environment limitation

The build container does not include a running Orca desktop/runtime, so live Orca Run/Task/Dispatch creation was not executed here. The repository-side state machine, Git gates, completion checks, fake transport, and dry-run command generation were tested. On the target machine, run `python scripts/fleet.py doctor` before the first real Run; it verifies the Orca runtime, orchestration skill, CLI access, and required Git merge-tree support.

## Target machine validation

Validated: 2026-08-23

- Python syntax compilation passed for 7 source and test files.
- All 9 unit/integration tests passed.
- The project-specific hackathon plan validated with no ownership or dependency errors.
- `fleet.py doctor` passed against Orca 1.4.188 with a ready runtime, the orchestration skill, and Git `merge-tree --write-tree` support.
- The coordinator dry run completed without creating a worktree and preserved its Chinese prompt as UTF-8.
- The original Kit dry run generated local state under its installation worktree and left later Waves planned.
- `orca orchestration run-list` confirmed that no real Run was created by the dry run.
- Repository hooks were intentionally not installed because `core.hooksPath` is shared across all worktrees of this repository.
- The project now has a concrete foundation -> parallel build -> integration plan with non-overlapping Flask ownership paths.

## Project baseline validation

Validated: 2026-08-23, `origin/main@648caa40ccd880f331b050bb27cfe80c361b0328`

- The isolated `.venv` installed the repository-declared Flask dependency.
- All 28 existing Python tests passed.
- All 4 Node match-flow tests passed.
- The HTTP workflow harness passed all 6 stages when invoked with the `.venv` Python interpreter.
- The checked-in `harness.cmd` currently resolves the global Python interpreter when a virtual environment is not activated. `INT-001` owns the small launcher correction; this baseline limitation is not reported as an application failure.
