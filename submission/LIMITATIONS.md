# Limitations and Non-Goals

## Current QA branch limitations

- QA-001 is based on the frozen architecture SHA. The target datasource sync
  route, provenance schema, and CORE-001 internal-candidate-ID fix are not
  assembled here. Their acceptance cases are explicit skips.
- No external API was contacted in this run. Current Public Live availability
  and end-to-end live success are unknown.
- The existing seeded product path can run offline, but the final 21-key Fixture
  vocabulary and provenance labels require integrated-candidate verification.
- Baseline screenshots are references only. QA-001 did not capture final
  desktop or 390x844 runtime evidence.

## Product limitations

- Public handles do not prove account ownership.
- Duolingo uses an internal/public endpoint rather than a claimed official
  stable API. GitHub unauthenticated REST has lower rate limits. LeetCode.com
  depends on the frozen public GraphQL shape.
- Keep live aggregation is not enabled. NetEase, WeRead, Steam, GitHub GraphQL,
  and LeetCode.cn product mapping are unavailable for P0.
- Merchant events, benefits, and manual redemption are synthetic demonstration
  behavior. There is no merchant self-service, payment, settlement, or POS
  integration.
- Demo progression accelerates a multi-day relationship path. It is not
  evidence of retention or natural relationship outcomes.

## Production gaps

The candidate is publicly deployed as a resettable hackathon demo, not a
production release. Vercel provides HTTPS and a managed WSGI runtime, but its
function-local SQLite database is ephemeral. Missing production work includes
durable managed storage and migrations, CSRF protection, rate limiting,
scheduled processing, monitoring, privacy and compliance review, and abuse
operations.

No user, partner, commercial, quality, performance, approval, score, ranking,
or award metric has been measured or claimed.
