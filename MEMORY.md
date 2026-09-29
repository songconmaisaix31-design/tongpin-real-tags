# Project Memory

## Purpose

This worktree is an isolated evaluation and execution environment for the Orca Directory Fleet Kit.

## Durable Decisions

- Keep `C:\Users\DW\Downloads\orca-directory-fleet-kit.zip` read-only.
- The imported archive SHA-256 is `FAC74080BF7517527743BE7ED3CB0EA9CB8A71039EF83B0E952BF8000B42678E`.
- Keep this worktree independent from `main`; do not copy the API validation workspace's untracked files into it.
- Do not launch a real multi-agent Wave until `.agents/fleet.json` ownership paths and checks match the target repository and a concrete objective is defined.
- Treat offline tests, plan validation, dry runs, and `doctor` output as separate evidence; none alone proves a successful live multi-agent Run.

## Workspace

- Worktree: `C:\Users\DW\orca\workspaces\xxx\orca-directory-fleet-kit`
- Branch: `songconmaisaix31-design/orca-directory-fleet-kit`
- Base: `origin/main` at `42cdcbf4e7c5004e7fbbbe26f769643f68b1a8bc`
- Imported: 2026-08-23

## Current Validation

- Python syntax checks passed for 7 source and test files on 2026-08-23.
- All 9 unit/integration tests passed, including a Windows UTF-8 subprocess regression test.
- The example 3-Wave, 5-Task plan validated with no errors.
- `fleet.py doctor` passed against Orca 1.4.188 with a ready runtime, orchestration support, and Git `merge-tree --write-tree`.
- Coordinator and launch dry runs passed. The launch dry run wrote `.agents/runs/20260822T182659Z-task/`, dispatched only the simulated foundation Wave, and created no real Orca Run.
- Repository hooks were not installed because Git configuration is shared across worktrees.

## Compatibility Fixes

- `scripts/common.py` decodes subprocess output as UTF-8 with replacement fallback so Orca JSON and check output do not fail under the Windows GBK locale.
- `scripts/fleet.py` configures UTF-8 stdout and stderr so dry-run prompts and JSON evidence remain readable.
