let apiToken = null;
let refreshTimer = null;
let spyFrameTimer = null;
let countdownTimer = null;
let spyFrameIndex = 0;
let spyFrames = ["/assets/monitor_spy_v2_frames/frame_000.webp"];
let normalSpyFrames = ["/assets/monitor_spy_v2_frames/frame_000.webp"];
let dojoSweepFrames = ["/assets/monitor_dojo_sweep_v2_frames/frame_000.webp"];
let spyFrameMs = 350;
let normalSpyFrameMs = 350;
let dojoSweepFrameMs = 300;
let activeFrameLayer = "A";
let activeAnimationMode = "scan";
let transitionIndex = 0;
let spyPaused = false;
let latestState = null;
let knownEventKeys = new Set();
let eventNotificationsReady = false;
let soundEnabled = true;
let dojoFramesPreloaded = false;

const $ = (id) => document.getElementById(id);
const pausedFrame = "/assets/monitor-paused-lounge.webp";
const deliveryEventTypes = new Set(["message_sent", "approval_sent"]);
const responseEventTypes = new Set(["message_sent", "approval_sent"]);
const reactionActionEventTypes = new Set([
  "reaction_added",
  "reaction_already_present",
  "reaction_failed",
  "reaction_skipped",
]);
const stageTransitionTypes = ["logo-swipe-left", "mask-zoom", "logo-swipe-right", "crest-iris"];
const dismissedActionStorageKey = "kabukiScannerDismissedActions:v1";
let dismissedActionKeys = loadDismissedActionKeys();

async function loadSession() {
  const response = await fetch("/api/session");
  if (!response.ok) throw new Error("Could not open Kabuki session.");
  const payload = await response.json();
  apiToken = payload.token;
}

async function api(path) {
  if (!apiToken) await loadSession();
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      "X-Kabuki-Token": apiToken,
    },
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function refresh() {
  try {
    const state = await api("/api/monitor-state");
    syncDeliveryNotifications(state);
    render(state);
  } catch (error) {
    $("monitorStatus").className = "status-pill error";
    $("monitorStatus").textContent = "Disconnected";
    $("currentTarget").textContent = "Kabuki-Cord unavailable";
    $("currentDetail").textContent = error.message || "Restart the app and reopen this monitor.";
  }
}

async function loadSpyAnimation() {
  const normal = await loadFrameSet(
    "/assets/monitor_spy_v2_frames",
    "/assets/monitor_spy_v2_frames/frame_000.webp"
  );
  normalSpyFrames = normal.frames;
  normalSpyFrameMs = normal.frameMs;
  spyFrameMs = normalSpyFrameMs;
  spyFrames = normalSpyFrames;
  const dojo = await loadFrameSet(
    "/assets/monitor_dojo_sweep_v2_frames",
    "/assets/monitor_dojo_sweep_v2_frames/frame_000.webp"
  );
  dojoSweepFrames = dojo.frames;
  dojoSweepFrameMs = dojo.frameMs || 300;
  preloadImages([...normalSpyFrames, pausedFrame]);
  restartSpyFrameTimer();
}

async function loadFrameSet(directory, fallbackFrame) {
  let frames = [fallbackFrame];
  let frameMs = 180;
  try {
    const response = await fetch(`${directory}/manifest.json`);
    if (response.ok) {
      const manifest = await response.json();
      const count = Number(manifest.frame_count || 1);
      frameMs = Number(manifest.frame_ms || 180);
      const extension = String(manifest.extension || "webp").replace(/[^a-z0-9]/gi, "") || "webp";
      frames = Array.from({ length: count }, (_, index) =>
        `${directory}/frame_${String(index).padStart(3, "0")}.${extension}`
      );
    }
  } catch {
    frames = [fallbackFrame];
  }
  return { frames, frameMs };
}

function preloadImages(sources) {
  sources.forEach((src) => {
    const image = new Image();
    image.src = src;
  });
}

function advanceSpyFrame() {
  if (spyPaused) return;
  showSceneFrame((spyFrameIndex + 1) % spyFrames.length, { transition: false });
}

