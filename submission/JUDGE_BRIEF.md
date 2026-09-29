# RealTags Judge Brief

## The product in one sentence

RealTags is a Chinese anonymous social-matching experience that turns private,
source-attributed behavioral signals into one match percentage, then helps two
people progress through conversation tools and a low-pressure group meal.

## What the demo proves

The local Flask candidate is designed to show one coherent path:

1. a signed-in person views behavioral tags that remain self-only;
2. matching reveals a smoothed percentage and hidden common-point count, not a
   browsable identity card;
3. a direct conversation uses server-generated dice, task, and unlock cards to
   progress from L0 to L4; and
4. a formed restaurant event opens an anonymous group conversation and shows a
   synthetic merchant benefit.

The acceptance suite currently proves the existing offline match, chat, safety,
and event path against a disposable SQLite database. Target datasource and
internal-candidate-ID checks remain assembly-dependent on this QA branch and
are reported as `SKIP`, not `PASS`.

## Truth boundary

| Class | What may be said | What this QA run proves |
|---|---|---|
| Public Live | The target contract permits bounded credential-free reads for Duolingo, GitHub REST, and the exact LeetCode.com public-profile query | No current live success. QA-001 blocked all external network access. The target route/schema is not assembled on this branch. |
| Fixture | Synthetic behavior data supports an offline product demonstration | The existing seeded offline product path completes. The target 21-key provenance contract is still assembly-pending here. |
| Unavailable | Keep live, NetEase, WeRead, Steam, GitHub GraphQL, and LeetCode.cn product mapping are not enabled for P0 | Defined by the frozen contract. Final UI and direct-route behavior require assembled-candidate evidence. |
| Roadmap | Ownership verification, production hardening, partner operations, and real settlement are future work | No roadmap item is claimed as implemented. |

## Why the architecture matters

Routes receive only a source identifier and a validated public handle. A
server-owned registry selects the mode and adapter. Mappers retain only
normalized self-only tags; matching receives no raw profile, handle, response,
or credential. A failed Public Live attempt must preserve the last successful
snapshot and must never silently substitute Fixture data.

## Explicit non-claims

This pack does not claim an official third-party API, account ownership,
authenticated data access, production readiness, durable availability, users,
partners, revenue, conversion, retention, match-quality metrics, judging score,
approval, ranking, or award. The separately evidenced public deployment is a
resettable demo only.
