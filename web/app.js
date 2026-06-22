let appState = null;
let selectedServer = 0;
let selectedChannel = 0;
let selectedUserKey = null;
let apiToken = null;
const approvalTargets = {};

const $ = (id) => document.getElementById(id);

async function loadSession() {
  const response = await fetch("/api/session");
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  apiToken = payload.token;
}

async function api(path, options = {}) {
  if (!apiToken && path !== "/api/session") await loadSession();
  const { headers = {}, ...rest } = options;
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(apiToken ? { "X-Kabuki-Token": apiToken } : {}),
      ...headers,
    },
    ...rest,
  });
  if (!response.ok) {
    const errorText = await response.text();
    let message = errorText;
    try {
      message = JSON.parse(errorText).error || errorText;
    } catch {
      message = errorText;
    }
    throw new Error(message);
  }
  return response.json();
}

async function loadState() {
  appState = await api("/api/state");
  selectedServer = Math.min(selectedServer, servers().length - 1);
  if (selectedServer < 0) selectedServer = 0;
  selectedChannel = Math.min(selectedChannel, channels().length - 1);
  if (selectedChannel < 0) selectedChannel = 0;
  render();
}

function servers() {
  return appState?.servers?.servers || [];
}

function server() {
  return servers()[selectedServer] || { channels: [] };
}

function channels() {
  return server().channels || [];
}

function channel() {
  return channels()[selectedChannel] || null;
}

function render() {
  renderRail();
  renderServerPanel();
  renderCharacterCards();
  renderCharacterEditor();
  renderSettings();
  renderRuntime();
  renderGrowth();
  renderApprovals();
  renderObserved();
  renderHistory();
  renderMetrics();
}

function renderRail() {
  $("serverRail").innerHTML = servers()
    .map((srv, index) => {
      const label = srv.label || `S${index + 1}`;
      const icon = srv.icon_path || srv.icon_url || "/assets/placeholders/server.svg";
      const initials = label
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0])
        .join("")
        .toUpperCase() || String(index + 1);
      return `
        <button class="server-bubble ${index === selectedServer ? "active" : ""}" data-server="${index}" title="${escapeHtml(label)}">
          <img src="${escapeAttr(icon)}" alt="" onerror="this.src='/assets/placeholders/server.svg'" />
          <span>${escapeHtml(initials)}</span>
        </button>
      `;
    })
    .join("");
  document.querySelectorAll("[data-server]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedServer = Number(button.dataset.server);
      selectedChannel = 0;
      render();
    });
  });
}

function renderServerPanel() {
  const srv = server();
  $("serverTitle").textContent = srv.label || srv.server_id || "No server";
  $("serverLabel").value = srv.label || "";
  $("serverPoll").value = srv.poll_seconds || 120;
  $("serverCharacter").innerHTML =
    `<option value="">Use global card</option>` +
    appState.characters
      .map((card) => `<option value="${escapeAttr(card.path)}">${escapeHtml(card.name)} (${escapeHtml(card.path)})</option>`)
      .join("");
  $("serverCharacter").value = srv.character_card || "";

  $("channelList").innerHTML = channels()
    .map((chan, index) => {
      const name = chan.label || chan.channel_id;
      const type = channelTypeLabel(chan.channel_type);
      const remembered = historyCount(chan.channel_id);
      const metaBase = [type, chan.category].filter(Boolean).join(" - ") || `ID ${chan.channel_id || ""}`;
      const meta = remembered ? `${metaBase} - ${remembered} remembered` : metaBase;
      return `
        <div class="channel-row ${index === selectedChannel ? "active" : ""}">
          <div class="channel-name" data-channel="${index}" title="Channel ID: ${escapeAttr(chan.channel_id || "")}">
            <img src="/assets/placeholders/channel.svg" alt="" />
            <div>
              <strong>${escapeHtml(formatChannelName(name, chan.channel_type))}</strong>
              <span>${escapeHtml(meta)}</span>
            </div>
          </div>
          <div class="channel-actions">
            <button class="pill-toggle observe ${chan.scan_enabled ? "on" : ""}" data-toggle="scan" data-channel="${index}">Observe</button>
            <button class="pill-toggle engage ${chan.engage_enabled ? "on" : ""}" data-toggle="engage" data-channel="${index}">Engage</button>
            <button class="pill-toggle auto ${chan.auto_respond_enabled ? "on" : ""}" data-toggle="auto" data-channel="${index}">Auto</button>
          </div>
        </div>
      `;
    })
    .join("");

  document.querySelectorAll("[data-channel]").forEach((el) => {
    el.addEventListener("click", () => {
      selectedChannel = Number(el.dataset.channel);
      render();
    });
  });
  document.querySelectorAll("[data-toggle]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const chan = channels()[Number(button.dataset.channel)];
      if (button.dataset.toggle === "scan") chan.scan_enabled = !chan.scan_enabled;
      if (button.dataset.toggle === "engage") chan.engage_enabled = !chan.engage_enabled;
      if (button.dataset.toggle === "auto") chan.auto_respond_enabled = !chan.auto_respond_enabled;
      render();
    });
  });

  const current = channel();
  $("channelAutoRespond").checked = Boolean(current?.auto_respond_enabled);
  $("approvalState").textContent = current?.auto_respond_enabled ? "auto allowed" : "required";
}

