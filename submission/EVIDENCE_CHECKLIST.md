# Submission Evidence Checklist

## QA-001 branch evidence — 2026-08-23

- [x] Frozen dependency identified as
  `origin/songconmaisaix31-design/trk-architecture-arch-001@eddb9dd3add3d898db1b5e6a419e835d48bda400`.
- [x] Acceptance discovery ran against disposable databases: 17 tests, 0
  failures, 9 explicit assembly skips.
- [x] Deterministic dry-run reported `PASS=1`, `FAIL=0`, `SKIP=17` and all five
  failure categories.
- [x] Normal offline runner reported `PASS=8`, `FAIL=0`, `SKIP=9` with external
  socket creation blocked.
- [x] A controlled `--require-assembly` run returned exit 1 and reported the
  expected current-branch assembly gaps as categorized failures.
- [ ] Target datasource route/schema checks pass on the assembled candidate.
- [ ] CORE-001 internal candidate-ID privacy check passes on the assembled
  candidate.
- [ ] `--require-assembly` reports `FAIL=0 SKIP=0` on the exact final SHA.
- [ ] Full Python, Node, syntax, HTTP harness, and diff gates pass on the exact
  final SHA.
- [ ] Fresh desktop and 390x844 screenshots have been captured from the exact
  final SHA.
- [ ] Local HEAD equals the pushed remote SHA and the final worktree is clean.

## Public Live evidence

- [ ] A separately authorized, current bounded smoke record exists for every
  Public Live source claimed in the final narrative.
- [ ] The record contains timestamp, source, response status/shape summary,
  elapsed time, timeout, byte cap, and `raw bodies stored: No`.
- [ ] No credential, public-profile body, cookie, token, authorization header,
  repository name, email, or unnecessary identity field is stored.
- [ ] Public-handle ownership is explicitly described as unverified.

QA-001 intentionally did not run a public smoke probe. The dated ARCH-001 probe
freezes mappings but is not current QA live-success evidence.

## Fixture and Unavailable evidence

- [ ] The offline account contains each required Fixture key exactly once and
  at least 21 behavior rows in total.
- [ ] Every Fixture row is `verified=false`, `self_only`, and
  `synthetic_fixture`.
- [ ] Fixture loading is rejected with demo mode disabled.
- [ ] A simulated Public Live network failure preserves prior rows and does not
  load Fixture data.
- [ ] Every Unavailable card has no active form, and forged POST requests cause
  no database side effect.
- [ ] Merchant benefits and manual redemption are visibly labeled Fixture.

## Claim hygiene

- [x] The submission pack separates Public Live, Fixture, Unavailable, and
  Roadmap.
- [x] The pack claims only the separately verified resettable public demo; it
  contains no claim of production readiness, users, revenue, conversion,
  retention, match quality, judging score, approval, ranking, or award.
- [x] Screenshots, contracts, source files, and skipped checks are not presented
  as successful runtime evidence.
- [ ] Every final present-tense claim points to exact-SHA evidence.
