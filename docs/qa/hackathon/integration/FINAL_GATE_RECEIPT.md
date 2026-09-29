# INT-001 Final Gate Receipt

> Deployment follow-up: this receipt proves the original integrated local
> candidate. The later isolated public-demo evidence is recorded in
> [`PUBLIC_DEMO_DEPLOYMENT_RECEIPT.md`](PUBLIC_DEMO_DEPLOYMENT_RECEIPT.md).

## Candidate identity and assembly

- Branch: `songconmaisaix31-design/trk-integration-int-001`
- Frozen governance base:
  `013633354f8b84e5ef5370bf8ace0b81ed1fc0f5`
- ARCH-001 ancestor:
  `eddb9dd3add3d898db1b5e6a419e835d48bda400`
- Final remote SHA: verify the branch head with `git ls-remote`; the exact SHA
  is also carried in the INT-001 orchestration completion receipt because a
  commit cannot truthfully contain its own object ID.

ARCH-001 is already contained by the frozen governance base. Each subsequent
accepted worker head is the exact second parent of a clean two-parent
`--no-ff` merge:

| Worker | Merge commit | First parent | Exact second parent |
| --- | --- | --- | --- |
| DATA-001 | `bf5d7aee8694b5ca0d3ac332aa4f7f4568d4d349` | `9e1cb713e45f826812d9bb3357024ce9e789d1ab` | `324b847dbe75bdf03f27fc5638cac30eed6a2ef7` |
| CORE-001 | `667f49755e2f3eb39be6d75db08930a1a44fb514` | `bf5d7aee8694b5ca0d3ac332aa4f7f4568d4d349` | `06012b59326c5a1de031d5f24a0027ec921d2397` |
| UX-001 | `9b6ddf4f000b55abd2569bc6d5aded671793f2c1` | `667f49755e2f3eb39be6d75db08930a1a44fb514` | `4c298caaa62d7f5b522b22a3f38ab7ded93f9253` |
| QA-001 | `ebd4bf1a5909fe68bd841a77fff8df8e3d16607c` | `9b6ddf4f000b55abd2569bc6d5aded671793f2c1` | `6f4ba724ff9e24c338b3da05558630f6c29b6cce` |
| UX-002 | `ddac0977d8369b75f38c27822aca7bdab398dddc` | `1624b3249ae476db02c2f7931b0cfed5eabed712` | `ac9c0d608c0b61ea0dbb93e885481a1cc2aa07b7` |

All five merges completed without conflicts. The dependency gate was
reinitialized once with coordinator-approved `--force`, preserving the base,
write paths, and checks while appending only UX-002. The committed-chain gate
then accepted five integration merges and the integration-owned authored
commits.

## Final clean-HEAD verification

| Check | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m compileall -q app tools` | PASS |
| `.venv\Scripts\python.exe -m unittest discover -s tests -v` | PASS: 78 tests |
| `.venv\Scripts\python.exe -m unittest discover -s tests/acceptance -v` | PASS: 17 tests |
| `.venv\Scripts\python.exe tools/hackathon_acceptance.py --require-assembly` | PASS: `PASS=17 FAIL=0 SKIP=0` |
| `node --test tests/match_flow.test.mjs` | PASS: 4 tests |
| `harness.cmd --no-color` | PASS: 6/6 stages |
| `git diff --check` | PASS |
| `python scripts/gate.py check --run-checks --check-commits --committed-only` | PASS |

The local startup probe used a disposable database and an explicit non-secret
test key. Demo mode returned HTTP 200 and created four demo users plus one demo
admin. `DEMO_MODE=0` returned HTTP 200 and created zero users and zero admins.
Neither probe read a secret file or reused the repository instance database.

## Product and evidence checks

- The bounded credential-free Public Live smoke was network-gated and emitted
  only sanitized status fields; see [`FINAL_CLAIMS.md`](FINAL_CLAIMS.md).
- Ten fresh integrated screenshots were captured at exact 1100x900 and 390x844
  viewports; see [`FINAL_VISUAL_EVIDENCE.md`](FINAL_VISUAL_EVIDENCE.md). Three
  mobile-flow primary actions require scrolling and are not claimed as visible
  in the initial 844px viewport.
- The root README points judges to this integrated evidence and distinguishes
  Public Live, Fixture, Unavailable, and Roadmap.
- No credential-like file or local SQLite database is tracked. The capture
  script deletes only the disposable database it creates.
- The final branch was pushed without force and its remote SHA was compared to
  the local clean HEAD. Neither local nor remote `main` was modified by this
  task.

## Evidence limitations

Passing these checks proves the recorded local candidate behavior. The later
deployment receipt separately proves a resettable public demo, but not
production security, durable availability, official third-party status, future
Public Live availability, account ownership, real merchants, or product
outcomes.