function renderCharacterCards() {
  const activePath = appState.env.NHI_ZUES_CHARACTER_CARD || appState.active_character.path;
  $("characterCards").innerHTML = appState.characters
    .map((card) => `
      <button class="character-card ${card.path === activePath ? "active" : ""}" data-card="${escapeAttr(card.path)}">
        <div class="portrait"><img src="/assets/placeholders/character.svg" alt="" /></div>
        <strong>${escapeHtml(card.name)}</strong>
        <small>${escapeHtml(card.path)}</small>
      </button>
    `)
    .join("");
  document.querySelectorAll("[data-card]").forEach((button) => {
    button.addEventListener("click", () => {
      appState.env.NHI_ZUES_CHARACTER_CARD = button.dataset.card;
      appState.active_character = readCardFromList(button.dataset.card);
      render();
    });
  });
}

function readCardFromList(path) {
  if (path === appState.active_character.path) return appState.active_character;
  const existing = appState.characters.find((card) => card.path === path);
  return {
    path,
    card: structuredClone(existing?.card || {
      name: existing?.name || "New Character",
      system_prompt: "",
      style_rules: [],
      engagement_rules: [],
      aliases: [],
      trigger_keywords: [],
    }),
  };
}

function renderCharacterEditor() {
  const card = appState.active_character.card;
  $("cardName").value = card.name || "";
  $("systemPrompt").value = card.system_prompt || "";
  $("aliases").value = (card.aliases || []).join("\n");
  $("triggerKeywords").value = (card.trigger_keywords || []).join("\n");
  $("styleRules").value = (card.style_rules || []).join("\n");
  $("engagementRules").value = (card.engagement_rules || []).join("\n");
  $("approvalRequired").checked = strBool(appState.env.NHI_ZUES_PROACTIVE_APPROVAL_REQUIRED, true);
}

function renderSettings() {
  $("apiStatus").textContent = appState.app.api_key_set ? "API key set" : "API key missing";
  $("apiStatus").className = `status-pill ${appState.app.api_key_set ? "ok" : ""}`;
  const discord = appState.discord || {};
  $("discordStatus").textContent = discord.complete
    ? "Discord credentials are stored locally. Sign In opens the persistent browser profile and can fill them."
    : discord.email_set || discord.password_set
      ? "Partial Discord credentials are stored. Add the missing value or sign in manually."
      : "No stored Discord credentials. Enter them here or click Sign In and complete Discord manually.";
  $("discordEmail").value = "";
  $("discordPassword").value = "";
  const updates = appState.updates || {};
  $("updateStatus").textContent = updates.remote_allowed
    ? `Ready to update from ${updates.remote}.`
    : "GitHub origin is not configured yet. Update will be available after publishing.";
  $("openaiModel").value = appState.env.OPENAI_MODEL || appState.app.openai_model || "";
  renderModelOptions();
  $("llmEnabled").checked = strBool(appState.env.NHI_ZUES_LLM_ENABLED, false);
  $("draftDryRun").checked = strBool(appState.env.NHI_ZUES_DRAFT_IN_DRY_RUN, false);
  $("dryRun").checked = strBool(appState.env.NHI_ZUES_DRY_RUN, true);
  $("dailyBudget").value = appState.env.NHI_ZUES_MAX_DAILY_USD || "0.25";
  $("sessionBudget").value = appState.env.NHI_ZUES_MAX_SESSION_USD || "0.05";
  $("maxCalls").value = appState.env.NHI_ZUES_MAX_LLM_CALLS_PER_RUN || "3";
  $("mistakeRate").value = Math.round(Number(appState.env.NHI_ZUES_WRITING_MISTAKE_RATE || "0.06") * 100);
  $("writingQuirk").value = appState.env.NHI_ZUES_WRITING_QUIRK || "lowercase_no_commas";
  $("writingMisspellings").value = appState.env.NHI_ZUES_WRITING_MISSPELLINGS || "definitely:definately,because:becuase,probably:prolly";
  $("typingIndicatorEnabled").checked = strBool(appState.env.NHI_ZUES_TYPING_INDICATOR_ENABLED, true);
  $("typingMinSeconds").value = appState.env.NHI_ZUES_TYPING_MIN_SECONDS || "2.5";
  $("typingMaxSeconds").value = appState.env.NHI_ZUES_TYPING_MAX_SECONDS || "18.0";
  $("typingCharsPerSecond").value = appState.env.NHI_ZUES_TYPING_CHARS_PER_SECOND || "10.0";
}

