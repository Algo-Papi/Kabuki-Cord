# Kabuki-Cord V2 Animation Roadmap

V2 replaces the app's raster character animations one at a time, with the original asset retained until the replacement is reviewed in a side-by-side playback harness.

## Acceptance Gate

Every replacement must meet all of these requirements:

- stable actor identity, mask markings, costume, proportions, camera, and prop geometry;
- one readable action story with anticipation, contact/impact, follow-through, and recovery;
- legible silhouette at the actual app display size, not only at the 256px source size;
- clean alpha edges, transparent corners, no text/watermarks, and no chroma fringe;
- explicit frame count, sheet width, duration, and CSS contract test;
- side-by-side test page/GIF with the original asset;
- `prefers-reduced-motion` behavior remains intact;
- original production asset is retained until the V2 replacement is accepted.

## Ordered Raster Animation Queue

| Order | Animation | Surface | Status | V2 direction |
| ---: | --- | --- | --- | --- |
| 1 | Discord sign-in blocked | Topbar status | Accepted | Fixed gate, failed key turn, denial impact, recoil, recovery. |
| 2 | Approved reply posting | Topbar operation | Accepted | Fixed mailbox, envelope insertion, flag/confirmation pulse, recovery. |
| 3 | Default scanner/search | Topbar status | Accepted | One magnifier, readable low-left/center/low-right sweep, discovery beat, seamless idle. |
| 4 | Discord server sync | Topbar operation | Accepted | One fixed three-node console, progressive connection, commit button, settle. |
| 5 | Server/channel repair | Topbar operation | Accepted | One control box, diagnose, reconnect, verify, close panel. |
| 6 | History backfill | Topbar operation | Accepted | One archive shelf/ledger, retrieve older pages, index, refile. |
| 7 | Refresh latest messages | Topbar operation | Accepted | One message kiosk, pull newest slip, verify recency, ready. |
| 8 | Refresh local state | Topbar operation | In review | One state console, sweep/update, confirmation, return. |
| 9 | Normal scanner monitor | Monitor scene | Accepted | Fixed moonlit alley plate, consistent actor/magnifier atlas, direct low-left/center/low-right search beats, cyan clue confirmation, and recovery without scene transitions. |
| 10 | Dojo Sweep monitor | Monitor scene | Accepted | Fixed moonlit alley plate, consistent actor/broom atlas, direct sweep beats, restrained dust, crimson evidence reveal, and recovery without full-scene crossfades. |
| 11 | Dry mode transition | Mode overlay | Accepted | Controlled outer-edge dehydration, one continuous dust column, stable ground line, and one residue mound with a mask fragment. |
| 12 | Semi-auto transition | Mode overlay | Accepted | One fixed inner holster and bronze prop, indexed draw, restrained status check, safe lower, re-holster, and guarded recovery. |
| 13 | Full-auto transition | Mode overlay | Accepted | One exaggerated impossible-pocket reveal with locked prop components, readable weight transfer, one charging-handle check, and stable hero hold. |
| 14 | Live-fire transition | Mode overlay | Accepted | One hand-anchored ignition, sole-powered short lift, directional crescent, grounded landing, and complete extinguish/recovery. |
| 15 | Delivery celebration | Monitor overlay | In review | One confirmation receipt, catch, seal check, compact bow, storage, restrained thumbs-up, and stars synchronized to acknowledgement. |

## CSS-Native Motion Review

These effects do not need raster regeneration, but they remain part of the V2 motion pass: launch logo/curtain/materialization, status spinner/alert, mode curtain/fade, monitor scene transitions, toast entry/exit, delivery stars, and all reduced-motion overrides.

## Release Cleanup

After every V2 replacement is accepted, remove superseded runtime references and decide whether to archive or delete the old production sheets and source keyframes. Retire the legacy `scanner-kabuki-spy-story-sheet.png` after both monitor sequences pass review. Keep cleanup separate from visual approval so rollback remains trivial during the one-by-one process.
