import { api } from "./api.js";
import { connectMeetingSocket } from "./socket.js";

const $ = (id) => document.getElementById(id);
const meetingId = new URLSearchParams(location.search).get("meeting");
const LANGUAGE = { vi: "Tiếng Việt", en: "English" };
let meetingState = { status: "loading", minutes_ready: false };
let controlPending = false;
let channel = null;
let lastSeq = null;
let lastSegmentId = null;
let eventChain = Promise.resolve();
let quietSince = null;
let timerAnchor = null;
let agendaItems = [];
let reconnectTimer = null;
let pageClosed = false;
const segments = new Map();
const summaries = new Map();

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = false;
}

function renderControls() {
  const active = ["live", "paused"].includes(meetingState.status);
  $("start-recording").disabled =
    controlPending || !meetingId || meetingState.status !== "ready";
  $("pause").disabled = controlPending || !active;
  $("stop-recording").disabled = controlPending || !active;
  $("pause").textContent = meetingState.status === "paused" ? "Tiếp tục" : "Tạm dừng";
  $("pause").setAttribute("aria-pressed", String(meetingState.status === "paused"));
  $("live-badge").hidden = !active;
  $("live-badge").textContent =
    meetingState.status === "paused" ? "ĐÃ TẠM DỪNG" : "ĐANG GHI ÂM";
  $("go-after-box").hidden = !meetingState.minutes_ready &&
    !(meetingState.transcript_saved && meetingState.error?.recoverable);
  $("go-after").href = `/after_meeting.html?meeting=${encodeURIComponent(meetingId)}`;
  $("transcript-status").textContent = {
    ready: "Sẵn sàng bắt đầu", live: "Đang ghi âm",
    paused: "Đã tạm dừng", processing: "Đang xử lý sau cuộc họp",
    review: "Biên bản đã sẵn sàng", archived: "Cuộc họp đã hoàn tất",
  }[meetingState.status] ?? "Đang tải cuộc họp…";
}

function applyState(state) {
  meetingState = { ...meetingState, ...state };
  if (["review", "archived"].includes(meetingState.status)) {
    meetingState.minutes_ready = true;
  }
  if (state.remaining_seconds !== undefined) {
    timerAnchor = { remaining: state.remaining_seconds, at: performance.now() };
  } else if (timerAnchor) {
    // Freeze/rebase between authoritative timer.sync messages.
    timerAnchor = { remaining: Number($("meeting-timer").dataset.remaining ?? timerAnchor.remaining),
      at: performance.now() };
  }
  if (meetingState.status !== "live") resetLevel();
  renderControls();
  tick();
}