function renderModelOptions() {
  const datalist = $("openaiModelOptions");
  const status = $("modelListStatus");
  if (!datalist || !status) return;
  const current = appState.env.OPENAI_MODEL || appState.app.openai_model || "";
  const models = Array.isArray(appState.model_options) ? appState.model_options : [];
  const byId = new Map();
  models.forEach((model) => {
    const id = typeof model === "string" ? model : model?.id;
    if (!id) return;
    byId.set(id, {
      id,
      label: typeof model === "string" ? model : model.label || model.id,
    });
  });
  if (current && !byId.has(current)) {
    byId.set(current, { id: current, label: `${current} - current setting` });
  }
  datalist.innerHTML = Array.from(byId.values())
    .map((model) => `<option value="${escapeAttr(model.id)}" label="${escapeAttr(model.label)}"></option>`)
    .join("");

  const catalog = appState.model_catalog || {};
  if (catalog.live) {
    const fetched = catalog.fetched_at ? ` Last refreshed ${formatTime(catalog.fetched_at)}.` : "";
    status.textContent = `${byId.size} model options loaded from ${catalog.source || "OpenAI"}.${fetched}`;
  } else {
    status.textContent = catalog.message || "Fallback model suggestions shown until models are refreshed.";
  }
}

function renderRuntime() {
  const runtime = appState.runtime || {};
  const running = Boolean(runtime.running);
  $("runtimeControl").innerHTML = running
    ? `<i class="bi bi-pause-fill"></i> Pause`
    : `<i class="bi bi-play-fill"></i> Start`;
  $("runtimeControl").className = running ? "secondary-button active-runtime" : "secondary-button";
  if (running) {
    $("runtimeStatus").textContent = appState.app.dry_run
      ? "scanner running - dry-run"
      : "scanner running - live sends allowed";
  } else {
    $("runtimeStatus").textContent = appState.app.dry_run
      ? "paused - dry-run"
      : "paused - live sends allowed";
  }
}

function renderGrowth() {
  const memory = appState.character_memory || {};
  const claims = memory.story_claims || [];
  const behavior = memory.behavior_notes || [];
  $("growthNotes").innerHTML =
    [...claims.map((note) => ["Story", note]), ...behavior.map((note) => ["Behavior", note])]
      .map(([type, note]) => `<div class="note-item"><strong>${type}</strong><br />${escapeHtml(note)}</div>`)
      .join("") || `<div class="note-item">No runtime growth notes yet.</div>`;

  const users = appState.memory.users || [];
  $("userList").innerHTML =
    users
      .map((user) => `
        <div class="user-item ${user.user_key === selectedUserKey ? "active" : ""}" data-user="${escapeAttr(user.user_key)}">
          <img src="/assets/placeholders/user.svg" alt="" />
          <div>
            <strong>${escapeHtml(user.display_name || user.user_key)}</strong>
            <span>${escapeHtml(user.user_key)} · ${user.message_count || 0} messages</span>
          </div>
        </div>
      `)
      .join("") || `<div class="note-item">No users observed yet.</div>`;
  document.querySelectorAll("[data-user]").forEach((row) => {
    row.addEventListener("click", () => {
      selectedUserKey = row.dataset.user;
      renderGrowth();
    });
  });
  renderSelectedUserDetails();
}

