# RealTags P0 Technical Specification

## 1. Scope and constraints

This document defines the smallest technical change that makes the existing
RealTags Flask MVP truthful and judge-ready. It is frozen against
`e7e4ee78826f213109955d345ed51a05839e4c0f`.

Constraints:

- preserve Flask 3, Jinja2, SQLite, server-side routing, and ordinary forms;
- use the Python standard library and existing dependencies only;
- do not read credentials, cookies, `.env` files, or authorization headers;
- make no state-changing third-party request;
- keep raw upstream responses and unnecessary identity fields out of storage;
- treat [`../contracts/API_INTERFACE_CATALOG.md`](../contracts/API_INTERFACE_CATALOG.md)
  as immutable evidence; and
- implement the normative types, mappings, and states in
  [`../contracts/DATA_SOURCE_CONTRACT.md`](../contracts/DATA_SOURCE_CONTRACT.md).

## 2. Target architecture

```text
Jinja source form
  -> POST /profile/connections/<source>/sync
  -> source registry + input validator
  -> DataSourceAdapter.fetch(subject)
       -> bounded credential-free HTTP transport OR deterministic Fixture
       -> source-specific response validator
       -> source-specific normalized tag mapper
  -> atomic SQLite persistence
  -> PRG redirect
  -> self-only profile with explicit provenance
  -> existing matching service consumes ready normalized tags
```

Routes never call remote APIs directly. Templates never receive raw response
objects. Matching never knows remote field names.

## 3. Module design

### 3.1 Source registry

`app/services/adapters.py` remains the application-facing seam. Source-specific
transport and mapping code moves into small modules under
`app/services/data_sources/`:

```text
app/services/adapters.py
app/services/data_sources/http.py
app/services/data_sources/duolingo.py
app/services/data_sources/github.py
app/services/data_sources/leetcode.py
app/services/data_sources/fixtures.py
```

The registry is declarative and is the only list consumed by the connection
page. Each entry defines `source_id`, label, mode, enabled state, input hint,
adapter, and mapping version. Unavailable entries have no adapter.

Do not introduce a plugin framework, dependency-injection container, generic
GraphQL client, or background queue. They do not improve the three-minute demo.

### 3.2 Application-facing interface

The implementation may use dataclasses or typed dictionaries, but it must
preserve this behavior:

```python
@dataclass(frozen=True)
class SourceSyncRequest:
    source: str
    subject: str | None


@dataclass(frozen=True)
class SourceSyncResult:
    source: str
    data_mode: str
    state: str
    identity_assurance: str
    fetched_at: str | None
    tags: tuple[ExternalTag, ...]
    error_code: str | None = None
    retryable: bool = False


class DataSourceAdapter(Protocol):
    def fetch(self, subject: str | None) -> SourceSyncResult: ...
```

`fetch()` returns a result for expected upstream failures. It raises only for a
programming error. This prevents a remote timeout from becoming a Flask 500.

`sync_source(user_id, source, subject)` performs registry lookup, input
validation, adapter invocation, and atomic persistence. It is the only function
called by the route.

### 3.3 HTTP transport

Use `urllib.request` (or another already-installed standard-library path) with:

- TLS certificate verification enabled;
- a 4-second timeout per request;
- no automatic retries;
- no redirect following;
- `Accept: application/json`;
- `Content-Type: application/json` only for LeetCode GraphQL;
- `User-Agent: RealTags-Hackathon/1.0`;
- response limits from the table below; and
- JSON parsing only after a complete bounded read.

Scheme, host, port, and path are fixed constants in source modules. The route
accepts only a validated handle and never accepts an upstream URL, which keeps
this feature out of the SSRF path.

| Request | Limit |
|---|---:|
| Duolingo profile | 64 KiB |
| GitHub user | 32 KiB |
| GitHub owner repositories (`per_page=10`) | 128 KiB |
| GitHub public events (`per_page=10`) | 128 KiB |
| LeetCode.com profile GraphQL | 32 KiB |

An oversized 2xx body is `malformed_response`, not a partial success. GitHub's
three reads may run sequentially; the judge path must not depend on an on-stage
refresh. No request may be retried automatically.

### 3.4 HTTP route contract