function showSceneFrame(nextIndex, { transition: useTransition }) {
  const active = activeFrameLayer === "A" ? $("spySceneFrameA") : $("spySceneFrameB");
  const incoming = activeFrameLayer === "A" ? $("spySceneFrameB") : $("spySceneFrameA");
  if (!active || !incoming || !spyFrames.length) return;
  nextIndex = Math.max(0, Math.min(spyFrames.length - 1, Number(nextIndex) || 0));
  if (nextIndex === spyFrameIndex && incoming.src.endsWith(spyFrames[nextIndex])) return;
  spyFrameIndex = nextIndex;
  incoming.src = spyFrames[spyFrameIndex];
  const scene = document.querySelector(".spy-scene");
  const stageTransition = $("stageTransition");
  scene?.classList.remove("transitioning");
  if (stageTransition) stageTransition.className = "stage-transition";
  void scene?.offsetWidth;
  incoming.classList.add("active");
  active.classList.remove("active");
  if (useTransition) scene?.classList.add("transitioning");
  if (useTransition && stageTransition) {
    const transitionType = stageTransitionTypes[transitionIndex % stageTransitionTypes.length];
    transitionIndex += 1;
    stageTransition.classList.add("active", transitionType);
  }
  activeFrameLayer = activeFrameLayer === "A" ? "B" : "A";
  setTimeout(() => {
    scene?.classList.remove("transitioning");
    if (stageTransition) stageTransition.className = "stage-transition";
  }, 1900);
}

function setAnimationMode(mode) {
  const nextMode = mode === "dojo_sweep" ? "dojo_sweep" : "scan";
  if (activeAnimationMode === nextMode) return;
  activeAnimationMode = nextMode;
  if (nextMode === "dojo_sweep" && !dojoFramesPreloaded) {
    dojoFramesPreloaded = true;
    preloadImages(dojoSweepFrames);
  }
  spyFrames = nextMode === "dojo_sweep" ? dojoSweepFrames : normalSpyFrames;
  spyFrameMs = nextMode === "dojo_sweep" ? dojoSweepFrameMs : normalSpyFrameMs;
  spyFrameIndex = 0;
  const scene = document.querySelector(".spy-scene");
  scene?.classList.toggle("dojo-sweep", nextMode === "dojo_sweep");
  const frameA = $("spySceneFrameA");
  const frameB = $("spySceneFrameB");
  if (frameA && frameB) {
    frameA.src = spyFrames[0] || "";
    frameB.src = frameA.src;
    frameA.classList.add("active");
    frameB.classList.remove("active");
    activeFrameLayer = "A";
  }
  restartSpyFrameTimer();
}

function isDojoSweepTarget(target) {
  return Boolean(target?.safety_review_enabled);
}

function restartSpyFrameTimer() {
  if (spyFrameTimer) clearInterval(spyFrameTimer);
  spyFrameTimer = null;
  if (!spyPaused) spyFrameTimer = setInterval(advanceSpyFrame, spyFrameMs);
}

function setSpyPaused(paused) {
  const scene = document.querySelector(".spy-scene");
  const frameA = $("spySceneFrameA");
  const frameB = $("spySceneFrameB");
  const transition = $("stageTransition");
  if (!scene || !frameA || !frameB) return;
  if (spyPaused === paused) return;
  spyPaused = paused;
  scene.classList.toggle("paused", paused);
  scene.classList.remove("transitioning");
  scene.classList.toggle("dojo-sweep", !paused && activeAnimationMode === "dojo_sweep");
  if (transition) transition.className = "stage-transition";

  if (paused) {
    if (spyFrameTimer) clearInterval(spyFrameTimer);
    spyFrameTimer = null;
    frameA.src = pausedFrame;
    frameB.src = pausedFrame;
    frameA.classList.add("active");
    frameB.classList.remove("active");
    activeFrameLayer = "A";
    return;
  }

  frameA.src = spyFrames[spyFrameIndex] || spyFrames[0] || "/assets/monitor_spy_frames/frame_000.webp";
  frameB.src = frameA.src;
  frameA.classList.add("active");
  frameB.classList.remove("active");
  activeFrameLayer = "A";
  restartSpyFrameTimer();
}

