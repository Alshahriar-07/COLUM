/* COLUM app wiring — events, commands, sessions, voice, kill switch. */
"use strict";

const App = {
  busy: false,

  async init() {
    UI.applyTheme("light");
    this.bindStaticEvents();
    this.bindWSEvents();
    WS.connect();
    await this.loadSessions();
    await UI.refreshStatus();
    this.bindVoiceHotkey();
    UI.logLine("COLUM ready. Backend events stream live.");
  },

  // ------------------------------------------------------------------
  // Static UI events
  // ------------------------------------------------------------------
  bindStaticEvents() {
    UI.el("command-bar").addEventListener("submit", (e) => {
      e.preventDefault();
      const shift = UI.el("command-input").matches(":focus")
        && window.event && window.event.shiftKey;
      this.sendCommand(shift === true ? false : true);
    });

    UI.el("command-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.shiftKey) {
        e.preventDefault();
        this.sendCommand(false); // plan only
      }
    });

    UI.el("btn-new-session").addEventListener("click", () => this.newSession());
    UI.el("btn-settings").addEventListener("click", () => UI.openSettings());
    UI.el("settings-save").addEventListener("click", () => UI.saveSettings());
    UI.el("settings-cancel").addEventListener("click",
      () => UI.el("settings-overlay").classList.add("hidden"));
    UI.el("set-perm").addEventListener("change", (e) => {
      UI.el("allow-all-warning").classList.toggle(
        "hidden", e.target.value !== "allow_all");
    });

    UI.el("btn-about").addEventListener("click",
      () => UI.el("about-overlay").classList.remove("hidden"));
    UI.el("about-close").addEventListener("click",
      () => UI.el("about-overlay").classList.add("hidden"));

    UI.el("btn-kill").addEventListener("click", () => this.emergencyStop());
    UI.el("btn-stop").addEventListener("click", async () => {
      try {
        const r = await API.stop();
        UI.logLine(r.stopped ? "stop signal sent" : "nothing to stop");
      } catch (e) { UI.logLine(`stop failed: ${e.message}`); }
    });

    UI.el("btn-terminal").addEventListener("click", () => {
      UI.el("terminal-drawer").classList.toggle("hidden");
    });
    UI.el("btn-drawer-close").addEventListener("click",
      () => UI.el("terminal-drawer").classList.add("hidden"));

    UI.el("perm-approve").addEventListener("click", () => this.decidePermission(true));
    UI.el("perm-deny").addEventListener("click", () => this.decidePermission(false));

    UI.el("btn-voice").addEventListener("click", () => this.startVoice());
  },

  // ------------------------------------------------------------------
  // Commands
  // ------------------------------------------------------------------
  async sendCommand(execute) {
    const input = UI.el("command-input");
    const text = input.value.trim();
    if (!text || this.busy) return;
    input.value = "";
    UI.addMessage("user", text);
    this.busy = true;
    UI.resetAgents();
    UI.setMasterState("in_progress");
    try {
      const resp = await API.chat(text, UI.state.sessionId, execute);
      if (!UI.state.sessionId) {
        UI.state.sessionId = resp.session_id;
      }
      const msg = resp.message || {};
      if (msg.content) {
        UI.addMessage(msg.role || "master", msg.content);
      }
      if (resp.plan) {
        UI.state.planId = resp.plan.id;
        UI.setPlan(resp.plan.steps);
      }
      await this.loadSessions();
    } catch (e) {
      UI.addMessage("error", `Request failed: ${e.message}`);
      UI.setMasterState("failed");
    } finally {
      this.busy = false;
      if (UI.el("mastpe-state-value").textContent === "IN_PROGRESS") {
        UI.setMasterState("idle");
      }
    }
  },

  async newSession() {
    UI.state.sessionId = null;
    UI.state.planId = null;
    UI.el("chat-messages").innerHTML = "";
    UI.setPlan([]);
    UI.resetAgents();
    UI.setMasterState("idle");
    UI.setSessionTitle("New session");
    await this.loadSessions();
  },

  async loadSessions() {
    try {
      const resp = await API.sessions();
      const ul = UI.el("session-list");
      ul.innerHTML = "";
      resp.sessions.forEach((s) => {
        const li = document.createElement("li");
        li.textContent = s.title || s.session_id;
        li.title = `${s.title} · ${s.message_count} msgs`;
        if (s.session_id === UI.state.sessionId) li.classList.add("active");
        li.addEventListener("click", () => this.openSession(s.session_id, s.title));
        ul.appendChild(li);
      });
    } catch (_) { /* backend may be starting */ }
  },

  async openSession(sessionId, title) {
    try {
      const data = await API.session(sessionId);
      UI.state.sessionId = sessionId;
      UI.el("chat-messages").innerHTML = "";
      data.messages.forEach((m) => UI.addMessage(m.role, m.content));
      const lastPlanId = data.summary.last_plan_id;
      if (lastPlanId && data.plans[lastPlanId]) {
        UI.setPlan(data.plans[lastPlanId].steps);
      }
      UI.setSessionTitle(title);
      this.highlightSession();
    } catch (e) {
      UI.logLine(`open session failed: ${e.message}`);
    }
  },

  highlightSession() {
    document.querySelectorAll("#session-list li").forEach((li) => {
      li.classList.remove("active");
    });
  },

  // ------------------------------------------------------------------
  // WebSocket event handlers (real backend state → UI)
  // ------------------------------------------------------------------
  bindWSEvents() {
    WS.on("*", (ev) => {
      if (ev.message) UI.logLine(`${ev.event}: ${ev.message}`);
    });

    WS.on("planning_started", () => {
      UI.setMasterState("in_progress");
      UI.setAgent("input_analysis", "in_progress", "analyzing");
    });

    WS.on("agent_started", (ev) => {
      if (ev.agent) UI.setAgent(ev.agent, "in_progress", ev.message);
    });

    WS.on("agent_error", (ev) => {
      if (ev.agent) UI.setAgent(ev.agent, "failed", ev.message);
      UI.addMessage("error", `Agent error (${ev.agent || "unknown"}): ${ev.message}`);
    });

    WS.on("plan_created", (ev) => {
      UI.state.planId = ev.plan_id;
      if (ev.data && ev.data.steps) UI.setPlan(ev.data.steps);
      UI.setMasterState("in_progress");
      UI.setAgent("planner", "completed", "plan ready");
      UI.setAgent("tool_call", "completed", "calls refined");
    });

    WS.on("execution_started", () => {
      UI.setAgent("execution", "in_progress", "running plan");
    });

    WS.on("step_started", (ev) => {
      UI.setMasterState("in_progress");
      if (ev.step_id) UI.setStepState(ev.step_id, "in_progress");
      UI.setAgent("execution", "in_progress", ev.message);
    });

    WS.on("tool_result", (ev) => {
      UI.setAgent("tool_call", ev.data && ev.data.ok ? "completed" : "failed",
        ev.message);
      if (ev.data && typeof ev.data.duration_ms === "number") {
        UI.logLine(`tool ${ev.message} (${ev.data.duration_ms} ms)`);
      }
    });

    WS.on("step_progress", (ev) => {
      UI.setAgent("execution", "completed", ev.message);
    });

    WS.on("step_completed", (ev) => {
      if (ev.step_id) UI.setStepState(ev.step_id, "completed");
      UI.setAgent("execution", "completed", ev.message);
    });

    WS.on("step_retry", (ev) => {
      UI.setAgent("error_handler", "in_progress", ev.message);
    });

    WS.on("step_failed", (ev) => {
      if (ev.step_id) UI.setStepState(ev.step_id, "failed");
      UI.setAgent("error_handler", "failed", ev.message);
    });

    WS.on("step_failed_continue", (ev) => {
      if (ev.step_id) UI.setStepState(ev.step_id, "failed");
      UI.setAgent("error_handler", "in_progress", "continuing despite failure");
    });

    WS.on("permission_required", (ev) => {
      UI.setMasterState("waiting_permission");
      if (ev.data) {
        UI.showPermission({
          request_id: ev.data.request_id,
          tool: ev.data.tool,
          description: ev.message,
          risk: ev.data.risk,
          args_summary: ev.data.args_summary,
        });
      }
    });

    WS.on("permission_resolved", () => {
      UI.hidePermission();
      UI.setMasterState("in_progress");
    });

    WS.on("completed", (ev) => {
      UI.setMasterState(ev.status || "completed");
      UI.resetAgents();
    });

    WS.on("cancelled", () => {
      UI.setMasterState("cancelled");
      UI.resetAgents();
      UI.hidePermission();
    });

    WS.on("kill_switch_activated", (ev) => {
      UI.setMasterState("cancelled");
      UI.resetAgents();
      UI.hidePermission();
      UI.addMessage("error", `🛑 ${ev.message}`);
      UI.logLine("EMERGENCY STOP activated");
      // Allow a fresh run immediately after an emergency stop.
      API.killReset().catch(() => {});
    });
  },

  // ------------------------------------------------------------------
  // Permission decision
  // ------------------------------------------------------------------
  async decidePermission(approved) {
    const req = UI.state.permRequest;
    if (!req) return;
    UI.hidePermission();
    try {
      await API.permissionDecide(req.request_id, approved);
      UI.logLine(`permission ${approved ? "approved" : "denied"} for ${req.tool}`);
    } catch (e) {
      UI.logLine(`permission decision failed: ${e.message}`);
    }
  },

  // ------------------------------------------------------------------
  // Emergency stop
  // ------------------------------------------------------------------
  async emergencyStop() {
    try {
      await API.kill();
      UI.logLine("EMERGENCY STOP triggered");
    } catch (e) {
      UI.logLine(`kill failed: ${e.message}`);
    }
  },

  // ------------------------------------------------------------------
  // Voice (browser Web Speech fallback; backend STT used when available)
  // ------------------------------------------------------------------
  bindVoiceHotkey() {
    document.addEventListener("keydown", (e) => {
      if (e.ctrlKey && e.code === "Space") {
        e.preventDefault();
        this.startVoice();
      }
    });
  },

  startVoice() {
    const overlay = UI.el("voice-overlay");
    const hint = UI.el("voice-hint");
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      hint.textContent = "Browser speech recognition unavailable in this browser.";
      overlay.classList.remove("hidden");
      setTimeout(() => overlay.classList.add("hidden"), 2500);
      return;
    }
    const rec = new SR();
    rec.lang = "en-US";
    rec.interimResults = false;
    overlay.classList.remove("hidden");
    hint.textContent = "Listening…";
    rec.onresult = (e) => {
      const text = e.results[0][0].transcript;
      overlay.classList.add("hidden");
      UI.el("command-input").value = text;
      this.sendCommand(true);
    };
    rec.onerror = () => {
      hint.textContent = "Microphone error or permission denied.";
      setTimeout(() => overlay.classList.add("hidden"), 1800);
    };
    rec.onend = () => overlay.classList.add("hidden");
    rec.start();
  },
};

window.addEventListener("DOMContentLoaded", () => App.init());