Replace the misleading mock authorization action with one route:

```text
POST /profile/connections/<source>/sync
```

Form fields:

| Source mode | Field | Rule |
|---|---|---|
| Public Live | `external_handle` | Required and validated before transport |
| Fixture | none | Server registry selects the deterministic Fixture |
| Unavailable | none | No form is rendered; direct POST returns 404 |

The endpoint is login-required and always uses POST/redirect/GET. It ignores
client-supplied mode, verified state, source label, mapping version, and tags.
Those values come from the server registry.

The old `/profile/connections/<source>/authorize` path and hidden
`authorization_code=demo-authorized` form are removed. No compatibility alias
is needed because this is a hackathon-only local interface.

## 4. Persistence migration

### 4.1 `external_connections`

Keep the current primary key `(user_id, source)` and add:

| Column | Type / default | Meaning |
|---|---|---|
| `data_mode` | `TEXT NOT NULL DEFAULT 'fixture'` | `public_live` or `fixture` |
| `external_subject` | `TEXT` | Public handle needed for an explicit refresh |
| `identity_assurance` | `TEXT NOT NULL DEFAULT 'synthetic_fixture'` | Ownership boundary; Public Live writes its value explicitly |
| `last_state` | `TEXT NOT NULL DEFAULT 'ready'` | Most recent attempt state |
| `last_error_code` | `TEXT` | Stable bounded code, never raw body text |
| `last_attempted_at` | `TEXT` | Most recent attempt time |
| `mapping_version` | `TEXT NOT NULL DEFAULT 'legacy-fixture-v1'` | Mapper version used by last success |

Existing `refreshed_at` becomes the last successful source-load time and is not
changed by a failed attempt. For Public Live it is the fetch-success time; for
Fixture it is the explicit Fixture-load time and MUST be labeled as such in the
UI. Existing `access_token` is a legacy column: all P0 sync paths write it as
`NULL`; migration clears `mock-*` values. Do not use it to store a public
handle.

Existing connection rows migrate to `fixture`, `synthetic_fixture`, and
`legacy-fixture-v1`. A Public Live success always writes all three fields
explicitly.

### 4.2 `tags`

Add:

| Column | Type / default |
|---|---|
| `data_mode` | `TEXT NOT NULL DEFAULT 'fixture'` |
| `evidence_kind` | `TEXT NOT NULL DEFAULT 'direct'` |
| `identity_assurance` | `TEXT NOT NULL DEFAULT 'synthetic_fixture'` |
| `mapping_version` | `TEXT NOT NULL DEFAULT 'legacy-fixture-v1'` |

Migration rules:

1. existing Duolingo, Keep, and `derived` seed rows become `fixture`;
2. all migrated Fixture rows set `verified=0`;
3. `derived` rows set `evidence_kind='derived'`;
4. all rows remain `visibility='self_only'`; and
5. no migration invents a Public Live timestamp or subject.

Existing `tags.updated_at` remains the row-write time. The logical contract
field `observed_at` is projected from it only for Public Live rows and is
`null` for Fixture rows; a Fixture write time is not upstream observation
evidence.

### 4.3 Atomic write algorithm

On `ready`:

1. start one SQLite transaction;
2. delete tags for `(user_id, source)`;
3. insert the complete normalized tag set;
4. upsert the connection's success and attempt metadata; and
5. commit.

On any non-ready result:

1. leave all last-success tags and `refreshed_at` unchanged;
2. upsert only `last_state`, `last_error_code`, and `last_attempted_at`; and
3. commit.

An exception before commit rolls back the whole success write. This ensures a
judge never sees half of a profile after an upstream schema change.

## 5. Mapping execution rules

- Mappers receive only parsed JSON and return normalized contract tags.
- Required container/type mismatches fail the whole result as
  `malformed_response`.
- Missing optional fields omit one tag; they never become fabricated zeroes.
- Empty valid collections are `ready` and may yield no tag for that collection.
- All lists are deduplicated deterministically and use stable sorting so tests
  and screenshots do not flicker.
- Numeric values reject booleans, negatives where nonsensical, NaN, and
  infinity.