function renderSelectedUserDetails() {
  const user = (appState.memory.users || []).find((item) => item.user_key === selectedUserKey);
  const notes = (appState.user_instructions.items || []).filter((item) => item.user_key === selectedUserKey);
  $("selectedUserDetails").innerHTML = user
    ? `
      <div class="note-item">
        <strong>${escapeHtml(user.display_name || user.user_key)}</strong><br />
        ${escapeHtml(user.summary || "No long-form summary yet.")}<br />
        <span>Recent topics: ${escapeHtml((user.recent_topics || []).join(", ") || "none")}</span>
      </div>
      <div class="note-list compact-notes">
        ${notes.map((item) => `<div class="note-item"><strong>${escapeHtml(scopeLabel(item))}</strong><br />${escapeHtml(item.note)}</div>`).join("") || `<div class="note-item">No behavior notes for this user yet.</div>`}
      </div>
    `
    : `<div class="note-item">Select a user to add scoped behavior guidance.</div>`;
}

function renderApprovals() {
  const approvals = appState.approvals || [];
  $("approvalList").innerHTML =
    approvals
      .map((item) => `
        <div class="approval-item" data-approval-item="${escapeAttr(item.approval_id)}">
          <strong>${escapeHtml(item.character_name)} · #${escapeHtml(item.channel_id)}</strong>
          <span>${escapeHtml(item.reason)}</span>
          <textarea class="approval-draft" data-approval-draft="${escapeAttr(item.approval_id)}" rows="5">${escapeHtml(item.draft)}</textarea>
          ${recentPosterChips(item.channel_id, item.approval_id)}
          <textarea class="approval-instruction" data-approval-instruction="${escapeAttr(item.approval_id)}" rows="2" placeholder="Regeneration note: say it more like x, disagree with y, make it shorter..."></textarea>
          <div class="approval-actions">
            <button class="small-button" data-approval-save="${escapeAttr(item.approval_id)}"><i class="bi bi-save2"></i> Save</button>
            <button class="small-button" data-approval-regenerate="${escapeAttr(item.approval_id)}"><i class="bi bi-stars"></i> Regenerate</button>
            <button class="small-button" data-copy="${escapeAttr(item.approval_id)}"><i class="bi bi-copy"></i> Copy</button>
            <button class="small-button" data-approval-discard="${escapeAttr(item.approval_id)}"><i class="bi bi-trash3"></i> Discard</button>
            <button class="primary-button approval-send" data-approval-send="${escapeAttr(item.approval_id)}"><i class="bi bi-send"></i> Approve & Send</button>
          </div>
          ${appState.app.dry_run ? `<div class="approval-warning">Dry-run is on. Approved messages will be blocked until Dry-run mode is turned off in API & Runtime.</div>` : ""}
        </div>
      `)
      .join("") || `<div class="approval-item"><strong>No queued approvals</strong><span>Proactive drafts will appear here.</span></div>`;
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      await navigator.clipboard.writeText(approvalDraft(button.dataset.copy));
      toast("Draft copied");
    });
  });
  document.querySelectorAll("[data-approval-save]").forEach((button) => {
    button.addEventListener("click", () => saveApproval(button.dataset.approvalSave));
  });
  document.querySelectorAll("[data-approval-discard]").forEach((button) => {
    button.addEventListener("click", () => discardApproval(button.dataset.approvalDiscard));
  });
  document.querySelectorAll("[data-approval-regenerate]").forEach((button) => {
    button.addEventListener("click", () => regenerateApproval(button.dataset.approvalRegenerate));
  });
  document.querySelectorAll("[data-approval-send]").forEach((button) => {
    button.addEventListener("click", () => sendApproval(button.dataset.approvalSend));
  });
  document.querySelectorAll("[data-poster-target]").forEach((button) => {
    button.addEventListener("click", () => selectApprovalTarget(button.dataset.approvalId, button.dataset.posterKey, button.dataset.posterPrefix));
  });
}

function recentPosterChips(channelId, approvalId) {
  const posters = appState.recent_posters?.[channelId] || [];
  if (!posters.length) return `<div class="poster-chips muted">No recent posters recorded for this channel yet.</div>`;
  return `
    <div class="poster-chips">
      <span>Reply to</span>
      ${posters
        .map((poster) => `
          <button type="button" class="${approvalTargets[approvalId]?.user_key === poster.user_key ? "active" : ""}" data-approval-id="${escapeAttr(approvalId)}" data-poster-key="${escapeAttr(poster.user_key)}" data-poster-prefix="${escapeAttr(poster.reply_prefix)}" data-poster-target="true">
            ${escapeHtml(poster.display_name)}
          </button>
        `)
        .join("")}
    </div>
  `;
}

