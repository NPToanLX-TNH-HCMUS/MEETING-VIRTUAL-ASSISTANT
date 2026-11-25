import { marked } from 'marked';
import DOMPurify from 'dompurify';
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
    if (['processing', 'review', 'archived'].includes(status)) await loadReview();
  });
}

render();
if (meetingId) load();
