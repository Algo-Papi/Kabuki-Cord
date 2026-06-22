let appState = null;
let selectedServer = 0;
let selectedChannel = 0;
let selectedUserKey = null;
let apiToken = null;

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
  if (!response.ok) throw new Error(await response.text());
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
  renderGrowth();
  renderApprovals();
  renderMetrics();
}

function renderRail() {
  $("serverRail").innerHTML = servers()
    .map((srv, index) => {
      const label = srv.label || `S${index + 1}`;
      const initials = label
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0])
        .join("")
        .toUpperCase() || String(index + 1);
      return `<button class="server-bubble ${index === selectedServer ? "active" : ""}" data-server="${index}" title="${escapeHtml(label)}">${escapeHtml(initials)}</button>`;
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
      return `
        <div class="channel-row ${index === selectedChannel ? "active" : ""}">
          <div class="channel-name" data-channel="${index}">
            <strong># ${escapeHtml(name)}</strong>
            <span>${escapeHtml(chan.channel_id || "")}</span>
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
        <div class="portrait">${escapeHtml((card.name || "K").slice(0, 2).toUpperCase())}</div>
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
    ? "Discord credentials are stored locally. Sign-in can use the persistent browser profile."
    : discord.email_set || discord.password_set
      ? "Partial Discord credentials are stored. Add the missing value or sign in manually."
      : "No stored Discord credentials. You can still sign in manually.";
  $("discordEmail").value = "";
  $("discordPassword").value = "";
  const updates = appState.updates || {};
  $("updateStatus").textContent = updates.remote_allowed
    ? `Ready to update from ${updates.remote}.`
    : "GitHub origin is not configured yet. Update will be available after publishing.";
  $("openaiModel").value = appState.env.OPENAI_MODEL || appState.app.openai_model || "";
  $("llmEnabled").checked = strBool(appState.env.NHI_ZUES_LLM_ENABLED, false);
  $("draftDryRun").checked = strBool(appState.env.NHI_ZUES_DRAFT_IN_DRY_RUN, false);
  $("dryRun").checked = strBool(appState.env.NHI_ZUES_DRY_RUN, true);
  $("dailyBudget").value = appState.env.NHI_ZUES_MAX_DAILY_USD || "0.25";
  $("sessionBudget").value = appState.env.NHI_ZUES_MAX_SESSION_USD || "0.05";
  $("maxCalls").value = appState.env.NHI_ZUES_MAX_LLM_CALLS_PER_RUN || "3";
  $("runtimeStatus").textContent = appState.app.dry_run ? "dry-run enabled" : "live sending possible";
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
          <strong>${escapeHtml(user.display_name || user.user_key)}</strong>
          <span>${escapeHtml(user.user_key)} · ${user.message_count || 0} messages</span>
        </div>
      `)
      .join("") || `<div class="note-item">No users observed yet.</div>`;
  document.querySelectorAll("[data-user]").forEach((row) => {
    row.addEventListener("click", () => {
      selectedUserKey = row.dataset.user;
      renderGrowth();
    });
  });
}

function renderApprovals() {
  const approvals = appState.approvals || [];
  $("approvalList").innerHTML =
    approvals
      .map((item) => `
        <div class="approval-item">
          <strong>${escapeHtml(item.character_name)} · #${escapeHtml(item.channel_id)}</strong>
          <span>${escapeHtml(item.reason)}</span>
          <p>${escapeHtml(item.draft)}</p>
          <button class="small-button" data-copy="${escapeAttr(item.draft)}"><i class="bi bi-copy"></i> Copy draft</button>
        </div>
      `)
      .join("") || `<div class="approval-item"><strong>No queued approvals</strong><span>Proactive drafts will appear here.</span></div>`;
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      await navigator.clipboard.writeText(button.dataset.copy || "");
      toast("Draft copied");
    });
  });
}

function renderMetrics() {
  $("dailySpend").textContent = `$${Number(appState.usage.daily_spend_usd || 0).toFixed(6)}`;
  $("usageCalls").textContent = appState.usage.records || 0;
  $("memoryUsers").textContent = appState.memory.user_count || 0;
  $("seenMessages").textContent = appState.memory.seen_ids || 0;
  $("triggerState").textContent = channel()?.engage_enabled ? "eligible" : "disabled";
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
  await api("/api/discord-login", { method: "POST", body: JSON.stringify({}) });
  toast("Discord sign-in window launched");
}

async function checkUpdates() {
  const result = await api("/api/update-check", { method: "POST", body: JSON.stringify({}) });
  renderUpdateResult(result);
}

async function applyUpdate() {
  const result = await api("/api/update", { method: "POST", body: JSON.stringify({}) });
  renderUpdateResult(result);
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
$("saveAll").addEventListener("click", saveAll);
$("saveServers").addEventListener("click", saveAll);
$("saveDiscord").addEventListener("click", saveDiscordCredentials);
$("launchDiscordLogin").addEventListener("click", launchDiscordLogin);
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
    body: JSON.stringify({ user_key: selectedUserKey, note }),
  });
  $("newUserNote").value = "";
  await loadState();
  toast("User note added");
});

loadState().catch((error) => {
  console.error(error);
  toast("Failed to load Kabuki-Cord state");
});
