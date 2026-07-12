# Kabuki-Cord Operator Guide

This guide covers what you need before starting Kabuki-Cord, what each setting does, and what can or cannot happen in common operating modes.

## Before You Start

Have these inputs ready:

- A Discord account you control and can sign into through the app's browser session.
- An OpenAI Project API key for draft generation.
- A small test budget and model choice, such as `gpt-5.4-nano` for low-cost testing.
- A character card JSON file under `%LOCALAPPDATA%\Kabuki-Cord\character_cards\`.
- A local server/channel config, managed by the app under `%LOCALAPPDATA%\Kabuki-Cord\config\servers.json`.
- A decision about response mode: Observe only, Review every draft, Limited autonomous, or Autonomous live.

Keep these local-only values out of Git:

- Legacy `.env`, `.local/`, `.state/`, and `.profiles/` directories
- `%LOCALAPPDATA%\Kabuki-Cord\state\`
- `%LOCALAPPDATA%\Kabuki-Cord\profiles\`
- Discord credentials saved through the GUI
- OpenAI API keys

## First-Time Setup Flow

1. Install or update Kabuki-Cord.
2. Launch the desktop app with `Run-Kabuki-Cord.cmd`.
3. Open **API & Runtime**.
4. Enter and save the OpenAI API key.
5. Click **Models** and choose a model available to that project.
6. Keep **Observe only** selected for first checks.
7. Open **Discord Session** and sign in.
8. Click **Sync Discord** to import servers and channels into local config.
9. Select only the channels you want to monitor.
10. Turn on **Observe** for channels you want remembered.
11. Turn on **Engage** for channels where drafts should be considered.
12. Leave **Auto** off until approval-based posting is working.
13. Click **Start** and watch the **Events** tab.

## Core Controls

### Observe

Observe means the scanner can visit the channel, read visible messages, and update memory/history.

If Observe is off:

- The channel is not scanned.
- Messages from that channel are not remembered.
- No draft or send decision is made for that channel.

### Engage

Engage means observed messages can be evaluated for reply opportunities.

If Engage is off:

- Messages can still be remembered if Observe is on.
- No model draft is generated.
- No approval is queued.
- No autonomous post happens.

### React

React means observed messages can receive a capped lightweight emoji reaction when the text has a clear cue, such as an obvious joke, agreement, thanks, or a notably weird claim.

If React is on and Observe is on:

- The channel can receive reactions even when Engage is off.
- Reactions are still blocked by Observe only.
- Each channel scan is capped by `NHI_ZUES_REACTION_MAX_PER_CHANNEL`, which defaults to `3`.
- The reaction ledger prevents repeating any app-made reaction on the same Discord message.

Reaction behavior has four app-level controls:

- **Reaction threshold**: `strict`, `normal`, or `loose`. Loose accepts lower-confidence acknowledgement-style messages.
- **Random reaction percent**: optional percentage of otherwise eligible fresh messages to react to. Keep this low.
- **Force recent reaction**: optional rolling target/cap for reacting across the latest five visible non-character messages. Repeated scans do not keep adding reactions after the cap is full, but if the window is below target, the scanner spends available per-scan reaction cap to catch up. For example, `20%` means Kabuki tries to keep up to 1 of those latest 5 non-character messages reacted until new messages move the window. It still obeys Observe only, per-channel React, the per-scan cap, and the reaction ledger.
- **Reaction emoji override**: optional emoji that replaces the smart choice.

Smart reaction selection is conservative: obvious jokes can get `😂`, clear agreement can get `👍`, thanks/help/support can get `🙏`, questions can get `🤔`, and serious or notably weird claims usually get `👀`. The forced-reaction percentage controls frequency, not a forced laugh emoji.

Suggested testing baseline: `normal` threshold, `0%` random sample, cap `1-3` per channel scan.

The **Events -> Reaction events** filter shows successful reactions, reaction failures, Dry/cap skips, already-present reactions, and no-action reaction scan summaries. A no-action scan summary includes candidate counts, `force_window=used/cap/size`, `force_window_capped`, and the last skip reason so you can tell whether React was blocked by config, the ledger, threshold, force-window saturation, or lack of recent eligible messages.

### Auto

Auto is the per-channel permission for unattended sends. It is intentionally separate from the global response mode; both must allow autonomy.

If Auto is off:

- Every generated reply remains approval-gated, including direct alias/name cues.

Use Auto only on channels where you are comfortable with unattended posts.

### Response Modes

**Observe only** is the master no-send mode:

- The app can scan and remember messages.
- The app can show Events history.
- The app can generate drafts only if **Draft while observing** is enabled.
- Nothing is posted to Discord.
- **Approve & Send** is blocked.
- Auto cannot post.

**Review every draft** permits approved live delivery but never unattended delivery. **Limited autonomous** can auto-send regular replies in Auto-enabled channels while new conversation starts and manual drafts require review. **Autonomous live** can auto-send eligible replies only in channels where Observe, Engage, and Auto are all enabled.

### Enable LLM Drafting

This controls whether OpenAI is used for drafts.

If LLM drafting is off:

- The app can still scan, remember, and record decision events.
- It cannot generate draft text.
- It cannot send model-generated replies.

### Draft While Observing

This allows paid draft generation while still preventing sends.

Use this for safe testing because it confirms:

- Channel scanning works.
- Topic/direct detection works.
- OpenAI calls work.
- Budgets are being recorded.
- Draft style and character behavior are acceptable.

### Proactive Review Policy

The response mode derives this policy. Review every draft gates every reply. Limited autonomous gates proactive conversation starts and manual drafts. Autonomous live can deliver eligible replies only when the selected channel's Auto permission is also on.

### Budgets

Budget settings prevent runaway API usage:

- **Daily Budget USD** limits spending per UTC day.
- **Session Budget USD** limits spending for the current runtime session.
- **Max Calls Per Run** limits model calls during one scanner run/session.
- **Max Output Tokens** and **Max Input Chars** can be configured in `%LOCALAPPDATA%\Kabuki-Cord\settings.env`.

If a budget blocks a draft:

- No API call is made for that draft.
- The Events feed records why it did not generate.

## Operating Modes

| Response mode | Channel Auto | What can happen |
| --- | --- | --- |
| Observe only | Any | Reads and remembers. Optional preview drafts can be generated, but all Discord writes are blocked. |
| Review every draft | Any | Approved drafts can post; unattended replies cannot. |
| Limited autonomous | Off | All drafts queue for review in this channel. |
| Limited autonomous | On | Eligible regular replies may auto-send; proactive starts and manual drafts require review. |
| Autonomous live | Off | All drafts queue for review in this channel. |
| Autonomous live | On | Eligible replies may auto-send after cooldown, rate, duplicate, and own-message guards. |

## What The Events Tab Means

The right-side **Events** tab is the main health and audit view.

### Runtime Checks

Shows:

- Whether the scanner is running.
- The last successful scanner check.
- How many channels are observed, engaged, and auto-enabled.
- The most recent runtime error.

### Response History

Shows:

- Drafts queued for approval.
- Manual suggested drafts.
- Regenerated drafts.
- Delivery-started status after **Approve & Send** is clicked.
- Duplicate-reply blocks when a draft overlaps source messages already answered.
- Approved sends.
- Autonomous sends.
- Observe-only preview drafts.
- Send failures.

### Activity Feed

Shows broader runtime activity, including routine checks such as:

```text
Reviewed 12 visible message(s), 3 new; no tracked topic or direct name cue.
```

This is how you know the scanner is actually running even when it decides not to reply.

## History, Memory, And Review

The **History** tab shows remembered channel messages and response/approval trail for the selected channel.

Local state is authoritative in `%LOCALAPPDATA%\Kabuki-Cord\state\state.db`; JSON files in the same directory are readable recovery/compatibility mirrors:

- `memory.json` stores remembered channel messages and per-user memory.
- `events.json` stores scan checks, approvals, sends, and failures.
- `approvals.json` stores the five newest pending approval drafts.
- `discarded_approvals.json` prevents repeated scanner loops from recreating discarded stale drafts.
- `sent_replies.json` prevents duplicate replies and identifies prior app-authored posts.
- `usage.json` stores estimated/recorded API usage and the shared runtime-session ID.

Use **Clear All** in Approvals before enabling live or Auto if there is any stale backlog. Semi-auto also prunes older drafts automatically once more than five are pending.

When **Auto** is off for a channel, generated replies queue for approval even when the trigger was a direct name or alias cue. Auto must be enabled per channel before the scanner can send generated replies without approval.

Auto replies have a second safety guard even when **Auto** is enabled. The default settings block unreviewed auto sends for a channel when the app has already posted there in the last 15 minutes, when it has sent 3 auto replies in the last hour, or when the last visible channel message is already from the character. The own-message guard uses display-name matching, known account IDs, posted Discord message IDs, and sanitized sent-text matching to avoid replying to the account's own prior posts. When this happens the Events feed records `reply_guard_blocked` or `own_reply_blocked` with the specific reason. Tune pacing under **API & Runtime -> Account safety pacing**.

## Character Cards

The active character is loaded from JSON. It is not hardcoded into the app.

Useful fields:

- `name`: display/persona name.
- `system_prompt`: core identity and behavior.
- `aliases`: names that count as direct cues.
- `trigger_keywords`: topics that can trigger proactive engagement.
- `style_rules`: tone and writing habits.
- `engagement_rules`: when to reply and when to stay quiet.

You can set:

- One global character card in the per-user `settings.env`.
- Optional per-server card overrides in the server/channel config.
- Runtime continuity notes in the Growth tab.
- Per-user behavior notes in the Growth tab.

## Discord Session Behavior

Kabuki-Cord uses a persistent local browser profile so the Discord login survives between runs.

Important constraints:

- Only one Kabuki-controlled Discord browser session should use the profile at a time.
- Starting scanner operations can conflict with a separate open Kabuki Discord channel window.
- The app pauses scanning before sync/open/send operations and waits for the profile lock.
- If a separate Kabuki-opened Discord window is still holding the profile, close that window and retry.
- If Discord asks for a password reset, human verification, 2FA, phone/email verification, or another account security action, stop the scanner and complete the visible Discord flow yourself. Kabuki-Cord records this as a `discord_account_challenge` event and does not keep retrying.
- Use **Sign In & Run** for reset/checkpoint situations where the scanner must continue immediately after you finish Discord's visible login flow. It opens the persistent automation profile visibly, waits for you to finish authentication manually, then runs the scanner in that same browser session without closing and reopening the profile.
- **Open** and **Open Conversation** launch the Discord URL in your normal browser instead of the hidden automation profile. This keeps manual review windows separate from background automation.
- Password reset links and new passwords must be handled manually. After a reset, update the saved Discord credentials in **API & Runtime** before using **Sign In** or **Sign In & Run** again.

### Account Safety Pacing

The scanner uses one global round-robin loop across every Observe-enabled channel. The conservative defaults are:

- `NHI_ZUES_SCANNER_MAX_CHANNELS_PER_CYCLE=1`
- `NHI_ZUES_SCANNER_CYCLE_SLEEP_SECONDS=45`
- `NHI_ZUES_SCANNER_CHANNEL_SETTLE_SECONDS=12`

`NHI_ZUES_SCANNER_CHANNEL_SETTLE_SECONDS` keeps the scanner on a channel briefly after navigation before message extraction. This reduces rapid browser churn and gives Discord time to finish rendering the latest messages. If you increase **Max channels per cycle**, the min/max wait settings add a pause between channel checks inside that cycle. Keep the observed channel list narrow and prefer **Observe only** or **Review every draft** while testing.

If Discord repeatedly forces password resets or login checkpoints, treat that as an account security signal and reduce activity rather than retrying harder:

- Keep only one Kabuki automation profile active and close extra Kabuki-opened Discord windows.
- Keep **Max channels per cycle** at `1` and use longer cycle rests while testing.
- Keep React cap and random reaction percent low; reaction writes are still Discord actions.
- Prefer Observe-only scanning for a while after a checkpoint, then re-enable Engage/React gradually.
- Avoid frequent sign-out/sign-in loops; use **Sign In & Run** so a manually completed login continues in the same persistent browser profile.
- Use a stable network/browser profile, keep the account's email/2FA/security settings current, and complete Discord security prompts manually.

Kabuki-Cord should not attempt to bypass Discord account security systems. If checkpoints continue even with conservative settings, stop automation for that account and review Discord account/security status before continuing.

### Scanner Monitor and Replies

Click **Monitor** in the top bar to open a separate scanner-status window. It reports the live scanner phase, current channel, next channel in the round-robin loop, upcoming channels, scanner pacing, the estimated full-loop countdown, loop counter, and the last completed scan counts. Normal scanner passes update remembered conversation history from the visible messages in each enabled channel as soon as the channel is read; use **Backfill** when you need deeper scrollback beyond what Discord currently renders.

The **Replies** tab lists remembered messages that appear to need attention after the character's last post. It flags explicit mentions/tags plus immediate adjacent replies in a short window, then shows red dots on the matching server icons. These indicators are based on local scan memory, so they clear after a later character response is scanned back into memory.

## Safe Test Checklist

Use this sequence before allowing live sends:

1. Select **Observe only**.
2. LLM drafting on.
3. Turn **Draft while observing** on.
4. Observe on for one test channel.
5. Engage on for one test channel.
6. Auto off.
7. Start scanner.
8. Confirm Events shows routine channel checks.
9. Confirm a draft queues only when expected.
10. Review the draft text and character behavior.
11. Clear stale approvals.

Discard and Clear All are persistent local decisions for the source messages behind those drafts. If the scanner returns to the same channel, it should log `discarded_approval_suppressed` instead of recreating the same approval.
12. Switch to **Review every draft**.
13. Send one approved draft manually.
14. Confirm Events shows `Approved response sent`.
15. Only then consider Auto for a narrow channel.

## Troubleshooting

### Nothing appears to be happening

Check:

- Is the runtime started?
- Does Events show a recent **Last check**?
- Is Observe enabled for at least one channel?
- Does the account still have access to that channel?
- Is another Kabuki Discord window holding the browser profile?

### It reads messages but never drafts

Check:

- Is Engage on for that channel?
- Is LLM drafting enabled?
- Is **Draft while observing** enabled in Observe only?
- Did Events say `no tracked topic or direct name cue`?
- Does the character card include useful aliases and trigger keywords?
- Did budget limits block the model call?

### It queues approvals but does not post

Check:

- Is the response mode **Review every draft**, **Limited autonomous**, or **Autonomous live**?
- Are you clicking **Approve & Send**?
- Is the Discord profile busy?
- Did the Events feed show a send failure?

### It has not posted autonomously

Check:

- Is the response mode **Limited autonomous** or **Autonomous live**?
- Is Observe on?
- Is Engage on?
- Is Auto on for this channel?
- Did the model actually decide to reply?
- Is the opportunity direct alias/name-cue or only topic-based?

### It might post too much

Before live use:

- Keep Auto off.
- Keep approval required on.
- Use Clear All to remove stale approvals.
- Use a low **Max Calls Per Run**.
- Watch Events for a full cycle before allowing live sends.

## Recommended Default For Testing

Use this baseline:

- Response mode: Observe only
- LLM drafting: on
- Draft while observing: on
- Proactive approval required: on
- Auto: off
- Max calls per run: 3
- Daily budget: small
- Session budget: small
- One observed and engaged channel at a time

Move beyond this only after Events and History show the expected behavior.
