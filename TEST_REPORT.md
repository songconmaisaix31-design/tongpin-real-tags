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
- The example plan validated with no contract errors.
- `fleet.py doctor` passed against Orca 1.4.188 with a ready runtime, the orchestration skill, and Git `merge-tree --write-tree` support.
- The coordinator dry run completed without creating a worktree and preserved its Chinese prompt as UTF-8.
- The example launch dry run generated local state under `.agents/runs/20260822T182659Z-task/`, simulated only the foundation Wave, and left later Waves planned.
- `orca orchestration run-list` confirmed that no real Run was created by the dry run.
- Repository hooks were intentionally not installed because `core.hooksPath` is shared across all worktrees of this repository.
- A real multi-agent Wave remains out of scope until the sample ownership paths and checks are replaced with a concrete project plan.
