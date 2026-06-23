let appState = null;
let selectedServer = 0;
let selectedChannel = 0;
let selectedUserKey = null;
let apiToken = null;
let previewPanelMode = "preview";
let unreadEventCount = 0;
let autoRefreshTimer = null;
let refreshInFlight = false;
const approvalTargets = {};
const approvalDeliveryState = {};
const approvalRegenerationState = {};
const activeOperations = new Map();
let knownEventKeys = new Set();

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
  let response;
  try {
    response = await fetch(path, {
      headers: {
        "Content-Type": "application/json",
        ...(apiToken ? { "X-Kabuki-Token": apiToken } : {}),
        ...headers,
      },
      ...rest,
    });
  } catch {
    throw new Error("Kabuki-Cord did not respond. Restart the app, then retry. If it keeps happening, check Events for the last backend error.");
  }
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

async function loadState(options = {}) {
  if (refreshInFlight && options.background) return;
  refreshInFlight = true;
  const previousEventKeys = new Set(knownEventKeys);
  const hadState = Boolean(appState);
  try {
    appState = await api("/api/state");
    selectedServer = Math.min(selectedServer, servers().length - 1);
    if (selectedServer < 0) selectedServer = 0;
    selectedChannel = Math.min(selectedChannel, channels().length - 1);
    if (selectedChannel < 0) selectedChannel = 0;
    render();
    syncEventNotifications({
      previousEventKeys,
      notify: Boolean(options.notify && hadState),
    });
    startAutoRefresh();
  } finally {
    refreshInFlight = false;
  }
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

function visibleChannels() {
  return channels()
    .map((chan, index) => ({ ...chan, __index: index }))
    .sort((left, right) => {
      if (Boolean(left.pinned) !== Boolean(right.pinned)) return left.pinned ? -1 : 1;
      return left.__index - right.__index;
    });
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
  renderEventsPanel();
  renderPreviewTabs();
  renderOperationStatus();
}

function renderRail() {
  $("serverRail").innerHTML = servers()
    .map((srv, index) => {
      const label = srv.label || `S${index + 1}`;
      const icon = srv.icon_path || srv.icon_url || "/assets/placeholders/server.svg";
      const railLabel = compactServerRailLabel(label, index);
      return `
        <button class="server-bubble ${index === selectedServer ? "active" : ""}" data-server="${index}" title="${escapeHtml(label)}">
          <span class="server-icon-frame">
            <img src="${escapeAttr(icon)}" alt="" onerror="this.src='/assets/placeholders/server.svg'" />
          </span>
          <span class="server-bubble-label">${escapeHtml(railLabel)}</span>
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

function compactServerRailLabel(label, index) {
  const cleaned = String(label || "").replace(/\s+/g, " ").trim();
  if (!cleaned) return `Server ${index + 1}`.slice(0, 10);
  return Array.from(cleaned).slice(0, 10).join("");
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

  $("channelList").innerHTML = visibleChannels()
    .map((chan) => {
      const index = chan.__index;
      const name = chan.label || chan.channel_id;
      const type = channelTypeLabel(chan.channel_type);
      const remembered = historyCount(chan.channel_id);
      const metaBase = [type, chan.category].filter(Boolean).join(" - ") || `ID ${chan.channel_id || ""}`;
      const metaParts = [metaBase];
      if (chan.pinned) metaParts.push("pinned");
      if (remembered) metaParts.push(`${remembered} remembered`);
      const meta = metaParts.filter(Boolean).join(" - ");
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
            <button class="icon-mini pin ${chan.pinned ? "on" : ""}" data-pin-channel="${index}" title="${chan.pinned ? "Unpin channel" : "Pin channel to top"}"><i class="bi bi-pin-angle${chan.pinned ? "-fill" : ""}"></i></button>
            <button class="pill-toggle observe ${chan.scan_enabled ? "on" : ""}" data-toggle="scan" data-channel="${index}">Observe</button>
            <button class="pill-toggle engage ${chan.engage_enabled ? "on" : ""}" data-toggle="engage" data-channel="${index}">Engage</button>
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
      render();
    });
  });
  document.querySelectorAll("[data-pin-channel]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const chan = channels()[Number(button.dataset.pinChannel)];
      if (!chan) return;
      chan.pinned = !chan.pinned;
      renderServerPanel();
    });
  });

  const current = channel();
  $("channelAutoRespond").checked = Boolean(current?.auto_respond_enabled);
  $("approvalState").textContent = runtimeModeLabel(currentRuntimeMode());
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
  $("approvalRequired").checked = currentRuntimeMode() !== "full_auto";
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
  $("runtimeMode").value = currentRuntimeMode();
  $("llmEnabled").checked = strBool(appState.env.NHI_ZUES_LLM_ENABLED, false);
  $("draftDryRun").checked = strBool(appState.env.NHI_ZUES_DRAFT_IN_DRY_RUN, false);
  $("conversationReply").checked = strBool(appState.env.NHI_ZUES_CONVERSATION_REPLY_ENABLED, false);
  $("headlessMode").checked = strBool(appState.env.NHI_ZUES_HEADLESS, false);
  $("dryRun").checked = currentRuntimeMode() === "dry";
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
  const browserMode = appState.app.headless ? "hidden browser" : "visible browser";
  $("runtimeControl").innerHTML = running
    ? `<i class="bi bi-pause-fill"></i> Pause`
    : `<i class="bi bi-play-fill"></i> Start`;
  $("runtimeControl").className = running ? "secondary-button active-runtime" : "secondary-button";
  const mode = runtimeModeLabel(currentRuntimeMode());
  if (running) {
    $("runtimeStatus").textContent = `scanner running - ${mode} - ${browserMode}`;
  } else {
    $("runtimeStatus").textContent = `paused - ${mode} - ${browserMode}`;
  }
}

function renderOperationStatus() {
  const el = $("operationStatus");
  if (!el) return;
  const active = Array.from(activeOperations.values()).at(-1);
  if (active) {
    el.className = `operation-status active ${escapeAttr(active.kind || "working")}`;
    el.innerHTML = `
      ${scannerSprite(active.kind || "working")}
      <span>${escapeHtml(active.label)}</span>
      ${active.detail ? `<small>${escapeHtml(active.detail)}</small>` : ""}
    `;
    return;
  }
  const runtime = appState?.runtime || {};
  if (runtime.running) {
    el.className = "operation-status scanning";
    el.innerHTML = `
      ${scannerSprite("scanning")}
      <span>Scanner running</span>
      <small>${escapeHtml(formatRuntimeTime(runtime.last_run_at))}</small>
    `;
    return;
  }
  el.className = "operation-status idle";
  el.innerHTML = `
    ${scannerSprite(runtime.last_error ? "error" : "idle")}
    <span>Idle</span>
    <small>${escapeHtml(runtime.last_error || runtimeModeLabel(currentRuntimeMode()))}</small>
  `;
}

function scannerSprite(state = "idle") {
  const safeState = String(state || "idle").toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
  return `<span class="scanner-sprite scanner-sprite-${escapeAttr(safeState)}" aria-hidden="true"></span>`;
}

function startOperation(id, label, detail = "", kind = "working", icon = "bi-arrow-repeat") {
  activeOperations.set(id, { label, detail, kind, icon });
  renderOperationStatus();
}

function updateOperation(id, detail) {
  const existing = activeOperations.get(id);
  if (!existing) return;
  activeOperations.set(id, { ...existing, detail });
  renderOperationStatus();
}

function finishOperation(id, label = "", kind = "idle", icon = "bi-check-circle") {
  if (label) {
    activeOperations.set(id, { label, detail: "", kind, icon });
    renderOperationStatus();
    setTimeout(() => {
      activeOperations.delete(id);
      renderOperationStatus();
    }, 1200);
    return;
  }
  activeOperations.delete(id);
  renderOperationStatus();
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
      .map((item) => {
        const delivery = approvalDeliveryState[item.approval_id] || null;
        const sending = delivery?.state === "sending";
        const regenerating = approvalRegenerationState[item.approval_id]?.state === "regenerating";
        return `
        <div class="approval-item" data-approval-item="${escapeAttr(item.approval_id)}">
          <strong>${escapeHtml(item.character_name)} · #${escapeHtml(item.channel_id)}</strong>
          <span>${escapeHtml(item.reason)}</span>
          <textarea class="approval-draft" data-approval-draft="${escapeAttr(item.approval_id)}" rows="5">${escapeHtml(item.draft)}</textarea>
          ${recentPosterChips(item.channel_id, item.approval_id)}
          <textarea class="approval-instruction" data-approval-instruction="${escapeAttr(item.approval_id)}" rows="2" placeholder="Regeneration note: say it more like x, disagree with y, make it shorter..."></textarea>
          ${approvalRegenerationStatus(item.approval_id)}
          ${approvalDeliveryStatus(item.approval_id)}
          <div class="approval-actions">
            <button class="small-button" data-approval-save="${escapeAttr(item.approval_id)}"><i class="bi bi-save2"></i> Save</button>
            <button class="small-button" data-approval-regenerate="${escapeAttr(item.approval_id)}" ${regenerating ? "disabled" : ""}><i class="bi ${regenerating ? "bi-hourglass-split" : "bi-stars"}"></i> ${regenerating ? "Regenerating" : "Regenerate"}</button>
            <button class="small-button" data-approval-open="${escapeAttr(item.approval_id)}"><i class="bi bi-box-arrow-up-right"></i> Open Conversation</button>
            <button class="small-button" data-copy="${escapeAttr(item.approval_id)}"><i class="bi bi-copy"></i> Copy</button>
            <button class="small-button" data-approval-discard="${escapeAttr(item.approval_id)}"><i class="bi bi-trash3"></i> Discard</button>
            <button class="primary-button approval-send" data-approval-send="${escapeAttr(item.approval_id)}" ${sending ? "disabled" : ""}><i class="bi ${sending ? "bi-hourglass-split" : "bi-send"}"></i> ${sending ? "Sending" : "Approve & Send"}</button>
          </div>
          ${currentRuntimeMode() === "dry" ? `<div class="approval-warning">Dry Mode is on. Approved messages will be blocked until Response Mode changes in API & Runtime.</div>` : ""}
        </div>
      `;
      })
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
  document.querySelectorAll("[data-approval-open]").forEach((button) => {
    button.addEventListener("click", () => openApprovalConversation(button.dataset.approvalOpen).catch((error) => toast(error.message)));
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

function approvalDeliveryStatus(approvalId) {
  const delivery = approvalDeliveryState[approvalId];
  if (!delivery) return "";
  const icon = delivery.state === "failed"
    ? "bi-exclamation-triangle"
    : delivery.state === "sent"
      ? "bi-check-circle"
      : "bi-hourglass-split";
  return `
    <div class="approval-delivery-status ${escapeAttr(delivery.state)}">
      <i class="bi ${icon}"></i>
      <span>${escapeHtml(delivery.message)}</span>
    </div>
  `;
}

function approvalRegenerationStatus(approvalId) {
  const state = approvalRegenerationState[approvalId];
  if (!state) return "";
  const isFailed = state.state === "failed";
  return `
    <div class="approval-delivery-status ${isFailed ? "failed" : ""}">
      <i class="bi ${isFailed ? "bi-exclamation-triangle" : "bi-hourglass-split"}"></i>
      <span>${escapeHtml(state.message || "Regenerating draft. Waiting for model response...")}</span>
    </div>
  `;
}

function insertReplyPrefix(approvalId, prefix) {
  const textarea = document.querySelector(`[data-approval-draft="${cssEscape(approvalId)}"]`);
  if (!textarea || !prefix) return;
  const current = textarea.value.trim();
  const withoutOldPrefix = current
    .replace(/^<@!?\d+>\s+/, "")
    .replace(/^@\S+(?:\s+\S+){0,3}\s+/, "")
    .trim();
  textarea.value = current.startsWith(prefix) ? current : `${prefix} ${withoutOldPrefix || current}`;
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
  if (approvalRegenerationState[approvalId]?.state === "regenerating") return;
  const instruction = document.querySelector(`[data-approval-instruction="${cssEscape(approvalId)}"]`)?.value.trim() || "";
  const draft = approvalDraft(approvalId);
  const opId = `regenerate:${approvalId}`;
  startOperation(opId, "Regenerating draft", "Waiting for OpenAI response", "api", "bi-stars");
  approvalRegenerationState[approvalId] = {
    state: "regenerating",
    message: "Regenerating draft. Waiting for model response...",
  };
  renderApprovals();
  toast("Regenerating draft...");
  try {
    const result = await api("/api/approval-regenerate", {
      method: "POST",
      body: JSON.stringify({
        approval_id: approvalId,
        draft,
        instruction,
        target_user_key: approvalTargets[approvalId]?.user_key || "",
      }),
    });
    delete approvalRegenerationState[approvalId];
    appState = result.state || (await api("/api/state"));
    render();
    finishOperation(opId, "Draft regenerated", "done", "bi-check-circle");
    toast("Approval regenerated");
  } catch (error) {
    approvalRegenerationState[approvalId] = {
      state: "failed",
      message: error.message,
    };
    renderApprovals();
    finishOperation(opId, "Regeneration failed", "failed", "bi-exclamation-triangle");
    toast(error.message);
  }
}

async function sendApproval(approvalId) {
  if (approvalDeliveryState[approvalId]?.state === "sending") return;
  const draft = approvalDraft(approvalId);
  const opId = `send:${approvalId}`;
  startOperation(opId, "Posting approved reply", "Opening Discord and waiting for delivery", "discord", "bi-send");
  approvalDeliveryState[approvalId] = {
    state: "sending",
    message: "Processing approved message. Waiting for Discord delivery...",
  };
  renderApprovals();
  toast("Processing approved message...");
  try {
    await api("/api/approval-send", {
      method: "POST",
      body: JSON.stringify({
        approval_id: approvalId,
        draft,
        reply_to_message_id: approvalReplyMessageId(approvalId),
      }),
    });
    approvalDeliveryState[approvalId] = {
      state: "sent",
      message: "Posted successfully to Discord.",
    };
    updateOperation(opId, "Refreshing channel and resuming scanner");
    await loadState();
    finishOperation(opId, "Posted and scanning", "done", "bi-check-circle");
    toast("Posted successfully to Discord");
  } catch (error) {
    approvalDeliveryState[approvalId] = {
      state: "failed",
      message: error.message,
    };
    await loadState().catch(() => {});
    finishOperation(opId, "Post failed", "failed", "bi-exclamation-triangle");
    toast(error.message);
  }
}

function approvalReplyMessageId(approvalId) {
  const target = approvalTargets[approvalId];
  if (!appState) return "";
  const approval = (appState.approvals || []).find((item) => item.approval_id === approvalId);
  if (!approval?.channel_id) return "";
  const fallbackSourceId = (approval.source_message_ids || []).at(-1) || "";
  if (!target?.user_key) return fallbackSourceId;
  const posters = appState.recent_posters?.[approval.channel_id] || [];
  const poster = posters.find((item) => item.user_key === target.user_key);
  return (
    poster?.message_id ||
    poster?.latest_message_id ||
    poster?.source_message_id ||
    fallbackSourceId ||
    ""
  );
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
  const daily = `$${Number(appState.usage.daily_spend_usd || 0).toFixed(6)}`;
  const calls = Number(appState.usage.records || 0);
  $("dailySpend").textContent = daily;
  $("usageCalls").textContent = calls;
  $("topDailySpend").textContent = daily;
  $("topUsageCalls").textContent = `${calls} call${calls === 1 ? "" : "s"}`;
  $("memoryUsers").textContent = appState.memory.user_count || 0;
  $("seenMessages").textContent = appState.memory.seen_ids || 0;
  $("triggerState").textContent = channel()?.engage_enabled ? "eligible" : "disabled";
}

function renderPreviewTabs() {
  document.querySelectorAll("[data-preview-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.previewTab === previewPanelMode);
  });
  $("previewMode").classList.toggle("active", previewPanelMode === "preview");
  $("eventsMode").classList.toggle("active", previewPanelMode === "events");
  renderEventBadge();
}

function renderEventsPanel() {
  renderRuntimeCheckSummary();
  renderResponseHistory();
  renderEventFeed();
}

function renderRuntimeCheckSummary() {
  const runtime = appState.runtime || {};
  const activeChannels = configuredChannels().filter((item) => item.scan_enabled);
  const engagedChannels = activeChannels.filter((item) => item.engage_enabled);
  $("runtimeCheckSummary").innerHTML = `
    <div><span>Status</span><strong>${escapeHtml(runtime.running ? "running" : "paused")}</strong></div>
    <div><span>Last check</span><strong>${escapeHtml(formatRuntimeTime(runtime.last_run_at))}</strong></div>
    <div><span>Observed</span><strong>${activeChannels.length}</strong></div>
    <div><span>Engage</span><strong>${engagedChannels.length}</strong></div>
    <div><span>Mode</span><strong>${escapeHtml(runtimeModeLabel(currentRuntimeMode()))}</strong></div>
    <div><span>Last issue</span><strong>${escapeHtml(runtime.last_error || "none")}</strong></div>
  `;
}

function renderResponseHistory() {
  const responseEvents = allEvents()
    .filter((event) => [
      "message_sent",
      "approval_sent",
      "approval_queued",
      "manual_approval_created",
      "approval_send_started",
      "duplicate_reply_blocked",
      "approval_regenerated",
      "approval_send_failed",
      "dry_run",
      "auto_respond_dry_run",
    ].includes(event.event_type))
    .slice(0, 30);
  $("responseHistory").innerHTML =
    responseEvents.map(renderEventCard).join("") ||
    `<div class="note-item">No drafts, approvals, or sent responses recorded yet.</div>`;
}

function renderEventFeed() {
  const events = allEvents().slice(0, 60);
  $("eventFeed").innerHTML =
    events.map(renderEventCard).join("") ||
    `<div class="note-item">No runtime events recorded yet.</div>`;
}

function renderEventCard(event) {
  const detail = event.draft || event.summary || "";
  return `
    <div class="event-card ${eventClass(event)}">
      <strong>${escapeHtml(eventTypeLabel(event))}</strong>
      <span>${escapeHtml(formatTime(event.created_at))} · ${escapeHtml(eventScope(event))}</span>
      ${detail ? `<p>${escapeHtml(detail)}</p>` : ""}
    </div>
  `;
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
          <div class="observed-copy">
            <strong>${escapeHtml(poster.display_name)}</strong>
            <span>${escapeHtml(poster.summary)}</span>
          </div>
          <div class="observed-actions">
            <button
              class="small-button"
              data-suggest-user="${escapeAttr(poster.user_key)}"
              title="Draft a suggested reply to this user's recent point."
            ><i class="bi bi-chat-left-text"></i> Suggest Reply</button>
            <button
              class="small-button"
              data-guide-user="${escapeAttr(poster.user_key)}"
              title="Add per-user behavior guidance for future replies."
            ><i class="bi bi-person-gear"></i> Guide User</button>
          </div>
        </div>
      `)
      .join("") || `<div class="note-item">No recent unique posters recorded.</div>`;
  document.querySelectorAll("[data-suggest-user]").forEach((button) => {
    button.addEventListener("click", () => createSuggestedApproval(button.dataset.suggestUser));
  });
  document.querySelectorAll("[data-guide-user]").forEach((button) => {
    button.addEventListener("click", () => openUserGuidance(button.dataset.guideUser));
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
      .reverse()
      .map((message) => `
        <div class="history-item">
          <div class="history-item-header">
            <div>
              <strong>${escapeHtml(message.author)}</strong>
              <span>${escapeHtml(formatTime(message.observed_at))}</span>
            </div>
            <button
              class="small-button"
              data-respond-message="${escapeAttr(message.message_id || "")}"
              data-respond-user="${escapeAttr(message.user_key || "")}"
            ><i class="bi bi-reply"></i> Respond</button>
            <button
              class="small-button"
              data-history-guide-user="${escapeAttr(message.user_key || "")}"
            ><i class="bi bi-person-gear"></i> Guide</button>
          </div>
          <p>${escapeHtml(message.text)}</p>
        </div>
      `)
      .join("") || emptyHistoryMessage();
  document.querySelectorAll("[data-respond-message]").forEach((button) => {
    button.addEventListener("click", () => createMessageApproval(
      button.dataset.respondMessage,
      button.dataset.respondUser,
    ));
  });
  document.querySelectorAll("[data-history-guide-user]").forEach((button) => {
    button.addEventListener("click", () => openUserGuidance(button.dataset.historyGuideUser));
  });
  $("historyEvents").innerHTML =
    events
      .slice(-40)
      .reverse()
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
  const opId = `suggest:${currentChannel.channel_id}:${userKey || "recent"}`;
  startOperation(opId, "Drafting suggested reply", "Waiting for OpenAI response", "api", "bi-chat-left-text");
  toast("Generating suggested response...");
  try {
    const result = await api("/api/approval-create", {
      method: "POST",
      body: JSON.stringify({
        server_id: currentServer.server_id,
        channel_id: currentChannel.channel_id,
        target_user_key: userKey,
        instruction: "Suggest a natural response to this user's recent point using the selected character.",
      }),
    });
    appState = result.state || (await api("/api/state"));
    render();
    finishOperation(opId, "Approval queued", "done", "bi-check-circle");
    toast("Suggested response queued for approval");
  } catch (error) {
    await loadState().catch(() => {});
    finishOperation(opId, "Draft failed", "failed", "bi-exclamation-triangle");
    toast(error.message);
  }
}

async function createMessageApproval(messageId, userKey) {
  const currentServer = server();
  const currentChannel = channel();
  if (!currentServer || !currentChannel || !messageId) {
    toast("Select a remembered message first");
    return;
  }
  const opId = `message-approval:${messageId}`;
  startOperation(opId, "Drafting response", "Using selected message context", "api", "bi-reply");
  toast("Generating response for selected message...");
  try {
    const result = await api("/api/approval-create", {
      method: "POST",
      body: JSON.stringify({
        server_id: currentServer.server_id,
        channel_id: currentChannel.channel_id,
        target_user_key: userKey || "",
        target_message_id: messageId,
        instruction: "Suggest a natural response to this selected message using the selected character.",
      }),
    });
    appState = result.state || (await api("/api/state"));
    render();
    finishOperation(opId, "Approval queued", "done", "bi-check-circle");
    toast("Response queued for approval");
  } catch (error) {
    await loadState().catch(() => {});
    finishOperation(opId, "Draft failed", "failed", "bi-exclamation-triangle");
    toast(error.message);
  }
}

function syncFormsToState() {
  const srv = server();
  srv.label = $("serverLabel").value.trim();
  srv.character_card = $("serverCharacter").value || null;
  srv.poll_seconds = Number($("serverPoll").value || 120);

  const card = appState.active_character.card;
  card.name = $("cardName").value.trim();
  card.system_prompt = $("systemPrompt").value.trim();
  card.aliases = lines("aliases");
  card.trigger_keywords = lines("triggerKeywords");
  card.style_rules = lines("styleRules");
  card.engagement_rules = lines("engagementRules");
}

async function saveAll() {
  const opId = "save-all";
  startOperation(opId, "Saving settings", "Writing local config files", "working", "bi-save2");
  try {
    syncFormsToState();
    const runtimeMode = currentRuntimeMode();
    const settings = {
      OPENAI_MODEL: $("openaiModel").value.trim(),
      NHI_ZUES_LLM_ENABLED: $("llmEnabled").checked,
      NHI_ZUES_RUNTIME_MODE: runtimeMode,
      NHI_ZUES_DRAFT_IN_DRY_RUN: $("draftDryRun").checked,
      NHI_ZUES_CONVERSATION_REPLY_ENABLED: $("conversationReply").checked,
      NHI_ZUES_HEADLESS: $("headlessMode").checked,
      NHI_ZUES_DRY_RUN: runtimeMode === "dry",
      NHI_ZUES_PROACTIVE_APPROVAL_REQUIRED: runtimeMode !== "full_auto",
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
    finishOperation(opId, "Settings saved", "done", "bi-check-circle");
    toast("Settings saved");
  } catch (error) {
    finishOperation(opId, "Save failed", "failed", "bi-exclamation-triangle");
    throw error;
  }
}

async function syncDiscordServers() {
  const opId = "sync-discord";
  startOperation(opId, "Syncing Discord", "Reading servers and channels", "sync", "bi-diagram-3");
  try {
    syncFormsToState();
    await api("/api/servers", { method: "POST", body: JSON.stringify(appState.servers) });
    const result = await api("/api/discord-sync-servers", { method: "POST", body: JSON.stringify({}) });
    appState = result.state;
    selectedServer = Math.min(selectedServer, servers().length - 1);
    if (selectedServer < 0) selectedServer = 0;
    selectedChannel = Math.min(selectedChannel, channels().length - 1);
    if (selectedChannel < 0) selectedChannel = 0;
    render();
    finishOperation(opId, "Discord synced", "done", "bi-check-circle");
    toast(`Synced ${result.discovered} servers and ${result.channels_discovered || 0} channels`);
  } catch (error) {
    finishOperation(opId, "Sync failed", "failed", "bi-exclamation-triangle");
    throw error;
  }
}

async function repairDiscordServer() {
  const currentServer = server();
  if (!currentServer?.server_id) {
    toast("Select a server first");
    return;
  }
  syncFormsToState();
  await api("/api/servers", { method: "POST", body: JSON.stringify(appState.servers) });
  const opId = `repair:${currentServer.server_id}`;
  startOperation(opId, "Repairing channels", "Reading Discord channel list", "repair", "bi-wrench-adjustable");
  toast("Repairing channel list...");
  try {
    const result = await api("/api/discord-repair-server", {
      method: "POST",
      body: JSON.stringify({ server_id: currentServer.server_id }),
    });
    appState = result.state;
    selectedServer = servers().findIndex((item) => item.server_id === currentServer.server_id);
    if (selectedServer < 0) selectedServer = 0;
    selectedChannel = Math.min(selectedChannel, channels().length - 1);
    if (selectedChannel < 0) selectedChannel = 0;
    render();
    finishOperation(opId, "Channels repaired", "done", "bi-check-circle");
    toast(`Repair found ${result.discovered || 0} items, added ${result.added || 0}`);
  } catch (error) {
    finishOperation(opId, "Repair failed", "failed", "bi-exclamation-triangle");
    throw error;
  }
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

async function openApprovalConversation(approvalId) {
  const approval = (appState.approvals || []).find((item) => item.approval_id === approvalId);
  if (!approval?.server_id || !approval?.channel_id) {
    throw new Error("Approval no longer has a Discord channel target.");
  }
  const sourceMessageId = (approval.source_message_ids || []).at(-1) || "";
  await api("/api/open-discord-channel", {
    method: "POST",
    body: JSON.stringify({
      server_id: approval.server_id,
      channel_id: approval.channel_id,
      message_id: sourceMessageId,
    }),
  });
  await loadState();
  toast(sourceMessageId ? "Discord conversation opened at source message" : "Discord channel window launched");
}

async function backfillChannelHistory() {
  const currentServer = server();
  const currentChannel = channel();
  if (!currentServer?.server_id || !currentChannel?.channel_id) {
    toast("Select a channel first");
    return;
  }
  const opId = `backfill:${currentChannel.channel_id}`;
  syncFormsToState();
  await api("/api/servers", { method: "POST", body: JSON.stringify(appState.servers) });
  startOperation(opId, "Backfilling history", "Reading Discord channel history", "backfill", "bi-clock-history");
  toast("Backfilling channel history...");
  try {
    const result = await api("/api/channel-backfill", {
      method: "POST",
      body: JSON.stringify({
        server_id: currentServer.server_id,
        channel_id: currentChannel.channel_id,
        limit: 160,
      }),
    });
    appState = result.state;
    render();
    finishOperation(opId, "History updated", "done", "bi-check-circle");
    toast(`Backfilled ${result.messages || 0} messages, ${result.new || 0} new`);
  } catch (error) {
    finishOperation(opId, "Backfill failed", "failed", "bi-exclamation-triangle");
    throw error;
  }
}

async function refreshChannelLatest() {
  const currentServer = server();
  const currentChannel = channel();
  if (!currentServer?.server_id || !currentChannel?.channel_id) {
    toast("Select a channel first");
    return;
  }
  const opId = `latest:${currentChannel.channel_id}`;
  syncFormsToState();
  await api("/api/servers", { method: "POST", body: JSON.stringify(appState.servers) });
  startOperation(opId, "Refreshing latest", "Reading visible Discord messages", "latest", "bi-arrow-clockwise");
  toast("Refreshing latest messages...");
  try {
    const result = await api("/api/channel-refresh", {
      method: "POST",
      body: JSON.stringify({
        server_id: currentServer.server_id,
        channel_id: currentChannel.channel_id,
      }),
    });
    appState = result.state;
    render();
    finishOperation(opId, "Latest refreshed", "done", "bi-check-circle");
    toast(`Latest refresh found ${result.messages || 0}, ${result.new || 0} new`);
  } catch (error) {
    finishOperation(opId, "Refresh failed", "failed", "bi-exclamation-triangle");
    throw error;
  }
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
  const opId = "openai-models";
  startOperation(opId, "Fetching models", "Waiting for OpenAI model list", "api", "bi-cloud-arrow-down");
  $("modelListStatus").textContent = "Fetching models from OpenAI...";
  try {
    const result = await api("/api/openai-models", { method: "POST", body: JSON.stringify({}) });
    appState.model_options = result.models || appState.model_options || [];
    appState.model_catalog = {
      live: Boolean(result.live),
      source: result.source || "",
      message: result.message || "",
      fetched_at: result.fetched_at || "",
    };
    renderModelOptions();
    finishOperation(opId, "Models refreshed", "done", "bi-check-circle");
    toast(result.message || "Model list refreshed");
  } catch (error) {
    finishOperation(opId, "Model fetch failed", "failed", "bi-exclamation-triangle");
    throw error;
  }
}

async function refreshAppStateManual() {
  const opId = "state-refresh";
  startOperation(opId, "Refreshing app state", "Reading local runtime files", "refresh", "bi-arrow-clockwise");
  try {
    await loadState();
    finishOperation(opId, "State refreshed", "done", "bi-check-circle");
  } catch (error) {
    finishOperation(opId, "Refresh failed", "failed", "bi-exclamation-triangle");
    throw error;
  }
}

async function toggleRuntime() {
  const opId = "runtime-toggle";
  startOperation(opId, appState.runtime?.running ? "Pausing scanner" : "Starting scanner", "", "working", "bi-power");
  const runtime = appState.runtime || {};
  const path = runtime.running ? "/api/runtime-pause" : "/api/runtime-start";
  try {
    const result = await api(path, { method: "POST", body: JSON.stringify({}) });
    appState = result.state;
    render();
    finishOperation(opId, appState.runtime.running ? "Scanner started" : "Scanner paused", "done", "bi-check-circle");
    toast(appState.runtime.running ? "Scanner started" : "Scanner paused");
  } catch (error) {
    finishOperation(opId, "Runtime change failed", "failed", "bi-exclamation-triangle");
    throw error;
  }
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

function currentRuntimeMode() {
  return appState?.env?.NHI_ZUES_RUNTIME_MODE || appState?.app?.runtime_mode || $("runtimeMode")?.value || "dry";
}

function runtimeModeLabel(mode) {
  return {
    dry: "dry mode",
    full_auto: "full auto",
    semi_auto: "semi auto",
    live_fire: "live fire",
  }[mode] || "dry mode";
}

function historyCount(channelId) {
  return appState.history?.[channelId]?.messages?.length || 0;
}

function configuredChannels() {
  return servers().flatMap((srv) =>
    (srv.channels || []).map((chan) => ({
      ...chan,
      server_id: srv.server_id,
      server_label: srv.label,
    }))
  );
}

function openUserGuidance(userKey) {
  if (!userKey) {
    toast("No stable user ID recorded for that message yet");
    return;
  }
  selectedUserKey = userKey;
  activateTab("growth");
  renderGrowth();
  const user = (appState.memory.users || []).find((item) => item.user_key === userKey);
  if (channel()) $("userNoteScope").value = "channel";
  $("newUserNote").placeholder = user?.display_name
    ? `Example: With ${user.display_name}, keep pushing on semantics without making it personal.`
    : "Example: Keep pushing this user on semantics without making it personal.";
  $("newUserNote").focus();
}

function allEvents() {
  return Array.isArray(appState.events?.items) ? appState.events.items : [];
}

function eventKey(event) {
  return [
    event.created_at || "",
    event.event_type || "",
    event.server_id || "",
    event.channel_id || "",
    event.summary || "",
    event.draft || "",
  ].join("|");
}

function eventTypeLabel(event) {
  const labels = {
    channel_checked: "Channel checked",
    channel_unavailable: "Channel unavailable",
    approval_queued: "Approval queued",
    manual_approval_created: "Draft queued",
    approval_regenerated: "Draft regenerated",
    approval_updated: "Draft edited",
    approval_discarded: "Draft discarded",
    approvals_cleared: "Approvals cleared",
    approval_send_started: "Delivery started",
    duplicate_reply_blocked: "Duplicate blocked",
    approval_sent: "Approved response sent",
    approval_send_failed: "Send failed",
    message_sent: "Auto response sent",
    dry_run: "Dry-run draft",
    auto_respond_dry_run: "Auto dry-run draft",
    discord_repair: "Discord repair",
    channel_backfilled: "Channel backfilled",
    channel_refreshed: "Channel refreshed",
  };
  return labels[event.event_type] || event.event_type || "Event";
}

function eventClass(event) {
  if (["approval_send_failed", "channel_unavailable"].includes(event.event_type)) return "failed";
  if (["message_sent", "approval_sent"].includes(event.event_type)) return "sent";
  if ([
    "approval_queued",
    "manual_approval_created",
    "approval_send_started",
    "duplicate_reply_blocked",
  ].includes(event.event_type)) return "attention";
  return "";
}

function eventScope(event) {
  if (event.channel_id) {
    const match = findChannel(event.server_id, event.channel_id);
    return `${match.serverLabel} / ${formatChannelName(match.channelLabel, match.channelType)}`;
  }
  if (event.server_id) return findServerLabel(event.server_id);
  return "All servers";
}

function isNotifiableEvent(event) {
  return [
    "approval_queued",
    "manual_approval_created",
    "approval_send_started",
    "duplicate_reply_blocked",
    "approval_sent",
    "approval_send_failed",
    "message_sent",
    "channel_unavailable",
  ].includes(event.event_type);
}

function syncEventNotifications({ previousEventKeys, notify }) {
  const events = allEvents();
  const nextKeys = new Set(events.map(eventKey));
  if (notify) {
    const newEvents = events.filter((event) => !previousEventKeys.has(eventKey(event)));
    const important = newEvents.filter(isNotifiableEvent);
    if (important.length) {
      unreadEventCount += important.length;
      const latest = important[0];
      const detail = latest.summary || latest.draft || "";
      toast(`${eventTypeLabel(latest)}: ${truncateText(detail, 96)}`);
    }
  }
  knownEventKeys = nextKeys;
  renderEventBadge();
}

function renderEventBadge() {
  const badge = $("eventBadge");
  if (!badge) return;
  badge.textContent = unreadEventCount > 99 ? "99+" : String(unreadEventCount);
  badge.classList.toggle("visible", unreadEventCount > 0);
}

function startAutoRefresh() {
  if (autoRefreshTimer) return;
  autoRefreshTimer = setInterval(() => {
    if (!appState || isUserEditing()) return;
    loadState({ notify: true, background: true }).catch((error) => console.warn(error));
  }, 10_000);
}

function isUserEditing() {
  if (Object.keys(approvalRegenerationState).length) return true;
  const active = document.activeElement;
  if (!active) return false;
  const tag = active.tagName?.toLowerCase();
  return active.isContentEditable || ["input", "textarea", "select"].includes(tag);
}

function truncateText(value, maxLength) {
  const text = String(value || "").trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 3)}...`;
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

function formatRuntimeTime(value) {
  if (!value) return "never";
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function channelTypeLabel(type) {
  if (type === "thread") return "discussion thread";
  if (type === "forum") return "forum channel";
  if (type === "announcement") return "announcement channel";
  if (type === "voice") return "voice channel";
  if (type === "stage") return "stage channel";
  if (type === "text") return "text channel";
  return "";
}

function formatChannelName(name, type) {
  if (!name) return "";
  if ((type === "text" || type === "forum" || type === "announcement" || type === "thread" || !type) && !String(name).startsWith("#")) {
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

function activateTab(tabId) {
  document.querySelectorAll(".tab").forEach((item) => {
    item.classList.toggle("active", item.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-pane").forEach((item) => {
    item.classList.toggle("active", item.id === tabId);
  });
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => activateTab(tab.dataset.tab));
});

document.querySelectorAll("[data-preview-tab]").forEach((tab) => {
  tab.addEventListener("click", () => {
    previewPanelMode = tab.dataset.previewTab;
    if (previewPanelMode === "events") unreadEventCount = 0;
    renderPreviewTabs();
  });
});

$("refresh").addEventListener("click", () => refreshAppStateManual().catch((error) => toast(error.message)));
$("runtimeControl").addEventListener("click", () => toggleRuntime().catch((error) => toast(error.message)));
$("saveAll").addEventListener("click", saveAll);
$("saveServers").addEventListener("click", saveAll);
$("syncDiscordServers").addEventListener("click", () => syncDiscordServers().catch((error) => toast(error.message)));
$("saveDiscord").addEventListener("click", saveDiscordCredentials);
$("launchDiscordLogin").addEventListener("click", launchDiscordLogin);
$("openDiscordChannel").addEventListener("click", () => openDiscordChannel().catch((error) => toast(error.message)));
$("repairDiscordServer").addEventListener("click", () => repairDiscordServer().catch((error) => toast(error.message)));
$("refreshChannelLatest").addEventListener("click", () => refreshChannelLatest().catch((error) => toast(error.message)));
$("backfillChannel").addEventListener("click", () => backfillChannelHistory().catch((error) => toast(error.message)));
$("refreshOpenAIModels").addEventListener("click", () => refreshOpenAIModels().catch((error) => toast(error.message)));
$("clearApprovals").addEventListener("click", () => clearApprovals().catch((error) => toast(error.message)));
$("checkUpdates").addEventListener("click", checkUpdates);
$("applyUpdate").addEventListener("click", applyUpdate);
$("runtimeMode").addEventListener("change", () => {
  appState.env.NHI_ZUES_RUNTIME_MODE = $("runtimeMode").value;
  appState.app.runtime_mode = $("runtimeMode").value;
  $("dryRun").checked = currentRuntimeMode() === "dry";
  $("approvalRequired").checked = currentRuntimeMode() !== "full_auto";
  renderServerPanel();
  renderApprovals();
  renderRuntime();
});

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
