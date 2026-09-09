/* COLUM UI state — renders real backend state only (no mock statuses). */
"use strict";

const UI = {
  state: {
    sessionId: null,
    planId: null,
    agents: {},       // agent -> {status, model, message}
    steps: [],        // roadmap steps from backend
    permRequest: null,
    busy: false,
  },

  AGENTS: ["input_analysis", "planner", "tool_call", "execution", "error_handler"],

  el(id) { return document.getElementById(id); },

  // ------------------------------------------------------------------
  // Chat
  // ------------------------------------------------------------------
  addMessage(role, content, meta) {
    const wrap = this.el("chat-messages");
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    bubble.textContent = content;
    div.appendChild(bubble);
    if (meta) {
      const m = document.createElement("div");
      m.className = "msg-meta";
      m.textContent = meta;
      div.appendChild(m);
    }
    wrap.appendChild(div);
    this.el("chat-scroll").scrollTop = this.el("chat-scroll").scrollHeight;
    return div;
  },

  // ------------------------------------------------------------------
  // MASTPE monitor
  // ------------------------------------------------------------------
  setMasterState(state) {
    const el = this.el("mastpe-state-value");
    el.textContent = (state || "idle").toUpperCase();
    el.className = `mastpe-state-value ${state || "idle"}`;
  },

  setAgent(agent, status, message) {
    const card = document.querySelector(`.agent-card[data-agent="${agent}"]`);
    if (!card) return;
    const st = card.querySelector(".agent-status");
    st.textContent = message ? `${status}: ${message}`.slice(0, 120) : status;
    card.classList.remove("active", "done", "error");
    if (["in_progress", "running", "started"].includes(status)) card.classList.add("active");
    else if (["completed", "ok"].includes(status)) card.classList.add("done");
    else if (["failed", "error", "cancelled"].includes(status)) card.classList.add("error");
  },

  resetAgents() {
    this.AGENTS.forEach((a) => this.setAgent(a, "idle", ""));
  },

  setPlan(steps) {
    this.state.steps = steps || [];
    const ol = this.el("plan-roadmap");
    ol.innerHTML = "";
    this.state.steps.forEach((s, i) => {
      const li = document.createElement("li");
      li.dataset.stepId = s.id;
      li.innerHTML =
        `<span class="step-num">${i + 1}.</span>` +
        `<span class="step-desc"></span>` +
        `<span class="step-state step-state-${s.state}">${s.state.replace("_", " ")}</span>` +
        `<span class="step-risk risk-${s.risk}">${s.risk}</span>`;
      li.querySelector(".step-desc").textContent = s.description;
      ol.appendChild(li);
    });
  },

  setStepState(stepId, state) {
    const li = document.querySelector(`.plan-roadmap li[data-step-id="${stepId}"]`);
    if (!li) return;
    const chip = li.querySelector(".step-state");
    chip.textContent = state.replace("_", " ");
    chip.className = `step-state step-state-${state}`;
  },

  // ------------------------------------------------------------------
  // Drawer log
  // ------------------------------------------------------------------
  logLine(text) {
    const pre = this.el("drawer-log");
    const stamp = new Date().toLocaleTimeString();
    pre.textContent += `[${stamp}] ${text}\n`;
    pre.scrollTop = pre.scrollHeight;
  },

  // ------------------------------------------------------------------
  // Permission dialog
  // ------------------------------------------------------------------
  showPermission(req) {
    this.state.permRequest = req;
    this.el("perm-tool").textContent = req.tool;
    this.el("perm-desc").textContent = req.description;
    const risk = this.el("perm-risk");
    risk.textContent = req.risk;
    risk.className = `risk-chip risk-${req.risk}`;
    this.el("perm-args").textContent = req.args_summary || "(no arguments)";
    this.el("permission-overlay").classList.remove("hidden");
  },

  hidePermission() {
    this.el("permission-overlay").classList.add("hidden");
    this.state.permRequest = null;
  },

  // ------------------------------------------------------------------
  // Settings
  // ------------------------------------------------------------------
  async openSettings() {
    try {
      const s = await API.getSettings();
      this.el("set-provider").value = s.active_provider || "openrouter";
      this.el("set-key1").value = "";
      this.el("set-key2").value = "";
      this.el("set-key1").placeholder = s.openrouter_key_1_set
        ? `configured (${s.openrouter_key_1_masked})` : "sk-or-…";
      this.el("set-key2").placeholder = s.openrouter_key_2_set
        ? `configured (${s.openrouter_key_2_masked})` : "sk-or-…";
      this.el("set-perm").value = s.permission_mode || "confirm_risky";
      this.el("set-theme").value = s.theme || "light";
      this.el("allow-all-warning").classList.toggle(
        "hidden", s.permission_mode !== "allow_all");
      this.el("settings-overlay").classList.remove("hidden");
    } catch (e) {
      this.logLine(`settings load failed: ${e.message}`);
    }
  },

  async saveSettings() {
    const patch = {
      active_provider: this.el("set-provider").value,
      permission_mode: this.el("set-perm").value,
      theme: this.el("set-theme").value,
    };
    const k1 = this.el("set-key1").value.trim();
    const k2 = this.el("set-key2").value.trim();
    if (k1) patch.openrouter_key_1 = k1;
    if (k2) patch.openrouter_key_2 = k2;
    try {
      const resp = await API.saveSettings(patch);
      this.applyTheme(resp.settings.theme);
      this.el("settings-overlay").classList.add("hidden");
      this.logLine("settings saved");
      this.refreshStatus();
    } catch (e) {
      this.logLine(`settings save failed: ${e.message}`);
    }
  },

  applyTheme(theme) {
    document.body.dataset.theme = theme === "dark" ? "dark" : "light";
  },

  // ------------------------------------------------------------------
  // Status panels
  // ------------------------------------------------------------------
  async refreshStatus() {
    try {
      const st = await API.status();
      this.el("usage-requests").textContent = st.usage.total_requests;
      this.el("usage-prompt").textContent = st.usage.total_prompt_tokens;
      this.el("usage-completion").textContent = st.usage.total_completion_tokens;
      this.el("provider-active").textContent = st.providers.active_provider;
      this.el("provider-chain").textContent =
        (st.providers.chain || []).map((p) => p.provider).join(" → ") || "—";
      this.el("about-version").textContent = st.version;
    } catch (_) { /* backend unreachable; conn dot already reflects it */ }
  },

  setSessionTitle(title) {
    this.el("session-title").textContent = title || "New session";
  },
};
