# Real User Test Environment Receipt

Recorded on 2026-08-23 at 06:57 +08:00 from the isolated
`realtags-real-user-test` worktree.

## Runtime receipt

- Listener: `127.0.0.1:5001` only.
- Database: ignored `instance/real-user-test.sqlite3`.
- `GET /`: HTTP 200.
- `GET /register`: HTTP 200.
- `POST /demo/login`: HTTP 404.
- Persistent runtime counts after startup: zero users, administrators, tags,
  external connections, events, conversations, and messages.
- No test account was written to the persistent runtime database.

## Automated verification

| Check | Result |
| --- | --- |
| Real-user environment focused tests | 3 passed |
| Two-new-user match/chat production-mode harness | 1 passed |
| Full Python discovery | 86 passed |
| HTTP workflow harness | 6/6 gates passed |
| Python compilation | passed |
| Whitespace diff check | passed |

The registration test proves normalized persistence of every submitted field,
password hashing, `is_demo=0`, immediate session establishment, and redirect to
`/profile/connections`. It also proves that Fixture sync is unavailable and
that an unverified user cannot create an offline event. All synthetic test
records live in disposable temporary databases.

## Bounded Public Live receipt

Each adapter made a single credential-free read using its checked-in four-second
timeout and response-size limits. The receipt records no raw response, handle,
tag value, cookie, token, credential, or authorization header.

| Source | State | Normalized tags | Mapping version | Elapsed |
| --- | --- | ---: | --- | ---: |
| Duolingo | `ready` | 5 | `duolingo-public-v1` | 1179 ms |
| GitHub REST | `ready` | 4 | `github-rest-public-v1` | 1658 ms |
| LeetCode.com | `ready` | 4 | `leetcode-com-public-v1` | 417 ms |

These results prove current public response provenance and mapper acceptance for
the bounded samples only. They do not prove account ownership, authentication,
official API status, future availability, or service-level reliability.

## Honest limitations

- Keep remains unavailable because safe authenticated access was not verified;
  this environment never substitutes Fixture data.
- Real phone verification is absent, so offline-event creation remains blocked
  instead of silently setting a fake verification flag.
- The existing Vercel demo uses ephemeral SQLite. No claim of public persistent
  real-user storage is made by this receipt.
