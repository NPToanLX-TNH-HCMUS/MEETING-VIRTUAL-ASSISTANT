import { TYPE_LABELS, extractionDetails, formatTime, renderReviewList } from "./review.js";
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
const extractions = new Map();
// Conflicts by id (two values said for one field); the user picks, never the UI.
const conflicts = new Map();
let meetingStatus = null;
// Questions asked on this page, oldest first: { question, result, error } (both null while waiting).
// Memory only, never localStorage: answers quote the transcript.
const asks = [];
let askPending = false;
let askUnread = 0; // answers (or failures) that came back while the chat window was closed
let meetingLanguage = null;
const ASK_STATUSES = ["live", "paused"];
// Starter questions in the meeting language, since the assistant answers in the question's language.
const STARTERS = {
  vi: ["Vừa rồi bàn gì?", "Đã quyết định những gì?", "Còn bao lâu nữa?"],
  en: ["What did we just discuss?", "What has been decided?", "How much time is left?"],
};
const INTENT_LABELS = {
  time_progress: "Time & progress",
  meeting_information: "From the meeting",
  // Text label, not only colour: a suggestion must never read like a team decision.
  idea_suggestion: "AI suggestion · not a team decision",
};


function renderAskControls() {
  const open = ASK_STATUSES.includes(meetingStatus);
  $("ask-input").disabled = !open;
  $("ask-submit").disabled = !open || askPending;
  $("ask-submit").textContent = askPending ? "Asking…" : "Ask";
  // Shown only before the first question, while asking is possible.
  const starters = asks.length || !open ? [] : STARTERS[meetingLanguage] ?? STARTERS.en;
  $("ask-starters").hidden = !starters.length;
  $("ask-starters").replaceChildren(
    ...starters.map((question) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ask__starter";
      button.textContent = question;
      button.disabled = askPending;
      button.addEventListener("click", () => sendQuestion(question));
      return button;
    }),
  );
}

function copyButton(text) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "ask__action";
  button.textContent = "Copy";
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
    } catch {
      // The browser can refuse clipboard access (permission, embedded frame).
      button.textContent = "Copy failed";
    }
    setTimeout(() => { button.textContent = "Copy"; }, 2000);
  });
  return button;
}

function sourceChip(id, byId) {
  const segment = byId.get(id);
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = "seg-tag ask__source";
  chip.textContent = segment ? `${formatTime(segment.start_seconds)} · ${segment.text}` : id;
  chip.title = segment ? `“${segment.text}” — show in the transcript` : "Not in the transcript on this page";
  chip.disabled = !segment;
  chip.addEventListener("click", () => showSegment(id));
  return chip;
}

function renderAsks() {
  const byId = new Map([...segments.values()].map((segment) => [segment.id, segment]));
  $("ask-empty").hidden = asks.length > 0;
  $("ask-list").replaceChildren(
    ...asks.map((entry) => {
      const { question, result, error } = entry;
      const card = document.createElement("li");
      card.className = "capture" + (result?.is_ai_suggestion ? " capture--ai" : "");
      const asked = document.createElement("p");
      asked.className = "ask__question";
      asked.textContent = question;
      card.append(asked);
      if (error) {
        // The failure stays on its own question, with a way to send it again.
        const flag = document.createElement("p");
        flag.className = "capture__meta capture__flag";
        flag.textContent = error;
        const retry = document.createElement("button");
        retry.type = "button";
        retry.className = "ask__action";
        retry.textContent = "Try again";
        retry.disabled = askPending || !ASK_STATUSES.includes(meetingStatus);
        retry.addEventListener("click", () => sendQuestion(question, entry));
        card.append(flag, retry);
        return card;
      }
      if (!result) {
        const waiting = document.createElement("p");
        waiting.className = "capture__meta";
        waiting.textContent = "Thinking…";
        card.append(waiting);
        return card;
      }

      const type = document.createElement("p");
      type.className = "capture__type";
      type.textContent = INTENT_LABELS[result.intent] ?? result.intent;
      const answer = document.createElement("p");
      answer.className = "capture__content";
      answer.textContent = result.answer;
      card.append(type, answer);

      if (result.sources.length) {
        const box = document.createElement("div");
        box.className = "seg-tags";
        box.append(...result.sources.map((id) => sourceChip(id, byId)));
        card.append(box);
      } else if (result.intent === "meeting_information") {
        // An answer about the meeting with no cited line is flagged, never shown as fact.
        const flag = document.createElement("p");
        flag.className = "capture__meta capture__flag";
        flag.textContent = "No evidence in the transcript";
        card.append(flag);
      }
      card.append(copyButton(result.answer));
      return card;
    }),
  );
  const panel = $("ask-list").parentElement;
  panel.scrollTop = panel.scrollHeight;
}

function setAskOpen(open) {
  $("ask-panel").hidden = !open;
  $("ask-toggle").hidden = open;
  $("ask-toggle").setAttribute("aria-expanded", String(open));
  if (open) {
    askUnread = 0;
    renderAskUnread();
    const thread = $("ask-list").parentElement;
    thread.scrollTop = thread.scrollHeight;
    ($("ask-input").disabled ? $("ask-close") : $("ask-input")).focus();
  } else {
    $("ask-toggle").focus();
  }
}

