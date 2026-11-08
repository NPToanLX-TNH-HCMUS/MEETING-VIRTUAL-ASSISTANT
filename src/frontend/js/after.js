import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { api } from './api.js';

const $ = (id) => document.getElementById(id);
const meetingId = new URLSearchParams(location.search).get('meeting');

let status = null; 
let minutes = null; 
let busy = false;

function render() {
  const canGenerate = status === 'processing';
  $('generate').disabled = busy || !meetingId || !canGenerate;
  $('confirm').disabled = busy || status !== 'review' || !minutes;

  $('minutes').hidden = !minutes;
  $('minutes-empty').hidden = !!minutes;
  if (minutes) {
    $('minutes').innerHTML = DOMPurify.sanitize(marked.parse(minutes.markdown));
    $('minutes-status').textContent = minutes.status === 'confirmed' ? 'Đã xác nhận' : 'Bản nháp — cần xem lại';
    $('minutes-status').className = `badge ${minutes.status === 'confirmed' ? 'badge--new' : 'badge--edited'}`;
  }
  $('minutes-status').hidden = !minutes;

  if (!meetingId) showError('Thiếu mã cuộc họp. Hãy quay lại trang đang họp.');
  else if (!minutes) {
    $('status').textContent = canGenerate
      ? 'Bấm “Tạo minute” để tạo biên bản từ transcript.'
      : `Không thể tạo minute khi cuộc họp đang ở trạng thái “${status ?? '…'}”.`;
  }
}

function showError(message) {
  $('error').textContent = message;
  $('error').hidden = false;
}

async function run(action) {
  busy = true;
  $('error').hidden = true;
  render();
  try {
    await action();
  } catch (e) {
    showError(`Lỗi ${e.code ?? ''}: ${e.message}`);
  } finally {
    busy = false;
    $('generate').textContent = 'Tạo minute';
    render();
  }
}

$('generate').addEventListener('click', () =>
  run(async () => {
    $('generate').textContent = 'Đang tạo…';
    minutes = await api.convertToMinutes(meetingId);
    status = 'review';
  }),
);

$('confirm').addEventListener('click', () =>
  run(async () => {
    const meeting = await api.confirmMinutes(meetingId);
    status = meeting.status;
    minutes = await api.getMinutes(meetingId);
  }),
);

async function load() {
  await run(async () => {
    const m = await api.getMeeting(meetingId);
    status = m.status;
    $('meeting-title').textContent = m.topic;
    if (status === 'processing') {
      $('generate').textContent = 'Đang tạo…';
      minutes = await api.convertToMinutes(meetingId);
      status = 'review';
    } else if (status === 'review' || status === 'archived') {
      minutes = await api.getMinutes(meetingId);
    }
  });
}

render();
if (meetingId) load();
