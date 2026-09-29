# Persistent Real-User Deployment Receipt

Status: **PASS WITH DOCUMENTED BETA LIMITS**
Verified at: `2026-08-23T08:52:20+08:00`

## Release identity

- Branch: `songconmaisaix31-design/realtags-real-user-test`
- Deployed application commit: `3961b91707ac7398380b6f0f61d3a484cacdeaf4`
- Persistent database implementation commit:
  `2164df5fb965b15c1dc9e885a703d79f1645a085`
- Vercel project: `dwwww/realtags-real-user`
- Vercel project ID: `prj_wdpE2Y4LPRVZAINBbURC33Rjj57s`
- Production deployment ID: `dpl_Jk89xsmbSz5T29VRDnvQcgKAeRCL`
- Generated deployment URL:
  `https://realtags-real-user-5yudddk4w-dwwww.vercel.app`
- Public URL: `https://app.davidwang.space`
- Function region: `iad1`

The receipt itself is excluded from the deployment bundle by `.vercelignore`.
The runtime therefore corresponds exactly to the deployed application commit
above; the branch may contain a later documentation-only receipt commit.

## Persistent store

- Provider: Turso through the Vercel Marketplace integration
- Database name: `realtags-real-user-db`
- Vercel resource ID: `store_tywM9V3uulfX6MPt`
- Provider resource ID: `01a02be8-5d01-739d-9717-aac2c46bfdc6`
- Plan and region: Starter free, `iad1`
- Provisioning state: Available
- Connected environments: Production and Preview

The final database was created after disposable online QA completed. No QA
registration or Fixture load was sent to this final resource. The production
deployment performs schema initialization only until a real user registers.

Configured environment variable names, with values kept encrypted and never
copied into this worktree:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `FLASK_SECRET_KEY`
- `SESSION_COOKIE_SECURE`
- `REAL_USER_ONLY`
- `DEMO_MODE`

## Disposable online QA evidence

The release verifier used two generated users and kept their passwords and
session cookies in process memory only. It ran against disposable Turso
resource `store_ZQU6a6kbEbDIQhBL`, then verified the same records after a second
deployment with new HTTP sessions.

Sanitized verifier output:

```text
PHASE1_READY duolingo=ready github=ready leetcode_com=ready
PHASE2_PERSISTENCE_PASS
DISPOSABLE_QA_DATABASE_READY_FOR_REMOVAL
```

The verified journey covered registration with complete profile data,
automatic login, three Public Live source synchronizations, anonymous matching,
direct-conversation creation, two-way persistent messages, report, block, and
the phone-verification event boundary. The disposable resource was then
permanently deleted. No QA data was migrated to the final resource.

## Interface truth table

| Source | Online result | Product boundary |
| --- | --- | --- |
| Duolingo | Public Live ready | Credential-free public handle lookup |
| GitHub | Public Live ready | Credential-free public REST lookup |
| LeetCode.com | Public Live ready | Credential-free public GraphQL lookup |
| Keep | Unavailable in real-user mode | Sync POST returns `404`; no Fixture data is loaded |

A successful public-handle lookup proves that the upstream response was read;
it does not prove that the signed-in RealTags user owns that external account.

## Final read-only production smoke

No user-data write was issued during the final-resource smoke check.

| Check | Result |
| --- | --- |
| `/` | `200` |
| `/register` | `200` |
| `/static/css/judge-journey.css` | `200` |
| `/static/js/motion.js` | `200` |
| `/static/js/registration-draft.js` | `200` |
| `/static/img/brand-mark.png` | `200` |
| Anonymous `/profile` | `302` to login |
| `POST /demo/login` | `404` |
| Registration link on landing page | Present |
| Demo-login link on landing page | Absent |
| Fixture copy on real-user landing page | Absent |
| Registration draft hook and notice | Present |

Both a reviewed Vercel edge and normal public DNS returned `200` for the public
origin.

## Registration draft persistence

- Registration fields are restored after refresh and history navigation within
  the same browser tab through `sessionStorage`.
- Persistence uses an explicit field allowlist and never stores the password.
- Signed-in pages clear the saved draft so a completed registration does not
  leave profile data behind in the tab.
- Storage parsing is bounded and malformed or unavailable Web Storage fails
  open without blocking registration.
- A clean Chrome session verified refresh restoration. Node behavior tests
  cover the `pagehide` and deferred `pageshow` lifecycle used by browser Back
  and BFCache restoration.

## Domain isolation and regression

- AliDNS record ID: `2091310372422056960`
- Record: `app CNAME cname.vercel-dns.com`
- Status and TTL: Enabled, `600`
- Vercel production alias: `app.davidwang.space`

The generic Vercel CNAME is the currently reachable target from the release
network. Vercel accepted it and HTTPS is live, but continues to recommend its
project-specific CNAME. That recommendation is retained as an operational
follow-up because the preferred target reset TLS connections from the release
region.

Post-deployment regression:

| Existing surface | Result |
| --- | --- |
| `https://davidwang.space/` | `200` |
| `https://davidwang.space/tags/` | `200` |
| `https://tags.davidwang.space/` | `200` |
| `https://realtags.davidwang.space/` | `200` |

No existing apex, `www`, `tags`, or `realtags` record was changed.

## Repository gates

- Python unit and acceptance tests: `91/91` passed.
- Browser behavior Node tests: `8/8` passed, including `4/4` registration-draft
  lifecycle tests.
- Persistent workflow harness: `6/6` passed.
- Python bytecode compilation: passed.
- `git diff --check`: passed.
- Remote branch SHA was verified after publication.

## Remaining limits

- Phone verification has no provider, so real users cannot host events. The
  server keeps that operation blocked instead of fabricating verification.
- Keep has no supported public interface in this release. Its registry entry is
  an unavailable placeholder only; the live route cannot load mock data.
- The Turso driver does not expose a per-request network timeout. Vercel's
  function duration is capped at 20 seconds as the outer execution bound.
- This is a hackathon beta, not a production-SLA service. CSRF protection,
  rate limiting, abuse operations, account recovery, and a formal retention
  policy remain required before broad public acquisition.

## Rollback

1. Detach only `app.davidwang.space` from `dwwww/realtags-real-user`.
2. Delete only AliDNS record `2091310372422056960`.
3. Retain the Turso database until an explicit data-retention decision is made;
   do not delete real-user data as part of DNS rollback.
