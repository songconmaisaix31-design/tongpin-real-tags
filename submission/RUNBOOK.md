# Clean-Worktree Demo and Acceptance Runbook

This runbook is Windows PowerShell-first and requires no credentials. Run it in
a new worktree at the exact candidate SHA. Do not use the protected `main`
checkout.

## 1. Confirm a clean candidate

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse --verify "@{upstream}"
```

Expected: no modified or untracked files and identical local/upstream SHAs.
Record the SHA in the evidence packet.

## 2. Create the local Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The repository requires Flask and the Python standard library. Do not create or
load an `.env` file. Do not provide API keys, tokens, cookies, passwords, or
authorization headers.

## 3. Run deterministic verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/acceptance -v
.\.venv\Scripts\python.exe tools/hackathon_acceptance.py --dry-run
.\.venv\Scripts\python.exe tools/hackathon_acceptance.py --require-assembly
.\.venv\Scripts\python.exe -m compileall -q app tests tools
node --test tests/match_flow.test.mjs
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/harness_cli.py --no-color
git diff --check
```

Acceptance execution blocks outbound sockets and creates temporary databases.
For the final integrated candidate, `--require-assembly` must end with
`FAIL=0 SKIP=0`. A `SKIP` on a worker branch is an explicit missing dependency,
not release evidence.

## 4. Start a fresh local demo

A clean worktree has no `instance/realtags.sqlite3`. Start the app once:

```powershell
.\.venv\Scripts\python.exe run.py
```

Open `http://127.0.0.1:5000`. The local server creates an ignored SQLite file
and deterministic demo seed. No credential is needed. Keep public networking
disabled or simply avoid every Public Live refresh; refresh is optional and is
not part of the critical path.

## 5. Reproduce the judge path

1. Use **Enter demo** and open **My Tags**.
2. Confirm the self-only boundary and truthful source labels.
3. Open **Connections**; verify Public Live, Fixture, and Unavailable are
   visibly distinct. Do not refresh a public profile while offline.
4. Start anonymous matching, complete it, and confirm only a smoothed
   percentage and hidden-point count appear.
5. Open the conversation, send text, use dice, task, and unlock, then use the
   demo-only progression control until L4.
6. Open the formed merchant event and its anonymous group conversation.
7. Confirm the merchant benefit is visibly Fixture.
8. Return to the source ledger and state the evidence boundary from
   [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).

Stop the server with `Ctrl+C`. The generated `instance/` directory is ignored
and is not submission evidence.

## 6. Record evidence

Record command, UTC timestamp, exact SHA, exit code, PASS/FAIL/SKIP counts, and
any named skip reason. Public smoke evidence, if separately authorized and run
by the integration owner, must record only bounded metadata and must never
store raw profiles or credentials.

Do not use baseline screenshots as proof of the final candidate. Capture fresh
desktop and 390x844 views only after all deterministic gates pass.
