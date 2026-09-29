# API Interface Catalog and Validation Status

## Document Control

| Item | Value |
|---|---|
| Scope | External HTTP and MCP contracts only: 34 archive-defined contracts plus 3 concrete workspace-supplemented probes |
| Source archive | `C:\Users\DW\Downloads\All_API_Interfaces_2026-08-22.zip` |
| Source SHA-256 | `88A3CA61F6539F82637B362510CF61D955134CF2952DC4D3D38184736F4909FF` |
| Evidence timestamp | `2026-08-22T14:56:27.730553Z` |
| Document updated | `2026-08-23` |
| Contract count | 37 validation items: 34 HTTP contracts and 3 MCP tools |
| Provenance split | 34 archive-defined contracts; 3 workspace supplements (`duolingo.users`, LeetCode CN GraphQL, LeetCode COM GraphQL) |
| Credentials used | No |
| Raw response bodies stored | No |
| Primary evidence | [`reports/api-interface-validation-2026-08-22.json`](reports/api-interface-validation-2026-08-22.json) |
| Human-readable evidence | [`reports/api-interface-validation-2026-08-22.md`](reports/api-interface-validation-2026-08-22.md) |

The archive itself defines 34 concrete external contracts: Keep 5, Steam 7,
GitHub 4, NetEase 9, and WeRead 9. It names Duolingo and LeetCode capabilities
but does not define their three concrete remote paths; those are workspace
supplements and are labeled accordingly below. Internal TypeScript interfaces
such as `IDataSourceAdapter` are programming contracts and are outside this
external HTTP/MCP catalog.

The status values below are a dated validation snapshot, not a claim about
current upstream uptime. Only `AVAILABLE` means that a safe sample functional
request returned the expected 2xx response shape. It does not prove private
data access, complete field mappings, every parameter variant, or production
rate-limit behavior. Authentication errors, validation errors, and
`OPTIONS 200` results do not prove authenticated business success.

## Executive Summary

| Status | Count | Functional meaning |
|---|---:|---|
| `AVAILABLE` | 6 | A safe functional request returned the expected 2xx response shape. |
| `AUTH_REQUIRED` | 7 | The route responded but authenticated functionality was not verified. |
| `REQUEST_REJECTED` | 3 | The route responded but rejected missing or synthetic input. |
| `INCONCLUSIVE_SAFE_PROBE` | 1 | Only a non-mutating handshake was performed. |
| `RESOURCE_NOT_FOUND` | 2 | A synthetic resource ID was absent; the route may still be valid. |
| `ROUTE_NOT_FOUND` | 3 | The documented fixed/list route returned 404. |
| `PREREQUISITE_MISSING` | 11 | A required localhost service was not running. |
| `NOT_TESTED_PREREQUISITE` | 3 | No MCP server was configured, so the tool was not called. |
| `CONTRACT_INVALID` | 1 | The documented target is invalid and no request was sent. |

### Platform Roll-up

| Platform | Contracts | Observed state |
|---|---:|---|
| Duolingo | 1 | 1 available public read |
| LeetCode | 2 | 2 available read-only GraphQL probes |
| Keep | 5 | 1 auth required, 1 inconclusive login handshake, 1 missing route, 2 synthetic resources missing |
| Steam | 7 | All routes responded; 4 require auth and 3 rejected missing/synthetic input |
| GitHub | 4 | 3 available public REST reads and 1 authenticated GraphQL route |
| NetEase Cloud Music | 9 | 8 blocked by missing localhost service and 1 invalid port contract |
| WeRead | 9 | 3 MCP tools not configured, 3 localhost assumptions unavailable, 1 internal route auth required, 2 internal routes missing |

## Validation Boundary

- The probe did not read a credential file, environment secret, cookie,
  password, private key, API key, or bearer token.
- TLS verification stayed enabled, redirects were not followed, each response
  read was capped at 4096 bytes, and raw response bodies were not persisted.
- Read-only GraphQL `POST` requests executed only `query`, never `mutation`.
- Login, QR session creation, check-in, and other state-changing operations
  were replaced with `OPTIONS` or not executed.
- `Functionally verified: Yes` is assigned only to `AVAILABLE` results.
- Response metadata is bounded evidence, not a complete response schema.
- The 37 validation items cover every concrete external route/tool in the
  archive plus the three workspace-supplemented probes. Capability-only prose
  without a route, method, tool name, and parameters is not counted as a
  testable contract.