- Timestamps must parse as upstream ISO-8601 values before use.
- Repository names, profile names, avatars, email addresses, biographies, and
  raw event payloads are not normalized or persisted.

The exact field-to-tag mappings are specified in the data contract, not in
templates or matching code.

## 6. Matching and privacy integration

`profile_tags()` returns provenance metadata for the self profile. A separate
matching projection exposes only `tag_id` and normalized value to
`calculate_match()`.

For the behavior weight:

- Public Live `ready` tags are usable in every mode;
- Fixture `ready` tags are usable only when `DEMO_MODE=1`;
- error-state sources contribute no new data but may retain their previous
  successful tags; and
- no usable external tags selects the existing `no_external_data` group.

The current matching formula is frozen. New datasource work must not add a new
weight, expose the weight group, or change the 60–98 display transform.

At L0, templates receive no public handle, provenance object, full candidate,
raw score, or per-source tag list. At L3, disclosed normalized tags may show
their source label, but never the queried public handle or raw profile content.

## 7. Fixture design

Fixture generation is deterministic by `(fixture_version, user_id, source)`.
It must produce at least 20 external/derived behavior-tag rows for the
dedicated offline fallback judge account, with stable values across a reset.

Fixture rules:

- `data_mode='fixture'`;
- `verified=false`;
- `identity_assurance='synthetic_fixture'`;
- `visibility='self_only'`;
- no timestamp that looks like a live fetch; and
- no copied public profile, real email, real repository name, real route, or
  merchant partnership claim.

Keep contributes the sport tags required by the PRD. The offline fallback may
seed Fixture equivalents of the frozen Duolingo, GitHub, and LeetCode tags.
It MUST NOT seed NetEase, WeRead, Steam, GitHub GraphQL, or LeetCode.cn data.
The required 21 keys and their value schemas are frozen in the data contract;
the generator cannot satisfy the count with duplicates or arbitrary labels.

## 8. Exact worker boundaries

Each lane uses a top-level worktree based on the integration base and writes
only its allowlist. A cross-lane need is reported to the coordinator; workers
do not patch another lane.

| Lane | Exclusive write allowlist | Required output | Depends on |
|---|---|---|---|
| `data-source-backend` | `app/services/adapters.py`; `app/services/data_sources/**`; `app/db.py`; `app/config.py`; `app/constants.py` | Registry, transport, mappers, Fixture generator, migrations, atomic sync | ARCH-001 contracts |
| `source-experience` | `app/routes/auth.py`; `app/routes/main.py`; `app/templates/connections.html`; `app/templates/profile.html`; `app/templates/home.html`; `app/static/css/trust-profile.css`; `app/static/css/brutalist-components.css` | Public-handle forms, truthful states/copy, provenance profile rendering | Frozen adapter interface; backend SHA before final verification |
| `offline-safety` | `app/services/events.py`; `app/routes/events.py`; `app/templates/event_form.html` | Enforce phone verification for event creation without changing POI/event state machines | ARCH-001 acceptance matrix |
| `qa-contract` | `tests/**`; `tools/public_source_probe.py`; `tools/harness_cli.py` | Offline state/mapping tests, HTTP workflow updates, bounded optional smoke probe | Contracts; final checks consume backend and UI SHAs |
| `release-integration` | `README.md`; `docs/qa/**`; `docs/release/**` | Truthful runbook, fresh desktop/390x844 evidence, exact-SHA merge and gate report | All accepted worker SHAs |

No lane may edit `docs/contracts/API_INTERFACE_CATALOG.md`. QA reports app
defects instead of fixing application code. Integration uses non-fast-forward
merges of exact pushed worker SHAs and does not rebase or amend them.

If a correction does not fit an allowlist, the coordinator creates a new
single-owner correction lane. It is not silently assigned to QA or integration.

## 9. Acceptance tests

### 9.1 Deterministic datasource tests

Use a local fake HTTP server or injected transport. CI must not depend on the
public internet.