function render(state) {
  latestState = state;
  const runtime = state.runtime || {};
  const scan = runtime.scan || {};
  const status = scan.status || runtime.phase || "idle";
  const sweepActive = runtime.running && status === "scanning" && isDojoSweepTarget(scan.current);
  setAnimationMode(sweepActive ? "dojo_sweep" : "scan");
  setSpyPaused(!runtime.running);
  $("monitorStatus").className = `status-pill ${sweepActive ? "sweep" : runtime.running ? "running" : "paused"}`;
  $("monitorStatus").textContent = runtime.running ? (sweepActive ? "Dojo Sweep" : statusLabel(status)) : "Paused";

  renderTarget("current", scan.current, {
    title: runtime.running ? currentTitle(status) : "Scanner paused",
    detail: runtime.running ? "No channel is active at this instant." : "Press Start in the main window.",
  });
  renderTarget("next", scan.next, {
    title: "None queued",
    detail: "The scanner is resting or waiting for the next loop slot.",
  });
  renderCompleted(scan.last_completed);
  renderUpcoming(scan.upcoming || []);
  renderActionHistory(state);
  renderPace(state);
  renderCountdowns();
  renderLoopHud(state);
}

function renderTarget(kind, target, fallback) {
  const titleEl = kind === "current" ? $("currentTarget") : $("nextTarget");
  const detailEl = kind === "current" ? $("currentDetail") : $("nextDetail");
  if (!target) {
    titleEl.textContent = fallback.title;
    detailEl.textContent = fallback.detail;
    return;
  }
  titleEl.textContent = formatTargetTitle(target);
  detailEl.textContent = target.channel_id
    ? `${target.safety_review_enabled ? "Dojo Sweep - " : ""}#${target.channel_label || target.channel_id} - ${target.channel_id}`
    : fallback.detail;
}

function renderCountdowns() {
  const runtime = latestState?.runtime || {};
  const scan = runtime.scan || {};
  const running = Boolean(runtime.running);
  const now = Date.now() / 1000;

  if (!running || scan.status !== "scanning" || !scan.current) {
    $("currentCountdownLabel").textContent = "Done in";
    $("currentCountdown").textContent = "--";
  } else {
    $("currentCountdownLabel").textContent = "Est. done";
    $("currentCountdown").textContent = formatCountdown(Number(scan.current_estimated_done_at || 0) - now);
  }

  const nextAt = Number(scan.next_scan_at || 0);
  renderIdleCountdown(running, scan, now, nextAt);

  if (!running) {
    $("nextCountdownLabel").textContent = "Next scan";
    $("nextCountdown").textContent = "--";
    return;
  }
  if (!nextAt) {
    $("nextCountdownLabel").textContent = scan.status === "scanning" ? "Queued after" : "Next scan";
    $("nextCountdown").textContent = scan.next ? "soon" : "--";
    return;
  }
  $("nextCountdownLabel").textContent = scan.next ? "Next channel" : "Next check";
  $("nextCountdown").textContent = formatCountdown(nextAt - now);
}

function renderLoopHud(state) {
  const runtime = state?.runtime || {};
  const scan = runtime.scan || {};
  const loop = scan.loop || {};
  const counter = $("loopCounter");
  const countdown = $("loopCountdown");
  if (!counter || !countdown) return;
  if (!runtime.running || !Number(loop.total_channels || 0)) {
    counter.textContent = "--";
    countdown.textContent = "--";
    return;
  }
  const now = Date.now() / 1000;
  const currentLoop = Number(loop.current_loop || loop.completed_loops + 1 || 1);
  const total = Number(loop.total_channels || 0);
  const completed = Number(loop.completed_in_loop || 0);
  counter.textContent = `${currentLoop} - ${Math.min(completed, total)}/${total}`;
  countdown.textContent = formatCountdown(Number(loop.estimated_complete_at || 0) - now);
}

function renderIdleCountdown(running, scan, now, nextAt) {
  const idleCountdown = $("idleCountdown");
  const idleLabel = $("idleCountdownLabel");
  if (!idleCountdown || !idleLabel) return;
  if (!running) {
    idleLabel.textContent = "Idle rest";
    idleCountdown.textContent = "--";
  } else if (scan.status === "scanning") {
    idleLabel.textContent = "Rest after";
    idleCountdown.textContent = formatSeconds(appConfigNumber("scanner_cycle_sleep_seconds"));
  } else if (nextAt) {
    idleLabel.textContent = scan.next ? "Until channel" : "Idle rest";
    idleCountdown.textContent = formatCountdown(nextAt - now);
  } else {
    idleLabel.textContent = "Idle rest";
    idleCountdown.textContent = "--";
  }
}

