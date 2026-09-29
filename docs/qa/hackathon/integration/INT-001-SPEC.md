# INT-001 Integration Specification

## Outcome

Produce one judge-ready release candidate from the frozen governance base by
merging the accepted DATA-001, CORE-001, UX-001, QA-001, and UX-002 heads
exactly, applying only integration-owned assembly fixes, and publishing current
evidence from the assembled candidate.

## Acceptance criteria

1. The candidate starts at
   `013633354f8b84e5ef5370bf8ace0b81ed1fc0f5`; ARCH-001
   (`eddb9dd3add3d898db1b5e6a419e835d48bda400`) remains an ancestor.
2. Each accepted worker head is the exact second parent of its own clean,
   two-parent `--no-ff` merge commit, in this order: DATA-001, CORE-001,
   UX-001, QA-001, UX-002. ARCH-001 remains inherited from the frozen base.
3. Every commit on the integration first-parent chain contains `[INT-001]` and
   integration-authored changes stay inside the task allowlist.
4. The strict assembly gate, Python syntax and unit suites, acceptance suite,
   Node tests, HTTP workflow harness, and `git diff --check` pass.
5. Both the default demo mode and `DEMO_MODE=0` start without reading secrets.
6. Fresh 1100x900 and 390x844 screenshots come from this assembled candidate
   and pass a visual smoke review for overflow, overlap, focus, primary flow,
   and truthful evidence labels.
7. A bounded credential-free Public Live smoke runs only if network reachability
   is available. The receipt records sanitized status and normalized counts,
   never raw upstream profiles.
8. README and release evidence distinguish Public Live response provenance,
   deterministic Fixture behavior, Unavailable integrations, and Roadmap items.
9. The final branch is pushed, its remote SHA is verified, the candidate
   worktree is clean, no local database or credentials are tracked, and neither
   local nor remote `main` is modified by this task.

## Constraints

- Abort and escalate any merge conflict; never repair a worker merge commit.
- Do not squash, cherry-pick, fast-forward, rebase, force-push, switch branches,
  or edit worker-owned evidence.
- Do not read `.env`, credential, token, cookie, authorization, or private-key
  material.
- Use the repository's current Flask/Jinja2/SQLite architecture and installed
  dependencies; add no speculative feature or dependency.
- Treat screenshots as visual evidence only, not runtime or deployment proof.

## Risks and controls

| Risk | User impact | Control |
| --- | --- | --- |
| Worker histories overlap | A conflict could hide ownership or alter accepted work | Merge one exact SHA at a time; abort immediately on conflict |
| Legacy E2E expectation rejects the assembled authorization behavior | The judge workflow fails despite correct product behavior | Update only the integration-owned expectation after reproducing the failure |
| Harness selects a global Python | Results differ from the candidate environment | Prefer `.venv\\Scripts\\python.exe` when present and verify the HTTP workflow |
| Public endpoint drift or no network | A live refresh can fail during judging | Bound the smoke, preserve Fixture/offline flow, and record current sanitized state |
| Stale worker screenshots are reused | Submission evidence does not prove the candidate | Capture both required viewports after final assembly |
| Evidence copy overclaims authentication or deployment | Judges receive a false trust signal | Audit all final claims against the four evidence classes |

## Execution and verification

1. Verify the frozen base and remote dependency heads.
2. Commit this integration specification.
3. Perform five clean exact-SHA `--no-ff` merges.
4. Run the strict assembly gate to identify integration-only failures.
5. Apply the smallest allowed assembly fixes and rerun focused checks.
6. Run the complete required gate set plus demo/production startup, bounded
   network smoke, and current desktop/mobile visual capture.
7. Write final claims and receipts, update README, commit, push, and verify the
   remote SHA and clean worktree.

Required commands:

```text
.venv\Scripts\python.exe -m compileall -q app tools
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m unittest discover -s tests/acceptance -v
.venv\Scripts\python.exe tools/hackathon_acceptance.py --require-assembly
node --test tests/match_flow.test.mjs
harness.cmd --no-color
git diff --check
```