function approvalDraft(approvalId) {
  return document.querySelector(`[data-approval-draft="${cssEscape(approvalId)}"]`)?.value.trim() || "";
}

function insertReplyPrefix(approvalId, prefix) {
  const textarea = document.querySelector(`[data-approval-draft="${cssEscape(approvalId)}"]`);
  if (!textarea || !prefix) return;
  const current = textarea.value.trim();
  textarea.value = current.startsWith(prefix) ? current : `${prefix} ${current}`;
  textarea.focus();
}

function selectApprovalTarget(approvalId, userKey, prefix) {
  approvalTargets[approvalId] = { user_key: userKey, prefix };
  insertReplyPrefix(approvalId, prefix);
  document.querySelectorAll(`[data-approval-id="${cssEscape(approvalId)}"][data-poster-target]`).forEach((button) => {
    button.classList.toggle("active", button.dataset.posterKey === userKey);
  });
}

async function saveApproval(approvalId) {
  await api("/api/approval-update", {
    method: "POST",
    body: JSON.stringify({ approval_id: approvalId, draft: approvalDraft(approvalId) }),
  });
  await loadState();
  toast("Approval draft saved");
}

async function discardApproval(approvalId) {
  await api("/api/approval-discard", {
    method: "POST",
    body: JSON.stringify({ approval_id: approvalId }),
  });
  await loadState();
  toast("Approval discarded");
}

async function regenerateApproval(approvalId) {
  const instruction = document.querySelector(`[data-approval-instruction="${cssEscape(approvalId)}"]`)?.value.trim() || "";
  await api("/api/approval-regenerate", {
    method: "POST",
    body: JSON.stringify({
      approval_id: approvalId,
      draft: approvalDraft(approvalId),
      instruction,
      target_user_key: approvalTargets[approvalId]?.user_key || "",
    }),
  });
  await loadState();
  toast("Approval regenerated");
}

async function sendApproval(approvalId) {
  try {
    await api("/api/approval-send", {
      method: "POST",
      body: JSON.stringify({ approval_id: approvalId, draft: approvalDraft(approvalId) }),
    });
    await loadState();
    toast("Approved message sent");
  } catch (error) {
    await loadState().catch(() => {});
    toast(error.message);
  }
}

async function clearApprovals() {
  const approvals = appState.approvals || [];
  if (!approvals.length) {
    toast("No queued approvals");
    return;
  }
  if (!confirm(`Clear ${approvals.length} queued approval draft${approvals.length === 1 ? "" : "s"}? Nothing will be sent.`)) {
    return;
  }
  const result = await api("/api/approvals-clear", { method: "POST", body: JSON.stringify({}) });
  appState = result.state;
  render();
  toast(`Cleared ${result.cleared || 0} queued approval${result.cleared === 1 ? "" : "s"}`);
}

function renderMetrics() {
  $("dailySpend").textContent = `$${Number(appState.usage.daily_spend_usd || 0).toFixed(6)}`;
  $("usageCalls").textContent = appState.usage.records || 0;
  $("memoryUsers").textContent = appState.memory.user_count || 0;
  $("seenMessages").textContent = appState.memory.seen_ids || 0;
  $("triggerState").textContent = channel()?.engage_enabled ? "eligible" : "disabled";
}

function renderObserved() {
  const current = channel();
  const observed = current ? appState.observed?.[current.channel_id] : null;
  if (!observed) {
    $("observedConversation").innerHTML = `<div class="note-item">No observed messages for this channel yet.</div>`;
    return;
  }
  $("observedConversation").innerHTML =
    (observed.poster_summaries || [])
      .map((poster) => `
        <div class="observed-card">
          <div>
            <strong>${escapeHtml(poster.display_name)}</strong>
            <span>${escapeHtml(poster.summary)}</span>
          </div>
          <button class="small-button" data-suggest-user="${escapeAttr(poster.user_key)}"><i class="bi bi-chat-left-text"></i> Suggest</button>
        </div>
      `)
      .join("") || `<div class="note-item">No recent unique posters recorded.</div>`;
  document.querySelectorAll("[data-suggest-user]").forEach((button) => {
    button.addEventListener("click", () => createSuggestedApproval(button.dataset.suggestUser));
  });
}

