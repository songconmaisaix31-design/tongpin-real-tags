# RealTags Persistent Real-User Deployment Specification

## Objective

Publish an isolated HTTPS environment for newly registered users with durable
shared storage, automatic login after registration, and no seeded Demo or
Fixture records. Keep the resettable hackathon demo, the blog, the blog `/tags/`
route, and `tags.davidwang.space` unchanged.

## Deployment isolation

- Deploy only from `songconmaisaix31-design/realtags-real-user-test`; never
  merge, deploy, or push this work through `main`.
- Create a separate Vercel project named `realtags-real-user`.
- Create a separate Turso database named `realtags-real-user-db` in `iad1`,
  colocated with the default Vercel function region.
- Prefer the Vercel-generated hostname for initial validation. If regional DNS
  prevents that hostname from being reached, bind the new
  `app.davidwang.space` hostname only after the isolated project, managed
  database, and rollback target are confirmed.
- Do not relink or reconfigure `realtags-prize-demo` or `realtags-demo`.
- Do not update or delete the apex, `www`, `realtags`, or `tags` DNS records.
- Store secret values only in Vercel's encrypted environment. Never pull them
  into the repository or a local `.env` file.

## Runtime contract

The application keeps SQLite as the single SQL dialect. Local development and
tests use Python's built-in `sqlite3`; the hosted environment uses the official
`turso-serverless` DB-API driver over HTTPS. Both backends retain qmark
parameters, SQLite row access, transactions, `PRAGMA`, JSON1, and the existing
schema.

The hosted project uses these environment variable names:

- `TURSO_DATABASE_URL`: marketplace-injected database URL;
- `TURSO_AUTH_TOKEN`: marketplace-injected database token;
- `FLASK_SECRET_KEY`: independently generated session-signing secret;
- `DEMO_MODE=0`: disables all Demo entry points and seeding;
- `REAL_USER_ONLY=1`: fails startup if Demo or Fixture data is detected; and
- `SESSION_COOKIE_SECURE=1`: limits session cookies to HTTPS.

`DATABASE_PATH` must not be set in the hosted project. If only one Turso
variable is present, startup fails rather than falling back to function-local
SQLite. Real-user-only mode also rejects Demo mode and the development session
key.

## Data boundary

- A fresh production database starts with schema rows only: zero users,
  administrators, tags, connections, events, conversations, and messages.
- Registration stores the submitted profile, hashes the password, establishes
  the signed session, and redirects to `/profile/connections`.
- Duolingo, GitHub REST, and LeetCode.com remain bounded credential-free public
  reads. Keep and every unavailable source remain disabled; failures never load
  Fixture data.
- A public handle proves response provenance, not account ownership.
- No user is marked `phone_verified` without a real verification provider, so
  hosted event creation remains blocked.
- Online QA uses a disposable managed database and reserved random email
  addresses. After persistence verification, delete that entire QA resource
  and create a new final database before the last deployment. No QA account is
  ever written to the final resource.

## Reliability and security controls

- Turso is shared persistent storage; Vercel's `/tmp` directory is never used
  for user records.
- Schema creation and migrations remain idempotent for serverless cold starts.
- Foreign-key enforcement is enabled for every connection.
- Turso's current Python serverless driver does not expose a per-request timeout.
  Vercel therefore applies a 20-second total function duration as the outer
  failure bound. Public datasource requests retain their existing four-second
  timeout and no-retry policy.
- The deployment is a hackathon real-user beta, not a claim of production SLA,
  verified identity, payments, merchant partnerships, CSRF hardening, or abuse
  prevention. Do not solicit sensitive personal data during testing.

## Acceptance criteria

1. Local SQLite tests and a mocked Turso backend test pass without changing the
   existing local database contract.
2. A clean managed database initializes successfully and contains no prohibited
   Demo or Fixture rows.
3. The Vercel production deployment reaches `READY`; `/`, `/register`, and
   representative static assets return HTTP 200, while `POST /demo/login`
   returns HTTP 404.
4. A reserved QA registration persists every submitted field, redirects to
   `/profile/connections`, and remains login-capable in a new HTTP session and
   after a new deployment.
5. Two reserved QA users can match, create exactly one direct conversation,
   exchange persistent messages, report, and block under existing authorization
   rules.
6. Public datasource success or explicit upstream failure is recorded without
   Fixture fallback or secret/raw-response persistence.
7. The disposable QA database is permanently removed after verification. A new
   final resource is connected and deployed without issuing any registration or
   other user-data write.
8. `app.davidwang.space` serves the verified persistent project over HTTPS,
   while the blog, `/tags/`, `tags.davidwang.space`, and
   `realtags.davidwang.space` retain their pre-deployment behavior.
9. The final branch is clean, pushed, and verified against the exact remote SHA.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_deployment tests.test_real_user_environment -v
.\.venv\Scripts\python.exe -m unittest tests.test_e2e_harness.RegisteredUserMatchChatHarness -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q app tests tools run_real_user_test.py
.\harness.cmd
git diff --check
```

Live verification records only HTTP status, bounded response metadata, Vercel
deployment identity, exact Git SHA, database row counts, and DNS targets. It
must never print session cookies, authorization headers, database URLs, tokens,
passwords, or environment values.

## Rollback

Detach only `app.davidwang.space` from `realtags-real-user`, then remove only
the new `app` DNS record. Keep the isolated Turso database until the operator
confirms whether registered-user data must be retained or deleted. No existing
project or DNS surface requires rollback because none is modified.