## 1. Duolingo

Platform notes: this is a public, credential-free profile read in the current
implementation. The archive defines a Duolingo adapter but omits a concrete
remote path; the workspace implementation supplies the tested endpoint. Treat
it as an upstream internal/public endpoint rather than a formal stable API.

| ID | Capability and contract | Inputs, auth, and expected response | Validation and current status |
|---|---|---|---|
| `duolingo.users` | Workspace supplement. Get a public user profile and language/streak data. `GET https://www.duolingo.com/2017-06-30/users?username={username}` | Input: `username`. Auth: none for a public profile. Expected JSON object with top-level `users`; the first item carries courses, XP, streak, and streak-date data. | Probe: `GET`, fixture `username=duo`. `AVAILABLE`; HTTP 200; 2061 ms; JSON object with `users`. Functionally verified: **Yes**, for public data only. Source: archive capability declaration in `DataSourceAdapter_Interface.md:203-230`; concrete path from `adapters/duolingo_adapter.py:24-39`. |

## 2. LeetCode

Platform notes: public profile reads are available without a cookie in the
tested environment. LeetCode CN and COM use different GraphQL schemas and must
not share one production query. The availability probe used only `__typename`;
profile and progress field mappings still require their site-specific queries.

| ID | Capability and contract | Inputs, auth, and expected response | Validation and current status |
|---|---|---|---|
| `leetcode.cn.graphql` | Workspace supplement. Read LeetCode CN public profile and question progress. `POST https://leetcode.cn/graphql` | JSON body: GraphQL `query` plus variables such as `userSlug`. Auth: none for public profile data. Expected top-level `data`; production schema uses `userProfilePublicProfile` and `userProfileUserQuestionProgress`. | Probe: read-only `POST` with `query AvailabilityProbe { __typename }`. `AVAILABLE`; HTTP 200; 462 ms; JSON object with `data`. Functionally verified: **Yes** for endpoint/query transport, not the complete profile mapping. Source: archive datasource declaration in `DataSourceAdapter_Interface.md:16`; concrete path from `adapters/leetcode_adapter.py:34-51,79-96`. |
| `leetcode.com.graphql` | Workspace supplement. Read LeetCode COM public profile, accepted submissions, and activity. `POST https://leetcode.com/graphql` | JSON body: GraphQL `query` plus variables such as `username`. Auth: none for public profile data. Expected top-level `data`; production schema uses `matchedUser`. | Probe: read-only `POST` with `query AvailabilityProbe { __typename }`. `AVAILABLE`; HTTP 200; 1512 ms; JSON object with `data`. Functionally verified: **Yes** for endpoint/query transport, not the complete profile mapping. Source: archive datasource declaration in `DataSourceAdapter_Interface.md:16`; concrete path from `adapters/leetcode_adapter.py:22-31,79-96`. |

## 3. Keep

Platform notes: the archive uses reverse-engineered mobile API contracts. The
official browser sign-in entry is `https://keep.com/kts/home`, which redirects
to Keep unified login on `open.gotokeep.com`; a browser session is not evidence
that the bearer-authenticated mobile API is authorized. No authenticated Keep
API report exists yet, so no personal-data interface is marked available.