function renderAskUnread() {
  $("ask-unread").hidden = !askUnread;
  $("ask-unread").textContent = ` · ${askUnread} new`;
}

function showSegment(id) {
  const row = [...$("transcript-final").children].find((el) => el.dataset.segmentId === id);
  if (!row) return;
  // On a phone the chat window covers the transcript, so it steps aside.
  if (matchMedia("(max-width: 767px)").matches) setAskOpen(false);
  row.scrollIntoView({ block: "center", behavior: "smooth" });
  row.classList.add("segment--focus");
  setTimeout(() => row.classList.remove("segment--focus"), 2000);
}

function segmentTag(item) {
  const tag = document.createElement("span");
  tag.className = `seg-tag seg-tag--${item.type}` + (item.needs_confirmation ? " seg-tag--confirm" : "");
  tag.textContent = [TYPE_LABELS[item.type], item.content, ...extractionDetails(item, conflicts.values())].join(" · ");
  return tag;
}

function renderSegments() {
  const all = [...extractions.values()];
  $("transcript-final").replaceChildren(
    ...[...segments.values()].map((segment) => {
      const row = document.createElement("div");
      row.className = "segment" + (segment.is_low_confidence ? " segment--low" : "");
      if (segment.id) row.dataset.segmentId = segment.id;
      const time = document.createElement("span");
      time.className = "segment__time";
      time.textContent = formatTime(segment.start_seconds);
      const body = document.createElement("div");
      const p = document.createElement("p");
      p.className = "segment__text";
      p.textContent = segment.text;
      body.append(p);
      if (segment.is_low_confidence) {
        const note = document.createElement("p");
        note.className = "segment__note";
        note.textContent = "Low confidence. Check the audio.";
        body.append(note);
      }
      // A tag under each sentence the item cites as evidence.
      const tags = all.filter((item) => segment.id && item.evidence.segment_ids.includes(segment.id));
      if (tags.length) {
        const box = document.createElement("div");
        box.className = "seg-tags";
        box.append(...tags.map(segmentTag));
        body.append(box);
      }
      row.append(time, body);
      return row;
    }),
  );
}

function renderCaptured() {
  const byId = new Map([...segments.values()].map((segment) => [segment.id, segment]));
  const items = [...extractions.values()];
  $("captured-count").textContent = `${items.length} ${items.length === 1 ? "item" : "items"}`;
  $("captured-empty").hidden = items.length > 0;
  $("captured-list").replaceChildren(
    ...items.map((item) => {
      const card = document.createElement("li");
      card.className = "capture" + (item.needs_confirmation ? " capture--confirm" : "");

      const type = document.createElement("p");
      type.className = "capture__type";
      type.textContent = [TYPE_LABELS[item.type] ?? item.type, item.needs_confirmation && "Needs confirmation"]
        .filter(Boolean).join(" · ");

      const content = document.createElement("p");
      content.className = "capture__content";
      content.textContent = item.content;
      card.append(type, content);

      const details = extractionDetails(item, conflicts.values());
      if (details.length) {
        const meta = document.createElement("p");
        meta.className = "capture__meta";
        meta.textContent = details.join(" · ");
        card.append(meta);
      }

      // Evidence is always shown; an item without it is flagged, never hidden.
      const evidence = document.createElement("p");
      const ids = item.evidence.segment_ids;
      if (ids.length) {
        evidence.className = "capture__meta";
        const times = ids.map((id) => formatTime(byId.get(id)?.start_seconds));
        evidence.textContent = `Evidence: ${times.join(", ")}` + (item.is_low_confidence ? " (low confidence)" : "");
        evidence.title = `“${item.evidence.quote}”`;
      } else {
        evidence.className = "capture__meta capture__flag";
        evidence.textContent = "No evidence in the transcript";
      }
      card.append(evidence);
      return card;
    }),
  );
}

// "Needs your choice": open conflicts, then items missing a field or evidence.
function renderChoices() {
  const count = renderReviewList($("choice-list"), {
    items: [...extractions.values()],
    conflicts: [...conflicts.values()],
    segmentsById: new Map([...segments.values()].map((segment) => [segment.id, segment])),
    onChoose: chooseValue,
    canChoose: ["live", "paused", "processing", "review"].includes(meetingStatus),
  });
  $("choice-count").textContent = count ? `${count} open` : "";
  $("choice-empty").hidden = count > 0;
}

function renderReview() {
  renderChoices();
  renderCaptured();
  renderSegments();
}

function setExtractions(items) {
  extractions.clear();
  for (const item of items) extractions.set(item.id, item);
  renderReview();
}

function setConflicts(items) {
  conflicts.clear();
  for (const conflict of items) conflicts.set(conflict.id, conflict);
  renderReview();
}

