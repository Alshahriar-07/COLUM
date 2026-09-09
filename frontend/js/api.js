/* COLUM API client — thin wrappers over the real backend endpoints. */
"use strict";

const API = {
  async _json(resp) {
    if (!resp.ok) {
      let detail = resp.statusText;
      try { detail = (await resp.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    return resp.json();
  },

  async status() {
    return this._json(await fetch("/api/status"));
  },

  async getSettings() {
    return this._json(await fetch("/api/settings"));
  },

  async saveSettings(patch) {
    return this._json(await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }));
  },

  async chat(message, sessionId, execute) {
    return this._json(await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId, execute }),
    }));
  },

  async sessions() {
    return this._json(await fetch("/api/session"));
  },

  async session(sessionId) {
    return this._json(await fetch(`/api/session/${sessionId}`));
  },

  async deleteSession(sessionId) {
    return this._json(await fetch(`/api/session/${sessionId}`, { method: "DELETE" }));
  },

  async permissionDecide(requestId, approved) {
    return this._json(await fetch("/api/permission/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: requestId, approved }),
    }));
  },

  async screen() {
    return this._json(await fetch("/api/screen"));
  },

  async kill() {
    return this._json(await fetch("/api/kill", { method: "POST" }));
  },

  async killReset() {
    return this._json(await fetch("/api/kill/reset", { method: "POST" }));
  },

  async stop() {
    return this._json(await fetch("/api/stop", { method: "POST" }));
  },
};
