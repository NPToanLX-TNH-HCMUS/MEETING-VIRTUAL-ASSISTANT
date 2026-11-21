import { api } from './api.js';
import { connectTranscriptTest } from "./socket.js";

const $ = (id) => document.getElementById(id);
const meetingId = new URLSearchParams(location.search).get('meeting');
const LANGUAGE = { vi: 'Vietnamese', en: 'English' };

let finished = false;
let hasTranscript = false;
let quietSince = null;
let realtimeTranscriptSaved = false;
let transcriptTestSocket = null;
let segments = [];
let realtimeReady = false;
let realtimePaused = false;
let realtimeStopping = false;
let pausePending = false;
let agendaItems = [];
// Extractions by id, in the order the backend created them. The backend merges; the UI never dedupes.
const extractions = new Map();

function renderRealtimeControls() {
  const connected = transcriptTestSocket?.readyState === WebSocket.OPEN;
  $("live-badge").hidden = !realtimeReady || realtimeStopping;
  $("live-badge").textContent = realtimePaused ? "LIVE · PAUSED" : "LIVE · RECORDING";
  $("live-badge").classList.toggle("live-badge--paused", realtimePaused);
  $("pause").disabled = !connected || !realtimeReady || realtimeStopping || pausePending;
  $("pause").textContent = pausePending
    ? "Working…"
    : realtimePaused ? "Resume" : "Pause";
  $("pause").setAttribute("aria-pressed", String(realtimePaused));
  $("stop-transcript").disabled = !connected || !realtimeReady || realtimeStopping;
  $("test-transcript").hidden = !!transcriptTestSocket;
  $("test-transcript").disabled = !meetingId || !!transcriptTestSocket || finished || realtimeTranscriptSaved;
}

function render() {
  $('transcript-empty').hidden = hasTranscript || !!transcriptTestSocket;
  $('agenda-empty').hidden = $('agenda-list').children.length > 0;
  $("go-after-box").hidden = !hasTranscript;
  $('go-after').href = `/after_meeting.html?meeting=${encodeURIComponent(meetingId)}`;

  if (!meetingId) showError('Missing meeting ID. Go back to the agenda step.');
  renderRealtimeControls();
}

