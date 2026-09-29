# INT-001 Final Claims Ledger

This ledger applies to the assembled candidate on
`songconmaisaix31-design/trk-integration-int-001` and its isolated deployment
branch `deploy/realtags-davidwang-space`. It supersedes QA-stage
assembly-pending language for this candidate but does not rewrite worker-owned
evidence. Deployment evidence was added later and is recorded separately in
[`PUBLIC_DEMO_DEPLOYMENT_RECEIPT.md`](PUBLIC_DEMO_DEPLOYMENT_RECEIPT.md).

## Supported claims

| Evidence class | Supported statement | Current evidence boundary |
| --- | --- | --- |
| Local runtime | The Flask candidate completes the tested anonymous match, conversation, safety, and event workflows against an isolated SQLite database. | Python discovery, strict acceptance, and the six-stage HTTP harness pass on the assembled candidate. This is local runtime evidence, not deployment evidence. |
| Public Live | The current bounded credential-free smoke received mapper-accepted public responses from Duolingo, GitHub REST, and the exact LeetCode.com query. | The smoke records only source, state, normalized tag count, mapping version, and elapsed time. Public handles remain `unverified_public_handle`; availability can change. |
| Fixture | The offline judge path uses deterministic synthetic tags, including the required 21-key vocabulary, with `verified=false`, `self_only`, and `synthetic_fixture` provenance. | Strict acceptance passed, repeated Keep Fixture loads were deterministic, the profile labels Fixture provenance, and `DEMO_MODE=0` rejected Fixture creation. Fixture is not current account data. |
| Unavailable | NetEase, WeRead, Steam, GitHub GraphQL, and LeetCode.cn have no enabled P0 sync action; Keep live aggregation is not enabled and Keep is Fixture-only. | Integrated route and UI acceptance passed, including forged-route and no-side-effect checks. |
| Public demo | The resettable hackathon build is reachable at `https://realtags.davidwang.space`. | The deployment receipt records Vercel `READY`, DNS isolation, HTTP 200 assets, and the signed-in demo path. Function-local SQLite is ephemeral and provides no production durability claim. |
| Roadmap | Ownership verification, official or authenticated integrations, production operations, merchant operations, payments, and real commercial outcomes require future work. | These items have no present-tense implementation or result claim. |

## Current sanitized Public Live receipt

Captured at `2026-08-22T20:44:37Z` only after TCP reachability was confirmed.
Each checked-in adapter used its four-second timeout and bounded response size.
No raw profile, normalized tag value, credential, cookie, token, or
authorization header was recorded.

| Source | State | Normalized tags | Mapping version | Elapsed |
| --- | --- | ---: | --- | ---: |
| Duolingo | `ready` | 5 | `duolingo-public-v1` | 1326 ms |
| GitHub REST | `ready` | 4 | `github-rest-public-v1` | 1741 ms |
| LeetCode.com | `ready` | 4 | `leetcode-com-public-v1` | 489 ms |

This proves current response provenance and mapper acceptance for bounded
public samples. It does not prove account ownership, identity, authentication,
an official API, or future availability. The separate deployment receipt proves
only the resettable end-to-end demo surface.

## Prohibited claims

- Official Duolingo or LeetCode API integration.
- Authenticated, ownership-verified, or identity-verified public handles.
- Live Keep, NetEase, WeRead, Steam, GitHub GraphQL, or LeetCode.cn product data.
- Persistent production operation, production readiness, security/compliance
  completion, or service-level availability.
- Real merchant onboarding, settlement, payment, POS integration, or coupon
  redemption.
- Users, partners, conversion, retention, revenue, match quality, benchmark,
  judge score, approval, ranking, award, or recovery results.
- Screenshots as proof of backend behavior, deployment, or third-party data.

## Judge-safe summary

RealTags demonstrates a resettable public Fixture journey from private
behavioral tags through anonymous matching, progressive chat, and restaurant
events. Public Live adapters are a bounded public-response capability with
unverified handles; unsupported sources remain visibly unavailable; persistent
production and commercial operation remain Roadmap.