| ID | Capability and contract | Inputs, auth, and expected response | Validation and current status |
|---|---|---|---|
| `keep.login` | Create a mobile API session. `POST https://api.gotokeep.com/v1.1/users/login` | Sensitive body: `mobile`, `password`, `countryCode`; source example also uses `loginType`. Expected success envelope: `ok=true`, `data.token`, and optional user ID. This legacy password flow is not approved for the current safe probe. | Probe: `OPTIONS` only. `INCONCLUSIVE_SAFE_PROBE`; HTTP 200; 438 ms; empty body. Functionally verified: **No**. The result proves only a safe handshake, not login success. Source: `Keep_API_Integration_Example.py:24,61-103`. |
| `keep.stats_detail` | Read aggregate sport statistics. `GET https://api.gotokeep.com/pd/v3/stats/detail` | Query: `dateUnit`, `type`, optional `lastDate`. Auth: `Authorization: Bearer <token>`. Expected Keep envelope with `ok` and `data`. | Baseline probe: credential-free `GET ?dateUnit=all&type=running`. `AUTH_REQUIRED`; HTTP 401; 27 ms; error code `100010`; envelope keys `data,errorCode,now,ok,text,version`. Functionally verified: **No**. Only `running` was represented in the dated JSON; `cycling`, `lastDate`, and authenticated success were not independently validated. Source: `Keep_API_Integration_Example.py:25,105-135`. |
| `keep.stats_records` | Intended paginated sport-record list. `GET https://api.gotokeep.com/pd/v3/stats/records` | Query: `page`, `limit`, `type`. Auth: bearer token. Intended response: record list used for activity history. | Probe: `GET ?page=1&limit=1&type=running`. `ROUTE_NOT_FOUND`; HTTP 404; 35 ms. Functionally verified: **No**. Remove from the active contract unless authenticated evidence disproves the 404. Source: `Keep_API_Integration_Example.py:26,137-166`. |
| `keep.running_log` | Read one running activity detail. `GET https://api.gotokeep.com/pd/v3/runninglog/{run_id}` | Path: a real `run_id`. Auth: bearer token. Expected response: one run's detail; it may contain sensitive route and health data. | Probe: `GET` with synthetic ID `0`. `RESOURCE_NOT_FOUND`; HTTP 404; 26 ms. Functionally verified: **No**. The result does not prove the route is absent; a valid privacy-safe test resource is required. Source: `Keep_API_Integration_Example.py:27,168-190`. |
| `keep.cycling_log` | Read one cycling activity detail. `GET https://api.gotokeep.com/pd/v3/cyclinglog/{ride_id}` | Path: a real `ride_id`. Auth: bearer token. Expected response: one ride's detail; it may contain sensitive route and health data. | Probe: `GET` with synthetic ID `0`. `RESOURCE_NOT_FOUND`; HTTP 404; 29 ms. Functionally verified: **No**. The result does not prove the route is absent; a valid privacy-safe test resource is required. Source: `Keep_API_Integration_Example.py:28,172-190`. |

Authenticated aggregate testing, if resumed, must use
[`keep_authenticated_probe.py`](keep_authenticated_probe.py). It accepts a
temporary bearer token only through hidden TTY input and writes no personal
response fields. Its 20 offline security tests passed, but live authenticated
evidence remains pending.

## 4. Steam Web API

Platform notes: all seven official-domain routes returned an HTTP response.
The test intentionally omitted a Web API key, so none is functionally verified.
Production requests require `key`; user-data endpoints also require a valid
SteamID64, and private profiles can suppress library or activity data.

| ID | Capability and contract | Inputs, auth, and expected response | Validation and current status |
|---|---|---|---|
| `steam.resolve_vanity` | Resolve a vanity name to SteamID64. `GET https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/` | Query: `key`, `vanityurl`. Expected `response.success` and `response.steamid`. | Probe omitted `key` and used `vanityurl=valve`. `REQUEST_REJECTED`; HTTP 400; 1038 ms. Functionally verified: **No**; route reachable. Source: `V2_DataSources_Full_Research.md:44-48`. |
| `steam.player_summaries` | Read player identity, avatar, visibility, presence, and account metadata. `GET https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/` | Query: `key`, comma-separated `steamids`. Expected `response.players[]`. | Probe omitted `key` and used `steamids=0`. `REQUEST_REJECTED`; HTTP 400; 763 ms. Functionally verified: **No**; route reachable. Source: `V2_DataSources_Full_Research.md:51-88`. |
| `steam.owned_games` | Read game library and playtime. `GET https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/` | Query: `key`, `steamid`, `include_appinfo`, `include_played_free_games`. Expected `response.game_count` and `response.games[]`. Profile game details must be public. | Probe omitted `key` and used synthetic SteamID `0`. `AUTH_REQUIRED`; HTTP 401; 294 ms. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:90-132`. |
| `steam.recent_games` | Read recently played games and recent playtime. `GET https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/` | Query: `key`, `steamid`, optional `count`. Expected recent games list. | Probe omitted `key`, used `steamid=0&count=1`. `AUTH_REQUIRED`; HTTP 403; 286 ms. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:134-145`. |
| `steam.level` | Read Steam community level. `GET https://api.steampowered.com/IPlayerService/GetSteamLevel/v1/` | Query: `key`, `steamid`. Expected player level metadata. | Probe omitted `key` and used `steamid=0`. `AUTH_REQUIRED`; HTTP 403; 654 ms. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:147-153`. |
| `steam.badges` | Read badges, XP, and level progress. `GET https://api.steampowered.com/IPlayerService/GetBadges/v1/` | Query: `key`, `steamid`. Expected `response.badges[]`, `player_xp`, and level fields. | Probe omitted `key` and used `steamid=0`. `AUTH_REQUIRED`; HTTP 403; 690 ms. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:154-183`. |
| `steam.achievements` | Read per-game player achievements. `GET https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/` | Query: `key`, `steamid`, `appid`. Expected per-achievement completion data. The game and user statistics must be visible. | Probe omitted `key`, used `steamid=0&appid=730`. `REQUEST_REJECTED`; HTTP 400; 465 ms. Functionally verified: **No**; route reachable. Source: `V2_DataSources_Full_Research.md:185-197`. |

