# UX-001 Judge Journey Evidence

## Scope and truth boundary

Captured on 2026-08-23 from the isolated UX-001 worktree with the Flask development server at `http://127.0.0.1:5127/`, `DEMO_MODE=True`, and a new temporary SQLite database. The capture used only the resettable local Fixture journey; it did not use credentials, external integrations, partner systems, payments, deployment infrastructure, or production data.

This evidence demonstrates the server-rendered judge path and local responsive behavior. It is not evidence of a deployed environment, a currently available Public Live source, a real restaurant partnership, or production readiness.

## Captured path

1. Trust promise and native demo entry.
2. Private verified-tag profile and source boundary.
3. Match ready, searching, and anonymous percentage-only result.
4. L0 anonymous chat tools and a separate Fixture-only progressive-reveal state.
5. Themed restaurant events and merchant Fixture event detail.

## Screenshots

- `home-desktop-1100x900.png`
- `home-mobile-390x844.png`
- `profile-mobile-390x844.png`
- `match-ready-mobile-390x844.png`
- `match-searching-mobile-390x844.png`
- `match-result-mobile-390x844.png`
- `chat-l0-mobile-390x844.png`
- `chat-progress-desktop-1100x900.png`
- `events-mobile-390x844.png`
- `event-detail-desktop-1100x900.png`

## Automated browser observations

The dependency-free Chrome DevTools Protocol runner in `capture_evidence.mjs` recorded the raw observations in `runtime-layout-metrics.json`.

| Check | Result |
| --- | --- |
| Requested viewport | Exact `1100x900` or `390x844` in all 10 captures |
| Initial scroll position | `0` in all captures |
| Horizontal overflow | `0px` in all captures |
| Horizontally clipped primary action | None |
| Primary action covered by the fixed mobile dock | None |
| Broken completed images | None |
| Keyboard focus indicator | Solid `3px` outline with `3px` offset in all captures |

One below-the-fold lazy image in the L0 chat was still pending at the initial top-of-page capture. It was not reported as broken; all completed images had a non-zero natural width.

## Manual visual review

- The guest first screen explains the differentiator and presents the Fixture demo POST action without external instructions.
- The mobile path rail stays within the viewport, remains legible, and does not overlap the fixed navigation.
- The profile source and next-match controls are both fully visible above the mobile dock.
- The match result exposes only the percentage and hidden common-signal count; no hidden identity or algorithm field is displayed.
- The L0 chat keeps the anonymous state visible and exposes native links to icebreaker tools and direct messaging.
- Progressive reveal is explicitly labeled as a Fixture demo control and not production capability evidence.
- The restaurant detail labels the merchant benefit as Fixture evidence and keeps the participation action visible on desktop.

## Verification results

- Focused SSR judge-experience tests: 6 passed.
- Existing Node match-flow tests: 4 passed.
- Full Python unit and workflow suite: 34 passed.
- HTTP workflow harness: 6 of 6 gates passed, including syntax, motion, privacy, and end-to-end journeys.
- UX-001 ownership and required-check gate: passed for all 26 changed artifacts.
- `git diff --check`: passed; Git emitted only the repository's expected Windows line-ending notices.

## Reproduction

Start the app with `DEMO_MODE=True` and a disposable database, launch local Chrome with a DevTools port, then run:

```powershell
node docs\qa\hackathon\ui\capture_evidence.mjs 9229 http://127.0.0.1:5127/ docs\qa\hackathon\ui
```

The capture script exits non-zero if a navigation or expected action fails. Layout observations are preserved in the JSON artifact for review.