function tick() {
  if (!timerAnchor) return;
  const delta = meetingState.status === "live"
    ? (performance.now() - timerAnchor.at) / 1000 : 0;
  const remaining = Math.max(0, timerAnchor.remaining - delta);
  $("meeting-timer").dataset.remaining = String(remaining);
  const seconds = Math.ceil(remaining);
  $("meeting-timer").textContent =
    `Còn lại ${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function resetLevel() {
  quietSince = null;
  $("audio-level").value = 0;
  $("audio-level-text").textContent = "Chưa có tín hiệu mới";
}

function showLevel(data) {
  if (meetingState.status !== "live") return;
  $("audio-level").value = data.level;
  if (data.dbfs < -50) {
    quietSince ??= Date.now();
    $("audio-level-text").textContent = Date.now() - quietSince >= 3000
      ? "Tín hiệu rất nhỏ. Hãy kiểm tra microphone." : "Đang chờ tiếng nói…";
  } else {
    quietSince = null;
    $("audio-level-text").textContent = `Mức tín hiệu: ${data.dbfs} dBFS`;
  }
}

function mergeSegments(items) {
  for (const segment of items) {
    segments.set(segment.id, segment);
  }
  if (items.length) lastSegmentId = items.at(-1).id;
  $("transcript-final").textContent = [...segments.values()].map(s => s.text).join("\n");
  $("transcript-empty").hidden = segments.size > 0;
}

function renderAgenda(items) {
  agendaItems = items;
  $("agenda-list").replaceChildren();
  const labels = {
    not_discussed: "Chưa thảo luận", in_progress: "Đang thảo luận",
    discussed: "Đã thảo luận", concluded: "Đã chốt",
  };
  for (const item of [...items].sort((a, b) => a.order - b.order)) {
    const row = document.createElement("li");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.disabled = true;
    checkbox.checked = ["discussed", "concluded"].includes(item.state);
    checkbox.setAttribute("aria-label", item.title);
    const label = document.createElement("span");
    label.textContent = ` ${item.title} — ${labels[item.state] ?? item.state}`;
    row.append(checkbox, label);
    $("agenda-list").appendChild(row);
  }
  $("agenda-empty").hidden = items.length > 0;
}

function addSummary(item) {
  const key = `${item.created_at}:${item.revision}`;
  if (summaries.has(key)) return;
  summaries.set(key, item);
  const container = $("live-summary");
  for (const old of container.querySelectorAll("details")) old.open = false;
  const entry = document.createElement("details");
  entry.open = true;
  const heading = document.createElement("summary");
  heading.textContent =
    `${new Date(item.created_at).toLocaleTimeString("vi-VN")} — đến đoạn ${item.revision}`;
  const content = document.createElement("div");
  content.style.whiteSpace = "pre-wrap";
  content.textContent = item.text;
  entry.append(heading, content);
  container.appendChild(entry);
  $("summary-status").textContent = `Có ${summaries.size} bản tóm tắt tạm thời.`;
}

// REST snapshot is fetched after subscribing. Events arriving during these requests
// remain queued in eventChain; replay only events newer than the snapshot seq.
async function synchronize() {
  const state = await api.getMeetingState(meetingId);
  let transcript;
  try {
    transcript = await api.getTranscript(meetingId, lastSegmentId);
  } catch (error) {
    if (error.code !== "INVALID_TRANSCRIPT_CURSOR") throw error;
    transcript = await api.getTranscript(meetingId);
    segments.clear();
    lastSegmentId = null;
  }
  const [agenda, history] = await Promise.all([
    api.getAgenda(meetingId), api.getSummaries(meetingId),
  ]);
  mergeSegments(transcript.segments);
  renderAgenda(agenda.items);
  for (const item of history.items) addSummary(item);
  applyState(state);
  lastSeq = state.seq;
  if (state.error) showError(state.error.message);
}

function enqueue(action) {
  const next = eventChain.then(action);
  eventChain = next.catch(error => showError(error.message));
  return next;
}

async function handleEnvelope(message) {
  if (lastSeq === null || message.seq > lastSeq + 1) {
    await synchronize();
  }
  if (message.seq <= lastSeq) return;
  lastSeq = message.seq;
  const data = message.data;
  switch (message.type) {
    case "meeting.status":
      applyState(data);
      if (data.status === "review") await synchronize();
      break;
    case "transcript.segment":
      // REST may already have supplied this segment while synchronization ran.
      if (!segments.has(data.id)) mergeSegments([data]);
      $("transcript-partial").textContent = "";
      break;
    case "transcript.partial":
      $("transcript-partial").textContent = data.text;
      break;
    case "audio.level": showLevel(data); break;
    case "summary.updated": addSummary(data); break;
    case "timer.sync": applyState(data); break;
    case "timer.warning": showError(`Cuộc họp còn ${data.remaining_seconds} giây.`); break;
    case "minutes.ready": await synchronize(); break;
    case "agenda.item_state": {
      const item = agendaItems.find(item => item.id === data.agenda_item_id);
      if (item) item.state = data.to;
      renderAgenda(agendaItems);
      break;
    }
    case "error":
      showError(data.message);
      await synchronize();
      break;
  }
}

function openChannel() {
  if (channel || pageClosed) return;
  channel = connectMeetingSocket(meetingId, {
    onOpen() {
      $("connection-status").textContent = "Đã kết nối cập nhật";
      enqueue(synchronize).catch(retrySynchronization);
    },
    onMessage(message) { enqueue(() => handleEnvelope(message)).catch(retrySynchronization); },
    onError(message) { $("connection-status").textContent = message; },
    onClose(event) {
      resetLevel();
      $("connection-status").textContent = event.code === 1008
        ? "Phiên không còn tồn tại."
        : "Đang kết nối lại. Các nút điều khiển REST vẫn hoạt động.";
      if (event.code === 1008) channel = null;
      // Never mark recording stopped merely because the viewer disconnected.
    },
  });
}

function retrySynchronization() {
  channel?.close();
  channel = null;
  clearTimeout(reconnectTimer);
  if (!pageClosed) reconnectTimer = setTimeout(openChannel, 2000);
}

async function runControl(action) {
  if (controlPending) return;
  controlPending = true;
  $("error").hidden = true;
  renderControls();
  try {
    await action();
    openChannel();
    await enqueue(synchronize);
  } catch (error) {
    showError(`${error.code ?? "ERROR"}: ${error.message}`);
    // An HTTP timeout does not mean that the server failed to execute start.
    try {
      await enqueue(synchronize);
      if (["live", "paused", "processing"].includes(meetingState.status)) openChannel();
    } catch { /* Preserve the original error. */ }
  } finally {
    controlPending = false;
    renderControls();
  }
}

$("start-recording").addEventListener("click", () => runControl(() => api.startMeeting(meetingId)));
$("pause").addEventListener("click", () => runControl(() =>
  meetingState.status === "paused" ? api.resumeMeeting(meetingId) : api.pauseMeeting(meetingId)
));
$("stop-recording").addEventListener("click", () => runControl(() => api.stopMeeting(meetingId)));

const ticker = setInterval(tick, 1000);
window.addEventListener("pagehide", () => {
  pageClosed = true;
  clearTimeout(reconnectTimer);
  channel?.close();
  clearInterval(ticker);
});

async function load() {
  if (!meetingId) {
    showError("Thiếu mã cuộc họp. Hãy quay lại bước agenda.");
    return;
  }
  try {
    const meeting = await api.getMeeting(meetingId);
    $("meeting-title").textContent = meeting.topic;
    $("meeting-meta").textContent =
      `${LANGUAGE[meeting.language] ?? meeting.language} · ${meeting.duration_minutes} phút · ${meeting.id}`;
    await enqueue(synchronize);
    if (["live", "paused", "processing", "review", "archived"].includes(meetingState.status)) openChannel();
  } catch (error) {
    showError(error.message);
  }
}
renderControls();
load();