## 5. GitHub

Platform notes: public REST reads worked without authentication. Unauthenticated
REST usage has a lower rate limit; private resources require an appropriately
scoped token. GraphQL requires authentication even for the safe `__typename`
query used by the validation probe.

| ID | Capability and contract | Inputs, auth, and expected response | Validation and current status |
|---|---|---|---|
| `github.user` | Read a public user profile. `GET https://api.github.com/users/{username}` | Path: `username`. Auth: optional for public data. Expected object includes login, profile links, public counts, and timestamps. | Probe: `GET /users/octocat`. `AVAILABLE`; HTTP 200; 902 ms; expected JSON object. Functionally verified: **Yes**, for public data. Source: `V2_DataSources_Full_Research.md:377-424`. |
| `github.repos` | List a user's public owner repositories. `GET https://api.github.com/users/{username}/repos` | Path: `username`; query: `sort`, `type`, `per_page`, optional page. Auth: optional for public data. Expected repository array. | Probe: `GET /users/octocat/repos?sort=updated&type=owner&per_page=1`. `AVAILABLE`; HTTP 200; 546 ms. The JSON list exceeded the 4096-byte evidence cap and was marked truncated; no raw body was stored. Functionally verified: **Yes**. Source: `V2_DataSources_Full_Research.md:426-442`. |
| `github.events` | List recent public events. `GET https://api.github.com/users/{username}/events` | Path: `username`; query: `per_page`, optional page. Auth: optional for public events. Expected event array such as Push/Create/Watch/Fork events. | Probe: `GET /users/octocat/events?per_page=1`. `AVAILABLE`; HTTP 200; 336 ms; JSON list. Functionally verified: **Yes**. Source: `V2_DataSources_Full_Research.md:444-461`. |
| `github.graphql` | Query profile, repositories, contributions, and organizations through GraphQL. `POST https://api.github.com/graphql` | JSON body: `query` and `variables`. Auth: bearer token required. Expected top-level `data` or bounded GraphQL errors. | Probe: read-only `POST` with `query AvailabilityProbe { __typename }`, no token. `AUTH_REQUIRED`; HTTP 403; 118 ms; response keys `documentation_url,message`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:463-520`. |

## 6. NetEase Cloud Music Local Service

Platform notes: these are contracts for a separately deployed, unofficial
localhost reverse-API service, not direct NetEase public APIs. No service was
listening on port 3000 during validation. The source dependency is archived;
do not describe it as an active stable production dependency without selecting
and auditing a maintained replacement. Login and check-in were not executed.
The research list documents `POST` for user detail, record, playlist, check-in,
and level, while its example code uses `GET` for at least detail, record, and
level. Because the safe probe used `OPTIONS`, the real method contract remains
unresolved and must be corrected against the selected server version.

| ID | Capability and contract | Inputs, auth, and expected response | Validation and current status |
|---|---|---|---|
| `netease.login_cellphone` | Create a session with phone/password. `POST http://localhost:3000/login/cellphone` | Sensitive body: `phone`, `password`. Expected local-service response contains profile and session cookie. This flow is not approved for a main account. | Probe: `OPTIONS`; localhost unavailable after 4125 ms. `PREREQUISITE_MISSING`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:731-739`. |
| `netease.qr_key` | Create a QR-login transaction key. `POST http://localhost:3000/login/qr/key` | No user data initially; expected unique key. The operation creates login state. | Probe: `OPTIONS`; localhost unavailable after 4094 ms. `PREREQUISITE_MISSING`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:741-743`. |
| `netease.qr_create` | Generate a QR code from a login key. `POST http://localhost:3000/login/qr/create` | Query: sensitive `key`, optional `qrimg=true`. Expected QR URL/image metadata. Requires `qr_key` first. | Probe: `OPTIONS` with synthetic redacted key; localhost unavailable after 4092 ms. `PREREQUISITE_MISSING`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:744`. |
| `netease.qr_check_invalid_port` | Poll QR-login state. Source contract: `POST http://localhost:300300/login/qr/check` | Query: sensitive `key`. Expected scan/authorization state and eventual session cookie. | Not executed. `CONTRACT_INVALID`: port `300300` exceeds the valid TCP port range. Functionally verified: **No**. Correct the source contract to a valid selected service port, then revalidate. Source: `V2_DataSources_Full_Research.md:745-746`. |
| `netease.user_detail` | Read user profile. `POST http://localhost:3000/user/detail` | Query: `uid`; auth: session cookie from login. Expected `code` and `profile` with identity, account, membership, and social metadata. | Probe: `OPTIONS` with `uid=0`; localhost unavailable after 4123 ms. `PREREQUISITE_MISSING`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:753-758`. |
| `netease.user_record` | Read recent or all listening history. `POST http://localhost:3000/user/record` | Query: `uid`, `type` (`0` weekly or `1` all in the source); auth: session cookie. Expected `weekData` or `allData` song/play records. | Probe: `OPTIONS` with `uid=0&type=1`; localhost unavailable after 4092 ms. `PREREQUISITE_MISSING`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:796-805`. |
| `netease.user_playlist` | Read a user's playlists. `POST http://localhost:3000/user/playlist` | Query: `uid`, optional `limit`; auth: session cookie. Expected playlist collection and metadata. | Probe: `OPTIONS` with `uid=0&limit=1`; localhost unavailable after 4087 ms. `PREREQUISITE_MISSING`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:851-856`. |
| `netease.daily_checkin` | Perform a daily check-in. `POST http://localhost:3000/daily_checkin` | Query: `type`; auth: session cookie. This is state-changing and can alter account state. | Probe: `OPTIONS` only; localhost unavailable after 4068 ms. `PREREQUISITE_MISSING`. Functionally verified: **No**. The business operation was deliberately not executed. Source: `V2_DataSources_Full_Research.md:862-867`. |
| `netease.user_level` | Read account level/progress. `POST http://localhost:3000/user/level` | Source query: `uid`; auth: session cookie. Expected user level and progress metadata. | Probe: `OPTIONS` with `uid=0`; localhost unavailable after 4082 ms. `PREREQUISITE_MISSING`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:869-871`. |

## 7. WeRead MCP Tools

Platform notes: the official WeRead Skill landing page, an npm package named
`weread-mcp`, assumed localhost HTTP routes, and WeRead internal HTTP routes are
separate products/transports. The source archive describes the npm package as
official, but current package metadata identifies it as unofficial. None of
these contracts may be used as evidence for another.

| ID | Capability and contract | Inputs, auth, and expected response | Validation and current status |
|---|---|---|---|
| `weread.mcp_reading_stats` | Read aggregate reading statistics. MCP tool `weread_reading_stats` (`mcp://weread/weread_reading_stats`). | Input: none; operates on the authorized account. Prerequisite: configured MCP server and scoped WeRead API key/session. Expected time totals, reading days, favorite categories/time/authors, and most-read-book summary. | Not executed because no configured MCP server was in scope. `NOT_TESTED_PREREQUISITE`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:1095-1138`. |
| `weread.mcp_shelf` | Read the authorized account's shelf. MCP tool `weread_shelf` (`mcp://weread/weread_shelf`). | Input: optional `limit` (source default 50). Expected books with title, author, progress, and category. Requires configured MCP server/auth. | Not executed. `NOT_TESTED_PREREQUISITE`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:1140-1158`. |
| `weread.mcp_notes` | Read notes/highlights. MCP tool `weread_notes` (`mcp://weread/weread_notes`). | Input: optional `bookId`; omission requests an account-wide summary in the source contract. Expected highlight, thought/review, and bookmark metadata. Requires configured MCP server/auth. | Not executed. `NOT_TESTED_PREREQUISITE`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:1160-1176`. |

## 8. WeRead Assumed Local HTTP Façade

These routes appear only as example-code assumptions for a service on port
3001. They are not MCP transport contracts and no such local service was
running during validation.

| ID | Capability and contract | Inputs, auth, and expected response | Validation and current status |
|---|---|---|---|
| `weread.local_reading_stats` | Assumed local reading statistics. `GET http://localhost:3001/reading/stats` | Source example sends an optional `X-API-Key`. Expected aggregate reading-statistics object. | Probe: `GET`; localhost unavailable after 4125 ms. `PREREQUISITE_MISSING`. Functionally verified: **No**; not evidence about the MCP tool. Source: `V2_DataSources_Full_Research.md:1197-1213`. |
| `weread.local_shelf` | Assumed local shelf. `GET http://localhost:3001/shelf` | Query: optional `limit`; source example sends optional `X-API-Key`. Expected book list or object containing `books`. | Probe: `GET ?limit=1`; localhost unavailable after 4105 ms. `PREREQUISITE_MISSING`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:1215-1229`. |
| `weread.local_notes` | Assumed local notes. `GET http://localhost:3001/notes` | Query: optional `bookId`; source example sends optional `X-API-Key`. Expected note list or object containing `notes`. | Probe: `GET`; localhost unavailable after 4112 ms. `PREREQUISITE_MISSING`. Functionally verified: **No**. Source: `V2_DataSources_Full_Research.md:1231-1247`. |