function renderPace(state) {
  const app = state.app || {};
  const runtime = state.runtime || {};
  const scan = runtime.scan || {};
  const loop = scan.loop || {};
  const maxChannels = Number(app.scanner_max_channels_per_cycle || 1);
  const cycleRest = Number(app.scanner_cycle_sleep_seconds || 45);
  const settleDelay = Number(app.scanner_channel_settle_seconds || 12);
  const minDelay = Number(app.scanner_min_channel_delay_seconds || 12);
  const maxDelay = Number(app.scanner_max_channel_delay_seconds || 35);
  const totalChannels = Number(loop.total_channels || 0);
  const target = $("idleTarget");
  const detail = $("idleDetail");
  if (!target || !detail) return;
  target.textContent = runtime.running
    ? scan.status === "scanning"
      ? "Scanning now"
      : "Between channels"
    : "Paused";
  detail.textContent = `${totalChannels || "No"} observed channel${totalChannels === 1 ? "" : "s"}, ${maxChannels}/cycle, ${formatSeconds(settleDelay)} settle, ${formatSeconds(cycleRest)} rest, loop est. ${formatSeconds(loop.estimated_loop_seconds || 0)}, ${formatDelayRange(minDelay, maxDelay)} channel delay`;
}

function renderCompleted(target) {
  if (!target) {
    $("lastCompleted").textContent = "None yet";
    $("lastCompletedDetail").textContent = "No completed channel scan in this run.";
    return;
  }
  $("lastCompleted").textContent = formatTargetTitle(target);
  $("lastCompletedDetail").textContent =
    `${target.visible_messages || 0} visible, ${target.fresh_messages || 0} new to memory`;
}

function renderUpcoming(items) {
  const visible = items.slice(0, 5);
  $("upcomingList").innerHTML = visible.length
    ? visible.map((item, index) => `
      <div class="queue-item">
        <span>${index === 0 ? "Next" : `+${index}`}</span>
        <strong>${escapeHtml(item.channel_label || item.channel_id || "Unknown channel")}</strong>
        <span>${escapeHtml(item.server_label || item.server_id || "Unknown server")}</span>
      </div>
    `).join("")
    : `<div class="queue-empty">No upcoming channels are queued right now.</div>`;
}

function renderActionHistory(state) {
  renderActionColumn("responseActions", visibleActionEvents(state, responseEventTypes, "response"), "response", state);
  renderActionColumn("reactionActions", visibleActionEvents(state, reactionActionEventTypes, "reaction"), "reaction", state);
}

function renderActionColumn(elementId, events, kind, state) {
  const host = $(elementId);
  if (!host) return;
  const items = events.slice(0, 12);
  host.innerHTML = items.length
    ? items.map((event, index) => renderActionCard(event, kind, state, index)).join("")
    : `<div class="action-empty">No ${kind === "reaction" ? "reaction activity" : "responses"} recorded yet.</div>`;
  host.querySelectorAll("[data-action-open]").forEach((button) => {
    button.addEventListener("click", () => {
      const url = button.getAttribute("data-action-open") || "";
      if (url) window.open(url, "_blank", "noopener,noreferrer");
    });
  });
  host.querySelectorAll("[data-action-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const url = button.getAttribute("data-action-copy") || "";
      if (!url) return;
      try {
        await navigator.clipboard.writeText(url);
        showMonitorNote("Discord link copied");
      } catch {
        window.prompt("Copy Discord link", url);
      }
    });
  });
}

function actionEvents(state, types) {
  const events = Array.isArray(state.events?.items) ? state.events.items : [];
  return events
    .filter((event) => types.has(event.event_type))
    .sort((left, right) => String(right.created_at || "").localeCompare(String(left.created_at || "")));
}

function visibleActionEvents(state, types, kind) {
  return actionEvents(state, types).filter((event) => !dismissedActionKeys[kind].has(eventKey(event)));
}

function setupActionClearButtons() {
  $("clearResponseActions")?.addEventListener("click", () => clearActionColumn("response", responseEventTypes));
  $("clearReactionActions")?.addEventListener("click", () => clearActionColumn("reaction", reactionActionEventTypes));
}

