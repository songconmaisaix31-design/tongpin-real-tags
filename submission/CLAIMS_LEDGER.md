# Claims Ledger

## Current QA-001 evidence

| Evidence class | Candidate claim | QA-001 status | Promotion requirement |
|---|---|---|---|
| Local runtime | The existing Flask baseline completes the tested offline match, conversation, safety, and formed-event path using a disposable database | **Supported on the architecture base** by the current offline acceptance run | Rerun on the exact integrated clean HEAD |
| Public Live | Duolingo, GitHub REST, and the exact LeetCode.com mapping can load bounded public behavior data | **Not current-run verified.** QA-001 made no external request, and its target sync route/schema checks are assembly-pending | Deterministic mapper tests, assembled HTTP/UI checks, and a separate current bounded credential-free smoke record |
| Fixture | The final offline demo account contains the frozen 21-key synthetic vocabulary with truthful provenance | **Assembly-pending.** The existing offline product path works, but the target provenance/count assertion is skipped on this branch | `tools/hackathon_acceptance.py --require-assembly` passes on the integrated candidate |
| Unavailable | Unsupported or unsafe sources show no active P0 sync action | **Contract-defined; assembly-pending in QA-001** | Integrated route/UI acceptance passes with zero side effects |
| Public demo | The resettable integrated candidate is reachable at `https://realtags.davidwang.space` | **Supported** by the isolated deployment receipt | Preserve HTTP, DNS-isolation, and signed-in-path evidence |
| Roadmap | Ownership verification, production release, and real commercial operations may be explored later | **Not implemented evidence** | Separate product decision, implementation, security review, and current proof |

## Claims allowed only after the exact final gate passes

- "The local Flask candidate completed the tested anonymous match, chat, and
  event workflows against an isolated database."
- "The candidate visibly distinguishes Public Live, Fixture, and Unavailable
  source states."
- "The offline demo uses deterministic Fixture content and does not require
  credentials."
- "A failed Public Live attempt preserves the prior snapshot and does not
  silently substitute Fixture data."
- "Merchant benefits in the demonstration are Fixtures."

Each statement must cite the exact candidate SHA and its current command or
artifact evidence. A passing QA worker branch alone does not promote an
assembly-dependent statement.

## Prohibited present-tense claims

- Official Duolingo or LeetCode API integration.
- Authenticated, ownership-verified, or identity-verified public handles.
- Live Keep, Steam, NetEase, WeRead, GitHub GraphQL, or LeetCode.cn product data.
- Persistently operated, production-ready, fully secure, or compliant for launch.
- Real merchant onboarding, settlement, payment, POS integration, or coupon
  redemption.
- Any user count, partner count, conversion, retention, revenue, match-quality
  metric, benchmark score, judging score, approval, ranking, award, or recovery
  result.
- A screenshot, frozen contract, or test source file described as current
  runtime proof.