## 9. WeRead Internal HTTP

These are undocumented internal API paths. They require browser/session
credentials where still present and can change without notice. The validation
did not send a cookie.

| ID | Capability and contract | Inputs, auth, and expected response | Validation and current status |
|---|---|---|---|
| `weread.internal_reading_stats` | Intended internal reading statistics. `GET https://i.weread.qq.com/user/reading/statistics` | Auth: WeRead browser/session cookie. Expected aggregate reading statistics per the source adapter assumption. | Probe: credential-free `GET`. `ROUTE_NOT_FOUND`; HTTP 404; 464 ms; empty body. Functionally verified: **No**. Retire this path unless later authenticated evidence disproves the result. Source: `V2_DataSources_Full_Research.md:1204-1213`. |
| `weread.internal_shelf` | Internal shelf synchronization. `GET https://i.weread.qq.com/shelf/sync` | Query: optional `limit`; auth: WeRead browser/session cookie. Expected book list/object. | Probe: `GET ?limit=1` without cookie. `AUTH_REQUIRED`; HTTP 401; 35 ms; error code `-2010`; keys `errcode,errlog,errmsg`. Functionally verified: **No**; route reachable. Source: `V2_DataSources_Full_Research.md:1215-1229`. |
| `weread.internal_notes` | Intended internal note list. `GET https://i.weread.qq.com/note/getList` | Query: optional `bookId`; auth: WeRead browser/session cookie. Expected notes/highlights list. | Probe: credential-free `GET`. `ROUTE_NOT_FOUND`; HTTP 404; 33 ms; empty body. Functionally verified: **No**. Retire this path unless later authenticated evidence disproves the result. Source: `V2_DataSources_Full_Research.md:1231-1247`. |