function clearActionColumn(kind, types) {
  const events = visibleActionEvents(latestState || {}, types, kind);
  if (!events.length) {
    showMonitorNote(`No ${kind === "reaction" ? "reaction" : "response"} activity to clear`);
    return;
  }
  events.forEach((event) => dismissedActionKeys[kind].add(eventKey(event)));
  trimDismissedActionKeys(kind);
  saveDismissedActionKeys();
  renderActionHistory(latestState || {});
  showMonitorNote(`${events.length} ${kind === "reaction" ? "reaction" : "response"} item${events.length === 1 ? "" : "s"} cleared`);
}

function loadDismissedActionKeys() {
  const fallback = { response: new Set(), reaction: new Set() };
  try {
    const raw = window.localStorage?.getItem(dismissedActionStorageKey);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return {
      response: new Set(Array.isArray(parsed.response) ? parsed.response : []),
      reaction: new Set(Array.isArray(parsed.reaction) ? parsed.reaction : []),
    };
  } catch {
    return fallback;
  }
}

function saveDismissedActionKeys() {
  try {
    window.localStorage?.setItem(dismissedActionStorageKey, JSON.stringify({
      response: Array.from(dismissedActionKeys.response),
      reaction: Array.from(dismissedActionKeys.reaction),
    }));
  } catch {
    return;
  }
}

function trimDismissedActionKeys(kind) {
  const values = Array.from(dismissedActionKeys[kind]);
  if (values.length <= 240) return;
  dismissedActionKeys[kind] = new Set(values.slice(values.length - 240));
}

function renderActionCard(event, kind, state, index) {
  const route = actionRoute(event, state);
  const messageId = kind === "response"
    ? (event.message_id || event.target_message_id || "")
    : (event.target_message_id || event.message_id || "");
  const url = discordUrl(event.server_id, event.channel_id, messageId);
  const target = event.target_author || parseTargetAuthor(event) || "channel";
  const body = kind === "reaction"
    ? reactionActionBody(event)
    : truncate(event.draft || event.summary || "", 260);
  const meta = `${route.server} / ${route.channel}`;
  const badge = kind === "reaction" ? reactionBadge(event) : responseBadge(event);
  return `
    <details class="action-item ${kind}" ${index < 2 ? "open" : ""}>
      <summary>
        <span class="action-badge">${escapeHtml(badge)}</span>
        <span class="action-summary">
          <strong>${escapeHtml(target)}</strong>
          <small>${escapeHtml(meta)}</small>
        </span>
      </summary>
      <div class="action-body">
        <p>${escapeHtml(body || "No text captured for this action.")}</p>
        <div class="action-buttons">
          <button type="button" data-action-open="${escapeAttr(url)}">Open</button>
          <button type="button" data-action-copy="${escapeAttr(url)}">Copy link</button>
        </div>
      </div>
    </details>
  `;
}

function actionRoute(event, state) {
  const serverId = String(event.server_id || "");
  const channelId = String(event.channel_id || "");
  const server = serverLabel(state, serverId);
  const channel = channelLabel(state, channelId);
  return {
    server: server || serverId || "Unknown server",
    channel: channel || channelId || "Unknown channel",
  };
}

function serverLabel(state, serverId) {
  const servers = Array.isArray(state.servers?.servers) ? state.servers.servers : [];
  const server = servers.find((item) => String(item.server_id || "") === String(serverId || ""));
  return server?.label || "";
}

function channelLabel(state, channelId) {
  const servers = Array.isArray(state.servers?.servers) ? state.servers.servers : [];
  for (const server of servers) {
    const channels = Array.isArray(server.channels) ? server.channels : [];
    const channel = channels.find((item) => String(item.channel_id || "") === String(channelId || ""));
    if (channel) return channel.label || channel.channel_id || "";
  }
  return "";
}

function discordUrl(serverId, channelId, messageId = "") {
  const server = encodeURIComponent(String(serverId || ""));
  const channel = encodeURIComponent(String(channelId || ""));
  if (!server || !channel) return "";
  const token = discordMessageToken(messageId);
  return `https://discord.com/channels/${server}/${channel}${token ? `/${encodeURIComponent(token)}` : ""}`;
}

