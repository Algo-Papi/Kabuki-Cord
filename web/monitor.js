let apiToken = null;
let refreshTimer = null;
let spyFrameTimer = null;
let countdownTimer = null;
let spyFrameIndex = 0;
let spyFrames = ["/assets/monitor_spy_frames/frame_000.png"];
let spyFrameMs = 180;
let activeFrameLayer = "A";
let transitionIndex = 0;
let spyPaused = false;
let latestState = null;
let knownEventKeys = new Set();
let eventNotificationsReady = false;

const $ = (id) => document.getElementById(id);
const pausedFrame = "/assets/monitor-paused-lounge.png";
const deliveryEventTypes = new Set(["message_sent", "approval_sent"]);
const stageTransitionTypes = ["logo-swipe-left", "mask-zoom", "logo-swipe-right", "crest-iris"];

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
    const state = await api("/api/state");
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
  try {
    const response = await fetch("/assets/monitor_spy_frames/manifest.json");
    if (response.ok) {
      const manifest = await response.json();
      const count = Number(manifest.frame_count || 1);
      spyFrameMs = Number(manifest.frame_ms || 180);
      spyFrames = Array.from({ length: count }, (_, index) =>
        `/assets/monitor_spy_frames/frame_${String(index).padStart(3, "0")}.png`
      );
    }
  } catch {
    spyFrames = ["/assets/monitor_spy_frames/frame_000.png"];
  }
  spyFrames.forEach((src) => {
    const image = new Image();
    image.src = src;
  });
  const pausedImage = new Image();
  pausedImage.src = pausedFrame;
  if (spyFrameTimer) clearInterval(spyFrameTimer);
  spyFrameTimer = null;
  if (!spyPaused) spyFrameTimer = setInterval(advanceSpyFrame, spyFrameMs);
}

function advanceSpyFrame() {
  if (spyPaused) return;
  const active = activeFrameLayer === "A" ? $("spySceneFrameA") : $("spySceneFrameB");
  const incoming = activeFrameLayer === "A" ? $("spySceneFrameB") : $("spySceneFrameA");
  if (!active || !incoming || !spyFrames.length) return;
  spyFrameIndex = (spyFrameIndex + 1) % spyFrames.length;
  incoming.src = spyFrames[spyFrameIndex];
  const scene = document.querySelector(".spy-scene");
  const transition = $("stageTransition");
  scene?.classList.remove("transitioning");
  if (transition) transition.className = "stage-transition";
  void scene?.offsetWidth;
  incoming.classList.add("active");
  active.classList.remove("active");
  scene?.classList.add("transitioning");
  if (transition) {
    const transitionType = stageTransitionTypes[transitionIndex % stageTransitionTypes.length];
    transitionIndex += 1;
    transition.classList.add("active", transitionType);
  }
  activeFrameLayer = activeFrameLayer === "A" ? "B" : "A";
  setTimeout(() => {
    scene?.classList.remove("transitioning");
    if (transition) transition.className = "stage-transition";
  }, 1900);
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

  frameA.src = spyFrames[spyFrameIndex] || spyFrames[0] || "/assets/monitor_spy_frames/frame_000.png";
  frameB.src = frameA.src;
  frameA.classList.add("active");
  frameB.classList.remove("active");
  activeFrameLayer = "A";
  if (!spyFrameTimer) spyFrameTimer = setInterval(advanceSpyFrame, spyFrameMs);
}

function render(state) {
  latestState = state;
  const runtime = state.runtime || {};
  const scan = runtime.scan || {};
  const status = scan.status || runtime.phase || "idle";
  setSpyPaused(!runtime.running);
  $("monitorStatus").className = `status-pill ${runtime.running ? "running" : "paused"}`;
  $("monitorStatus").textContent = runtime.running ? statusLabel(status) : "Paused";

  renderTarget("current", scan.current, {
    title: runtime.running ? currentTitle(status) : "Scanner paused",
    detail: runtime.running ? "No channel is active at this instant." : "Press Start in the main window.",
  });
  renderTarget("next", scan.next, {
    title: "None queued",
    detail: "The scanner is resting or waiting for a channel to become due.",
  });
  renderCompleted(scan.last_completed);
  renderUpcoming(scan.upcoming || []);
  renderPace(state);
  renderCountdowns();
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
    ? `#${target.channel_label || target.channel_id} - ${target.channel_id}`
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
  const maxChannels = Number(app.scanner_max_channels_per_cycle || 1);
  const cycleRest = Number(app.scanner_cycle_sleep_seconds || 45);
  const settleDelay = Number(app.scanner_channel_settle_seconds || 12);
  const minDelay = Number(app.scanner_min_channel_delay_seconds || 12);
  const maxDelay = Number(app.scanner_max_channel_delay_seconds || 35);
  const target = $("idleTarget");
  const detail = $("idleDetail");
  if (!target || !detail) return;
  target.textContent = runtime.running
    ? scan.status === "scanning"
      ? "Scanning now"
      : "Between channels"
    : "Paused";
  detail.textContent = `${maxChannels} channel${maxChannels === 1 ? "" : "s"}/cycle, ${formatSeconds(settleDelay)} settle, ${formatSeconds(cycleRest)} rest, ${formatDelayRange(minDelay, maxDelay)} channel delay`;
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
    : `<div class="queue-empty">No upcoming due channels are queued right now.</div>`;
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
  const toast = document.createElement("article");
  toast.className = "monitor-toast";
  toast.innerHTML = `
    <div class="toast-stars" aria-hidden="true"><span></span><span></span><span></span><span></span></div>
    <img src="/assets/monitor-arigato-sprite.png" alt="" />
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

loadSpyAnimation();
refresh();
refreshTimer = setInterval(refresh, 1800);
countdownTimer = setInterval(renderCountdowns, 1000);
window.addEventListener("beforeunload", () => {
  if (refreshTimer) clearInterval(refreshTimer);
  if (spyFrameTimer) clearInterval(spyFrameTimer);
  if (countdownTimer) clearInterval(countdownTimer);
});
