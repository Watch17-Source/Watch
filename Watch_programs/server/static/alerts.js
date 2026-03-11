// WATCH Global Alerts (always-on alarm prompt + audio ring)
// - Runs on every page while logged in (injected by base.html)
// - Polls /api/v1/admin/alerts for active alarms
// - Shows a prompt with room name + status
// - Plays a "ringing" siren using Web Audio (no external file needed)
// - Sends ACK to server when guard clicks "Okay" (stops ringing immediately)

(function () {
  if (!window.WATCH) return;

  const ALERTS_URL = "/api/v1/admin/alerts";
  const ACK_URL_PREFIX = "/api/v1/admin/device/"; // + <id> + /ack

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";

  // ---- Tab identity + "master tab" lock (prevents multiple tabs ringing at once) ----
  const TAB_ID = (function () {
    try {
      const existing = sessionStorage.getItem("watch_tab_id");
      if (existing) return existing;
      const id = (crypto && crypto.randomUUID) ? crypto.randomUUID() : ("tab_" + Math.random().toString(16).slice(2));
      sessionStorage.setItem("watch_tab_id", id);
      return id;
    } catch {
      return "tab_" + Math.random().toString(16).slice(2);
    }
  })();

  const MASTER_KEY = "watch_alert_master";
  const MASTER_TTL_MS = 6500;

  function nowMs() { return Date.now(); }

  function readMaster() {
    try {
      const raw = localStorage.getItem(MASTER_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  function writeMaster(tabId) {
    try {
      localStorage.setItem(MASTER_KEY, JSON.stringify({ tabId, ts: nowMs() }));
    } catch {
      // ignore
    }
  }

  function isMaster() {
    const m = readMaster();
    if (!m) return false;
    return m.tabId === TAB_ID && (nowMs() - (m.ts || 0)) < MASTER_TTL_MS;
  }

  function ensureMaster() {
    const m = readMaster();
    const expired = !m || (nowMs() - (m.ts || 0)) >= MASTER_TTL_MS;
    if (expired) {
      writeMaster(TAB_ID);
      return;
    }
    if (m.tabId === TAB_ID) {
      // heartbeat
      writeMaster(TAB_ID);
    }
  }

  // heartbeat periodically
  setInterval(ensureMaster, 2500);
  window.addEventListener("beforeunload", () => {
    try {
      const m = readMaster();
      if (m && m.tabId === TAB_ID) localStorage.removeItem(MASTER_KEY);
    } catch {}
  });

  // ---- Audio (Web Audio siren) ----
  let audioCtx = null;
  let sirenOsc = null;
  let sirenGain = null;
  let sirenTimer = null;

  function isAudioEnabled() {
    try {
      return localStorage.getItem("watch_audio_enabled") === "1";
    } catch {
      return false;
    }
  }

  function setAudioEnabled(v) {
    try {
      localStorage.setItem("watch_audio_enabled", v ? "1" : "0");
    } catch {}
  }

  async function enableAudioFromGesture() {
    if (!("AudioContext" in window) && !("webkitAudioContext" in window)) {
      throw new Error("Web Audio not supported");
    }
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    // resume must be triggered by user gesture
    await audioCtx.resume();
    setAudioEnabled(true);
  }

  function startSiren() {
    if (!isAudioEnabled()) return;
    if (!isMaster()) return;

    // don't double-start
    if (sirenOsc) return;

    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();

      sirenOsc = audioCtx.createOscillator();
      sirenGain = audioCtx.createGain();

      sirenOsc.type = "sine";
      sirenOsc.frequency.value = 740;

      // Keep volume moderate; adjust here if needed
      sirenGain.gain.value = 0.08;

      sirenOsc.connect(sirenGain);
      sirenGain.connect(audioCtx.destination);

      sirenOsc.start();

      // Simple two-tone siren
      let high = false;
      sirenTimer = setInterval(() => {
        if (!sirenOsc) return;
        high = !high;
        const f = high ? 980 : 620;
        try {
          sirenOsc.frequency.setTargetAtTime(f, audioCtx.currentTime, 0.015);
        } catch {
          sirenOsc.frequency.value = f;
        }
      }, 420);
    } catch {
      // If anything goes wrong, fail silently (UI still works)
      stopSiren();
    }
  }

  function stopSiren() {
    if (sirenTimer) {
      clearInterval(sirenTimer);
      sirenTimer = null;
    }
    if (sirenOsc) {
      try { sirenOsc.stop(); } catch {}
      try { sirenOsc.disconnect(); } catch {}
      sirenOsc = null;
    }
    if (sirenGain) {
      try { sirenGain.disconnect(); } catch {}
      sirenGain = null;
    }
  }

  // If user already enabled audio in localStorage, try to resume audio on the first tap/click anywhere.
  // (Browsers still require a gesture per session.)
  if (isAudioEnabled()) {
    const resumeOnce = async () => {
      try {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        await audioCtx.resume();
      } catch {}
    };
    window.addEventListener("pointerdown", resumeOnce, { once: true, capture: true });
    window.addEventListener("keydown", resumeOnce, { once: true, capture: true });
  }

  // ---- UI Elements ----
  const overlay = document.getElementById("watch-alert-overlay");
  const itemsEl = document.getElementById("watch-alert-items");
  const subtitleEl = document.getElementById("watch-alert-subtitle");

  const audioToast = document.getElementById("watch-audio-toast");
  const audioBtn = document.getElementById("watch-enable-audio");
  const audioDismissBtn = document.getElementById("watch-dismiss-audio");
  const audioStatusEl = document.getElementById("watch-audio-status");

  function showAudioToast(reason) {
    if (!audioToast) return;
    // If previously dismissed, still show again during a real alarm
    const dismissed = (function () {
      try { return localStorage.getItem("watch_audio_dismissed") === "1"; } catch { return false; }
    })();

    if (dismissed && reason !== "alarm") return;
    audioToast.hidden = false;
    if (audioStatusEl) audioStatusEl.textContent = "";
  }

  function hideAudioToast() {
    if (!audioToast) return;
    audioToast.hidden = true;
  }

  if (audioBtn) {
    audioBtn.addEventListener("click", async () => {
      try {
        await enableAudioFromGesture();
        if (audioStatusEl) audioStatusEl.textContent = "Sound enabled ✅";
        setTimeout(hideAudioToast, 550);
      } catch (e) {
        if (audioStatusEl) audioStatusEl.textContent = "Could not enable sound in this browser/device.";
      }
    });
  }

  if (audioDismissBtn) {
    audioDismissBtn.addEventListener("click", () => {
      try { localStorage.setItem("watch_audio_dismissed", "1"); } catch {}
      hideAudioToast();
    });
  }

  // Show toast once right after login (server sets audioPrompt flag)
  if (window.WATCH.audioPrompt && !isAudioEnabled()) {
    showAudioToast("login");
  }

  // ---- Alarm state tracking ----
  const seenCaseIds = new Set(); // unacked alarms we've already reacted to (this tab)

  function setOverlayVisible(v) {
    if (!overlay) return;
    overlay.hidden = !v;
  }

  function setFlashEnabled(v) {
    if (!window.WATCH.flashEnabled) return;
    document.body.classList.toggle("watch-flash", !!v);
  }

  function formatStarted(iso) {
    if (!iso) return "—";
    // Keep it readable (UTC ISO already)
    return iso.replace("T", " ").replace("+00:00", "Z");
  }

  function renderAlarms(alarms) {
    if (!itemsEl) return;
    itemsEl.innerHTML = "";

    for (const a of alarms) {
      const row = document.createElement("div");
      row.className = "watch-alert-row";

      const top = document.createElement("div");
      top.className = "watch-alert-row-top";

      const left = document.createElement("div");
      left.innerHTML = `
        <div class="watch-alert-room">${escapeHtml(a.device_name || "Unknown room")}</div>
      `;

      const pill = document.createElement("div");
      pill.className = "pill broke";
      pill.textContent = (a.status || "Broke");

      top.appendChild(left);
      top.appendChild(pill);

      const meta = document.createElement("div");
      meta.className = "watch-alert-meta";
      meta.innerHTML = `
        <div><span class="k">Started:</span> <span class="v">${escapeHtml(formatStarted(a.case_started_at))}</span></div>
        <div><span class="k">IP:</span> <span class="v">${escapeHtml(a.ip || "—")}</span></div>
        <div><span class="k">Ack:</span> <span class="v">${a.ack_pending ? "sent (waiting)" : "not sent"}</span></div>
      `;

      const actions = document.createElement("div");
      actions.className = "watch-alert-actions";

      const okBtn = document.createElement("button");
      okBtn.className = "btn primary";
      okBtn.type = "button";
      okBtn.textContent = "Okay";
      okBtn.disabled = !!a.ack_pending;

      okBtn.addEventListener("click", async () => {
        // Stop ringing immediately on OK click (per requirement)
        stopSiren();
        setFlashEnabled(false);

        okBtn.disabled = true;
        okBtn.textContent = "Sending…";

        try {
          const resp = await fetch(`${ACK_URL_PREFIX}${encodeURIComponent(a.device_id)}/ack`, {
            method: "POST",
            headers: {
              "Accept": "application/json",
              "Content-Type": "application/json",
              "X-CSRF-Token": csrfToken,
            },
            body: "{}",
            cache: "no-store",
            credentials: "same-origin",
          });

          if (!resp.ok) throw new Error("ACK failed");
          okBtn.textContent = "Ack sent ✅";
        } catch {
          okBtn.disabled = false;
          okBtn.textContent = "Okay";
          // Keep UI visible; siren remains stopped for this tab, but polling may re-trigger if still unacked.
          // Provide a subtle hint:
          if (subtitleEl) subtitleEl.textContent = "Network error while sending ACK. Try again.";
        }
      });

      const openLink = document.createElement("a");
      openLink.className = "btn";
      openLink.href = `/device/${encodeURIComponent(a.device_id)}`;
      openLink.textContent = "Open room";

      actions.appendChild(okBtn);
      actions.appendChild(openLink);

      row.appendChild(top);
      row.appendChild(meta);
      row.appendChild(actions);

      itemsEl.appendChild(row);
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  // ---- Optional: browser notifications (only if already granted) ----
  function notifyIfAllowed(alarm) {
    try {
      if (!("Notification" in window)) return;
      if (Notification.permission !== "granted") return;

      const title = "🚨 Intruder detected";
      const body = `${alarm.device_name || "Unknown room"} — tap to open`;
      const n = new Notification(title, { body, tag: "watch-intruder", renotify: true });
      n.onclick = () => { window.focus(); window.location.href = `/device/${alarm.device_id}`; };
    } catch {
      // ignore
    }
  }

  // ---- Poll loop with adaptive timing ----
  let lastHadUnacked = false;

  async function pollOnce() {
    ensureMaster(); // keep master lock fresh

    let data;
    try {
      const resp = await fetch(ALERTS_URL, {
        headers: { "Accept": "application/json" },
        cache: "no-store",
        credentials: "same-origin",
      });
      if (!resp.ok) throw new Error("bad response");
      data = await resp.json();
    } catch {
      // If the server is temporarily unreachable, don't break the UI.
      return { alarms: [], hadUnacked: false };
    }

    const alarms = Array.isArray(data.alarms) ? data.alarms : [];
    const unacked = alarms.filter(a => !a.ack_pending);

    // Update subtitle
    if (subtitleEl) {
      if (alarms.length === 0) subtitleEl.textContent = "";
      else subtitleEl.textContent = `Active alarm(s): ${alarms.length}`;
    }

    // Render + visibility
    if (alarms.length > 0) {
      renderAlarms(alarms);
      setOverlayVisible(true);
    } else {
      setOverlayVisible(false);
    }

    // Ring if there is at least one unacked alarm
    const hadUnacked = unacked.length > 0;

    if (hadUnacked) {
      // If audio isn't enabled, prompt immediately
      if (!isAudioEnabled()) showAudioToast("alarm");

      // Detect new alarm(s) by case_id
      for (const a of unacked) {
        const cid = a.case_id;
        if (cid && !seenCaseIds.has(cid)) {
          seenCaseIds.add(cid);
          notifyIfAllowed(a);
        }
      }

      setFlashEnabled(true);
      startSiren();
    } else {
      setFlashEnabled(false);
      stopSiren();
    }

    lastHadUnacked = hadUnacked;
    return { alarms, hadUnacked };
  }

  async function pollLoop() {
    await pollOnce();

    // Adaptive delay:
    // - Unacked alarm: poll faster
    // - Hidden tab: slightly slower (still responsive)
    const base = Number(window.WATCH.alertPollMs || 1200);
    const hidden = document.visibilityState === "hidden";
    const delay = lastHadUnacked ? 850 : (hidden ? Math.max(base * 2, 2200) : base);

    setTimeout(pollLoop, delay);
  }

  pollLoop();
})();
