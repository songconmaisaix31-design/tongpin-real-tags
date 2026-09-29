# API Interface Availability Validation

- Generated: `2026-08-22T14:56:27.730553Z`
- Source SHA-256: `88A3CA61F6539F82637B362510CF61D955134CF2952DC4D3D38184736F4909FF`
- Interfaces: `37`
- Credentials read: `false`
- Raw response bodies stored: `false`
- Redirects followed: `false`
- TLS verification: `enabled`

## Summary

| Label | Count |
|---|---:|
| `AUTH_REQUIRED` | 7 |
| `AVAILABLE` | 6 |
| `CONTRACT_INVALID` | 1 |
| `INCONCLUSIVE_SAFE_PROBE` | 1 |
| `NOT_TESTED_PREREQUISITE` | 3 |
| `PREREQUISITE_MISSING` | 11 |
| `REQUEST_REJECTED` | 3 |
| `RESOURCE_NOT_FOUND` | 2 |
| `ROUTE_NOT_FOUND` | 3 |

## Results

| Platform | Contract ID | Documented | Probe | HTTP | Latency | Result |
|---|---|---:|---:|---:|---:|---|
| Duolingo | `duolingo.users` | `GET` | `GET` | 200 | 2061 ms | `AVAILABLE` |
| LeetCode CN | `leetcode.cn.graphql` | `POST` | `POST` | 200 | 462 ms | `AVAILABLE` |
| LeetCode COM | `leetcode.com.graphql` | `POST` | `POST` | 200 | 1512 ms | `AVAILABLE` |
| Keep | `keep.login` | `POST` | `OPTIONS` | 200 | 438 ms | `INCONCLUSIVE_SAFE_PROBE` |
| Keep | `keep.stats_detail` | `GET` | `GET` | 401 | 27 ms | `AUTH_REQUIRED` |
| Keep | `keep.stats_records` | `GET` | `GET` | 404 | 35 ms | `ROUTE_NOT_FOUND` |
| Keep | `keep.running_log` | `GET` | `GET` | 404 | 26 ms | `RESOURCE_NOT_FOUND` |
| Keep | `keep.cycling_log` | `GET` | `GET` | 404 | 29 ms | `RESOURCE_NOT_FOUND` |
| Steam | `steam.resolve_vanity` | `GET` | `GET` | 400 | 1038 ms | `REQUEST_REJECTED` |
| Steam | `steam.player_summaries` | `GET` | `GET` | 400 | 763 ms | `REQUEST_REJECTED` |
| Steam | `steam.owned_games` | `GET` | `GET` | 401 | 294 ms | `AUTH_REQUIRED` |
| Steam | `steam.recent_games` | `GET` | `GET` | 403 | 286 ms | `AUTH_REQUIRED` |
| Steam | `steam.level` | `GET` | `GET` | 403 | 654 ms | `AUTH_REQUIRED` |
| Steam | `steam.badges` | `GET` | `GET` | 403 | 690 ms | `AUTH_REQUIRED` |
| Steam | `steam.achievements` | `GET` | `GET` | 400 | 465 ms | `REQUEST_REJECTED` |
| GitHub | `github.user` | `GET` | `GET` | 200 | 902 ms | `AVAILABLE` |
| GitHub | `github.repos` | `GET` | `GET` | 200 | 546 ms | `AVAILABLE` |
| GitHub | `github.events` | `GET` | `GET` | 200 | 336 ms | `AVAILABLE` |
| GitHub | `github.graphql` | `POST` | `POST` | 403 | 118 ms | `AUTH_REQUIRED` |
| NetEase Cloud Music local service | `netease.login_cellphone` | `POST` | `OPTIONS` | - | 4125 ms | `PREREQUISITE_MISSING` |
| NetEase Cloud Music local service | `netease.qr_key` | `POST` | `OPTIONS` | - | 4094 ms | `PREREQUISITE_MISSING` |
| NetEase Cloud Music local service | `netease.qr_create` | `POST` | `OPTIONS` | - | 4092 ms | `PREREQUISITE_MISSING` |
| NetEase Cloud Music local service | `netease.qr_check_invalid_port` | `POST` | `NOT_EXECUTED` | - | - | `CONTRACT_INVALID` |
| NetEase Cloud Music local service | `netease.user_detail` | `POST` | `OPTIONS` | - | 4123 ms | `PREREQUISITE_MISSING` |
| NetEase Cloud Music local service | `netease.user_record` | `POST` | `OPTIONS` | - | 4092 ms | `PREREQUISITE_MISSING` |
| NetEase Cloud Music local service | `netease.user_playlist` | `POST` | `OPTIONS` | - | 4087 ms | `PREREQUISITE_MISSING` |
| NetEase Cloud Music local service | `netease.daily_checkin` | `POST` | `OPTIONS` | - | 4068 ms | `PREREQUISITE_MISSING` |
| NetEase Cloud Music local service | `netease.user_level` | `POST` | `OPTIONS` | - | 4082 ms | `PREREQUISITE_MISSING` |
| WeRead MCP | `weread.mcp_reading_stats` | `MCP_TOOL` | `NOT_EXECUTED` | - | - | `NOT_TESTED_PREREQUISITE` |
| WeRead MCP | `weread.mcp_shelf` | `MCP_TOOL` | `NOT_EXECUTED` | - | - | `NOT_TESTED_PREREQUISITE` |
| WeRead MCP | `weread.mcp_notes` | `MCP_TOOL` | `NOT_EXECUTED` | - | - | `NOT_TESTED_PREREQUISITE` |
| WeRead assumed local HTTP | `weread.local_reading_stats` | `GET` | `GET` | - | 4125 ms | `PREREQUISITE_MISSING` |
| WeRead assumed local HTTP | `weread.local_shelf` | `GET` | `GET` | - | 4105 ms | `PREREQUISITE_MISSING` |
| WeRead assumed local HTTP | `weread.local_notes` | `GET` | `GET` | - | 4112 ms | `PREREQUISITE_MISSING` |
| WeRead internal API | `weread.internal_reading_stats` | `GET` | `GET` | 404 | 464 ms | `ROUTE_NOT_FOUND` |
| WeRead internal API | `weread.internal_shelf` | `GET` | `GET` | 401 | 35 ms | `AUTH_REQUIRED` |
| WeRead internal API | `weread.internal_notes` | `GET` | `GET` | 404 | 33 ms | `ROUTE_NOT_FOUND` |

## Interpretation

- `AVAILABLE` means a safe request succeeded with the expected response shape.
- `AUTH_REQUIRED` proves route reachability, not authenticated business success.
- `INCONCLUSIVE_SAFE_PROBE` means only a non-mutating handshake was executed.
- `PREREQUISITE_MISSING` means the documented local service was not running.
- MCP tools require a configured MCP server and are not equivalent to local HTTP paths.
