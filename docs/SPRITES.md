# Kabuki-Cord Sprite Inventory

This is the replacement checklist for animated and sprite-like visual assets currently used by the app.

## Active Animated Sprites

| Asset | Purpose | Used by |
| --- | --- | --- |
| `web/assets/monitor_spy_frames/frame_000.png` through `frame_005.png` | Scanner Monitor popup activity animation: generated high-resolution keyframes of the kabuki actor sneaking through Japanese alleys, dropping mail, scanning with a magnifying glass, peeking into a shoji window from behind, and looping out of frame. | `web/monitor.html`, `web/monitor.js`, `web/monitor.css` |
| `web/assets/scanner-kabuki-sheet.png` | Default topbar operation/status sprite, including idle/working/scanning fallback. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-sync-sheet.png` | Topbar animation while syncing Discord servers/channels. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-repair-sheet.png` | Topbar animation while repairing/reloading a server channel list. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-backfill-sheet.png` | Upgraded 8-frame, 256px-source topbar animation while backfilling older channel history: the actor pulls a ledger from a wooden archive shelf, indexes it, files it back, and settles into a loop. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-latest-sheet.png` | Topbar animation while refreshing the latest visible messages. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-refresh-sheet.png` | Topbar animation while refreshing local app state. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-posting-sheet.png` | Topbar animation while posting an approved reply. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-discord-blocked-sheet.png` | Topbar animation for Discord sign-in blocked/waiting/denied states. | `web/styles.css`, `web/app.js` |
| `web/assets/mode-kabuki-dry-sheet.png` | Response mode transition animation for Dry Mode. | `web/styles.css`, `web/app.js` |
| `web/assets/mode-kabuki-full-auto-sheet.png` | Response mode transition animation for Full Auto. | `web/styles.css`, `web/app.js` |
| `web/assets/mode-kabuki-semi-auto-sheet.png` | Response mode transition animation for Semi Auto. | `web/styles.css`, `web/app.js` |
| `web/assets/mode-kabuki-live-fire-sheet.png` | Response mode transition animation for Live Fire. | `web/styles.css`, `web/app.js` |

## Static Sprite-Like Assets

| Asset | Purpose | Used by |
| --- | --- | --- |
| `web/assets/source/kabuki-actor-reference.png` | High-resolution actor reference for regenerating upgraded sprite frames. | `scripts/generate_monitor_spy_frames.py` |
| `web/assets/source/kabuki-bookcase-reference.png` | High-resolution bookcase/backfill reference used for the upgraded Backfill action sprite. | Source/reference asset |
| `web/assets/source/backfill_keyframes/frame_000.png` through `frame_007.png` | Cleaned transparent keyframes used to assemble the upgraded Backfill topbar sprite sheet. | Source/reference asset |
| `web/assets/runtime-mask-pixel.png` | Small pixel mask icon in the runtime footer. | `web/index.html` |
| `web/assets/monitor-arigato-sprite.png` | Monitor-only success notification sprite for posted/delivered replies. | `web/monitor.js`, `web/monitor.css` |
| `web/assets/app-icon-*.png`, `web/assets/app-icon.png` | Window/fav/taskbar app icons at multiple sizes. | `web/index.html`, packaging/runtime shell |
| `web/assets/app-icon-badge-32.png` | Red-dot/badged favicon for activity attention. | `web/app.js` |
| `web/assets/placeholders/server.svg` | Generic server placeholder icon. | `web/app.js`, `web/index.html` |
| `web/assets/placeholders/user.svg` | Generic remembered-user placeholder icon. | `web/app.js` |
| `web/assets/placeholders/channel.svg` | Generic channel placeholder icon. | Static asset reserve |
| `web/assets/placeholders/character.svg` | Generic character placeholder icon. | Static asset reserve |
| `web/assets/placeholders/runtime.svg` | Generic runtime placeholder icon. | Static asset reserve |

## Legacy / Candidate Cleanup

| Asset | Status |
| --- | --- |
| `web/assets/scanner-kabuki-spy-story-sheet.png` | Previous Scanner Monitor single-sheet animation. Replaced by frame-by-frame monitor sequence but kept for now as a fallback/reference. |
| `web/assets/scanner-kabuki-cutout.png` | Older cutout/reference asset. Not currently referenced by app code. |

## Generators

| Script | Output |
| --- | --- |
| `scripts/generate_monitor_spy_frames.py` | Legacy deterministic compositor for the Scanner Monitor animation. The current active frames were generated as individual imagegen keyframes instead. |
| `scripts/generate_spy_story_sprite.py` | Generates the legacy single-sheet Scanner Monitor animation. |
| `scripts/generate_discord_blocked_sprite.py` | Regenerates `scanner-kabuki-discord-blocked-sheet.png`. |

## Scanner Timing Defaults

The Scanner Monitor now displays the active pace in its Pace card. With default environment values, Kabuki-Cord scans `1` channel per cycle, waits `12s` on the loaded channel before reading, rests for `45s`, then checks the next due channel. The `12-35s` per-channel delay only becomes visible between channels when `NHI_ZUES_SCANNER_MAX_CHANNELS_PER_CYCLE` is raised above `1`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `NHI_ZUES_SCANNER_MAX_CHANNELS_PER_CYCLE` | `1` | Number of enabled channels visited before the scanner rests. |
| `NHI_ZUES_SCANNER_CYCLE_SLEEP_SECONDS` | `45` | Idle/rest period after a scan cycle. |
| `NHI_ZUES_SCANNER_CHANNEL_SETTLE_SECONDS` | `12` | Fixed wait after loading a channel and before reading visible messages. |
| `NHI_ZUES_SCANNER_MIN_CHANNEL_DELAY_SECONDS` | `12` | Minimum cooldown between channels inside one cycle. |
| `NHI_ZUES_SCANNER_MAX_CHANNEL_DELAY_SECONDS` | `35` | Maximum cooldown between channels inside one cycle. |

## Upgrade Standard

New action sprites should use the HD kabuki actor style from `web/assets/source/kabuki-actor-reference.png`: readable white/red mask, black hair mass, dark robe with red/purple trim, scarf/sleeve movement, and clear body-weight changes. Do not ship static-pose sprites with only an icon pasted over the actor.

Recommended replacement order:

1. `mode-kabuki-dry-sheet.png`, `mode-kabuki-full-auto-sheet.png`, `mode-kabuki-semi-auto-sheet.png`, `mode-kabuki-live-fire-sheet.png` because they render large in the mode transition overlay.
2. `scanner-kabuki-sheet.png`, `scanner-kabuki-posting-sheet.png`, `scanner-kabuki-discord-blocked-sheet.png` because they are the most visible day-to-day runtime states.
3. `scanner-kabuki-sync-sheet.png`, `scanner-kabuki-repair-sheet.png`, `scanner-kabuki-latest-sheet.png`, `scanner-kabuki-refresh-sheet.png`.
4. `scanner-kabuki-backfill-sheet.png` is already upgraded as the first pass, but can be refined later with hand-painted in-betweens if needed.

For upgraded topbar sheets, prefer 256px source frames and a CSS-specific frame count/duration rather than forcing every animation into the legacy 20-frame, 128px-source path. For the larger mode transition overlay, use at least 256px source frames and export at the display scale or higher.
