import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { connectMeetingSocket } from './socket.js';
import { api } from './api.js';
import { openConflicts, renderReviewList } from './review.js';

const $ = (id) => document.getElementById(id);
const meetingId = new URLSearchParams(location.search).get('meeting');

let status = null; 
let minutes = null; 
let busy = false;
// What to check before confirming: conflicts block the confirm, flagged items are a reminder.
let review = { items: [], conflicts: [], segmentsById: new Map() };
const hasOpenConflicts = () => openConflicts(review.conflicts).length > 0;

let meetingChannel = null;

function watchProcessing() {
  if (meetingChannel) return;
  meetingChannel = connectMeetingSocket(meetingId, {
    onOpen() { refreshProcessing().catch(e => showError(e.message)); },
    onMessage(event) {
      if (event.type === 'minutes.ready' || event.type === 'meeting.status') {
        refreshProcessing().catch(e => showError(e.message));
      }
      if (event.type === 'error') {
        showError(event.data.message);
        refreshProcessing().catch(e => showError(e.message));
      }
    },
    onError(message) { showError(message); },
  });
}

let processingRefresh = null;
async function refreshProcessing() {
  if (processingRefresh) return processingRefresh;
  processingRefresh = (async () => {
    const state = await api.getMeetingState(meetingId);
    status = state.status;
    if (state.minutes_ready) {
      minutes = await api.getMinutes(meetingId);
      meetingChannel?.close();
      meetingChannel = null;
    }
    if (["processing", "review", "archived"].includes(status)) await loadReview();
    render();
    if (!state.minutes_ready && !state.error) {
      $('generate').disabled = true;
      $('status').textContent = 'Backend đang hoàn tất transcript và tạo biên bản…';
    }
    if (state.error) showError(state.error.message);
  })();
  try { await processingRefresh; } finally { processingRefresh = null; }
}

window.addEventListener('pagehide', () => meetingChannel?.close());


function render() {
  const canGenerate = status === 'processing';
  $('generate').disabled = busy || !meetingId || !canGenerate;
  $('confirm').disabled = busy || status !== 'review' || !minutes || hasOpenConflicts();
  $('confirm').title = hasOpenConflicts() ? 'Choose a value for every conflict first.' : '';
  renderCheck();

  $('minutes').hidden = !minutes;
  $('minutes-empty').hidden = !!minutes;
  if (minutes) {
    $('minutes').innerHTML = DOMPurify.sanitize(marked.parse(minutes.markdown));
    $('minutes-status').textContent = minutes.status === 'confirmed' ? 'Confirmed' : 'Review · draft minutes';
    $('minutes-status').className = `badge ${minutes.status === 'confirmed' ? 'badge--new' : 'badge--edited'}`;
  }
  $('minutes-status').hidden = !minutes;

  if (!meetingId) showError('Missing meeting ID. Go back to the live meeting page.');
  else if (!minutes) {
    $('status').textContent = canGenerate
      ? 'Press “Generate minutes” to build the minutes from the transcript.'
      : `Minutes can't be generated while the meeting is “${status ?? '…'}”.`;
  }
}

function renderCheck() {
  const count = renderReviewList($('check-list'), {
    ...review,
    onChoose: chooseValue,
    canChoose: ['processing', 'review'].includes(status) && !busy,
  });
  const open = openConflicts(review.conflicts).length;
  $('check-count').textContent = open ? `${open} conflict${open === 1 ? '' : 's'} to choose` : count ? `${count} to check` : '';
  $('check-empty').hidden = count > 0;
}

async function loadReview() {
  // Extractions and conflicts exist once the meeting has been recorded.
  const [found, disputes, transcript] = await Promise.all([
    api.getExtractions(meetingId), api.getConflicts(meetingId), api.getTranscript(meetingId),
  ]);
  review = {
    items: found.items,
    conflicts: disputes.items,
    segmentsById: new Map(transcript.segments.map((segment) => [segment.id, segment])),
  };
}

function chooseValue(conflict, value) {
  run(async () => {
    try {
      await api.resolveConflict(meetingId, conflict.id, value);
    } finally {
      await loadReview();  // show what the backend has now, even if the choice failed
    }
  });
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
    showError(`Error ${e.code ?? ''}: ${e.message}`);
  } finally {
    busy = false;
    $('generate').textContent = 'Generate minutes';
    render();
  }
}

$('generate').addEventListener('click', () =>
  run(async () => {
    $('generate').textContent = 'Generating…';
    minutes = await api.convertToMinutes(meetingId);
    status = 'review';
  }),
);

$('confirm').addEventListener('click', () =>
  run(async () => {
    try {
      const meeting = await api.confirmMinutes(meetingId);
      status = meeting.status;
      minutes = await api.getMinutes(meetingId);
    } catch (e) {
      if (e.code !== 'UNRESOLVED_CONFLICTS') throw e;
      await loadReview();
      throw new Error('Choose a value for every conflict under “Before you confirm”, then confirm again.');
    }
  }),
);

async function load() {
  await run(async () => {
    const m = await api.getMeeting(meetingId);
    status = m.status;
    $('meeting-meta').textContent = `${m.topic} · ${m.id}`;
    if (status === 'processing') {
      $('generate').textContent = 'Generating…';
      minutes = await api.convertToMinutes(meetingId);
      status = 'review';
    } else if (status === 'review' || status === 'archived') {
      minutes = await api.getMinutes(meetingId);
    }
    if (['review', 'archived'].includes(status)) await loadReview();
  });
  if (status === 'processing') await refreshProcessing();
}

render();
if (meetingId) load();
