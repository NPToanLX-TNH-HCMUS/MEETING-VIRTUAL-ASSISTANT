import { api } from './api.js';

const $ = (id) => document.getElementById(id);
const meetingId = new URLSearchParams(location.search).get('meeting');

let recording = false;
let busy = false;
let finished = false;
let transcribing = false;
let startedAt = 0;
let timer = null;

function render() {
  const btn = $('toggle');
  btn.disabled = busy || finished || !meetingId;
  btn.textContent = recording ? 'Dừng ghi âm' : 'Bắt đầu ghi âm';
  btn.classList.toggle('btn--danger', recording);
  btn.classList.toggle('btn--primary', !recording);
  $('transcribe').disabled = !finished || transcribing;
  $('transcribe').textContent = transcribing ? 'Đang chuyển…' : 'Chuyển thành văn bản';
  if (!meetingId) showError('Thiếu mã cuộc họp. Hãy quay lại bước agenda.');
  else if (finished) $('status').textContent = 'Đã dừng. Âm thanh đã được lưu.';
  else if (recording) tick();
}

function tick() {
  const s = Math.floor((Date.now() - startedAt) / 1000);
  $('status').textContent = `● ĐANG GHI ÂM ${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

function showError(message) {
  $('error').textContent = message;
  $('error').hidden = false;
}

$('toggle').addEventListener('click', async () => {
  busy = true;
  $('error').hidden = true;
  render();

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
  busy = false; // nếu thiếu, nút bị khóa mãi và không đổi sang "Dừng ghi âm"
  render();
});

$('transcribe').addEventListener('click', async () => {
  transcribing = true;
  $('error').hidden = true;
  render();
  const { transcript } = await api.transcribe(meetingId);
  $('transcript').textContent = transcript;
  $('transcript').hidden = false;
});

render();
