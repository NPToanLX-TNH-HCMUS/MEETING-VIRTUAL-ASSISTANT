import { api } from './api.js';

const $ = (id) => document.getElementById(id);
const meetingId = new URLSearchParams(location.search).get('meeting');
const LANGUAGE = { vi: 'Tiếng Việt', en: 'English' };

let recording = false;
let busy = false; // đang chờ backend trả lời
let finished = false;
let transcribing = false;
let hasTranscript = false;
let startedAt = 0;
let timer = null;

function render() {
  const toggle = $('toggle');
  toggle.disabled = busy || finished || !meetingId;
  toggle.textContent = recording ? 'Dừng ghi âm' : 'Bắt đầu ghi âm';
  toggle.classList.toggle('btn--danger', recording);
  toggle.classList.toggle('btn--primary', !recording);

  $('transcribe').disabled = !finished || transcribing;
  $('transcribe').textContent = transcribing ? 'Đang chuyển…' : 'Chuyển thành văn bản';

  $('live-badge').hidden = !recording;
  $('transcript').hidden = !hasTranscript;
  $('transcript-empty').hidden = hasTranscript;
  $('agenda-empty').hidden = $('agenda-list').children.length > 0;

  if (!meetingId) showError('Thiếu mã cuộc họp. Hãy quay lại bước agenda.');
  else if (finished) $('status').textContent = 'Đã dừng. Âm thanh đã được lưu, bấm “Chuyển thành văn bản”.';
  else if (recording) $('status').textContent = 'Đang ghi âm…';
  if (recording) tick();
}

function tick() {
  const s = Math.floor((Date.now() - startedAt) / 1000);
  $('live-badge').textContent = `● LIVE · ĐANG GHI ÂM ${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

function showError(message) {
  $('error').textContent = message;
  $('error').hidden = false;
}

// Chạy một thao tác gọi backend: khóa nút trong lúc chờ, hiện lỗi nếu có, luôn mở khóa lại.
async function run(action) {
  busy = true;
  $('error').hidden = true;
  render();
  try {
    await action();
  } catch (e) {
    showError(`${e.code ?? 'ERROR'}: ${e.message}`);
  } finally {
    busy = false;
    render();
  }
}

$('toggle').addEventListener('click', () =>
  run(async () => {
    if (!recording) {
      await api.startRecording(meetingId);
      recording = true;
      startedAt = Date.now();
      timer = setInterval(tick, 1000);
    } else {
      await api.stopRecording(meetingId);
      recording = false;
      finished = true;
      clearInterval(timer);
    }
  }),
);

$('transcribe').addEventListener('click', async () => {
  transcribing = true;
  await run(async () => {
    const { transcript } = await api.transcribe(meetingId);
    $('transcript').textContent = transcript;
    hasTranscript = true;
  });
  transcribing = false;
  render();
});

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
if (meetingId) loadMeeting();