function discordMessageToken(messageId) {
  const raw = String(messageId || "").trim();
  if (!raw) return "";
  const parts = raw.split("-");
  return parts.length >= 2 ? parts[parts.length - 1] : raw;
}

function responseBadge(event) {
  if (event.event_type === "approval_sent") return "approved";
  if (event.event_type === "message_sent") return "auto";
  return "sent";
}

function reactionActionBody(event) {
  if (event.event_type === "reaction_failed") {
    return truncate(event.summary || "Reaction failed.", 260);
  }
  if (event.event_type === "reaction_skipped") {
    return truncate(event.summary || "Reaction skipped.", 260);
  }
  if (event.event_type === "reaction_already_present") {
    return truncate(event.summary || "Reaction already present.", 260);
  }
  const emoji = reactionBadge(event);
  const text = truncate(event.draft || "", 220);
  const reason = truncate(event.summary || "", 180);
  if (emoji && emoji !== "react" && text) return `${emoji} reacted to: ${text}`;
  if (text) return `reacted to: ${text}`;
  return reason;
}

function reactionBadge(event) {
  if (event.event_type === "reaction_failed") return "failed";
  if (event.event_type === "reaction_skipped") return "skip";
  if (event.event_type === "reaction_already_present") return "exists";
  const emoji = cleanEmoji(event.emoji) || cleanEmoji(parseEmoji(event.summary));
  return emoji || "react";
}

function cleanEmoji(value) {
  const text = String(value || "").trim();
  if (!text || /^[?]+$/.test(text)) return "";
  return text;
}

function parseTargetAuthor(event) {
  const summary = String(event.summary || "");
  const reactionMatch = summary.match(/reaction (?:was already present from this account on|to) ([^:;]+)(?::|;)/i);
  if (reactionMatch) return reactionMatch[1].trim();
  return "";
}

function parseEmoji(value) {
  const text = String(value || "");
  const match = text.match(/(?:Added|Could not add|Suggested)\s+(\S+)\s+reaction/i);
  return match ? match[1] : "";
}

function syncDeliveryNotifications(state) {
  const events = Array.isArray(state.events?.items) ? state.events.items : [];
  const currentKeys = new Set(events.map(eventKey));
  if (!eventNotificationsReady) {
    knownEventKeys = currentKeys;
    eventNotificationsReady = true;
    return;
  }
  const fresh = events
    .filter((event) => !knownEventKeys.has(eventKey(event)) && deliveryEventTypes.has(event.event_type))
    .reverse();
  knownEventKeys = currentKeys;
  fresh.forEach(showDeliveryToast);
}

function showDeliveryToast(event) {
  const host = $("monitorToasts");
  if (!host) return;
  playArigatoCue();
  playDeliveryBurst(event);
  const toast = document.createElement("article");
  toast.className = "monitor-toast";
  toast.innerHTML = `
    <div class="toast-stars" aria-hidden="true"><span></span><span></span><span></span><span></span></div>
    <span class="delivery-character delivery-character-toast" aria-hidden="true"></span>
    <div>
      <strong>Arigato</strong>
      <span>${escapeHtml(deliveryLabel(event))}</span>
      <small>${escapeHtml(truncate(event.summary || event.draft || "", 92))}</small>
    </div>
    <button type="button" title="Dismiss notification">&times;</button>
  `;
  const dismiss = () => {
    toast.classList.add("leaving");
    setTimeout(() => toast.remove(), 260);
  };
  toast.querySelector("button")?.addEventListener("click", dismiss);
  host.append(toast);
  setTimeout(dismiss, 5200);
}

function playDeliveryBurst(event) {
  const scene = document.querySelector(".spy-scene");
  if (!scene) return;
  const burst = document.createElement("div");
  burst.className = "delivery-burst";
  burst.innerHTML = `
    <div class="delivery-stars" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span></div>
    <span class="delivery-character delivery-character-burst" aria-hidden="true"></span>
    <strong>Arigato!</strong>
    <small>${escapeHtml(deliveryLabel(event))}</small>
  `;
  scene.append(burst);
  setTimeout(() => burst.remove(), 2600);
}