async function chooseValue(conflict, value) {
  try {
    conflicts.set(conflict.id, await api.resolveConflict(meetingId, conflict.id, value));
  } catch (e) {
    showError(`Could not save the choice: ${e.message}`);
    // Someone else may have chosen already: show what the backend has now.
    if (e.code === "CONFLICT_ALREADY_RESOLVED") setConflicts((await api.getConflicts(meetingId)).items);
    else renderChoices();
    return;
  }
  // The extraction took the chosen value on the backend; read it back.
  await loadExtractions();
}


async function loadExtractions() { await synchronize(); }
const stateLabels = {
  not_discussed: "Not discussed",
  in_progress: "In progress",
  discussed: "Discussed",
  concluded: "Concluded",
};
const scoreFormat = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function renderRichAgenda() {
  // Tạo bản sao rồi sắp xếp theo thứ tự agenda.
  const sortedItems = [...agendaItems].sort((a, b) => a.order - b.order);

  $("agenda-list").replaceChildren(
    ...sortedItems.map((item, i) => {
      const row = document.createElement("li");
      row.className = "agenda-card" + (item.state === "in_progress" ? " agenda-card--active" : "");

      const top = document.createElement("div");
      top.className = "agenda-card__top";
      const title = document.createElement("span");
      title.textContent = `${i + 1}. ${item.title}`;
      // Trạng thái luôn có chữ, không chỉ dựa vào màu.
      const state = document.createElement("span");
      state.className = `state-badge state-badge--${item.state}`;
      state.textContent = stateLabels[item.state] ?? "Unknown";
      if (item.last_evidence?.quote) state.title = `Evidence: “${item.last_evidence.quote}”`;
      top.append(title, state);

      const meta = document.createElement("p");
      meta.className = "agenda-card__meta";
      meta.textContent = [
        item.estimated_minutes != null && `Estimated ${item.estimated_minutes} min`,
        item.priority_score != null && `Priority ${scoreFormat.format(item.priority_score)}`,
      ].filter(Boolean).join(" · ");

      row.append(top, meta);
      return row;
    }),
  );

  // Đoạn nào rộng theo số phút dự kiến, màu theo trạng thái; chưa có số phút thì không vẽ (không đoán).
  $("clock-track").replaceChildren(
    ...sortedItems.filter((it) => it.estimated_minutes > 0).map((item) => {
      const seg = document.createElement("span");
      seg.className = `clock__seg clock__seg--${item.state}`;
      seg.style.flexGrow = item.estimated_minutes;
      seg.title = `${item.title} · ${item.estimated_minutes} min`;
      return seg;
    }),
  );

  const concluded = agendaItems.filter((it) => it.state === "concluded").length;
  $("agenda-count").textContent = agendaItems.length ? `${concluded}/${agendaItems.length} concluded` : "";
  $("agenda-empty").hidden = agendaItems.length > 0;
}



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
  meetingStatus = meetingState.status;
  renderAskControls();
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
  renderReview();
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
  renderSegments();
  $("transcript-empty").hidden = segments.size > 0;
}

function renderAgenda(items) {
  agendaItems = items;
  renderRichAgenda();
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
  if (["live", "paused", "processing", "review", "archived"].includes(state.status)) {
    const [found, disputes] = await Promise.all([api.getExtractions(meetingId), api.getConflicts(meetingId)]);
    extractions.clear();
    for (const item of found.items) extractions.set(item.id, item);
    conflicts.clear();
    for (const item of disputes.items) conflicts.set(item.id, item);
  }
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
      if (item) { item.state = data.to; item.last_evidence = data.evidence; }
      renderAgenda(agendaItems);
      break;
    }
    case "extraction.created":
    case "extraction.updated":
      extractions.set(data.id, data); renderReview(); break;
    case "conflict.created":
    case "conflict.updated":
      conflicts.set(data.id, data); renderReview(); break;
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

// Enter that only commits a Vietnamese IME word (Telex/VNI) must not send the question.
$("ask-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.isComposing) event.preventDefault();
});

// `entry` is given when a failed question is sent again, so it keeps its place in the list.
async function sendQuestion(question, entry = null) {
  if (!question || askPending || !ASK_STATUSES.includes(meetingStatus)) return;
  if (entry) entry.error = null;
  else asks.push((entry = { question, result: null, error: null }));
  askPending = true;
  renderAsks();
  renderAskControls();
  try {
    entry.result = await api.ask(meetingId, question);
  } catch (e) {
    entry.error = e.code === "INVALID_MEETING_STATE"
      ? "Questions can be asked only while the meeting is recording or paused."
      : `Could not answer: ${e.message}`;
  } finally {
    askPending = false;
    if ($("ask-panel").hidden) {
      askUnread += 1;
      renderAskUnread();
    }
    renderAsks();
    renderAskControls();
  }
}

$("ask-toggle").addEventListener("click", () => setAskOpen(true));
$("ask-close").addEventListener("click", () => setAskOpen(false));
$("ask-panel").addEventListener("keydown", (event) => {
  if (event.key === "Escape") setAskOpen(false);
});

$("ask-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const question = $("ask-input").value.trim();
  if (!question || askPending || !ASK_STATUSES.includes(meetingStatus)) return;
  $("ask-input").value = "";
  sendQuestion(question);
});


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
    meetingLanguage = meeting.language;
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