function renderHistory() {
  const current = channel();
  const history = current ? appState.history?.[current.channel_id] : null;
  const messages = history?.messages || [];
  const events = history?.events || [];
  $("historyMessageTitle").textContent = current
    ? `${formatChannelName(current.label || current.channel_id, current.channel_type)} conversation`
    : "Selected Channel Conversation";
  $("historyMessages").innerHTML =
    messages
      .slice(-40)
      .map((message) => `
        <div class="history-item">
          <strong>${escapeHtml(message.author)}</strong>
          <span>${escapeHtml(formatTime(message.observed_at))}</span>
          <p>${escapeHtml(message.text)}</p>
        </div>
      `)
      .join("") || emptyHistoryMessage();
  $("historyEvents").innerHTML =
    events
      .slice(-40)
      .map((event) => `
        <div class="history-item event">
          <strong>${escapeHtml(event.event_type)}</strong>
          <span>${escapeHtml(formatTime(event.created_at))}</span>
          <p>${escapeHtml(event.summary || event.draft || "")}</p>
        </div>
      `)
      .join("") || `<div class="note-item">No approval or response events recorded yet.</div>`;
}

function emptyHistoryMessage() {
  const channelsWithHistory = channels()
    .filter((item) => historyCount(item.channel_id) > 0)
    .slice(0, 5)
    .map((item) => `${formatChannelName(item.label || item.channel_id, item.channel_type)} (${historyCount(item.channel_id)})`)
    .join(", ");
  return channelsWithHistory
    ? `<div class="note-item">No remembered messages for the selected channel yet. Channels with history here: ${escapeHtml(channelsWithHistory)}.</div>`
    : `<div class="note-item">No channel history recorded yet. Enable Observe, then run Start or scan once.</div>`;
}

async function createSuggestedApproval(userKey) {
  const currentServer = server();
  const currentChannel = channel();
  if (!currentServer || !currentChannel) return;
  await api("/api/approval-create", {
    method: "POST",
    body: JSON.stringify({
      server_id: currentServer.server_id,
      channel_id: currentChannel.channel_id,
      target_user_key: userKey,
      instruction: "Suggest a natural response to this user's recent point using the selected character.",
    }),
  });
  await loadState();
  toast("Suggested response queued for approval");
}

function syncFormsToState() {
  const srv = server();
  srv.label = $("serverLabel").value.trim();
  srv.character_card = $("serverCharacter").value || null;
  srv.poll_seconds = Number($("serverPoll").value || 120);
  const current = channel();
  if (current) current.auto_respond_enabled = $("channelAutoRespond").checked;

  const card = appState.active_character.card;
  card.name = $("cardName").value.trim();
  card.system_prompt = $("systemPrompt").value.trim();
  card.aliases = lines("aliases");
  card.trigger_keywords = lines("triggerKeywords");
  card.style_rules = lines("styleRules");
  card.engagement_rules = lines("engagementRules");
}

async function saveAll() {
  syncFormsToState();
  const settings = {
    OPENAI_MODEL: $("openaiModel").value.trim(),
    NHI_ZUES_LLM_ENABLED: $("llmEnabled").checked,
    NHI_ZUES_DRAFT_IN_DRY_RUN: $("draftDryRun").checked,
    NHI_ZUES_DRY_RUN: $("dryRun").checked,
    NHI_ZUES_PROACTIVE_APPROVAL_REQUIRED: $("approvalRequired").checked,
    NHI_ZUES_CHARACTER_CARD: appState.env.NHI_ZUES_CHARACTER_CARD || appState.active_character.path,
    NHI_ZUES_MAX_DAILY_USD: $("dailyBudget").value,
    NHI_ZUES_MAX_SESSION_USD: $("sessionBudget").value,
    NHI_ZUES_MAX_LLM_CALLS_PER_RUN: $("maxCalls").value,
    NHI_ZUES_WRITING_MISTAKE_RATE: String(Math.max(0, Math.min(Number($("mistakeRate").value || 0), 35)) / 100),
    NHI_ZUES_WRITING_QUIRK: $("writingQuirk").value,
    NHI_ZUES_WRITING_MISSPELLINGS: $("writingMisspellings").value.trim(),
    NHI_ZUES_TYPING_INDICATOR_ENABLED: $("typingIndicatorEnabled").checked,
    NHI_ZUES_TYPING_MIN_SECONDS: $("typingMinSeconds").value,
    NHI_ZUES_TYPING_MAX_SECONDS: $("typingMaxSeconds").value,
    NHI_ZUES_TYPING_CHARS_PER_SECOND: $("typingCharsPerSecond").value,
  };
  if ($("apiKey").value.trim()) settings.OPENAI_API_KEY = $("apiKey").value.trim();
  await api("/api/servers", { method: "POST", body: JSON.stringify(appState.servers) });
  await api("/api/character", {
    method: "POST",
    body: JSON.stringify(appState.active_character),
  });
  await api("/api/settings", { method: "POST", body: JSON.stringify(settings) });
  $("apiKey").value = "";
  await loadState();
  toast("Settings saved");
}

