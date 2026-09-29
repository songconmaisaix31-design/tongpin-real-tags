# RealTags Hackathon Implementation Specification

## Document control

| Item | Value |
|---|---|
| Status | Frozen for P0 implementation |
| Logical task | `ARCH-001` |
| Frozen base | `e7e4ee78826f213109955d345ed51a05839e4c0f` |
| Date | 2026-08-23 |
| Product authority | [`../../产品需求文档_PRD.md`](../../产品需求文档_PRD.md) |
| External API evidence | [`../contracts/API_INTERFACE_CATALOG.md`](../contracts/API_INTERFACE_CATALOG.md) (immutable input) |
| Normative data contract | [`../contracts/DATA_SOURCE_CONTRACT.md`](../contracts/DATA_SOURCE_CONTRACT.md) |
| P0 gate | [`../acceptance/P0_ACCEPTANCE_MATRIX.md`](../acceptance/P0_ACCEPTANCE_MATRIX.md) |

This specification optimizes for a reliable, truthful three-minute hackathon
demo. It does not define a production launch, a deployed service, commercial
traction, or authenticated ownership of third-party accounts.

## 1. Outcome

The P0 product must let a judge see one coherent story:

1. a signed-in user has self-only behavioral tags with explicit provenance;
2. Public Live data is visibly distinct from deterministic Fixture data;
3. matching discloses only a smoothed percentage and hidden common-point count;
4. an anonymous conversation uses tools to progress from L0 through L4; and
5. a 3–10 person restaurant event demonstrates anonymous formation, group chat,
   and a Fixture merchant benefit.

The shortest reliable implementation path is to preserve the existing Flask,
Jinja2, and SQLite product flows and replace the misleading datasource seam.
Rebuilding matching, chat, events, or the visual system is not part of this
freeze.

## 2. Truth model

Every product claim and every source card must use one of these evidence
classes. They are not interchangeable.

| Class | Meaning | Allowed claim | Prohibited claim |
|---|---|---|---|
| Baseline fact | Behavior present in the frozen repository and, where stated, exercised locally | "The Flask baseline contains an anonymous match flow" | "The public deployment works" |
| Public Live | A credential-free request returned the contracted current public profile shape | "Loaded from a live public profile" | "The user authenticated" or "the user owns this profile" |
| Fixture | Deterministic synthetic data used to demonstrate a product path | "Demo Fixture" | "Live", "verified account", or "real user data" |
| Unavailable | The source is intentionally disabled or a useful public mapping is not available | "Unavailable in this demo" | A clickable authorization or sync path that cannot work |
| Roadmap | A future authenticated, commercial, or production capability | "Planned after the hackathon" | Any present-tense implementation claim |

`Public Live` verifies the response provenance only. Duolingo, GitHub REST, and
LeetCode public handles do not prove that the signed-in RealTags user owns the
queried profile. The UI must never translate Public Live into "identity
verified" or "account connected".

## 3. Frozen baseline

### 3.1 Implemented facts

At the frozen base, the repository contains:

- a Flask application factory, Jinja2 pages, SQLite persistence, and standard
  POST/redirect/GET actions;
- registration with the eight PRD self-declared fields;
- a server-owned matching flow with hard filtering, centralized weights,
  similarity scoring, 60–98 display smoothing, stale-attempt rejection, and
  demo/real candidate-pool isolation;
- direct and event-group conversations, text messages, system cards, dice,
  task cards, common-point unlocks, L0–L4 progression, reporting, blocking, and
  archive behavior;
- user-hosted events, administrator review, restaurant-POI validation,
  anonymous signup review, deadline settlement, group creation, Fixture
  merchant benefits, and manual redemption; and
- the checked-in responsive visual system and representative desktop/mobile
  screenshots described by [`../FRONTEND_HANDOFF.md`](../FRONTEND_HANDOFF.md)
  and [`../../brand-spec.md`](../../brand-spec.md).

The isolated local Harness was run with the existing virtual environment on
2026-08-23. All 6 pipeline stages passed: runtime preflight, syntax, 4 match
motion checks, 23 unit/SSR checks, feature checks, and 5 HTTP product journeys.
This is local baseline evidence only; it is not deployment evidence.

### 3.2 Datasource gap

The current `app/services/adapters.py` has only Duolingo and Keep
`MockDataSourceAdapter` instances. The connection form submits the fixed value
`demo-authorized`, and Fixture tags default to `verified=true`. Seed users have
12 external/derived behavior-tag rows, below the PRD's 20+ behavior-tag target.

Therefore the baseline must not be described as a real Duolingo or Keep
integration. The first implementation priority is provenance correctness, not
adding another visual surface.

### 3.3 Current Public Live evidence

ARCH-001 performed one-shot, credential-free probes with TLS verification, an
8-second timeout, a 16 KiB response cap, no retries, and no raw-body storage.
The evidence is a dated availability observation, not an uptime guarantee.

