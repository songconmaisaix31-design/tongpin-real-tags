# RealTags P0 Acceptance Matrix

## 1. Control and evidence rules

| Item | Value |
|---|---|
| Frozen base | `e7e4ee78826f213109955d345ed51a05839e4c0f` |
| Product authority | [`../../产品需求文档_PRD.md`](../../产品需求文档_PRD.md) |
| Implementation specification | [`../specs/IMPLEMENTATION_SPEC.md`](../specs/IMPLEMENTATION_SPEC.md) |
| Technical specification | [`../specs/TECHNICAL_SPEC.md`](../specs/TECHNICAL_SPEC.md) |
| Data contract | [`../contracts/DATA_SOURCE_CONTRACT.md`](../contracts/DATA_SOURCE_CONTRACT.md) |
| Date | 2026-08-23 |

Status meanings:

| Status | Meaning |
|---|---|
| `EVIDENCED` | Present at the frozen base with identified source/test evidence |
| `FIXTURE-EVIDENCED` | Product path exists, but its data or actor is explicitly synthetic |
| `GAP` | Concrete implementation or current verification is still required |
| `NON-GOAL` | Explicitly outside hackathon P0 |

Checked-in screenshots and design reports are visual artifacts. They are not
live deployment or current post-change runtime evidence. A test file is
coverage intent until it is executed; the baseline Harness execution recorded
below is the current local runtime evidence.

## 2. Baseline verification record

On 2026-08-23, the following command used the existing repository virtual
environment and a disposable SQLite database:

```powershell
.\.venv\Scripts\python.exe tools\harness_cli.py --no-color
```

Result: 6/6 stages passed, covering runtime preflight, syntax, 4 Node match
motion checks, 23 unit/SSR checks, feature checks, and 5 HTTP product journeys.
This proves the frozen local baseline only. It does not prove a public
deployment, upstream availability, production security, user traffic, or a
business result.

ARCH-001 also ran bounded credential-free source probes. The exact evidence
boundary and mappings are recorded in
[`../contracts/DATA_SOURCE_CONTRACT.md`](../contracts/DATA_SOURCE_CONTRACT.md).

## 3. P0 capability matrix

