import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { api } from './api.js';
import { refreshLibrary, setCrumb } from './shell.js';
import { openConflicts, renderReviewList } from './review.js';

const $ = (id) => document.getElementById(id);
const meetingId = new URLSearchParams(location.search).get('meeting');

let status = null; 
let minutes = null; 
let busy = false;
let editing = false;
let meeting = null; // what GET /meetings/{id} last said; the workspace select follows its workspace_id
let workspaces = [];
// What to check before confirming: conflicts block the confirm, flagged items are a reminder.
let review = { items: [], conflicts: [], segmentsById: new Map() };
const hasOpenConflicts = () => openConflicts(review.conflicts).length > 0;

function render() {
  const canGenerate = status === 'processing';
  $('generate').disabled = busy || !meetingId || !canGenerate;
  $('confirm').disabled = busy || status !== 'review' || !minutes || hasOpenConflicts();
  $('confirm').title = hasOpenConflicts() ? 'Choose a value for every conflict first.' : '';
  renderCheck();

  // Minutes can be edited from the first draft on, and still after they are confirmed.
  $('edit-minutes').hidden = !minutes || editing || !['review', 'archived'].includes(status);
  $('edit-minutes').disabled = busy;
  $('minutes-editor').hidden = !editing;
  $('save-minutes').disabled = busy;
  $('minutes').hidden = !minutes || editing;
  $('minutes-empty').hidden = !!minutes;
  renderWorkspace();
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

function renderWorkspace() {
  const filed = status === 'archived';
  $('workspace-box').hidden = !filed;
  if (!filed) return;
  const options = [new Option('No workspace', '')];
  for (const workspace of workspaces) options.push(new Option(workspace.name, workspace.id));
  $('workspace-select').replaceChildren(...options); // Option text is plain text, never markup
  $('workspace-select').value = workspaces.some((item) => item.id === meeting?.workspace_id) ? meeting.workspace_id : '';
  $('workspace-select').disabled = busy;
}

async function loadWorkspace() {
  if (status !== 'archived') return;
  [meeting, workspaces] = await Promise.all([api.getMeeting(meetingId), api.getWorkspaces().then((found) => found.items)]);
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
      const confirmed = await api.confirmMinutes(meetingId);
      status = confirmed.status;
      minutes = await api.getMinutes(meetingId);
      await loadWorkspace();
      refreshLibrary(); // the minutes now appear in the sidebar
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
    meeting = m;
    $('meeting-meta').textContent = `${m.topic} · ${m.id}`;
    setCrumb(m.topic);
    if (status === 'processing') {
      $('generate').textContent = 'Generating…';
      minutes = await api.convertToMinutes(meetingId);
      status = 'review';
    } else if (status === 'review' || status === 'archived') {
      minutes = await api.getMinutes(meetingId);
    }
    if (['processing', 'review'].includes(status)) await loadReview();
    // Once confirmed this list is only for reference: a failure to load it must not hide the minutes.
    else if (status === 'archived') await loadReview().catch(() => {});
    await loadWorkspace();
  });
}

$('edit-minutes').addEventListener('click', () => {
  $('minutes-text').value = minutes.markdown;
  editing = true;
  render();
  $('minutes-text').focus();
});

$('cancel-edit').addEventListener('click', () => {
  if ($('minutes-text').value !== minutes.markdown && !confirm('Discard your changes to the minutes?')) return;
  editing = false;
  render();
  $('edit-minutes').focus();
});

$('save-minutes').addEventListener('click', () =>
  run(async () => {
    minutes = await api.saveMinutes(meetingId, $('minutes-text').value);
    editing = false;
  }),
);

$('workspace-select').addEventListener('change', () => {
  // Read the choice first: run() redraws the page, and the redraw puts the select back to the saved value.
  const workspaceId = $('workspace-select').value || null;
  run(async () => {
    meeting = await api.assignWorkspace(meetingId, workspaceId);
    await refreshLibrary();
  });
});

// The sidebar can file this meeting too (by dragging it), so the select follows what the backend has.
document.addEventListener('library-changed', async () => {
  if (status !== 'archived' || busy) return;
  try {
    await loadWorkspace();
    renderWorkspace();
  } catch {
    // the sidebar already reports a failed refresh
  }
});

render();
if (meetingId) load();