| Source | Probe result on 2026-08-23 (Asia/Shanghai) | Product decision |
|---|---|---|
| Duolingo | `GET /2017-06-30/users?username=duo` returned HTTP 200, a non-empty `users` list, and the contracted streak, total XP, current-course, and course fields (1,973 bytes) | Freeze a narrow Public Live mapping |
| GitHub REST | Public user and two owner-repository reads for `octocat` returned HTTP 200; its empty events list was accepted as valid. A separate three-event sample for `sindresorhus` returned HTTP 200 with `type`, `repo`, and `created_at` (15,523 bytes) | Freeze user, repository-language, and recent-public-event mappings |
| LeetCode.com GraphQL | A bounded `matchedUser(username: "leetcode")` query returned HTTP 200, non-null profile ranking, and `All/Easy/Medium/Hard` accepted-count records without GraphQL errors (321 bytes) | Freeze the exact LeetCode.com Public Live mapping in the data contract |

These sample handles exist only to validate response shapes. Their data must
not be seeded into a product account as proof of ownership.

## 4. P0 source disposition

| Source | P0 mode | User action | Notes |
|---|---|---|---|
| Duolingo public profile | Public Live | Enter a public username and sync | Internal/public endpoint, not an official stable API and not ownership proof |
| GitHub public REST | Public Live | Enter a public username and sync | Three bounded unauthenticated REST reads; lower rate limit applies |
| LeetCode.com GraphQL | Public Live | Enter a public username and sync | Only the exact frozen profile query is permitted |
| Keep | Fixture | Explicitly load deterministic demo data | No authenticated Keep success evidence exists |
| NetEase Cloud Music | Unavailable | No active control | Depends on an unselected unofficial localhost service |
| WeRead | Unavailable | No active control | MCP/local/internal transports are not configured or usable |
| Steam | Unavailable | No active control | A Web API key and a public profile are required; no functional request was verified |
| GitHub GraphQL | Unavailable | No active control | Credentialed route; public REST already supplies the P0 behavior signal |
| LeetCode.cn GraphQL | Unavailable for product mapping | No active control | Transport evidence exists, but ARCH-001 did not validate a CN profile mapping |

No unavailable source may silently load a Fixture. Keep is the only
user-loadable P0 Fixture source because it is central to the PRD's
learning-plus-exercise story. A separate offline fallback account may contain
clearly labeled Fixture versions of the Public Live mappings.

## 5. Required implementation behavior

### R1. Source registry and connection page

The server owns a single source registry conforming to the data contract. The
connection page renders registry entries instead of hard-coding two sources.

- Duolingo, GitHub, and LeetCode.com cards show `Public Live` and accept a
  public handle.
- Keep shows `Demo Fixture` and requires an explicit "Load demo data" action.
- NetEase, WeRead, Steam, GitHub GraphQL, and LeetCode.cn show `Unavailable in
  this demo`; they have no form action.
- Public Live actions say "Sync public profile", not "Authorize".
- The card displays last successful refresh time, current state, and identity
  assurance `Public handle not ownership-verified`.
- A source error is visible on its own card and through the existing flash
  region. It does not appear as a successful connection.

### R2. Boundary validation and outbound requests

Validate the handle before any network request. Encode GET query/path values
and pass GraphQL handles only as variables. Use TLS verification, explicit
timeouts, bounded response reads, a descriptive User-Agent, and no automatic
retries. Remote scheme, host, port, and path come only from the server registry;
the user can submit a handle, never a URL. Do not read credentials or send
cookies or authorization headers.

The exact remote paths, field mappings, and response-state rules are normative
in [`../contracts/DATA_SOURCE_CONTRACT.md`](../contracts/DATA_SOURCE_CONTRACT.md).

### R3. Atomic source synchronization

A successful result replaces that user's tags for the same source and mode in
one SQLite transaction and updates the connection's last-success metadata. A
failed result writes only bounded state/error metadata. It must not delete or
partially replace the last successful normalized tags.

Raw upstream bodies, cookies, headers, tokens, email addresses, profile names,
repository names, and other unnecessary identity fields are not persisted.
Only the public handle needed for an explicit future refresh and the normalized
self-only tags are stored.

### R4. Provenance-correct tags

Every external tag has `data_mode`, `evidence_kind`, `mapping_version`, and
`identity_assurance` in addition to the existing source and visibility fields.

- Public Live direct and deterministic-derived tags may set
  `verified=true`; this means only that the backing public response passed the
  frozen mapping.
- Fixture tags always set `verified=false`.
- All P0 external tags remain `self_only`.
- The profile UI labels Public Live, Fixture, and derived values explicitly.
  It must not reduce these states to the ambiguous word "certified".
- Missing optional upstream fields omit the relevant tag. Mappers never invent
  a zero, an empty achievement, a language, or a behavioral conclusion.

### R5. Matching integration

The existing weights and 60–98 presentation smoothing remain unchanged.
Matching consumes only normalized tags from a `ready` source result.

