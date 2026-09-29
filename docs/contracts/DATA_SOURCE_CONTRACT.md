# RealTags Data Source Contract

## 1. Contract status

| Item | Value |
|---|---|
| Version | `1.0.0` |
| Status | Frozen for hackathon P0 |
| Frozen by | `ARCH-001` |
| Frozen base | `e7e4ee78826f213109955d345ed51a05839e4c0f` |
| Date | 2026-08-23 |
| External interface evidence | [`API_INTERFACE_CATALOG.md`](API_INTERFACE_CATALOG.md) (immutable input) |

This file is the single source of truth for datasource modes, result states,
normalized tags, and Public Live mappings. It does not claim an official API,
account ownership, private-data access, or production stability.

Normative terms `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are used deliberately.

## 2. Core distinctions

### 2.1 Data modes

| Machine value | Display class | Meaning |
|---|---|---|
| `public_live` | Public Live | A credential-free request returned a currently valid public profile shape |
| `fixture` | Fixture | Deterministic synthetic data used only to demonstrate product behavior |
| `unavailable` | Unavailable | No safe, useful P0 product mapping is enabled |

Mode is a server registry decision. A browser MUST NOT select or override it.
An adapter MUST NOT silently change from `public_live` to `fixture` after an
error.

### 2.2 Fetch states

Canonical machine values use underscores. The corresponding prose terms are
unavailable, timeout, invalid-input, malformed-response, and upstream-error.

| Machine value | Terminal? | Retryable? | Meaning |
|---|---:|---:|---|
| `ready` | yes | no | Valid source result; tags may be empty when an optional collection is validly empty |
| `unavailable` | yes | no | Source disabled, public profile absent/private, or no P0 mapping |
| `timeout` | yes | yes | Request exceeded the configured timeout |
| `invalid_input` | yes | no | Subject failed local validation; no network request occurred |
| `malformed_response` | yes | no | 2xx response was oversized, non-JSON, or violated a required response shape |
| `upstream_error` | yes | conditional | Redirect, network failure, rate limit, or unexpected non-2xx upstream response |

`ready` describes the latest attempt. Persistence may retain a previous
successful snapshot after a non-ready attempt, but the UI MUST show both the
latest state and the last-success timestamp.

### 2.3 Identity assurance

| Value | Meaning |
|---|---|
| `unverified_public_handle` | Public data was found for the entered handle; ownership was not proven |
| `synthetic_fixture` | No person or account is represented |
| `not_applicable` | The source is unavailable and returned no data |

Public Live MUST NOT use an assurance value that contains `authenticated`,
`owned`, or `verified_identity`.

### 2.4 Evidence kind

| Value | Meaning |
|---|---|
| `direct` | Normalized directly from one or more allowlisted upstream fields |
| `derived` | Deterministically computed only from allowlisted direct fields |

Derived does not mean inferred by an AI model. P0 contains no model-generated
behavior tag.

## 3. Result envelope

Every adapter returns the same logical envelope:

```json
{
  "source": "github",
  "data_mode": "public_live",
  "state": "ready",
  "identity_assurance": "unverified_public_handle",
  "attempted_at": "2026-08-23T00:00:00Z",
  "fetched_at": "2026-08-23T00:00:00Z",
  "mapping_version": "github-rest-public-v1",
  "tags": [],
  "error": null
}
```

Error form:

```json
{
  "source": "github",
  "data_mode": "public_live",
  "state": "timeout",
  "identity_assurance": "unverified_public_handle",
  "attempted_at": "2026-08-23T00:00:00Z",
  "fetched_at": null,
  "mapping_version": "github-rest-public-v1",
  "tags": [],
  "error": {
    "code": "request_timeout",
    "retryable": true
  }
}
```

Rules:

- `source`, `data_mode`, `state`, `identity_assurance`, `attempted_at`,
  `mapping_version`, and `tags` are required.
- `fetched_at` is present only for `ready` Public Live results. Fixture results
  use `null`; their creation time is application state, not a live fetch time.
- Non-ready results return `tags: []` and a stable bounded error object.
- Error objects MUST NOT contain a raw body, URL query value, public handle,
  response header dump, stack trace, cookie, token, or authorization value.
- Expected upstream failures return the envelope rather than raising through
  the Flask route.

## 4. Normalized tag

```json
{
  "tag_id": "coding_primary_languages",
  "category": "技术",
  "name": "公开仓库主要语言",
  "value": {
    "items": ["Python", "TypeScript"],
    "sample_size": 8,
    "window": "latest_10_owner_repositories"
  },
  "source": "github",
  "data_mode": "public_live",
  "evidence_kind": "direct",
  "verified": true,
  "identity_assurance": "unverified_public_handle",
  "visibility": "self_only",
  "mapping_version": "github-rest-public-v1",
  "observed_at": "2026-08-23T00:00:00Z"
}
```

Rules:

- `tag_id` is a stable snake-case key and is the only identifier consumed by
  matching.
- `category` and `name` are Chinese-facing UI labels.
- `value` is always an object with a source-specific schema frozen below.
- `source` identifies the adapter, not the mode.
- Public Live tags set `verified=true` only after a `ready` response passes the
  exact mapper. This verifies data provenance, not profile ownership.
- Fixture tags always set `verified=false`.
- Every P0 tag is `self_only` in storage and at the match-result boundary.
- `observed_at` is the successful fetch time for Public Live and `null` for
  Fixture.
- Unknown fields are ignored at the upstream boundary and are never copied
  wholesale into `value`.

## 5. Stable error codes

| State | Allowed codes |
|---|---|
| `unavailable` | `source_disabled`, `profile_not_found`, `profile_not_public` |
| `timeout` | `request_timeout` |
| `invalid_input` | `missing_handle`, `invalid_handle` |
| `malformed_response` | `response_too_large`, `invalid_json`, `schema_mismatch` |
| `upstream_error` | `redirect_rejected`, `network_error`, `rate_limited`, `http_4xx`, `http_5xx` |

HTTP 404 or a source-specific empty profile result maps to
`profile_not_found`, not `invalid_input`: the handle syntax was valid and the
request occurred. GitHub 403 with exhausted public rate-limit metadata maps to
`rate_limited`. An unexpected 401/403 without credentials remains `http_4xx`;
the adapter MUST NOT request a token.

## 6. P0 source registry

| `source` | Mode | Enabled | Mapping version | Identity assurance |
|---|---|---:|---|---|
| `duolingo` | `public_live` | yes | `duolingo-public-v1` | `unverified_public_handle` |
| `github` | `public_live` | yes | `github-rest-public-v1` | `unverified_public_handle` |
| `leetcode_com` | `public_live` | yes | `leetcode-com-public-v1` | `unverified_public_handle` |
| `keep` | `fixture` | yes, demo mode only | `keep-fixture-v1` | `synthetic_fixture` |
| `netease` | `unavailable` | no | `none` | `not_applicable` |
| `weread` | `unavailable` | no | `none` | `not_applicable` |
| `steam` | `unavailable` | no | `none` | `not_applicable` |
| `github_graphql` | `unavailable` | no | `none` | `not_applicable` |
| `leetcode_cn` | `unavailable` | no | `none` | `not_applicable` |

The offline fallback demo account MAY contain deterministic Fixture versions
of the same normalized Duolingo, GitHub, and LeetCode tags, but those rows and
source groups remain `fixture`, `verified=false`, and
`synthetic_fixture`. They are a separate seeded account/snapshot, never an
automatic fallback for a Public Live sync.

## 7. Duolingo Public Live mapping

### 7.1 Request

```text
GET https://www.duolingo.com/2017-06-30/users?username={url_encoded_handle}
```

- No credentials, cookie, or authorization header.
- Input is trimmed, 1–64 characters, and matches
  `^[A-Za-z0-9._-]+$` before URL encoding.
- The endpoint is an upstream internal/public route, not a claimed official
  stable API.

### 7.2 Required response shape

- top level is an object;
- `users` is a list with at least one object;
- first user has non-negative integer `streak` and `totalXp`;
- `courses` is a list;
- every mapped course has string `learningLanguage`, non-negative integer
  `xp`, and optional string `id` and `title`; and
- `currentCourseId` is optional string/null.

An empty `users` list is `unavailable/profile_not_found`. A wrong required type
is `malformed_response/schema_mismatch`.

### 7.3 Tags

| `tag_id` | Chinese name | Kind | Value schema | Upstream fields |
|---|---|---|---|---|
| `learning_languages` | 在学语种 | direct | `{ "items": [language_code...], "titles": {code: title} }` | unique `courses[].learningLanguage`; optional `courses[].title` |
| `learning_streak` | 连续学习天数 | direct | `{ "days": integer }` | `streak` |
| `learning_total_xp` | 总学习经验 | direct | `{ "xp": integer }` | `totalXp` |
| `learning_course_xp` | 分语种学习经验 | direct | `{ "items": [{"language": code, "xp": integer}...] }` | `courses[].learningLanguage`, `courses[].xp` |
| `learning_current_course` | 当前学习课程 | direct | `{ "course_id": string, "language": code, "xp": integer }` | `currentCourseId` joined to `courses[].id` |

Sort languages by code and course-XP items by descending XP then language.
Omit `learning_current_course` if the optional ID is absent or has no course
match.

P0 MUST NOT map active time, weekly active days, league, crowns, level, or a
"learning consistency" band. The verified response does not supply enough
frozen evidence for those PRD concepts.

The offline fallback account may include these Duolingo-shaped Fixture-only
keys. Public Live MUST NOT emit them:

| `tag_id` | Chinese name | Value schema | Why Fixture-only |
|---|---|---|---|
| `learning_consistency` | 学习坚持度 | `{ "level": one of "轻度", "稳定", "硬核" }` | Frozen public response lacks weekly activity needed by the PRD rule |
| `learning_active_hours` | 学习活跃时段 | `{ "hours": [integer 0..23...] }` | Frozen public response has no activity-time series |
| `learning_level` | 当前学习等级 | `{ "level": integer }` | No verified public level field was frozen |

## 8. GitHub REST Public Live mapping

### 8.1 Requests

```text
GET https://api.github.com/users/{url_encoded_handle}
GET https://api.github.com/users/{url_encoded_handle}/repos?sort=pushed&direction=desc&type=owner&per_page=10&page=1
GET https://api.github.com/users/{url_encoded_handle}/events?per_page=10&page=1
```

- No token or authorization header.
- Input is trimmed, 1–39 characters, and matches
  `^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$`.
- The repository and event reads are deliberately bounded to the first 10
  public items. Their tags are samples, not lifetime totals.

### 8.2 Required response shapes

- user response is an object with string `login` and non-negative integer
  `public_repos`;
- repository response is a list; mapped items have boolean `fork`,
  string/null `language`, and valid string/null `pushed_at`;
- event response is a list; mapped items have string `type` and valid string
  `created_at`; and
- empty repository or event lists are valid `ready` results.

The mapper ignores repository name, description, URL, owner, avatar, stars,
fork count, biography, company, location, email, and event payload.

### 8.3 Tags

| `tag_id` | Chinese name | Kind | Value schema | Rule |
|---|---|---|---|---|
| `coding_public_repositories` | 公开仓库数量 | direct | `{ "count": integer }` | `user.public_repos` |
| `coding_primary_languages` | 公开仓库主要语言 | direct | `{ "items": [language...], "sample_size": integer, "window": "latest_10_owner_repositories" }` | non-null language on sampled non-fork owner repos; sort by frequency then name |
| `coding_recent_event_types` | 近期公开活动类型 | direct | `{ "counts": {event_type: integer}, "event_count": integer, "window": "latest_10_public_events" }` | count sampled `events[].type` |
| `coding_recent_activity_days` | 近期公开活跃天数 | derived | `{ "days": integer, "event_count": integer, "window": "latest_10_public_events" }` | distinct UTC dates from sampled `created_at` |

Emit `coding_primary_languages` only when at least one sampled language exists.
Emit the two recent-activity tags for a valid empty event list with zero counts;
that is a statement about the bounded public sample, not lifetime inactivity.

P0 MUST NOT map followers, stars, account age, repository names, organizations,
contribution totals, private activity, or an inferred skill level. GitHub
GraphQL is not called.

## 9. LeetCode.com Public Live mapping

### 9.1 Request

```text
POST https://leetcode.com/graphql
Content-Type: application/json
```

Exact body shape:

```json
{
  "operationName": "PublicProfile",
  "query": "query PublicProfile($username: String!) { matchedUser(username: $username) { username profile { ranking } submitStatsGlobal { acSubmissionNum { difficulty count submissions } } } }",
  "variables": { "username": "<validated handle>" }
}
```

- Only this `query` operation is allowed; no mutation.
- Handle is passed as a GraphQL variable, never interpolated into the query.
- Input is trimmed, 1–64 characters, and matches `^[A-Za-z0-9_-]+$`.
- No cookie or authorization header.

ARCH-001 verified this actual profile query on 2026-08-23. The older transport-
only `__typename` result is not the basis of this mapping.

### 9.2 Required response shape

- top level is an object with object `data` and no non-empty `errors`;
- `data.matchedUser` is an object, otherwise
  `unavailable/profile_not_found`;
- `submitStatsGlobal.acSubmissionNum` is a list containing exactly one usable
  item for each of `All`, `Easy`, `Medium`, and `Hard`;
- each item has non-negative integer `count` and `submissions`; and
- `profile.ranking` may be a non-negative integer or null.

### 9.3 Tags

| `tag_id` | Chinese name | Kind | Value schema | Rule |
|---|---|---|---|---|
| `coding_solved_total` | 公开解题总数 | direct | `{ "count": integer }` | `All.count` |
| `coding_solved_by_difficulty` | 分难度公开解题数 | direct | `{ "easy": integer, "medium": integer, "hard": integer }` | difficulty `count` values |
| `coding_accepted_submissions` | 公开通过提交次数 | direct | `{ "total": integer, "easy": integer, "medium": integer, "hard": integer }` | difficulty `submissions` values |
| `coding_public_ranking` | 公开排名 | direct | `{ "rank": integer }` | `profile.ranking`; omit when null |

P0 MUST NOT calculate an acceptance rate, contest rating, activity streak,
programming language preference, or skill level from this query. LeetCode.cn
uses a different schema and remains unavailable for product mapping.

## 10. Keep Fixture mapping

Keep has no P0 live request. In `DEMO_MODE=1`, an explicit Fixture action may
produce deterministic values for:

| `tag_id` | Chinese name | Value schema |
|---|---|---|
| `sport_primary` | 主要运动类型 | `{ "items": [string...] }` |
| `sport_weekly` | 周运动频次 | `{ "times": integer }` |
| `sport_total` | 累计运动量 | `{ "km": number, "minutes": integer }` |
| `sport_active_hours` | 运动活跃时段 | `{ "hours": [integer...] }` |
| `sport_intensity` | 运动强度等级 | `{ "level": one of "入门", "进阶", "资深" }` |

All values are synthetic. Every tag is `fixture`, `verified=false`,
`synthetic_fixture`, and `self_only`. Production mode MUST reject Fixture
loading and MUST NOT treat persisted Fixture rows as usable matching data.

## 11. Offline Fixture snapshot

A dedicated offline demo account MAY seed Fixture equivalents of the frozen
normalized keys so the entire judge path works without internet. It MUST:

- contain at least 20 external/derived behavior-tag rows;
- keep Public Live-capable source groups visibly marked `Fixture`;
- use a fixed `fixture_version` and deterministic values;
- have no `fetched_at` value and no public handle;
- never be used as the result of a failed Public Live sync; and
- remain isolated from non-demo users by the existing demo-pool boundary.

This snapshot proves UI and product behavior only. It is not current API
evidence.

### 11.1 Required 21-key Fixture vocabulary

The offline fallback account MUST contain exactly one usable row for each key
below before optional extra derived rows are added. This prevents satisfying
the 20+ requirement with arbitrary or duplicate fields.

| Group | Required keys | Count |
|---|---|---:|
| Duolingo-shaped Fixture | `learning_languages`, `learning_streak`, `learning_total_xp`, `learning_course_xp`, `learning_current_course`, `learning_consistency`, `learning_active_hours`, `learning_level` | 8 |
| Keep Fixture | `sport_primary`, `sport_weekly`, `sport_total`, `sport_active_hours`, `sport_intensity` | 5 |
| GitHub-shaped Fixture | `coding_public_repositories`, `coding_primary_languages`, `coding_recent_event_types`, `coding_recent_activity_days` | 4 |
| LeetCode-shaped Fixture | `coding_solved_total`, `coding_solved_by_difficulty`, `coding_accepted_submissions`, `coding_public_ranking` | 4 |
| **Total** | | **21** |

Fixture equivalents use the same value schemas as their Public Live keys so
matching and templates have one normalized contract. The source group MUST
still show `Fixture`, and the three Duolingo Fixture-only keys MUST NOT be
accepted from the Public Live mapper.

## 12. Unavailable sources

### Keep live

The bearer-authenticated aggregate route has no successful authenticated
evidence. Login and activity-detail flows may contain sensitive health and
location data. No P0 request is permitted.

### NetEase Cloud Music

The catalog describes an unofficial localhost service that was not running,
includes unresolved method contracts, and contains an invalid port entry. No
P0 service, login, QR, check-in, or HTTP request is permitted.

### WeRead

No configured MCP server exists; assumed localhost routes were absent; internal
routes require credentials or returned 404. No P0 MCP or HTTP request is
permitted.

### Steam

All useful mappings require a Web API key and, for user data, a suitable public
Steam profile. No successful functional request was verified. No P0 request is
permitted.

### GitHub GraphQL

The endpoint requires authentication even for a minimal query. P0 uses public
REST only; no GraphQL request is permitted.

### LeetCode.cn

The transport-only query is evidence of endpoint reachability, not a product
profile mapping. No P0 request is permitted.

## 13. Persistence and replacement rules

- A `ready` result replaces one user's rows for the same source atomically.
- A non-ready result never deletes or partially updates last-success tags.
- A Public Live success may replace a prior Fixture snapshot only after the
  user explicitly submits the Public Live sync for that account/source.
- A Public Live failure never replaces live data with Fixture data.
- `refreshed_at` means last successful source load. For Public Live it is the
  fetch-success time; for Fixture it is the explicit Fixture-load time and is
  never presented as a live fetch.
- Storage `tags.updated_at` is an application row-write time. It projects to
  contract `observed_at` only for Public Live rows; Fixture `observed_at`
  remains `null`.
- Public handles are self-only operational metadata and MUST NOT be supplied to
  matching/result/chat templates.
- Raw remote JSON is never persisted.

## 14. Matching projection

The matching layer receives only:

```json
{
  "tag_id": "coding_primary_languages",
  "value": { "items": ["Python", "TypeScript"] }
}
```

It MUST NOT receive source handles, response metadata, error bodies, mapping
versions, or identity fields. Public Live and allowed demo Fixture tags use the
same normalized `tag_id` semantics; mode eligibility is checked before this
projection.

The current `behavior` similarity can consume language/sport sets after a
single explicit key map. New coding keys MAY add common hidden points, but P0
MUST NOT change the frozen match-weight percentages without a separate product
decision.

## 15. UI and claim rules

- Public Live badge: `公开数据 · 已同步`.
- Ownership disclaimer: `来自实时公开资料，不代表账号归属已验证`.
- Fixture badge: `演示数据 Fixture`.
- Fixture disclaimer: `用于演示流程，不是账号实况`.
- Unavailable source: `本次演示不可用` with a bounded reason.
- Do not use `已认证` as the only visible label for a tag.
- Do not call any P0 source an official API unless the immutable catalog says
  so; none of the newly enabled profile mappings receives that claim here.
- Do not claim a deployment, user count, partner, merchant agreement, match
  quality, conversion, retention, or business result from this contract.

## 16. Current live evidence record

On 2026-08-23 (Asia/Shanghai), ARCH-001 used one-shot credential-free probes
with TLS verification, no retries, an 8-second timeout, and a 16 KiB read cap.
No raw body was stored.

| Probe | Result used by this contract |
|---|---|
| Duolingo `username=duo` | HTTP 200; non-empty `users`; required profile and course fields present |
| GitHub `octocat` user and two owner repos | HTTP 200; required user/repository fields present |
| GitHub `octocat` events | HTTP 200; valid empty list, proving empty is a success state |
| GitHub `sindresorhus` three public events | HTTP 200; `type`, `repo`, and `created_at` present |
| LeetCode.com `matchedUser(username: "leetcode")` | HTTP 200; non-null user, ranking, and four accepted-count records; no GraphQL errors |

This dated record supports the mapping freeze. It does not guarantee future
availability or prove that any sample handle belongs to a RealTags user.
