# UX-001 Judge Journey Plan

## Objective

Make the shortest truthful judge journey understandable and operable without presenter instructions:

1. understand the verified-behavior trust promise;
2. enter the resettable demo;
3. inspect private Public Live or Fixture tag provenance;
4. receive one percentage-only anonymous match;
5. use the L0 chat tools and demo-only progressive reveal;
6. reach a themed public-restaurant event.

The implementation remains Flask/Jinja2 SSR. JavaScript may enhance motion and orientation, but every navigation and form action must retain a native no-JavaScript path.

## Visual source of truth

- `brand-spec.md` defines the current brutalist tokens, hierarchy, focus, motion, and mobile rules.
- `docs/design-reference-brutalist.png` supplies visual direction only.
- The existing templates and `app/static/qa/` images establish the pre-change implementation baseline; they are not post-change runtime evidence.
- `docs/acceptance/P0_ACCEPTANCE_MATRIX.md` defines the truth boundary for Public Live, Fixture, unavailable, and roadmap claims.

## Completion criteria

- The guest home hero names the differentiator, shows the privacy boundary, and presents a dominant demo entry above the fold.
- Signed-in pages provide a visible, ordered demo route from private tags through match, chat/reveal, and events without adding client-side routing.
- Match result copy and markup expose only the display percentage and hidden-point count; no candidate identity, raw score, weight, handle, or source detail is rendered.
- Primary actions, navigation, forms, chat tools, reveal controls, and event actions remain visible and usable at 1100px and 390x844.
- The audited pages have no horizontal document overflow, clipped primary action, overlapping navigation, or missing keyboard focus indicator.
- Reduced-motion and no-JavaScript behavior remain usable.
- Focused SSR tests, the existing Node match-flow tests, the full unit suite, syntax checks, the HTTP harness, and `git diff --check` pass.
- Fresh 1100px desktop and 390x844 mobile screenshots are captured when the local runtime/browser supports it; otherwise the exact limitation is recorded.

## Constraints and risks

- Only UX-001 owned templates, static files, focused tests, and this QA directory may change.
- Data-source and domain-service behavior belongs to other tracks. UX work must consume current projections without changing their contracts.
- Existing direct-chat projections include level-gated fields. Templates must not infer or reveal fields beyond the server projection.
- Fixed mobile navigation can obscure composers or actions; every signed-in page needs dock clearance.
- Hard shadows and long Chinese copy can create width overflow; mobile styles must constrain width without weakening the brand hierarchy.
- Demo acceleration is Fixture evidence and must remain explicitly labeled as non-production behavior.

## Tasks

1. Add focused SSR assertions for the judge entry, ordered journey orientation, privacy copy, native form/link fallbacks, and required static accessibility safeguards.
2. Add a compact server-rendered journey rail to signed-in pages and strengthen home/demo copy without changing routes or form contracts.
3. Polish match, chat/reveal, profile, and event action hierarchy with minimal template changes.
4. Add a final scoped CSS layer for responsive containment, focus visibility, mobile dock clearance, and reduced motion.
5. Run the application with an isolated demo database, audit the complete path at both target viewports, and record screenshot evidence and limitations.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_judge_experience.py" -v
node --test tests/match_flow.test.mjs
.\.venv\Scripts\python.exe -m compileall -q app tests tools
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools\harness_cli.py --no-color
python scripts\gate.py check --run-checks
git diff --check
```