// Seconds from the meeting start (pauses excluded) as m:ss; "—" when the backend sent no time.
function formatTime(seconds) {
  if (typeof seconds !== "number") return "—";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

const TYPE_LABELS = {
  decision: "Decision",
  action_item: "Action item",
  deadline: "Deadline",
  unresolved_issue: "Unresolved issue",
};

// "2026-10-30" -> "30/10"; split instead of Date so no time zone can shift the day.
function formatDeadline(deadline) {
  const [, month, day] = deadline.split("-");
  return `${day}/${month}`;
}

// Owner, due date and what is missing; a missing field is said in words, never guessed.
function extractionDetails(item) {
  return [
    item.assignee,
    item.deadline && `due ${formatDeadline(item.deadline)}`,
    ...item.missing_fields.map((field) => `${field} missing`),
  ].filter(Boolean);
}

function segmentTag(item) {
  const tag = document.createElement("span");
  tag.className = `seg-tag seg-tag--${item.type}` + (item.needs_confirmation ? " seg-tag--confirm" : "");
  tag.textContent = [TYPE_LABELS[item.type], item.content, ...extractionDetails(item)].join(" · ");
  return tag;
}

function renderSegments() {
  const all = [...extractions.values()];
  $("test-transcript-final").replaceChildren(
    ...segments.map((segment) => {
      const row = document.createElement("div");
      row.className = "segment" + (segment.is_low_confidence ? " segment--low" : "");
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
  const byId = new Map(segments.map((segment) => [segment.id, segment]));
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

      const details = extractionDetails(item);
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

function setExtractions(items) {
  extractions.clear();
  for (const item of items) extractions.set(item.id, item);
  renderCaptured();
  renderSegments();
}

async function loadExtractions() {
  try {
    setExtractions((await api.getExtractions(meetingId)).items);
  } catch (e) {
    // Before the meeting starts there is nothing to load yet.
    if (e.code !== "INVALID_MEETING_STATE") showError(`Could not load the captured items: ${e.message}`);
  }
}

function showError(message) {
  $('error').textContent = message;
  $('error').hidden = false;
}

const stateLabels = {
  not_discussed: "Not discussed",
  in_progress: "In progress",
  discussed: "Discussed",
  concluded: "Concluded",
};
const scoreFormat = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function renderAgenda() {
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

async function loadAgenda() {
  try {
    const result = await api.getAgenda(meetingId);

    agendaItems = result.items;

    renderAgenda();
  } catch (e) {
    showError(`Could not load the agenda: ${e.message}`);
  }
}

// Tiêu đề và dòng thông tin của header lấy từ backend.
async function loadMeeting() {
  try {
    const m = await api.getMeeting(meetingId);
    $('meeting-title').textContent = m.topic;
    const day = new Date(m.created_at).toLocaleDateString('en-US', { dateStyle: 'full' });
    $('meeting-meta').textContent = [day, LANGUAGE[m.language] ?? m.language, `${m.duration_minutes} min`, m.id].join(' · ');
    // After a refresh, bring back what was already captured.
    if (!["draft", "ready"].includes(m.status)) loadExtractions();
  } catch (e) {
    showError(`${e.code ?? 'ERROR'}: ${e.message}`);
  }
}

// Keep the newest line in view, like a chat: follow the bottom unless the user scrolled up
// to read something older; scrolling back to the bottom resumes following.
const transcriptBox = $("transcript-scroll");
let followLatest = true;
transcriptBox.addEventListener("scroll", () => {
  followLatest = transcriptBox.scrollHeight - transcriptBox.scrollTop - transcriptBox.clientHeight < 40;
});
new MutationObserver(() => {
  if (followLatest) transcriptBox.scrollTop = transcriptBox.scrollHeight;
}).observe(transcriptBox, { childList: true, subtree: true, characterData: true });

render();
if (meetingId) {
  loadMeeting();
  loadAgenda();
}

$("pause").addEventListener("click", () => {
  if (transcriptTestSocket?.readyState !== WebSocket.OPEN || !realtimeReady || realtimeStopping || pausePending) return;
  pausePending = true;
  transcriptTestSocket.send(JSON.stringify({type: realtimePaused ? "resume" : "pause"}));
  renderRealtimeControls();
});

$("stop-transcript").addEventListener("click", () => {
  if (transcriptTestSocket?.readyState !== WebSocket.OPEN || !realtimeReady || realtimeStopping) return;
  realtimeStopping = true;
  transcriptTestSocket.send(JSON.stringify({type: "stop"}));
  $("test-transcript-status").textContent = "Stopping and processing the last part…";
  renderRealtimeControls();
});

$("test-transcript").addEventListener("click", () => {
  if (!meetingId || transcriptTestSocket || realtimeTranscriptSaved || finished) return;
  realtimeReady = false;
  realtimePaused = false;
  realtimeStopping = false;
  pausePending = false;

  $("error").hidden = true;
  resetRealtimeLevel("...");
  segments = [];
  renderSegments();
  $("test-transcript-partial").textContent = "";

  $("test-transcript").disabled = true;
  $("test-transcript-status").textContent = "Connecting…";

  let completed = false;
  let failed = false;

  transcriptTestSocket = connectTranscriptTest(meetingId, {
    onOpen() {
      $("test-transcript-status").textContent =
        "Connected to the backend — opening the ElevenLabs session…";
      renderRealtimeControls();
    },

    onMessage(message) {
      if (message.type === "level") {
        if (realtimeReady && !realtimePaused && !realtimeStopping) {
          showRealtimeLevel(message);
        }

        return;
      }
      if (message.type === "partial") {
        $("test-transcript-partial").textContent = message.text;
      }

      if (message.type === "committed") {
        segments.push({ id: message.id, text: message.text, start_seconds: message.start_seconds });
        renderSegments();
        $("test-transcript-partial").textContent = "";
      }

      if (message.type === "extraction.created" || message.type === "extraction.updated") {
        extractions.set(message.data.id, message.data);
        renderCaptured();
        renderSegments();
      }

      if (message.type === "agenda.item_state") {
        // The backend decided this change; the UI only shows it.
        const item = agendaItems.find((it) => it.id === message.data.agenda_item_id);
        if (item) {
          item.state = message.data.to;
          item.last_evidence = message.data.evidence;
          renderAgenda();
        }
      }

      if (message.type === "done") {
        realtimeReady = false;
        completed = true;
        realtimeTranscriptSaved = message.saved === true;

        if (realtimeTranscriptSaved) {
          hasTranscript = true;
          finished = true;

          // Hiển thị đúng bản backend đã lưu.
          segments = message.segments ?? message.transcript.split("\n").filter(Boolean).map((text) => ({ text }));
          renderSegments();
          $("test-transcript-partial").textContent = "";

          $("test-transcript-status").textContent =
            "Transcript saved. You can move on to the minutes.";

          render();
          // The last sentences may not have been checked live; this covers them.
          loadExtractions();
        } else {
          $("test-transcript-status").textContent =
            "The session ended but the transcript was not saved.";
        }
      }

      if (message.type === "error") {
        failed = true;
        realtimeReady = false;
        resetRealtimeLevel("Connection error");
        $("test-transcript-status").textContent = message.message;
        // The status line is easy to miss when the session ends a second after it started.
        showError(`Recording stopped: ${message.message}`);
      }

      if (message.type === "ready") {
        realtimeReady = true;
        resetRealtimeLevel("Waiting for speech…");
        $("test-transcript-status").textContent = message.message;
      }
      if (message.type === "paused" || message.type === "resumed") {
        realtimePaused = message.type === "paused";
        pausePending = false;
        resetRealtimeLevel(
          realtimePaused ? "Microphone paused" : "Waiting for speech…"
        );
        if (!realtimeStopping) $("test-transcript-status").textContent = message.message;
      }
      if (message.type === "stopping") {
        realtimeStopping = true;
        resetRealtimeLevel("Microphone stopped");
        $("test-transcript-status").textContent = message.message;
      }
      renderRealtimeControls();
    },

    onError(message) {
      failed = true;
      realtimeReady = false;
      resetRealtimeLevel("Connection error");
      $("test-transcript-status").textContent = message;
      renderRealtimeControls();
    },

    onClose() {
      transcriptTestSocket = null;
      realtimeReady = false;
      realtimePaused = false;
      realtimeStopping = false;
      pausePending = false;
      render();
      resetRealtimeLevel("Microphone stopped");

      if (!completed && !failed) {
        $("test-transcript-status").textContent =
          "The connection closed before the transcript was saved.";
      }
    },
  });
  render();
});

function showRealtimeLevel(message) {
  $("audio-level").value = message.level;

  if (message.dbfs < -50) {
    quietSince ??= Date.now();

    $("audio-level-text").textContent =
      Date.now() - quietSince >= 3000
        ? "Very weak signal. Try speaking and check the microphone."
        : "Waiting for speech…";
  } else {
    quietSince = null;

    $("audio-level-text").textContent =
      `Signal level: ${message.dbfs} dBFS`;
  }
}

function resetRealtimeLevel(text) {
  quietSince = null;
  $("audio-level").value = 0;
  $("audio-level-text").textContent = text;
}