### WeRead Capability Descriptions Without Testable Contracts

The source capability table also mentions bookstore search, book details,
public book reviews, and book recommendations. It provides no stable tool name,
HTTP path, method, or parameter contract for these capabilities, so they are
documented as research ideas only and are not included in the 37 validation
items. They must not be reported as tested or available.

## Recommended Disposition

| Decision | Contracts |
|---|---|
| Use for a credential-free MVP | `duolingo.users`, `leetcode.cn.graphql`, `leetcode.com.graphql`, `github.user`, `github.repos`, `github.events` |
| Validate with scoped authentication before use | `keep.stats_detail`, all seven Steam contracts, `github.graphql`, `weread.internal_shelf` |
| Remove or correct now | `keep.stats_records`, `weread.internal_reading_stats`, `weread.internal_notes`, `netease.qr_check_invalid_port` |
| Requires a real but privacy-safe resource ID | `keep.running_log`, `keep.cycling_log` |
| Requires a selected and running local service | Eight valid-port NetEase contracts and three WeRead localhost assumptions |
| Requires an explicitly configured MCP server | Three WeRead MCP tools |
| Never classify from the current handshake alone | `keep.login` |
| Do not execute in availability testing | `netease.daily_checkin` and all login/session-creation operations |

## Reproduction

```powershell
python -m unittest tests.test_endpoint_probe -v
python endpoint_probe.py `
  --json reports\api-interface-validation-2026-08-22.json `
  --markdown reports\api-interface-validation-2026-08-22.md
```

Re-running the live probe updates network evidence. Do not overwrite the dated
2026-08-22 evidence unless the new run is written to a new dated report first.
