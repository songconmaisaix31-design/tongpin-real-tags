# Public Demo Deployment Receipt

## Deployment identity

- Verified at: `2026-08-23T06:11:57+08:00`
- Application branch: `deploy/realtags-davidwang-space`
- Application commit: `32642a861ff49dc7cf778ecc1754a554719f2d76`
- Vercel project: `dwwww/realtags-prize-demo`
- Vercel project ID: `prj_n3AqlfIYQICxn9nOSIsNbLVdp7Ov`
- Ready production deployment: `dpl_DYePMLuA4RRF1NQhTvdkFEAvhKok`
- Public URL: <https://realtags.davidwang.space>

The deployment uses Vercel's Flask framework preset, the top-level `index.py`
WSGI entrypoint, and build-generated `public/static` runtime assets. Secret
values were written directly to Vercel's encrypted environment and were not
read, printed, or committed. The configured variable names are
`FLASK_SECRET_KEY`, `DEMO_MODE`, `DATABASE_PATH`, and
`SESSION_COOKIE_SECURE`.

## DNS isolation receipt

Only one AliDNS record was added:

| RR | Type | Value | TTL | Record ID |
| --- | --- | --- | ---: | --- |
| `realtags` | `CNAME` | `9df316820fdcbb4c.vercel-dns-017.com` | 600 | `2091285074485882880` |

The pre-existing records were unchanged after deployment:

| Surface | Preserved DNS or route | Verified behavior |
| --- | --- | --- |
| Blog apex | Four A records: `185.199.108.153` through `185.199.111.153` | `https://davidwang.space/` returned HTTP 200 |
| Blog `www` | `songconmaisaix31-design.github.io` | Existing HTTP 301 behavior remained |
| Blog tags route | Same GitHub Pages apex | `https://davidwang.space/tags/` returned HTTP 200 |
| Existing tags app | `9ac6b2035aca735c.vercel-dns-017.com` | `https://tags.davidwang.space/` returned HTTP 200 |

No apex, `www`, or `tags` record was updated or deleted. The existing Vercel
project `realtags-demo` was not relinked, reconfigured, or redeployed.

## Runtime verification

| Check | Result |
| --- | --- |
| Vercel production state | `READY` |
| `/` | HTTP 200, HTML |
| `/static/css/judge-journey.css` | HTTP 200, CSS |
| `/static/js/motion.js` | HTTP 200, JavaScript |
| `/static/img/brand-mark.png` | HTTP 200, PNG |
| `POST /demo/login` | Redirected to `/profile`; final HTTP 200 with signed-in shell |
| `/profile`, `/profile/connections`, `/matches`, `/conversations`, `/events` | HTTP 200 with signed-in shell in one in-memory demo session |

The request client retained its demo session in memory without printing or
persisting cookie contents.

## Truth boundary and rollback

Vercel Functions do not provide persistent shared SQLite storage. This build
writes to `/tmp/realtags.sqlite3`, so state can reset between function instances
or deployments. The receipt proves a resettable hackathon demo, not production
durability, service-level availability, user traction, or commercial operation.

Rollback is isolated: remove only AliDNS record `2091285074485882880`, then
detach only `realtags.davidwang.space` from `realtags-prize-demo`. The blog and
existing tags surfaces require no rollback because they were never changed.
