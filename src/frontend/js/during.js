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

function renderSegments() {
  $("test-transcript-final").replaceChildren(
    ...segments.map((text) => {
      const row = document.createElement("div");
      row.className = "segment";
      const time = document.createElement("span");
      time.className = "segment__time";
      time.textContent = "—"; // backend chưa gửi thời điểm của từng câu
      const p = document.createElement("p");
      p.className = "segment__text";
      p.textContent = text;
      row.append(time, p);
      return row;
    }),
  );
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
  } catch (e) {
    showError(`${e.code ?? 'ERROR'}: ${e.message}`);
  }
}

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
        segments.push(message.text);
        renderSegments();
        $("test-transcript-partial").textContent = "";
      }

      if (message.type === "done") {
        realtimeReady = false;
        completed = true;
        realtimeTranscriptSaved = message.saved === true;

        if (realtimeTranscriptSaved) {
          hasTranscript = true;
          finished = true;

          // Hiển thị đúng bản backend đã lưu.
          segments = message.transcript.split("\n").filter(Boolean);
          renderSegments();
          $("test-transcript-partial").textContent = "";

          $("test-transcript-status").textContent =
            "Transcript saved. You can move on to the minutes.";

          render();
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