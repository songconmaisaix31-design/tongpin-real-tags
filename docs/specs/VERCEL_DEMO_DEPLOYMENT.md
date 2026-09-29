# RealTags Vercel Demo Deployment Specification

## Objective

Publish the hackathon build as a resettable HTTPS demo at
`realtags.davidwang.space` without changing the existing blog, the blog's
`/tags` route, or `tags.davidwang.space`.

## Isolation invariants

- Deploy from `deploy/realtags-davidwang-space`, never from or into `main`.
- Create a new Vercel project named `realtags-prize-demo`.
- Add only the `realtags` DNS record under `davidwang.space`.
- Do not update or delete apex, `www`, or `tags` DNS records.
- Do not relink, redeploy, or reconfigure the existing `realtags-demo` project.
- Store secret values only in the deployment provider's encrypted environment.

## Runtime design

The versioned `vercel.json` selects Vercel's `flask` framework preset, and
Vercel invokes the top-level `index.py` WSGI application. The build command
copies only `app/static/css`, `app/static/img`, and `app/static/js` to
`public/static`, which is Vercel's supported static-asset boundary. QA evidence
is intentionally excluded.

The deployment uses these environment variable names:

- `FLASK_SECRET_KEY`: generated deployment secret;
- `DEMO_MODE=1`: enables the synthetic judge journey;
- `DATABASE_PATH=/tmp/realtags.sqlite3`: writable function-local database; and
- `SESSION_COOKIE_SECURE=1`: HTTPS-only session cookies.

An explicit application `DATABASE` setting takes precedence over
`DATABASE_PATH`, preserving isolated test and local configurations.

## Data and reliability boundary

Vercel Functions do not provide persistent shared SQLite storage. The database
can reset between function instances or deployments. This is acceptable only
for the synthetic hackathon demo. It is not production durability evidence and
must not be represented as a persistent user service.

## Acceptance criteria

1. Unit, acceptance, and deployment tests pass from the deployment worktree.
2. The Vercel production deployment reaches `READY` in the new project.
3. The root page and representative CSS, JavaScript, and image assets return
   HTTP 200 from the production URL.
4. The demo-entry journey reaches an authenticated product screen.
5. `realtags.davidwang.space` resolves to the new Vercel project over HTTPS.
6. `davidwang.space`, `www.davidwang.space`, `davidwang.space/tags/`, and
   `tags.davidwang.space` retain their pre-deployment DNS and HTTP behavior.
7. No secret, cookie, credential file, or local database is committed.

## Rollback

Remove only the `realtags` DNS record and detach only
`realtags.davidwang.space` from `realtags-prize-demo`. The preserved blog and
`tags` records require no rollback because this deployment never changes them.