async function syncDiscordServers() {
  syncFormsToState();
  await api("/api/servers", { method: "POST", body: JSON.stringify(appState.servers) });
  const result = await api("/api/discord-sync-servers", { method: "POST", body: JSON.stringify({}) });
  appState = result.state;
  selectedServer = Math.min(selectedServer, servers().length - 1);
  if (selectedServer < 0) selectedServer = 0;
  selectedChannel = Math.min(selectedChannel, channels().length - 1);
  if (selectedChannel < 0) selectedChannel = 0;
  render();
  toast(`Synced ${result.discovered} servers and ${result.channels_discovered || 0} channels`);
}

async function saveDiscordCredentials() {
  const email = $("discordEmail").value.trim();
  const password = $("discordPassword").value;
  if (!email && !password) {
    toast("Enter a Discord email or password to save");
    return;
  }
  await api("/api/discord-credentials", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  $("discordEmail").value = "";
  $("discordPassword").value = "";
  await loadState();
  toast("Discord credentials saved locally");
}

async function launchDiscordLogin() {
  const email = $("discordEmail").value.trim();
  const password = $("discordPassword").value;
  if (email || password) {
    await api("/api/discord-credentials", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    $("discordEmail").value = "";
    $("discordPassword").value = "";
  }
  await api("/api/discord-login", { method: "POST", body: JSON.stringify({}) });
  await loadState();
  toast("Discord sign-in window launched");
}

async function openDiscordChannel() {
  const currentServer = server();
  const currentChannel = channel();
  if (!currentServer?.server_id || !currentChannel?.channel_id) {
    toast("Select a channel first");
    return;
  }
  await api("/api/open-discord-channel", {
    method: "POST",
    body: JSON.stringify({
      server_id: currentServer.server_id,
      channel_id: currentChannel.channel_id,
    }),
  });
  await loadState();
  toast("Discord channel window launched");
}

async function checkUpdates() {
  const result = await api("/api/update-check", { method: "POST", body: JSON.stringify({}) });
  renderUpdateResult(result);
}

async function applyUpdate() {
  const result = await api("/api/update", { method: "POST", body: JSON.stringify({}) });
  renderUpdateResult(result);
}

async function refreshOpenAIModels() {
  $("modelListStatus").textContent = "Fetching models from OpenAI...";
  const result = await api("/api/openai-models", { method: "POST", body: JSON.stringify({}) });
  appState.model_options = result.models || appState.model_options || [];
  appState.model_catalog = {
    live: Boolean(result.live),
    source: result.source || "",
    message: result.message || "",
    fetched_at: result.fetched_at || "",
  };
  renderModelOptions();
  toast(result.message || "Model list refreshed");
}

async function toggleRuntime() {
  const runtime = appState.runtime || {};
  const path = runtime.running ? "/api/runtime-pause" : "/api/runtime-start";
  const result = await api(path, { method: "POST", body: JSON.stringify({}) });
  appState = result.state;
  render();
  toast(appState.runtime.running ? "Scanner started" : "Scanner paused");
}

function renderUpdateResult(result) {
  const message = result.ok
    ? result.update_available
      ? `Update available: ${result.behind} commit(s) behind.`
      : result.message || "Kabuki-Cord is up to date."
    : result.error || "Update check failed.";
  $("updateStatus").textContent = message;
  toast(message);
}

function lines(id) {
  return $(id)
    .value.split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function strBool(value, fallback) {
  if (value === undefined || value === null || value === "") return fallback;
  return String(value).toLowerCase() === "true";
}

function historyCount(channelId) {
  return appState.history?.[channelId]?.messages?.length || 0;
}

function scopeLabel(item) {
  if (item.channel_id) {
    const match = findChannel(item.server_id, item.channel_id);
    return `${match.serverLabel} / ${formatChannelName(match.channelLabel, match.channelType)}`;
  }
  if (item.server_id) return findServerLabel(item.server_id);
  return "All servers";
}

function findServerLabel(serverId) {
  const match = servers().find((srv) => srv.server_id === serverId);
  return match?.label || `Server ${serverId}`;
}

function findChannel(serverId, channelId) {
  const srv = servers().find((item) => item.server_id === serverId) || {};
  const chan = (srv.channels || []).find((item) => item.channel_id === channelId) || {};
  return {
    serverLabel: srv.label || `Server ${serverId}`,
    channelLabel: chan.label || channelId,
    channelType: chan.channel_type || "text",
  };
}

function userNoteScopePayload() {
  const scope = $("userNoteScope").value;
  if (scope === "channel" && channel()) {
    return { server_id: server().server_id, channel_id: channel().channel_id };
  }
  if (scope === "server" && server()) {
    return { server_id: server().server_id };
  }
  return {};
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function channelTypeLabel(type) {
  if (type === "forum") return "forum channel";
  if (type === "announcement") return "announcement channel";
  if (type === "voice") return "voice channel";
  if (type === "stage") return "stage channel";
  if (type === "text") return "text channel";
  return "";
}

function formatChannelName(name, type) {
  if (!name) return "";
  if ((type === "text" || type === "forum" || type === "announcement" || !type) && !String(name).startsWith("#")) {
    return `# ${name}`;
  }
  return name;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("'", "&#39;");
}

function cssEscape(value) {
  if (window.CSS?.escape) return CSS.escape(value || "");
  return String(value || "").replaceAll('"', '\\"');
}

function toast(message) {
  $("toast").textContent = message;
  $("toast").classList.add("show");
  setTimeout(() => $("toast").classList.remove("show"), 2400);
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    $(tab.dataset.tab).classList.add("active");
  });
});

$("refresh").addEventListener("click", loadState);
$("runtimeControl").addEventListener("click", () => toggleRuntime().catch((error) => toast(error.message)));
$("saveAll").addEventListener("click", saveAll);
$("saveServers").addEventListener("click", saveAll);
$("syncDiscordServers").addEventListener("click", () => syncDiscordServers().catch((error) => toast(error.message)));
$("saveDiscord").addEventListener("click", saveDiscordCredentials);
$("launchDiscordLogin").addEventListener("click", launchDiscordLogin);
$("openDiscordChannel").addEventListener("click", () => openDiscordChannel().catch((error) => toast(error.message)));
$("refreshOpenAIModels").addEventListener("click", () => refreshOpenAIModels().catch((error) => toast(error.message)));
$("clearApprovals").addEventListener("click", () => clearApprovals().catch((error) => toast(error.message)));
$("checkUpdates").addEventListener("click", checkUpdates);
$("applyUpdate").addEventListener("click", applyUpdate);

$("addChannel").addEventListener("click", () => {
  const id = prompt("Discord channel ID");
  if (!id) return;
  channels().push({
    channel_id: id.trim(),
    label: "",
    scan_enabled: true,
    engage_enabled: false,
    auto_respond_enabled: false,
  });
  selectedChannel = channels().length - 1;
  render();
});

$("channelAutoRespond").addEventListener("change", () => {
  const current = channel();
  if (current) current.auto_respond_enabled = $("channelAutoRespond").checked;
  renderServerPanel();
});

$("addStoryNote").addEventListener("click", async () => {
  const note = $("newStoryNote").value.trim();
  if (!note) return;
  await api("/api/character-memory", {
    method: "POST",
    body: JSON.stringify({
      card_id: appState.env.NHI_ZUES_CHARACTER_CARD || appState.active_character.path,
      type: "story",
      note,
    }),
  });
  $("newStoryNote").value = "";
  await loadState();
  toast("Story note added");
});

$("addUserNote").addEventListener("click", async () => {
  if (!selectedUserKey) {
    toast("Select a user first");
    return;
  }
  const note = $("newUserNote").value.trim();
  if (!note) return;
  await api("/api/user-instruction", {
    method: "POST",
    body: JSON.stringify({ user_key: selectedUserKey, note, ...userNoteScopePayload() }),
  });
  $("newUserNote").value = "";
  await loadState();
  toast("User note added");
});

loadState().catch((error) => {
  console.error(error);
  toast("Failed to load Kabuki-Cord state");
});