function setupSoundToggle() {
  const button = $("soundToggle");
  if (!button) return;
  button.addEventListener("click", () => {
    if (button.classList.contains("needs-click") && soundEnabled) {
      button.classList.remove("needs-click");
      button.textContent = "Sound on";
      playArigatoCue({ quietFailure: true });
      return;
    }
    soundEnabled = !soundEnabled;
    button.setAttribute("aria-pressed", soundEnabled ? "true" : "false");
    button.textContent = soundEnabled ? "Sound on" : "Sound off";
    if (soundEnabled) playArigatoCue({ quietFailure: true });
  });
}

function playArigatoCue(options = {}) {
  if (!soundEnabled) return;
  const audio = new Audio("/assets/monitor-arigato.wav");
  audio.volume = 0.72;
  audio.play().then(() => {
    const button = $("soundToggle");
    if (button && soundEnabled) {
      button.classList.remove("needs-click");
      button.textContent = "Sound on";
    }
  }).catch(() => {
    const button = $("soundToggle");
    if (button && !options.quietFailure) {
      button.textContent = "Click for sound";
      button.classList.add("needs-click");
    }
  });
}

function showMonitorNote(message) {
  const host = $("monitorToasts");
  if (!host) return;
  const toast = document.createElement("article");
  toast.className = "monitor-toast compact";
  toast.innerHTML = `
    <div>
      <strong>${escapeHtml(message)}</strong>
    </div>
    <button type="button" title="Dismiss notification">&times;</button>
  `;
  const dismiss = () => {
    toast.classList.add("leaving");
    setTimeout(() => toast.remove(), 220);
  };
  toast.querySelector("button")?.addEventListener("click", dismiss);
  host.append(toast);
  setTimeout(dismiss, 2200);
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

function deliveryLabel(event) {
  if (event.event_type === "approval_sent") return "Approved reply posted";
  if (event.event_type === "message_sent") return "Auto reply posted";
  return "Response posted";
}

function formatTargetTitle(target) {
  const server = target.server_label || target.server_id || "Unknown server";
  const channel = target.channel_label || target.channel_id || "Unknown channel";
  return `${server} / ${channel}`;
}

function formatCountdown(seconds) {
  if (!Number.isFinite(seconds)) return "--";
  if (seconds <= 0) return "now";
  const rounded = Math.ceil(seconds);
  const minutes = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  if (minutes <= 0) return `${remainder}s`;
  return `${minutes}m ${String(remainder).padStart(2, "0")}s`;
}

function formatSeconds(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value)) return "--";
  if (value < 60) return `${Math.round(value)}s`;
  const minutes = Math.floor(value / 60);
  const remainder = Math.round(value % 60);
  return remainder ? `${minutes}m ${String(remainder).padStart(2, "0")}s` : `${minutes}m`;
}

function formatDelayRange(minDelay, maxDelay) {
  if (!Number.isFinite(minDelay) || !Number.isFinite(maxDelay)) return "--";
  if (Math.round(minDelay) === Math.round(maxDelay)) return `${Math.round(minDelay)}s`;
  return `${Math.round(minDelay)}-${Math.round(maxDelay)}s`;
}

function appConfigNumber(key) {
  const value = Number(latestState?.app?.[key]);
  return Number.isFinite(value) ? value : 0;
}

function truncate(value, maxLength) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
}

function currentTitle(status) {
  return status === "waiting_for_discord_login" ? "Waiting for Discord sign-in" : "Between channels";
}

function statusLabel(status) {
  return {
    starting: "Starting",
    queued: "Queued",
    scanning: "Scanning",
    completed_channel: "Channel complete",
    resting: "Resting",
    waiting: "Waiting",
    waiting_for_discord_login: "Sign-in handoff",
    stopping: "Stopping",
    idle: "Idle",
  }[status] || status;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

loadSpyAnimation();
setupSoundToggle();
setupActionClearButtons();
refresh();
refreshTimer = setInterval(refresh, 1800);
countdownTimer = setInterval(() => {
  renderCountdowns();
  renderLoopHud(latestState);
}, 1000);
window.addEventListener("beforeunload", () => {
  if (refreshTimer) clearInterval(refreshTimer);
  if (spyFrameTimer) clearInterval(spyFrameTimer);
  if (countdownTimer) clearInterval(countdownTimer);
});
