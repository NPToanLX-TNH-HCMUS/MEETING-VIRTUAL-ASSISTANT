import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const root = new URL("../", import.meta.url);
const source = fs.readFileSync(new URL("src/frontend/js/during.js", root), "utf8");
const html = fs.readFileSync(new URL("src/frontend/during.html", root), "utf8");
const flush = async () => { for (let n = 0; n < 10; n++) await new Promise(setImmediate); };

function element() {
  return {
    children: [], textContent: "", dataset: {}, style: {}, hidden: false, disabled: false,
    addEventListener(name, handler) { this[name] = handler; },
    setAttribute() {},
    replaceChildren(...children) { this.children = children; },
    append(...children) { this.children.push(...children); },
    appendChild(child) { this.children.push(child); },
    querySelectorAll() { return this.children; },
  };
}

test("REST catch-up deduplicates live delivery; disconnected viewer can still stop", async () => {
  const elements = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m => [m[1], element()]));
  let handlers, starts = 0, stops = 0;
  let state = { status: "live", seq: 1, elapsed_seconds: 10, remaining_seconds: 110 };
  const stored = [{ id: "s1", text: "First" }];
  const afterCalls = [];
  const api = {
    getMeeting: async () => ({ topic: "Offline", language: "vi", duration_minutes: 2 }),
    getMeetingState: async () => ({ ...state }),
    getTranscript: async (id, after) => {
      afterCalls.push(after);
      return { segments: stored.slice(after ? stored.findIndex(s => s.id === after) + 1 : 0) };
    },
    getAgenda: async () => ({ items: [] }),
    getSummaries: async () => ({ items: [] }),
    getExtractions: async () => ({ items: [] }),
    getConflicts: async () => ({ items: [] }),
    startMeeting: async () => { starts++; return state; },
    stopMeeting: async () => { stops++; state = { ...state, status: "processing", seq: 8 }; return state; },
  };
  const context = {
    TYPE_LABELS: {}, extractionDetails: () => [], formatTime: () => "--:--", renderReviewList: () => 0,
    api, URLSearchParams, location: { search: "?meeting=m1" }, Date, performance, console,
    document: {
      getElementById(id) { assert(elements[id], id); return elements[id]; },
      createElement: element,
    },
    window: { addEventListener() {} },
    setInterval: () => 1, clearInterval() {}, setTimeout, clearTimeout,
    connectMeetingSocket(id, callbacks) { handlers = callbacks; return { close() {} }; },
  };
  vm.createContext(context);
  vm.runInContext(source.replace(/^import .*;\r?\n/gm, ""), context);
  await flush();
  handlers.onOpen();
  await flush();
  assert.equal(elements["transcript-final"].children.map(row => row.children[1].children[0].textContent).join("\n"), "First");
  handlers.onClose({ code: 1006 });
  assert.equal(elements["stop-recording"].disabled, false);
  stored.push({ id: "s2", text: "Missed" });
  state.seq = 5;
  handlers.onOpen();
  await flush();
  assert(afterCalls.includes("s1"));
  handlers.onMessage({ type: "transcript.segment", meeting_id: "m1", seq: 6, data: stored[1] });
  await flush();
  assert.equal(elements["transcript-final"].children.map(row => row.children[1].children[0].textContent).join("\n"), "First\nMissed");
  stored.push({ id: "s3", text: "Gap recovered" });
  state.seq = 8;
  handlers.onMessage({ type: "timer.sync", meeting_id: "m1", seq: 8, data: {} });
  await flush();
  assert.equal(elements["transcript-final"].children.map(row => row.children[1].children[0].textContent).join("\n"), "First\nMissed\nGap recovered");
  await elements["stop-recording"].click();
  assert.equal(stops, 1);
  assert.equal(starts, 0); // Reconnect never starts another microphone.
});

test("socket uses canonical route, backs off and cancels reconnect on close", () => {
  const sockets = [], timers = new Map();
  let nextTimer = 0, delivered;
  class Socket {
    constructor(url) { this.url = url; this.handlers = {}; sockets.push(this); }
    addEventListener(type, callback) { this.handlers[type] = callback; }
    close() {}
  }
  const context = {
    location: { protocol: "http:", host: "localhost:5173" }, WebSocket: Socket,
    setTimeout(fn, delay) { const id = ++nextTimer; timers.set(id, { fn, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
  };
  vm.createContext(context);
  const socketCode = fs.readFileSync(new URL("src/frontend/js/socket.js", root), "utf8");
  vm.runInContext(socketCode.replace("export function", "function"), context);
  const channel = context.connectMeetingSocket("m1", { onMessage: event => delivered = event });
  assert.equal(sockets[0].url, "ws://localhost:5173/ws/meetings/m1");
  sockets[0].handlers.message({ data: JSON.stringify({
    meeting_id: "m1", seq: 1, type: "meeting.status", at: "now", data: { status: "live" },
  }) });
  assert.equal(delivered.data.status, "live");
  sockets[0].handlers.close({ code: 1006 });
  const first = timers.get(1);
  assert.equal(first.delay, 1000);
  timers.delete(1);
  first.fn();
  assert.equal(sockets.length, 2);
  sockets[1].handlers.close({ code: 1006 });
  assert.equal(timers.get(2).delay, 2000);
  channel.close();
  assert.equal(timers.size, 0);
});