| ID | PRD capability | Frozen-base evidence | Current status | Concrete close condition |
|---|---|---|---|---|
| `P0-01` | Registration with eight self-declared fields and a datasource next step | `app/services/users.py:create_user`; `app/templates/register.html`; `tests/test_e2e_harness.py::test_registration_authorization_and_profile_flow` | `EVIDENCED` | Preserve field validation and redirect while replacing the misleading mock authorization step |
| `P0-02` | Datasource adapter abstraction | `DataSourceAdapter`, `MockDataSourceAdapter`, and `connect_source` exist in `app/services/adapters.py` | `GAP` | Implement the frozen Public Live `fetch` result contract; routes must not call sources directly |
| `P0-03` | Public Live Duolingo behavior mapping | Current app has only a Duolingo Fixture adapter; ARCH-001 separately observed the frozen public shape | `GAP` | Implement `duolingo-public-v1`, state tests, atomic persistence, and current bounded smoke evidence |
| `P0-04` | Public Live GitHub behavior mapping | No GitHub adapter/UI exists; catalog plus ARCH-001 observed public user/repos/events shapes | `GAP` | Implement `github-rest-public-v1` with first-page bounds, valid empty events, and no GraphQL/token use |
| `P0-05` | Public Live LeetCode behavior mapping | No LeetCode adapter/UI exists; ARCH-001 verified the exact LeetCode.com `matchedUser` query | `GAP` | Implement only `leetcode-com-public-v1`; keep CN transport unavailable for product mapping |
| `P0-06` | Keep exercise signal for the demo | Keep currently uses deterministic mock values but labels them verified | `GAP` | Retain as explicit demo-only Fixture, migrate to `verified=false`, and reject it in production mode |
| `P0-07` | 20+ external/derived behavior tags for an offline demo | Seeded users currently receive 12 behavior-tag rows | `GAP` | Dedicated offline Fixture account contains the data contract's 21 unique required keys, excluding eight self-declared fields, with every row visibly Fixture |
| `P0-08` | Provenance, self-only visibility, and truthful source state | Existing rows carry source/visibility, but Fixture rows use `verified=true` and the UI reduces state to connected/certified | `GAP` | Persist/render mode, evidence kind, mapping version, identity assurance, last attempt, and last success; no Fixture-to-Live fallback |
| `P0-09` | Hard filter, centralized 100% weights, similarity scoring, and display smoothing | `app/constants.py:MATCH_WEIGHT_GROUPS`; `app/services/matching.py`; core and E2E tests | `EVIDENCED` | Keep weights and 60–98 transform unchanged; add datasource eligibility tests |
| `P0-10` | Match result shows only percentage and hidden points | `app/routes/matches.py`; `match_detail.html`; searching/result privacy assertions in core/E2E tests | `EVIDENCED` | New handles/provenance/raw source values remain absent from searching and L0 result DOM |
| `P0-11` | Anonymous text chat and system cards | `app/services/chat.py`; `conversation.html`; chat UI and E2E tests | `EVIDENCED` | Preserve member authorization, 500-character limit, and server-owned system-card whitelist |
| `P0-12` | Dice, task card, and common-point unlock tools | `TASK_CARDS` contains 30 entries across five categories; `use_tool()` persists shared system cards; tests cover all actions | `EVIDENCED` | Preserve direct/group behavior and never generate tool results in the browser |
| `P0-13` | Relationship progress and an L0 -> L1 -> L4 demo path | `relationship_progress`, `advance_demo_progress`, disclosure projection, and E2E journey | `FIXTURE-EVIDENCED` | Demo accelerator remains visible only in `DEMO_MODE`; natural progression and privacy tests continue to pass |
| `P0-14` | User-hosted 3–10 person event form and restaurant POI restriction | `create_user_event`, `POIS`, `event_form.html`, admin review, E2E formation flow | `EVIDENCED` | Preserve 3–10, 1–5 tags, time, deadline, and whitelist validation |
| `P0-15` | Event plaza with personalized match score and ordering | `event_match_score`, `list_events`, event templates, nearby tests | `EVIDENCED` | Raw event score remains server-only; default sort remains raw score; displayed score remains smoothed |
| `P0-16` | Signup, anonymous host review, formation/cancellation, and group chat | `event_members`, `review_applicants`, `refresh_event_statuses`, `_form_group`; E2E user-event journey | `EVIDENCED` | Preserve anonymous applicant projection and archived group behavior |
| `P0-17` | Merchant event, benefit issue, static redemption path | Seed merchant events and benefit records; deadline/coupon E2E journey | `FIXTURE-EVIDENCED` | UI and submission label merchant/benefit data Fixture; no partner, payment, POS, or real redemption claim |
| `P0-18` | Phone-verification threshold for offline-event hosts | `phone_verified` exists; demo users are seeded true; `create_user_event()` does not enforce it | `GAP` | Unverified user POST is rejected; demo verification is labeled Fixture; production copy does not claim real verification |
| `P0-19` | Gender composition visibility and same-gender option | Event form, stored policy, approved-member counts, event view | `EVIDENCED` | Preserve bounded enums and visible aggregate counts without member identity disclosure |
| `P0-20` | Report/block safety and administrator handling | Conversation/event reporting, blocks, separate admin session, review/audit tables; feature/E2E tests | `EVIDENCED` | Preserve non-member rejection, blocked read-only behavior, one-way state transitions, and audit actor/time |
| `P0-21` | Responsive branded UI, focus, reduced motion, and no-JS core flows | `brand-spec.md`, `docs/FRONTEND_HANDOFF.md`, CSS/JS layers, checked-in desktop/mobile artifacts, match-motion tests | `EVIDENCED` for baseline; post-change `GAP` | Capture fresh desktop and 390x844 source-state/profile views and rerun runtime/accessibility regression checks after integration |

## 4. Datasource state acceptance

All rows are blocking for the final candidate.

| ID | Required scenario | Acceptance evidence |
|---|---|---|
| `STATE-01` | Public Live success | Deterministic fake-server test validates a `ready` result, exact tags, Public Live badge, last-success time, and ownership disclaimer |
| `STATE-02` | Fixture success | Fixture is deterministic, visibly Fixture, `verified=false`, has no live fetch time/handle, and is disabled in production mode |
| `STATE-03` | Unavailable source/profile | No active form for disabled sources; valid missing profile creates no tags and shows a bounded unavailable state |
| `STATE-04` | Timeout | Returns `timeout/request_timeout`, preserves the last-success rows, and renders a retryable state |
| `STATE-05` | Invalid input | Invalid or missing handle returns before transport; asserted transport call count is zero |
| `STATE-06` | Malformed response | Oversized, invalid JSON, missing required containers, and wrong required types return `malformed_response` with no partial replacement |
| `STATE-07` | Upstream error | Redirect, rate limit, network error, 4xx, and 5xx map to stable bounded codes; no raw response enters HTML/log/storage |
| `STATE-08` | Atomic replacement | Injected persistence failure rolls back all new tags and success metadata |
| `STATE-09` | Valid empty collections | Empty GitHub repos/events are `ready`, not malformed; sample-based zero values are labeled by their bounded window |
| `STATE-10` | Privacy projection | Handles, raw JSON, excluded identity fields, source errors, raw score, and weights are absent from searching/L0 DOM |

## 5. Three-minute demo acceptance

