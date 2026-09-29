# INT-001 Assembly Blocker Receipt

> Status: **NOT A RELEASE CANDIDATE**. This receipt records assembled progress
> and one ownership blocker. It is not final gate, screenshot, deployment, or
> judge-ready evidence.

> **Superseded by [`FINAL_GATE_RECEIPT.md`](FINAL_GATE_RECEIPT.md).** The
> owner-scoped UX-002 correction was formally
> accepted at `ac9c0d608c0b61ea0dbb93e885481a1cc2aa07b7` and merged without
> conflicts as `ddac0977d8369b75f38c27822aca7bdab398dddc`. The strict assembled
> gate then passed with `PASS=17 FAIL=0 SKIP=0`. The failure counts below are
> intentionally preserved as historical evidence, not current candidate status.

Observed at `2026-08-22T20:27:55Z` in
`songconmaisaix31-design/trk-integration-int-001`.

## Exact merge receipts

| Step | Commit | First parent | Exact second parent |
| --- | --- | --- | --- |
| Frozen governance base | `013633354f8b84e5ef5370bf8ace0b81ed1fc0f5` | `97ecb35612f9c00c834aa94dcd47224480eb60a8` | n/a |
| Integration specification | `9e1cb713e45f826812d9bb3357024ce9e789d1ab` | frozen base | n/a |
| DATA-001 merge | `bf5d7aee8694b5ca0d3ac332aa4f7f4568d4d349` | specification | `324b847dbe75bdf03f27fc5638cac30eed6a2ef7` |
| CORE-001 merge | `667f49755e2f3eb39be6d75db08930a1a44fb514` | DATA-001 merge | `06012b59326c5a1de031d5f24a0027ec921d2397` |
| UX-001 merge | `9b6ddf4f000b55abd2569bc6d5aded671793f2c1` | CORE-001 merge | `4c298caaa62d7f5b522b22a3f38ab7ded93f9253` |
| QA-001 merge | `ebd4bf1a5909fe68bd841a77fff8df8e3d16607c` | UX-001 merge | `6f4ba724ff9e24c338b3da05558630f6c29b6cce` |

All four merges completed without conflicts. Each is a two-parent `--no-ff`
merge with the accepted worker SHA as its exact second parent. The repository
gate accepted the chain with four integration merges and two integration-owned
authored commits after `c0cca83f363c7a5f65a951534b2b26e8169947bc`.

## Completed integration-owned adjustments

- `tests/test_e2e_harness.py` now treats the retired authorization route as a
  `404`, loads Keep only through the explicit Fixture sync route, and verifies
  the five resulting tags are Fixture, unverified, and self-only.
- `harness.cmd` now prefers the current worktree's
  `.venv\Scripts\python.exe`, with PATH `python` as the fallback.
- The focused replacement E2E test passed, and `harness.cmd --no-color doctor`
  passed both runtime and syntax stages.

## Current verification results

| Check | Result | Bounded evidence |
| --- | --- | --- |
| Integration commit/ownership gate | PASS | 4 exact merges, 2 authored commits |
| Python syntax | PASS | `compileall -q app tools` |
| Node motion suite | PASS | 4 passed, 0 failed |
| HTTP workflow harness | PASS | 6/6 stages, exit 0 |
| Demo startup | PASS | home 200; 4 demo users; 1 demo admin in an isolated temporary database |
| `DEMO_MODE=0` startup | PASS | home 200; 0 users; 0 admins in an isolated temporary database |
| Bounded Public Live smoke | PASS | network reachable; sanitized mapper receipts below |
| Full Python discovery | **FAIL** | 77 run; 1 assertion failure |
| Acceptance discovery | **FAIL** | 17 run; 1 assertion failure |
| Strict assembly gate | **FAIL** | PASS=16, FAIL=1, SKIP=0 |
| HTTP/text diff check | PASS | no whitespace errors |

The Public Live smoke used only credential-free public sample handles, the
checked-in adapters' four-second timeouts and response limits, and emitted no
raw profile or tag values:

| Source | State | Normalized tag count | Mapping version | Elapsed |
| --- | --- | ---: | --- | ---: |
| Duolingo | `ready` | 5 | `duolingo-public-v1` | 880 ms |
| GitHub REST | `ready` | 4 | `github-rest-public-v1` | 1556 ms |
| LeetCode.com | `ready` | 4 | `leetcode-com-public-v1` | 753 ms |

These receipts prove only current response provenance and mapper acceptance for
the queried public samples. They do not prove account ownership,
authentication, official API status, availability at judging time, or a public
deployment.

## Blocking defect

`tests/acceptance/test_datasource_boundaries.py` requires an offline Fixture
profile to contain both:

- `演示数据 Fixture`
- `用于演示流程，不是账号实况`

The assembled `app/templates/profile.html` currently renders only `已连接` or
`系统生成` for a source group. Consequently, the profile hides the difference
between a ready Public Live connection and the seeded Fixture connection even
though the database provenance is correct.

The smallest correct repair is in the UX-owned profile template: derive the
display state from `connections[source_group.grouper].data_mode`, render the
contracted Public Live or Fixture badge, and include the Fixture disclaimer.
That file is outside the INT-001 write allowlist. An `app/__init__.py`
post-render HTML rewrite would technically fit the allowlist but would be a
fragile ownership bypass and could mislabel future states, so it was not used.

## Required continuation

1. Dispatch an owner-authorized correction for `app/templates/profile.html`,
   or explicitly amend INT-001 ownership before editing it.
2. If a new worker SHA is produced, update the accepted dependency set before
   integration; INT-001 must not merge an unapproved head.
3. Rerun every required command from a clean assembled HEAD.
4. Only after `FAIL=0 SKIP=0`, capture fresh 1100x900 and 390x844 screenshots,
   write final integrated claims, and update the root README.

No final screenshots, final claims, or judge README pointer were created in
this blocked state. Existing UX-001 screenshots were not reused as integrated
evidence.

## Coordination state

The required heartbeat and blocker escalation were attempted from the assigned
terminal, but Orca returned `Dispatch ctx_48292b82ef17 capability is revoked`.
A subsequent read-only coordinator check returned no messages. A fresh live
dispatch is required for further coordinated work and final lifecycle receipt.
