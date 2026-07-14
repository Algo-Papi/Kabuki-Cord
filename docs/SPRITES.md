# Kabuki-Cord Sprite Inventory

This is the replacement checklist for animated and sprite-like visual assets currently used by the app.

## Active Animated Sprites

| Asset | Purpose | Used by |
| --- | --- | --- |
| `src/nhi_zues/web/assets/monitor_spy_frames/frame_000.webp` through `frame_005.webp` | Original Scanner Monitor sequence: six independently generated alley scenes held for five seconds each with full-scene transition overlays. Retained for comparison and rollback. | V2 comparison harness only |
| `src/nhi_zues/web/assets/monitor_spy_v2_frames/frame_000.webp` through `frame_007.webp` | Scanner Monitor V2 loop: one fixed alley plate and one consistent actor/magnifier atlas with direct alert, raise, low-left, center, low-right, cyan discovery, confirmation, and recovery beats. | `src/nhi_zues/web/monitor.html`, `src/nhi_zues/web/monitor.js`, `src/nhi_zues/web/monitor.css` |
| `src/nhi_zues/web/assets/monitor_dojo_sweep_frames/frame_000.webp` through `frame_047.webp` | Original Dojo Sweep loop. Five independently generated full scenes are crossfaded and augmented with procedural dust. Retained for comparison and rollback. | V2 comparison harness only |
| `src/nhi_zues/web/assets/monitor_dojo_sweep_v2_frames/frame_000.webp` through `frame_007.webp` | Dojo Sweep V2 monitor loop: one fixed empty alley plate plus one consistent actor/broom atlas, with direct ready, wind-up, contact, sweep, follow-through, evidence-reveal, and recovery frames. No full-scene interpolation or opacity crossfade. | `src/nhi_zues/web/monitor.html`, `src/nhi_zues/web/monitor.js`, `src/nhi_zues/web/monitor.css` |
| `src/nhi_zues/web/assets/scanner-kabuki-sheet.png` | Upgraded 16-frame, 256px-source default topbar operation/status sprite: the actor dances through a searching loop with an integrated magnifying glass. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-v2-sheet.png` | Experimental 8-frame default scanner replacement: one fixed magnifier, controlled low-left/center/low-right sweep, cyan clue beat, confirmation nod, and baseline-stable recovery. The original sheet is retained for comparison. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-sync-sheet.png` | Upgraded 11-frame, 256px-source topbar animation while syncing Discord servers/channels: the actor unrolls a channel scroll, connects cyan cords between server lanterns, stamps the sync, and settles back to idle. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-sync-v2-sheet.png` | Experimental 8-frame sync replacement: one fixed three-socket shrine console, node-by-node cyan state changes, brass commit beat, confirmation nod, and stable recovery. The original sheet is retained for comparison. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-repair-sheet.png` | Upgraded 10-frame, 256px-source topbar animation while repairing/reloading a server channel list: the actor inspects a broken shrine-like channel control box, crouches, opens the panel, wrenches, reconnects glowing cyan cables, stamps the fix, and returns to idle. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-repair-v2-sheet.png` | Experimental 8-frame repair replacement: one fixed cabinet and failed indicator, diagnosis, one hinged access panel, one loose plug/socket reconnection, verification button, three-light success state, and stable recovery. The original sheet is retained for comparison. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-backfill-sheet.png` | Upgraded 8-frame, 256px-source topbar animation while backfilling older channel history: the actor pulls a ledger from a wooden archive shelf, indexes it, files it back, and settles into a loop. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-backfill-v2-sheet.png` | Experimental 8-frame backfill replacement: one fixed four-slot archive cabinet, one violet ledger visibly extracted from and returned to its slot, backward page review, brass index tab, ready light, and stable recovery. The original sheet is retained for comparison. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-latest-sheet.png` | Upgraded 10-frame, 256px-source topbar animation while refreshing latest visible messages: the actor checks a Japanese message kiosk, pulls a fresh glowing scroll, clears stale slips, verifies a clock/timeline dial, stamps the current scroll, and returns to idle. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-latest-v2-sheet.png` | Experimental 8-frame latest-message replacement: one fixed kiosk, one cyan-edged message visibly extracted from and returned to its slot, one brass recency dial, one ready lamp, and stable recovery. The original sheet is retained for comparison. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-refresh-sheet.png` | Upgraded 10-frame, 256px-source topbar animation while refreshing local app state: the actor runs a shrine-like app-state console through pull, sweep, spin, burst, stamp, and ready poses. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-refresh-v2-sheet.png` | Experimental 8-frame local-state replacement: one fixed console and lever, progressive three-bar state sweep, commit button, compact status-core pulse, healthy confirmation, and stable recovery. The original sheet is retained for comparison. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-posting-sheet.png` | Upgraded 10-frame, 256px-source topbar animation while posting an approved reply: the actor writes, seals, dashes to a message box, posts the envelope, and confirms delivery. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-posting-v2-sheet.png` | Experimental 8-frame posting replacement: one fixed mailbox, envelope insertion with clear body-weight transfer, brass flag/confirmation pulse, and a compact recovery loop. The original sheet is retained for comparison. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-discord-blocked-sheet.png` | Upgraded 10-frame, 256px-source topbar animation for Discord sign-in blocked/waiting/denied states: the actor tries a locked Japanese gate, gets a denial seal, slumps outside, and returns to a retry pose. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/scanner-kabuki-discord-blocked-v2-sheet.png` | Experimental 8-frame replacement for Discord sign-in blocked states: fixed gate/camera staging, key-turn anticipation, denial impact, recoil follow-through, and a faster seamless recovery loop. The original sheet is retained for comparison. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/mode-kabuki-dry-sheet.png` | Original 10-frame Dry Mode transition, retained for comparison and rollback. | V2 comparison harness only |
| `src/nhi_zues/web/assets/mode-kabuki-dry-v2-sheet.png` | Dry Mode V2 eight-frame transition: one stable actor dehydrates from one outer edge into one connected dust column and one centered residue mound. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/mode-kabuki-full-auto-sheet.png` | Original 12-frame Full-auto transition, retained for comparison and rollback. | V2 comparison harness only |
| `src/nhi_zues/web/assets/mode-kabuki-full-auto-v2-sheet.png` | Full-auto V2 eight-frame transition: one oversized theatrical prop emerges on one axis, receives one restrained charging-handle check, and settles into one stable upward-away hero hold. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/mode-kabuki-semi-auto-sheet.png` | Original 12-frame Semi-auto transition, retained for comparison and rollback. | V2 comparison harness only |
| `src/nhi_zues/web/assets/mode-kabuki-semi-auto-v2-sheet.png` | Semi-auto V2 eight-frame transition: one fixed bronze prop and inner holster move through a disciplined draw, status check, safe lower, re-holster, and guarded recovery. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/mode-kabuki-live-fire-sheet.png` | Original 12-frame Live-fire transition, retained for comparison and rollback. | V2 comparison harness only |
| `src/nhi_zues/web/assets/mode-kabuki-live-fire-v2-sheet.png` | Live-fire V2 eight-frame transition: one hand-anchored ignition powers a short lift and directional crescent before a grounded landing and complete extinguish/recovery. | `src/nhi_zues/web/styles.css`, `src/nhi_zues/web/app.js` |

## Static Sprite-Like Assets

| Asset | Purpose | Used by |
| --- | --- | --- |
| `design_assets/kabuki-actor-reference.png` | High-resolution actor reference for regenerating upgraded sprite frames. | `scripts/generate_monitor_spy_frames.py` |
| `design_assets/kabuki-bookcase-reference.png` | High-resolution bookcase/backfill reference used for the upgraded Backfill action sprite. | Source/reference asset |
| `design_assets/backfill_keyframes/frame_000.png` through `frame_007.png` | Cleaned transparent keyframes used to assemble the upgraded Backfill topbar sprite sheet. | Source/reference asset |
| `design_assets/kabuki-dry-mode-reference.png` | High-resolution actor reference used for the upgraded Dry Mode dust/disintegration transition. | Source/reference asset |
| `design_assets/dry_mode_keyframes/frame_000.png` through `frame_009.png` | Cleaned transparent keyframes used to assemble the upgraded Dry Mode transition sprite sheet. | Source/reference asset |
| `design_assets/dry_mode_v2_keyframes/frame_000.png` through `frame_007.png` | Transparent source keyframes assembled from the reviewed Dry Mode V2 atlas. | Source/reference asset |
| `design_assets/full_auto_keyframes/frame_000.png` through `frame_011.png` | Cleaned transparent keyframes used to assemble the upgraded Full Auto transition sprite sheet. | Source/reference asset |
| `design_assets/full_auto_v2_keyframes/frame_000.png` through `frame_007.png` | Transparent source keyframes assembled from the reviewed Full-auto V2 atlas. | Source/reference asset |
| `design_assets/semi_auto_keyframes/frame_000.png` through `frame_011.png` | Cleaned transparent keyframes used to assemble the upgraded Semi Auto transition sprite sheet. | Source/reference asset |
| `design_assets/semi_auto_v2_keyframes/frame_000.png` through `frame_007.png` | Transparent source keyframes assembled from the reviewed Semi-auto V2 atlas. | Source/reference asset |
| `design_assets/live_fire_keyframes/frame_000.png` through `frame_011.png` | Cleaned transparent keyframes used to assemble the upgraded Live Fire transition sprite sheet. | Source/reference asset |
| `design_assets/live_fire_v2_keyframes/frame_000.png` through `frame_007.png` | Transparent source keyframes assembled from the reviewed Live-fire V2 atlas. | Source/reference asset |
| `design_assets/sync_keyframes/frame_000.png` through `frame_010.png` | Cleaned transparent keyframes used to assemble the upgraded Sync Discord action sprite sheet. | Source/reference asset |
| `design_assets/repair_keyframes/frame_000.png` through `frame_009.png` | Cleaned transparent keyframes used to assemble the upgraded Repair action sprite sheet. | Source/reference asset |
| `design_assets/latest_keyframes/frame_000.png` through `frame_009.png` | Cleaned transparent keyframes used to assemble the upgraded Latest action sprite sheet. | Source/reference asset |
| `design_assets/refresh_keyframes/frame_000.png` through `frame_009.png` | Cleaned transparent keyframes used to assemble the upgraded Refresh action sprite sheet. | Source/reference asset |
| `design_assets/posting_keyframes/frame_000.png` through `frame_009.png` | Cleaned transparent keyframes used to assemble the upgraded Posting action sprite sheet. | Source/reference asset |
| `design_assets/discord_blocked_keyframes/frame_000.png` through `frame_009.png` | Cleaned transparent keyframes used to assemble the upgraded Discord Blocked action sprite sheet. | Source/reference asset |
| `design_assets/scanner_keyframes/frame_000.png` through `frame_015.png` | Cleaned transparent keyframes used to assemble the upgraded default Scanner topbar sprite sheet. | Source/reference asset |
| `src/nhi_zues/web/assets/runtime-mask-pixel.png` | Small pixel mask icon in the runtime footer. | `src/nhi_zues/web/index.html` |
| `src/nhi_zues/web/assets/monitor-paused-lounge.webp` | Scanner Monitor paused-state still: the upgraded actor rests on a beach lounger with a drink so pause/break is visually obvious. | `src/nhi_zues/web/monitor.js`, `src/nhi_zues/web/monitor.css` |
| `src/nhi_zues/web/assets/monitor-arigato-sprite.png` | Original static monitor success actor, retained for comparison and rollback. | V2 comparison harness only |
| `src/nhi_zues/web/assets/monitor-arigato-v2-sheet.png` | Delivery Celebration V2 eight-frame sheet: catch one confirmation receipt, verify its seal, bow, store it, and settle into a restrained thumbs-up. | `src/nhi_zues/web/monitor.js`, `src/nhi_zues/web/monitor.css` |
| `design_assets/delivery_celebration_v2_keyframes/frame_000.png` through `frame_007.png` | Transparent source keyframes assembled from the reviewed Delivery Celebration V2 atlas. | Source/reference asset |
| `src/nhi_zues/web/assets/app-icon-*.png`, `src/nhi_zues/web/assets/app-icon.png` | Window/fav/taskbar app icons at multiple sizes. | `src/nhi_zues/web/index.html`, packaging/runtime shell |
| `src/nhi_zues/web/assets/app-icon-badge-32.png` | Red-dot/badged favicon for activity attention. | `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/placeholders/server.svg` | Generic server placeholder icon. | `src/nhi_zues/web/app.js`, `src/nhi_zues/web/index.html` |
| `src/nhi_zues/web/assets/placeholders/user.svg` | Generic remembered-user placeholder icon. | `src/nhi_zues/web/app.js` |
| `src/nhi_zues/web/assets/placeholders/channel.svg` | Generic channel placeholder icon. | Static asset reserve |
| `src/nhi_zues/web/assets/placeholders/character.svg` | Generic character placeholder icon. | Static asset reserve |
| `src/nhi_zues/web/assets/placeholders/runtime.svg` | Generic runtime placeholder icon. | Static asset reserve |

## Legacy / Candidate Cleanup

| Asset | Status |
| --- | --- |
| `src/nhi_zues/web/assets/scanner-kabuki-spy-story-sheet.png` | Previous Scanner Monitor single-sheet animation. Replaced by frame-by-frame monitor sequence but kept for now as a fallback/reference. |
| `src/nhi_zues/web/assets/scanner-kabuki-cutout.png` | Older cutout/reference asset. Not currently referenced by app code. |

## Generators

| Script | Output |
| --- | --- |
| `scripts/generate_monitor_spy_frames.py` | Legacy deterministic compositor for the Scanner Monitor animation. The current active frames were generated as individual imagegen keyframes instead. |
| `scripts/generate_scanner_monitor_v2_frames.py` | Composites the transparent eight-pose magnifier atlas over the fixed monitor alley, exports direct 640x480 WebPs and manifest, and builds standalone/comparison GIF previews. |
| `scripts/generate_dojo_sweep_v2_frames.py` | Composites the transparent eight-pose actor atlas over one fixed background, exports direct 640x480 WebPs and manifest, and builds standalone/comparison GIF previews. |
| `scripts/generate_spy_story_sprite.py` | Generates the legacy single-sheet Scanner Monitor animation. |
| `scripts/generate_discord_blocked_sprite.py` | Reassembles `scanner-kabuki-discord-blocked-sheet.png` from cleaned source keyframes. |
| `scripts/generate_discord_blocked_v2_sprite.py` | Crops the generated V2 atlas, exports its eight transparent production frames and horizontal sheet, and builds standalone/comparison GIF previews. |
| `scripts/generate_posting_v2_sprite.py` | Uses the shared V2 atlas pipeline to export the Posting V2 frames, horizontal app sheet, and standalone/comparison GIFs. |
| `scripts/generate_scanner_v2_sprite.py` | Uses the shared V2 atlas pipeline to export the default Scanner V2 frames, horizontal app sheet, and standalone/comparison GIFs. |
| `scripts/generate_sync_v2_sprite.py` | Crops the bordered generated atlas and uses the shared V2 pipeline to export the Sync V2 frames, sheet, and GIF comparisons. |
| `scripts/generate_sync_sprite.py` | Reassembles `scanner-kabuki-sync-sheet.png` from cleaned source keyframes. |
| `scripts/generate_repair_sprite.py` | Reassembles `scanner-kabuki-repair-sheet.png` from cleaned source keyframes. |
| `scripts/generate_repair_v2_sprite.py` | Uses the shared V2 atlas pipeline to export the Repair V2 frames, sheet, and GIF comparisons. |
| `scripts/generate_backfill_v2_sprite.py` | Uses the shared V2 atlas pipeline to export the Backfill V2 frames, sheet, and GIF comparisons. |
| `scripts/generate_latest_sprite.py` | Reassembles `scanner-kabuki-latest-sheet.png` from cleaned source keyframes. |
| `scripts/generate_latest_v2_sprite.py` | Uses the shared V2 atlas pipeline to export the Latest V2 frames, sheet, and GIF comparisons. |
| `scripts/generate_refresh_sprite.py` | Reassembles `scanner-kabuki-refresh-sheet.png` from cleaned source keyframes. |
| `scripts/generate_refresh_v2_sprite.py` | Uses the shared V2 atlas pipeline to export the Refresh V2 frames, sheet, and GIF comparisons. |
| `scripts/generate_semi_auto_sprite.py` | Reassembles `mode-kabuki-semi-auto-sheet.png` from cleaned source keyframes. |
| `scripts/generate_live_fire_sprite.py` | Reassembles `mode-kabuki-live-fire-sheet.png` from cleaned source keyframes. |

## Scanner Timing Defaults

The Scanner Monitor now displays the active pace in its Pace card and a loop HUD over the bottom-right of the animation frame. With default environment values, Kabuki-Cord scans `1` observed channel per cycle, waits `12s` on the loaded channel before reading, rests for `45s`, then checks the next channel in the global round-robin order. Adding or removing observed channels automatically changes the full-loop estimate and loop countdown. The `12-35s` per-channel delay only becomes visible between channels when `NHI_ZUES_SCANNER_MAX_CHANNELS_PER_CYCLE` is raised above `1`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `NHI_ZUES_SCANNER_MAX_CHANNELS_PER_CYCLE` | `1` | Number of enabled channels visited before the scanner rests. |
| `NHI_ZUES_SCANNER_CYCLE_SLEEP_SECONDS` | `45` | Idle/rest period after a scan cycle. |
| `NHI_ZUES_SCANNER_CHANNEL_SETTLE_SECONDS` | `12` | Fixed wait after loading a channel and before reading visible messages. |
| `NHI_ZUES_SCANNER_MIN_CHANNEL_DELAY_SECONDS` | `12` | Minimum cooldown between channels inside one cycle. |
| `NHI_ZUES_SCANNER_MAX_CHANNEL_DELAY_SECONDS` | `35` | Maximum cooldown between channels inside one cycle. |

## Upgrade Standard

New action sprites should use the HD kabuki actor style from `design_assets/kabuki-actor-reference.png`: readable white/red mask, black hair mass, dark robe with red/purple trim, scarf/sleeve movement, and clear body-weight changes. Do not ship static-pose sprites with only an icon pasted over the actor.

Recommended replacement order:

1. First-pass action and response-mode sprite upgrades are complete.
2. `scanner-kabuki-sheet.png`, `scanner-kabuki-backfill-sheet.png`, `scanner-kabuki-sync-sheet.png`, `scanner-kabuki-repair-sheet.png`, `scanner-kabuki-latest-sheet.png`, `scanner-kabuki-refresh-sheet.png`, `scanner-kabuki-posting-sheet.png`, `scanner-kabuki-discord-blocked-sheet.png`, `mode-kabuki-dry-sheet.png`, `mode-kabuki-full-auto-sheet.png`, `mode-kabuki-semi-auto-sheet.png`, and `mode-kabuki-live-fire-sheet.png` can be refined later with hand-painted in-betweens if needed.

For upgraded topbar sheets, prefer 256px source frames and a CSS-specific frame count/duration rather than forcing every animation into the legacy 20-frame, 128px-source path. For the larger mode transition overlay, use at least 256px source frames and export at the display scale or higher.

The ordered one-by-one replacement queue and acceptance gate live in `docs/V2_ANIMATION_ROADMAP.md`.
