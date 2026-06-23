# Kabuki-Cord Operator Guide

This guide covers what you need before starting Kabuki-Cord, what each setting does, and what can or cannot happen in common operating modes.

## Before You Start

Have these inputs ready:

- A Discord account you control and can sign into through the app's browser session.
- An OpenAI Project API key for draft generation.
- A small test budget and model choice, such as `gpt-5.4-nano` for low-cost testing.
- A character card JSON file under `character_cards/`.
- A local server/channel config file, normally `.local/servers.local.json`.
- A decision about safety mode: dry-run only, approval-based live sends, or limited autonomous sends.

Keep these local-only values out of Git:

- `.env`
- `.local/`
- `.state/`
- `.profiles/`
- Discord credentials saved through the GUI
- OpenAI API keys

## First-Time Setup Flow

1. Install or update Kabuki-Cord.
2. Launch the desktop app with `Run-Kabuki-Cord.cmd`.
3. Open **API & Runtime**.
4. Enter and save the OpenAI API key.
5. Click **Models** and choose a model available to that project.
6. Keep **Dry-run mode** on for first checks.
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

### Auto

Auto allows proactive, approval-required opportunities to be sent without manual approval when live sending is otherwise allowed.

If Auto is off:

- Proactive topic-based drafts are queued for approval.
- Direct alias/name-cue replies can still send live when dry-run is off, because they are not treated as proactive approval-required drafts.

Use Auto only on channels where you are comfortable with unattended posts.

### Dry-Run Mode

Dry-run is the master safety switch for sending.

If Dry-run is on:

- The app can scan and remember messages.
- The app can show Events history.
- The app can generate drafts only if **Draft during dry-run** is enabled.
- Nothing is posted to Discord.
- **Approve & Send** is blocked.
- Auto cannot post.

If Dry-run is off:

- Approved drafts can post.
- Direct alias/name-cue replies can post if the model decides to reply.
- Proactive replies can post only when their channel is eligible for live sending through the current approval/Auto settings.

### Enable LLM Drafting

This controls whether OpenAI is used for drafts.

If LLM drafting is off:

- The app can still scan, remember, and record decision events.
- It cannot generate draft text.
- It cannot send model-generated replies.

### Draft During Dry-Run

This allows paid draft generation while still preventing sends.

Use this for safe testing because it confirms:

- Channel scanning works.
- Topic/direct detection works.
- OpenAI calls work.
- Budgets are being recorded.
- Draft style and character behavior are acceptable.

### Require Approval For Proactive Drafts

This is the default safety layer for topic-only opportunities.

When on:

- Topic-based opportunities require approval unless the selected channel has Auto on.
- Direct alias/name-cue opportunities do not use this proactive approval requirement.

When off:

- More model decisions can move directly to send when dry-run is off.

### Budgets

Budget settings prevent runaway API usage:

- **Daily Budget USD** limits spending per UTC day.
- **Session Budget USD** limits spending for the current runtime session.
- **Max Calls Per Run** limits model calls during one scanner run/session.
- **Max Output Tokens** and **Max Input Chars** are configured in `.env`.

If a budget blocks a draft:

- No API call is made for that draft.
- The Events feed records why it did not generate.

## Operating Modes

| Mode | Observe | Engage | Dry-run | Auto | What can happen |
| --- | --- | --- | --- | --- | --- |
| Passive memory | On | Off | Any | Off | Reads and remembers only. No drafts. No posts. |
| Safe drafting | On | On | On | Off | Reads, remembers, may draft if dry-run drafting is enabled. No posts. |
| Approval-based live | On | On | Off | Off | Proactive drafts queue for approval. Approved drafts can post. Direct alias/name-cue replies may post live. |
| Limited autonomous | On | On | Off | On | Proactive opportunities can post without approval in that channel. Direct alias/name-cue replies may also post. |
| Fully blocked | Off | Any | Any | Any | Channel is ignored by the scanner. |

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
- Dry-run drafts.
- Send failures.

### Activity Feed

Shows broader runtime activity, including routine checks such as:

```text
Reviewed 12 visible message(s), 3 new; no tracked topic or direct name cue.
```

This is how you know the scanner is actually running even when it decides not to reply.

## History, Memory, And Review

The **History** tab shows remembered channel messages and response/approval trail for the selected channel.

Local state lives under `.state/`:

- `.state/memory.json` stores remembered channel messages and per-user memory.
- `.state/events.json` stores scan checks, approvals, sends, and failures.
- `.state/approvals.json` stores pending approval drafts.
- `.state/sent_replies.json` stores successful send receipts keyed by source message IDs so stale approvals cannot double-reply to the same Discord message.
- `.state/usage.json` stores estimated/recorded API usage.

Use **Clear All** in Approvals before enabling live or Auto if there is any stale backlog.

When **Auto** is off for a channel, generated replies queue for approval even when the trigger was a direct name or alias cue. Auto must be enabled per channel before the scanner can send generated replies without approval.

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

- One global character card in `.env`.
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
- **Open** and **Open Conversation** launch the Discord URL in your normal browser instead of the hidden automation profile. This keeps manual review windows separate from background automation.
- Password reset links and new passwords must be handled manually. After a reset, update the saved Discord credentials in **API & Runtime** before using Sign In again.

### Account Safety Pacing

The scanner should not sweep every enabled channel back-to-back. The conservative defaults are:

- `NHI_ZUES_SCANNER_MAX_CHANNELS_PER_CYCLE=1`
- `NHI_ZUES_SCANNER_CYCLE_SLEEP_SECONDS=45`
- `NHI_ZUES_POLL_SECONDS=180`

If you increase **Max channels per cycle**, the min/max wait settings add a pause between channel checks. Keep the observed channel list narrow, keep server scan cadences in minutes rather than seconds, and prefer **Dry Mode** or approval-based modes while testing.

## Safe Test Checklist

Use this sequence before allowing live sends:

1. Dry-run on.
2. LLM drafting on.
3. Draft during dry-run on.
4. Observe on for one test channel.
5. Engage on for one test channel.
6. Auto off.
7. Start scanner.
8. Confirm Events shows routine channel checks.
9. Confirm a draft queues only when expected.
10. Review the draft text and character behavior.
11. Clear stale approvals.
12. Turn dry-run off.
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
- Is **Draft during dry-run** enabled if dry-run is on?
- Did Events say `no tracked topic or direct name cue`?
- Does the character card include useful aliases and trigger keywords?
- Did budget limits block the model call?

### It queues approvals but does not post

Check:

- Is dry-run off?
- Are you clicking **Approve & Send**?
- Is the Discord profile busy?
- Did the Events feed show a send failure?

### It has not posted autonomously

Check:

- Is dry-run off?
- Is Observe on?
- Is Engage on?
- Is Auto on for proactive posts?
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

- Dry-run: on
- LLM drafting: on
- Draft during dry-run: on
- Proactive approval required: on
- Auto: off
- Max calls per run: 3
- Daily budget: small
- Session budget: small
- One observed and engaged channel at a time

Move beyond this only after Events and History show the expected behavior.