| ID | Test |
|---|---|
| `DS-001` | Duolingo valid response maps only the frozen tags |
| `DS-002` | GitHub user/repos/events responses map counts, language set, and event summary; empty events remain `ready` |
| `DS-003` | LeetCode exact query maps ranking and accepted counts |
| `DS-004` | Invalid handle returns `invalid_input` and transport call count is zero |
| `DS-005` | Timeout returns `timeout`, is retryable, and preserves last success |
| `DS-006` | Oversized, non-JSON, or wrong required shape returns `malformed_response` |
| `DS-007` | 429/5xx and other unexpected HTTP failures return `upstream_error` |
| `DS-008` | Missing public profile returns `unavailable` without creating tags |
| `DS-009` | Fixture is deterministic, contains 20+ behavior rows, and every row is unverified |
| `DS-010` | A write failure rolls back all tag and connection success changes |
| `DS-011` | Raw bodies, headers, tokens, and excluded identity fields never enter SQLite or rendered HTML |
| `DS-012` | Production mode rejects Fixture loading and excludes old Fixture rows from matching |

### 9.2 Product regression tests

Run with the repository virtual environment:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app tests tools
node --test tests/match_flow.test.mjs
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools\harness_cli.py --no-color
git diff --check
```

The optional live smoke probe is run manually, records only bounded metadata,
uses known public sample handles, and is not a deterministic CI gate. A network
failure must not be reported as a product regression.

### 9.3 Visual verification

Capture current desktop and 390x844 views for:

1. connection registry with Public Live, Fixture, and Unavailable cards;
2. a Public Live success and a timeout/error state;
3. self profile provenance labels and long values;
4. L0 match result with no source leakage; and
5. the event-creation phone-verification failure.

Check overflow, focus order, 44px touch targets, reduced motion, bottom-nav
clearance, and no hidden action on an unavailable source.

## 10. Three-minute judge path

The demo uses a resettable database with a pre-synced normalized Public Live
snapshot and explicit Fixture data. A live refresh is optional, not a critical
path.

| Time | Action | Judge-visible proof |
|---:|---|---|
| `0:00–0:25` | Enter the demo account and open My Tags | Public Live and Fixture badges, self-only boundary, last-success time, ownership disclaimer |
| `0:25–0:50` | Open Connections; optionally refresh one public sample | Three live-capable sources, explicit Keep Fixture, unavailable sources disabled; failure preserves snapshot |
| `0:50–1:20` | Start and complete anonymous matching | One percentage, hidden-point count, no profile details or weights |
| `1:20–2:05` | Open chat; send text, use dice/task/unlock, advance demo to L4 | Shared system cards, relationship progress, controlled disclosure, optional contact exchange |
| `2:05–2:40` | Open a formed merchant event and group conversation | 3–10 person anonymous group, real whitelist POI, clearly Fixture benefit and static redemption path |
| `2:40–3:00` | Return to the source ledger | State the truth boundary: live public behavior, Fixture gaps, no account-ownership/deployment/merchant claim |

If networking is unavailable, skip the optional refresh and say that the screen
shows the last successful normalized Public Live snapshot with its timestamp.
Do not switch modes or relabel Fixture data.

## 11. Risks and mitigations

| Risk | User/judge impact | Mitigation |
|---|---|---|
| Duolingo internal/public route changes | Sync can stop working | Strict schema state, preserved last success, honest unavailable/error copy |
| LeetCode GraphQL schema changes | Mapper could fabricate or crash | Exact frozen query, required-shape validation, no generic query builder |
| GitHub unauthenticated rate limit | Demo refresh may return 403 | Pre-sync, bounded reads, no retries, visible upstream/rate-limit state |
| Public handle is not ownership proof | Product could overclaim trust | Fixed `unverified_public_handle` assurance and UI copy |
| Fixture marked verified | Core trust story becomes misleading | Migration to `verified=0`; contract and rendering tests |
| Partial source replacement | Matching sees inconsistent tags | Single transaction; preserve last success on failure |
| Profile identity leaks through tags | Anonymous promise is broken | Excluded-field list, self-only storage, L0 DOM tests |
| Phone verification not enforced | Unsafe offline hosting path | Dedicated offline-safety lane and HTTP test |
| Baseline lacks CSRF/rate limiting/production secrets | Product is not production-ready | Keep as explicit release limitation; make no production claim |
| Screenshot artifacts are mistaken for runtime proof | Submission overstates readiness | Fresh integration screenshots plus separate runtime Harness evidence |