Run the path in
[`../specs/TECHNICAL_SPEC.md`](../specs/TECHNICAL_SPEC.md#10-three-minute-judge-path)
from a resettable database.

The path passes only if:

1. it completes within 180 seconds without manual database editing;
2. networking can be disabled before launch and the path still completes using
   a clearly labeled offline Fixture snapshot plus any pre-synced last-success
   Public Live tags;
3. an optional failed refresh leaves the last-success snapshot visible and
   does not change its mode;
4. the match result exposes no profile/source detail;
5. one direct conversation reaches L4 through the demo-only accelerator;
6. one formed event opens an anonymous group conversation;
7. the merchant benefit is visibly Fixture; and
8. the presenter makes no ownership, deployment, user, partner, metric, score,
   or commercial-success claim.

## 6. Required automated gates

```powershell
.\.venv\Scripts\python.exe -m compileall -q app tests tools
node --test tests/match_flow.test.mjs
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools\harness_cli.py --no-color
git diff --check
```

The optional public smoke probe is separate from deterministic CI. Its record
must include timestamp, source, HTTP status/shape summary, elapsed time, byte
count, timeout/cap settings, and whether raw bodies were stored (`No`). It must
not include raw profiles or secrets.

## 7. Visual gates

Fresh evidence is required after implementation for desktop and 390x844:

- connection registry containing all three modes;
- Public Live ready and one failure state;
- self profile showing direct/derived provenance without overflow;
- L0 matching with no new leakage;
- Fixture merchant benefit; and
- unverified-host event-creation rejection.

Inspect focus visibility, keyboard order, reduced motion, 44px touch targets,
text overflow, bottom-navigation clearance, and disabled-source affordances.
Checked-in baseline screenshots may be comparison references but cannot be
reused as evidence of the final candidate.

## 8. Explicit P0 non-goals

| Capability | Status | Reason |
|---|---|---|
| Voice chat | `NON-GOAL` | PRD P1 and not needed for the judge story |
| Poker and Monopoly | `NON-GOAL` | P1/P2; dice and task cards already prove the tool seam |
| A/B experimentation or user-adjustable weights | `NON-GOAL` | PRD excludes it from the demo; weights stay server-only |
| Keep authenticated live API | `NON-GOAL` | No safe authenticated success evidence |
| NetEase/WeRead local service deployment | `NON-GOAL` | Unselected or missing unofficial prerequisites |
| Steam Web API integration | `NON-GOAL` | Requires a key and profile visibility evidence |
| GitHub GraphQL | `NON-GOAL` | Requires credentials; public REST is sufficient |
| LeetCode.cn product mapping | `NON-GOAL` | Only transport evidence is frozen |
| OAuth/account-ownership verification | `NON-GOAL` | Public-handle reads do not prove ownership |
| Real-time WebSocket/SSE chat | `NON-GOAL` | Existing SSR persistence is sufficient for a demo |
| Real payment, settlement, coupon/POS integration | `NON-GOAL` | Merchant path is explicitly Fixture |
| Merchant self-service, real qualification, or partnership | `NON-GOAL` | No business evidence exists |
| Public production deployment and production readiness | `NON-GOAL` | CSRF, rate limiting, production secrets, scheduler, and compliance work remain |
| User, conversion, retention, match-quality, or revenue metrics | `NON-GOAL` | No measured evidence exists |

## 9. Claim ledger

### Safe claims after all gates pass

- "The local Flask candidate completes the tested anonymous matching, chat,
  and event workflows."
- "Duolingo, GitHub REST, and the exact LeetCode.com profile mapping can read
  useful credential-free public behavior fields, subject to current upstream
  availability."
- "Public Live, Fixture, and unavailable states are visibly distinct."
- "The demo works offline from a deterministic Fixture snapshot and preserves
  the last successful Public Live snapshot on refresh failure."
- "Merchant events and benefits shown in the demo are Fixtures."

### Unsafe claims

- "Official Duolingo/LeetCode API integration."
- "Authenticated" or "ownership-verified" Duolingo, GitHub, or LeetCode
  accounts.
- "Live Keep/Steam/NetEase/WeRead integration" or "GitHub GraphQL works."
- "Production deployed", "production ready", "secure for launch", or
  "end-to-end in production."
- Any user count, merchant partner, coupon redemption, match-quality score,
  conversion, retention, revenue, ranking, award, or judging result.

## 10. Final candidate gate

The integration owner may call the candidate P0-ready only when:

- every `GAP` row above is closed by an exact pushed worker SHA or explicitly
  re-scoped by the product owner;
- all source-state, privacy, Fixture, and phone-verification tests pass;
- the full automated and visual gates pass on the assembled clean HEAD;
- the remote SHA equals local HEAD; and
- release materials use the safe claim ledger without promoting Fixture,
  probe, screenshot, or roadmap evidence into a runtime fact.
