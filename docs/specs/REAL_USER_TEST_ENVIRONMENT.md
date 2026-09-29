# Real User Test Environment Specification

## Objective

Provide an isolated local environment for testing newly registered people with
persistent SQLite data and no seeded demo or Fixture records. A successful
registration must persist every submitted profile field, establish the session,
and redirect directly to the public-data connection step.

## Scope

- Run only from the `realtags-real-user-test` worktree and its dedicated branch.
- Store runtime data in the ignored `instance/real-user-test.sqlite3` file.
- Bind the Flask development server to `127.0.0.1:5001` with debug and reload
  disabled.
- Force `DEMO_MODE=False` independently of shell environment variables.
- Keep Duolingo, GitHub, and LeetCode public-profile reads available. Keep and
  every other Fixture-only source remain unavailable.
- Keep the existing Vercel demo, DNS, blog, `/tags/`, and `tags.davidwang.space`
  unchanged.

## Non-goals

- This local Flask server is not a public production deployment.
- This change does not provision a third-party database account or billing plan.
- This change does not make a public handle proof of account ownership.
- This change does not delete Fixture support from the separate hackathon demo.
- This change does not fake phone verification. Real users may browse events,
  but creating an offline event remains blocked until a real phone-verification
  provider and consent flow exist.

## Runtime invariants

1. The runtime database path is explicit and cannot fall back to the demo
   database or `DATABASE_PATH`.
2. The application never seeds demo users, the demo administrator, Fixture tags,
   Fixture connections, or demo events in this mode.
3. Startup fails closed if the selected database already contains a demo user,
   the demo administrator, or Fixture-backed tags/connections.
4. The session signing key is generated in memory for each local server process;
   it is never printed or written to disk. A restart requires users to log in
   again but does not remove their persisted account data.
5. The real-user database is ignored by Git and must never be committed.
6. Test accounts and test messages are created only in disposable temporary
   databases, never in `instance/real-user-test.sqlite3`.

## Acceptance criteria

1. First startup creates the dedicated schema with zero users, administrators,
   tags, external connections, events, conversations, and messages.
2. `GET /` and `GET /register` return HTTP 200; demo login is absent and
   `POST /demo/login` returns HTTP 404.
3. A valid registration stores the normalized email, password hash, anonymous
   alias, birth year, gender, match preference, city, purposes, interests, MBTI,
   zodiac, and schedule with `is_demo=0`.
4. The registration response redirects to `/profile/connections`, and the same
   client session is authenticated immediately.
5. The production-mode connection page does not offer a Fixture sync action;
   direct Fixture sync attempts return HTTP 404.
6. Two newly registered users can match, start exactly one direct conversation,
   exchange persistent messages, report, and block according to the existing
   authorization rules.
7. A newly registered user can browse the empty real event directory, while an
   event-creation attempt is rejected with the phone-verification requirement.
   No account is silently marked verified.
8. Focused tests, the full unit suite, syntax compilation, the HTTP workflow
   harness, and `git diff --check` pass from the final clean commit.

## Risks and controls

- **Accidental demo contamination:** fixed database path, forced production mode,
  and startup contamination checks.
- **Accidental network exposure:** loopback-only binding and no debug server.
- **Session invalidation on restart:** deliberate in-memory key; persistent user
  records remain available through normal login.
- **External API availability:** bounded credential-free reads may fail because
  of upstream status or rate limits; failures must remain explicit and must not
  fall back to Fixture data.
- **Public persistence:** Vercel function-local SQLite is ephemeral. A future
  public real-user environment requires an explicitly selected managed database
  and a verified storage migration before DNS or deployment changes.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_real_user_environment -v
.\.venv\Scripts\python.exe -m unittest tests.test_e2e_harness.RegisteredUserMatchChatHarness -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q app tests run_real_user_test.py
.\harness.cmd
git diff --check
```
