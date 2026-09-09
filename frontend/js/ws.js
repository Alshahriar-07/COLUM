/* COLUM WebSocket client — live AgentEvent stream with reconnect. */
"use strict";

const WS = {
  _sock: null,
  _retry: 0,
  _handlers: {},

  on(event, fn) { (this._handlers[event] = this._handlers[event] || []).push(fn); },

  _dispatch(ev) {
    (this._handlers[ev.event] || []).forEach((fn) => {
      try { fn(ev); } catch (e) { console.error("ws handler failed", e); }
    });
    (this._handlers["*"] || []).forEach((fn) => fn(ev));
  },

  connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const sock = new WebSocket(`${proto}://${location.host}/ws/events`);
    this._sock = sock;

    sock.onopen = () => {
      this._retry = 0;
      document.getElementById("connection-dot").classList.add("connected");
      document.getElementById("connection-dot").classList.remove("disconnected");
    };

    sock.onmessage = (m) => {
      try { this._dispatch(JSON.parse(m.data)); } catch (_) {}
    };

    sock.onclose = () => {
      document.getElementById("connection-dot").classList.remove("connected");
      document.getElementById("connection-dot").classList.add("disconnected");
      const delay = Math.min(1000 * 2 ** this._retry++, 15000);
      setTimeout(() => this.connect(), delay);
    };

    sock.onerror = () => sock.close();
  },
};