- In `DEMO_MODE=1`, explicitly loaded Fixture tags may participate and remain
  visibly Fixture on the self profile.
- In `DEMO_MODE=0`, Fixture loading is unavailable and Fixture tags do not
  participate.
- When no usable external tags exist, the existing `no_external_data` weight
  group applies.
- Source mode, raw score, individual similarities, public handles, and full
  tag data never appear in the L0 match DOM.

### R6. Fixture sufficiency

The dedicated offline fallback judge account must have at least 20
deterministic normalized behavior-tag rows in Fixture mode so the PRD's breadth
can be demonstrated without a network. The count excludes the eight
self-declared registration fields. Each row must be synthetic,
`verified=false`, `self_only`, and visibly marked Fixture.

Public Live results are never padded to reach 20. The profile must show the
actual number returned by the frozen mappings.

### R7. Preserve the existing P0 product

Datasource work must not change:

- the match weights, hard filters, smoothing formula, attempt-token state
  machine, or candidate-pool isolation;
- L0 disclosure boundaries or L1–L4 server-owned progression;
- system-card generation, report/block enforcement, or group archive rules;
- restaurant POI allowlisting, anonymous application review, event settlement,
  or merchant-benefit Fixture behavior; or
- Flask SSR, ordinary links/forms, no-JavaScript operation, reduced motion,
  mobile navigation, and the checked-in visual tokens.

### R8. Hosting safety gap

The PRD requires a phone-verification threshold for creating offline events.
The baseline stores `phone_verified` but `create_user_event()` does not enforce
it. P0 implementation must reject event creation when `phone_verified` is
false. Demo accounts may use an explicitly labeled Fixture verification state;
production mode must not describe that state as real verification.

## 6. Chinese product copy contract

The product is Chinese-facing. These state labels are fixed to prevent truth
drift across pages:

| Internal value | Required visible label | Supporting copy |
|---|---|---|
| `public_live` + `ready` | `公开数据 · 已同步` | `来自实时公开资料，不代表账号归属已验证` |
| `fixture` + `ready` | `演示数据 Fixture` | `用于演示流程，不是账号实况` |
| `unavailable` | `本次演示不可用` | Source-specific bounded reason |
| `timeout` | `公开数据请求超时` | `已保留上次成功结果，可稍后重试` |
| `invalid_input` | `公开账号格式无效` | Source-specific input guidance |
| `malformed_response` | `公开数据格式已变化` | `本次未更新标签` |
| `upstream_error` | `上游服务暂时不可用` | `本次未更新标签` |

Never show `已授权`, `账号已验证`, `官方接口`, or `真实用户` for these
credential-free P0 integrations.

## 7. Explicit non-goals

- OAuth, cookies, API keys, password flows, ownership challenges, or private
  third-party data.
- Keep live integration; Steam live integration; NetEase or WeRead service
  deployment; GitHub GraphQL authentication; LeetCode.cn product mapping.
- WebSocket/SSE chat, voice, media, payments, POS integration, real coupon
  settlement, merchant self-service, notifications, or reputation scoring.
- A/B tests, production analytics, production rate-limit handling, production
  deployment, or claims about users, partners, conversion, recovery, or score.
- Redesigning the established visual language or converting the app to an SPA.

## 8. Roadmap (not P0 evidence)

| Candidate future capability | Evidence required before promotion |
|---|---|
| Public-handle ownership verification | A source-supported ownership challenge or scoped OAuth flow plus privacy review |
| Keep live aggregation | Successful privacy-safe authenticated aggregate probe; no route/health detail collection |
| GitHub GraphQL/private contributions | Scoped token flow, least-privilege review, rate-limit handling, and explicit consent |
| Steam public game behavior | Approved key storage and a successful bounded mapping for a public profile |
| NetEase or WeRead | A selected maintained service/tool, corrected versioned contracts, and security review |
| Production release | CSRF, rate limiting, production secrets, scheduler, HTTPS/WSGI, migrations, monitoring, and compliance work |
| Real merchant benefits | Verified merchant onboarding, benefit authorization, settlement rules, and audit evidence |

Nothing in this table is implemented, scheduled, deployed, or validated by
ARCH-001.

## 9. Definition of done

Implementation is complete only when all of the following are true:

1. the source registry and persistence model implement the normative contract;
2. Duolingo, GitHub REST, and the exact LeetCode.com query pass deterministic
   mapper tests and a separately recorded credential-free smoke probe;
3. every required failure state is tested without real network access;
4. Fixture tags cannot present as Public Live or `verified=true`;
5. the P0 acceptance matrix has no unresolved blocking row;
6. the three-minute judge path completes with networking disabled by using the
   pre-synced last-success snapshot plus explicit Fixture content;
7. the full local Harness, Python syntax checks, relevant visual checks, and
   `git diff --check` pass; and
8. release copy makes no unsupported integration, deployment, metric, user,
   merchant, or business claim.
