# Beijing POIs and AI Match Reliability Specification

Status: **Implemented and locally verified; live AI activation on HOLD**

Date: 2026-08-23

## Product outcome

RealTags dinner discovery uses a useful Beijing restaurant whitelist instead of
three Shanghai placeholders. Matching always leaves the animated search state:
an eligible human remains the first choice, while an empty human pool enters a
clearly labeled AI standby conversation when the provider is available.

## Scope and boundaries

- Replace the restaurant whitelist with eight public Beijing venues.
- Keep restaurant metadata in one application contract and server-only
  coordinates in the location service.
- Expand Demo-only event fixtures so every whitelisted restaurant is visible.
- Preserve the `Fixture` disclosure for synthetic events and merchant benefits.
- Preserve `REAL_USER_ONLY`: no demo user, synthetic event, or merchant benefit
  may be seeded into the real-user database.
- Repair both the server-side candidate race and the legacy-browser form-submit
  path that can otherwise leave the search animation spinning.
- Activate AI standby through Vercel AI Gateway OIDC without using the credential
  previously pasted into chat.

Public venue existence is not evidence of a commercial relationship,
reservation inventory, pricing, opening hours, or RealTags partnership.

## POI contract

The coordinates below use the same GCJ-02 source and are retained server-side
only for approximate distance sorting.

| ID | Venue | Address | Latitude | Longitude | Public source |
| --- | --- | --- | ---: | ---: | --- |
| `poi_001` | 四季民福烤鸭店(故宫店) | 北京市东城区南池子大街11号 | 39.914525 | 116.402873 | [Amap](https://ditu.amap.com/place/B0FFG9V1R9) |
| `poi_002` | 胡大饭馆24h(簋街总店) | 北京市东城区东直门内大街233号 | 39.941174 | 116.419240 | [Amap](https://ditu.amap.com/place/B0FFF9XSVV) |
| `poi_003` | 聚宝源(牛街创始店) | 北京市西城区牛街5-2号 | 39.886721 | 116.363329 | [Amap](https://ditu.amap.com/place/B000A67FB7) |
| `poi_004` | 京A Taproom·隆福寺店 | 北京市东城区钱粮胡同38号隆福寺北里19号楼 | 39.927286 | 116.413522 | [Amap](https://ditu.amap.com/place/B0FFLIXJFZ) |
| `poi_005` | 南门涮肉(天坛店) | 北京市东城区永定门东街东里13号楼1-2号 | 39.871734 | 116.405566 | [Amap](https://ditu.amap.com/place/B0LAOSJQIU) |
| `poi_006` | 全聚德(北京和平门店) | 北京市西城区前门西大街14号楼 | 39.899292 | 116.385072 | [Amap](https://ditu.amap.com/place/B000A87JDG) |
| `poi_007` | 牛街清真满恒記(平安里西大街店) | 北京市西城区平安里西大街14号 | 39.932207 | 116.367609 | [Amap](https://ditu.amap.com/place/B000A9ONPA) |
| `poi_008` | 浩海火烧云傣家菜(东安市场店) | 北京市东城区王府井大街138号北京apm六层L619 | 39.914089 | 116.412053 | [Amap](https://ditu.amap.com/place/B0KKP1XJCP) |

Sources were checked on 2026-08-23. Venue metadata can drift and should be
revalidated before claiming current hours or availability.

## Acceptance criteria

1. `POIS` contains exactly the eight Beijing records above and no Shanghai
   restaurant placeholder.
2. Demo initialization creates or upgrades eight future event fixtures, one per
   POI, without duplicating existing group conversations or memberships.
3. The formed `event_002` group flow remains intact for the judge path.
4. `REAL_USER_ONLY=1` and `DEMO_MODE=0` create no seeded events or Fixture data.
5. Nearby filtering reports Beijing, sorts all eight POIs by approximate
   distance, and does not persist request coordinates.
6. A valid human candidate always takes precedence over AI standby.
7. If the selected human disappears during the search animation, the server
   immediately continues with another valid human or redirects to AI standby
   when the human pool is empty.
8. The animated page submits within 3 seconds in browsers with `requestSubmit`
   and legacy WebViews that expose only native `submit`.
9. Request-scoped Vercel OIDC can authenticate only the exact
   `https://ai-gateway.vercel.sh/v1/chat/completions` endpoint. It is never
   persisted or forwarded to a custom base URL.
10. No secret enters source control, documentation, logs, browser storage,
    test evidence, or project memory.

## Risks and controls

| Risk | Control |
| --- | --- |
| Venue details become stale | Keep dated public source links and avoid claims about live hours or inventory. |
| A public venue looks like a partner | Retain Fixture labeling and state that listing is not partnership evidence. |
| Search animation never exits | Test both DOM submission APIs and recover from candidate invalidation server-side. |
| Platform credential is forwarded to an attacker | Allow OIDC only for the exact Vercel AI Gateway completion URL. |
| AI is mistaken for a person | Preserve persistent `AI standby / not a real person` disclosure and human precedence. |
| Real-user database receives demo data | Keep existing startup contamination checks and add an explicit zero-event assertion. |

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_nearby_events tests.test_ai_fallback -v
node --test tests/match_flow.test.mjs
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/*.test.mjs
.\harness.cmd
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe tools/verify_live_ai_deployment.py https://<isolated-qa-domain>
git diff --check
```

Runtime verification must cover the Beijing event list on desktop and 390x844
mobile layouts, one empty-human-pool transition, one controlled AI reply, and a
post-deploy contamination check that does not read or print credentials.

## Local verification result

- Python: 110 tests passed.
- JavaScript: 11 tests passed.
- Harness: 6/6 gates passed.
- Visual: ten route captures passed at 1100x900 and 390x844 with zero page
  horizontal overflow and zero broken images. A full mobile event-list check
  confirmed eight rows, no title or venue overflow, and no title/venue overlap.

## Live activation result

- The isolated runtime probe verified registration, the empty-human-pool AI
  standby transition, truthful AI disclosure, user-message persistence, and
  safe provider-failure copy.
- Vercel AI Gateway rejected the request-scoped OIDC call with HTTP 403,
  recorded only as the bounded code `permission_denied`. A real model reply is
  therefore not verified.
- This AI runtime candidate was not promoted. The concurrent avatar deployment
  remained current at the production domain. AI activation stays on hold until
  the account-level Gateway permission boundary is resolved and the controlled
  reply probe passes.
