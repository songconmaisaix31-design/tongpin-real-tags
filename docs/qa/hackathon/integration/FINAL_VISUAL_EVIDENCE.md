# INT-001 Final Visual Evidence

## Capture boundary

These screenshots were captured at `2026-08-22T20:43:04Z` from the assembled
integration worktree with `DEMO_MODE=1`, an explicit non-secret test key, a new
local SQLite database, and a dedicated temporary headless-browser profile. The
database and profile were removed after capture. No UX-001 screenshot was
copied or reused.

Reproduce the capture from the repository root:

```powershell
.\docs\qa\hackathon\integration\capture_final.ps1
```

The script refuses to overwrite an existing `instance/realtags.sqlite3`,
requires unused local server and DevTools ports, and writes only this
integration evidence directory.

## Current screenshots

| State | Viewport | Artifact |
| --- | --- | --- |
| Guest home | 1100x900 | [`home-desktop-1100x900.png`](screenshots/home-desktop-1100x900.png) |
| Guest home | 390x844 | [`home-mobile-390x844.png`](screenshots/home-mobile-390x844.png) |
| Private profile | 390x844 | [`profile-mobile-390x844.png`](screenshots/profile-mobile-390x844.png) |
| Match ready | 390x844 | [`match-ready-mobile-390x844.png`](screenshots/match-ready-mobile-390x844.png) |
| Match searching | 390x844 | [`match-searching-mobile-390x844.png`](screenshots/match-searching-mobile-390x844.png) |
| Anonymous match result | 390x844 | [`match-result-mobile-390x844.png`](screenshots/match-result-mobile-390x844.png) |
| L0 conversation | 390x844 | [`chat-l0-mobile-390x844.png`](screenshots/chat-l0-mobile-390x844.png) |
| Progressed conversation | 1100x900 | [`chat-progress-desktop-1100x900.png`](screenshots/chat-progress-desktop-1100x900.png) |
| Event list | 390x844 | [`events-mobile-390x844.png`](screenshots/events-mobile-390x844.png) |
| Event detail | 1100x900 | [`event-detail-desktop-1100x900.png`](screenshots/event-detail-desktop-1100x900.png) |

Machine-readable measurements are in
[`runtime-layout-metrics.json`](screenshots/runtime-layout-metrics.json).

## Visual smoke result

- All 10 viewport measurements match the requested dimensions.
- Horizontal overflow, broken images, horizontally clipped primary actions,
  and primary-action/mobile-dock overlap are zero in every state. These metrics
  do not imply that an action is inside the initial viewport.
- Keyboard navigation reached the primary action with a visible 3px solid
  focus outline in every state.
- Manual review of the home, private profile, match result, L0 conversation,
  progressed conversation, event list, and event detail found no visible text
  overlap, critical truncation, or unintended image crop.
- The mobile primary CTA is below the initial 844px viewport in match ready
  (`top=964`), match searching (`top=1541`), and match result (`top=1092`). A
  judge must scroll to reach those actions. This is a truthful demo usability
  limitation; the actions remain horizontally unclipped and are not covered by
  the mobile dock.
- The L0 mobile DOM reports one pending image: a below-viewport
  `loading="lazy"` conversation-tool illustration. It is not visible in the
  captured viewport, is not reported broken, and loads in the progressed
  desktop state. This receipt does not mislabel an untriggered lazy load as a
  completed image request.

## Truth boundary

The images prove the current local Fixture journey and responsive rendering of
this assembled candidate. They are not proof of Public Live response data,
deployment, production readiness, account ownership, merchant participation,
or commercial results.
