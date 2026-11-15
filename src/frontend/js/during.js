import { api } from './api.js';
import { connectTranscriptTest } from "./socket.js";

const $ = (id) => document.getElementById(id);
const meetingId = new URLSearchParams(location.search).get('meeting');
const LANGUAGE = { vi: 'Tiếng Việt', en: 'English' };

let finished = false;
let hasTranscript = false;
let quietSince = null;
let realtimeTranscriptSaved = false;
let transcriptTestSocket = null;
let testCommittedText = "";
let realtimeReady = false;
let realtimePaused = false;
let realtimeStopping = false;
let pausePending = false;
let agendaItems = [];

function renderRealtimeControls() {
  const connected = transcriptTestSocket?.readyState === WebSocket.OPEN;
  $("live-badge").hidden = !realtimeReady || realtimeStopping;
  $("live-badge").textContent = realtimePaused ? "ĐÃ TẠM DỪNG" : "ĐANG GHI ÂM";
  $("pause").disabled = !connected || !realtimeReady || realtimeStopping || pausePending;
  $("pause").textContent = pausePending
    ? "Đang xử lý…"
    : realtimePaused ? "Tiếp tục" : "Tạm dừng";
  $("pause").setAttribute("aria-pressed", String(realtimePaused));
  $("stop-transcript").disabled = !connected || !realtimeReady || realtimeStopping;
  $("test-transcript").disabled = !meetingId || !!transcriptTestSocket || finished || realtimeTranscriptSaved;
}

function render() {
  $('transcript-empty').hidden = hasTranscript || !!transcriptTestSocket;
  $('agenda-empty').hidden = $('agenda-list').children.length > 0;
  $("go-after-box").hidden = !hasTranscript;
  $('go-after').href = `/after_meeting.html?meeting=${encodeURIComponent(meetingId)}`;

  if (!meetingId) showError('Thiếu mã cuộc họp. Hãy quay lại bước agenda.');
  renderRealtimeControls();
}

function showError(message) {
  $('error').textContent = message;
  $('error').hidden = false;
}

function renderAgenda() {
  const list = $("agenda-list");

  // Xóa nội dung cũ trước khi vẽ lại.
  list.replaceChildren();

  const stateLabels = {
    not_discussed: "Chưa thảo luận",
    in_progress: "Đang thảo luận",
    discussed: "Đã thảo luận",
    concluded: "Đã chốt",
  };

  // Tạo bản sao rồi sắp xếp theo thứ tự agenda.
  const sortedItems = [...agendaItems].sort(
    (a, b) => a.order - b.order
  );

  for (const item of sortedItems) {
    const row = document.createElement("li");

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";

    checkbox.checked =
      item.state === "discussed" ||
      item.state === "concluded";

    // Hiện tại checkbox chỉ phản ánh trạng thái từ backend.
    checkbox.disabled = true;
    checkbox.setAttribute("aria-label", item.title);

    const title = document.createElement("span");
    title.textContent = ` ${item.title}`;

    const status = document.createElement("small");
    status.textContent =
      ` — ${stateLabels[item.state] ?? "Chưa xác định"}`;

    row.append(checkbox, title, status);
    list.appendChild(row);
  }

  $("agenda-empty").hidden = agendaItems.length > 0;
}

async function loadAgenda() {
  try {
    const result = await api.getAgenda(meetingId);

    agendaItems = result.items;

    renderAgenda();
  } catch (e) {
    showError(`Không tải được agenda: ${e.message}`);
  }
}

// Tiêu đề và dòng thông tin của header lấy từ backend.
async function loadMeeting() {
  try {
    const m = await api.getMeeting(meetingId);
    $('meeting-title').textContent = m.topic;
    const day = new Date(m.created_at).toLocaleDateString('vi-VN', { dateStyle: 'full' });
    $('meeting-meta').textContent = [day, LANGUAGE[m.language] ?? m.language, `${m.duration_minutes} phút`, m.id].join(' · ');
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
  $("test-transcript-status").textContent = "Đang dừng và xử lý phần cuối…";
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
  testCommittedText = "";
  $("test-transcript-final").textContent = "";
  $("test-transcript-partial").textContent = "";

  $("test-transcript").disabled = true;
  $("test-transcript-status").textContent = "Đang kết nối…";

  let completed = false;
  let failed = false;

  transcriptTestSocket = connectTranscriptTest(meetingId, {
    onOpen() {
      $("test-transcript-status").textContent =
        "Đã kết nối backend — đang mở phiên ElevenLabs…";
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
        testCommittedText +=
          (testCommittedText ? "\n" : "") + message.text;

        $("test-transcript-final").textContent = testCommittedText;
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
          $("test-transcript-final").textContent = message.transcript;
          $("test-transcript-partial").textContent = "";

          $("test-transcript-status").textContent =
            "Đã lưu transcript. Bạn có thể sang bước tạo biên bản.";

          render();
        } else {
          $("test-transcript-status").textContent =
            "Phiên đã kết thúc nhưng transcript chưa được lưu.";
        }
      }

      if (message.type === "error") {
        failed = true;
        realtimeReady = false;
        resetRealtimeLevel("Có lỗi kết nối");
        $("test-transcript-status").textContent = message.message;
      }

      if (message.type === "ready") {
        realtimeReady = true;
        resetRealtimeLevel("Đang chờ tiếng nói…");
        $("test-transcript-status").textContent = message.message;
      }
      if (message.type === "paused" || message.type === "resumed") {
        realtimePaused = message.type === "paused";
        pausePending = false;
        resetRealtimeLevel(
          realtimePaused ? "Đã tạm dừng microphone" : "Đang chờ tiếng nói…"
        );
        if (!realtimeStopping) $("test-transcript-status").textContent = message.message;
      }
      if (message.type === "stopping") {
        realtimeStopping = true;
        resetRealtimeLevel("Đã dừng microphone");
        $("test-transcript-status").textContent = message.message;
      }
      renderRealtimeControls();
    },

    onError(message) {
      failed = true;
      realtimeReady = false;
      resetRealtimeLevel("Có lỗi kết nối");
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
      resetRealtimeLevel("Microphone đã dừng");

      if (!completed && !failed) {
        $("test-transcript-status").textContent =
          "Kết nối đóng trước khi lưu transcript hoàn tất.";
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
        ? "Tín hiệu rất nhỏ. Hãy thử nói và kiểm tra microphone."
        : "Đang chờ tiếng nói…";
  } else {
    quietSince = null;

    $("audio-level-text").textContent =
      `Mức tín hiệu: ${message.dbfs} dBFS`;
  }
}

function resetRealtimeLevel(text) {
  quietSince = null;
  $("audio-level").value = 0;
  $("audio-level-text").textContent = text;
}