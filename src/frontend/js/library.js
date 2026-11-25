// The sidebar's library: confirmed minutes, and the workspaces they can be filed under by dragging.
// The backend owns the data (GET /meetings, /workspaces); this file only draws it and sends the user's choices.
// Every text is set with textContent: meeting and workspace names are user text.
import { api } from './api.js';
import { icon, WORKSPACE_COLORS, WORKSPACE_ICONS, workspaceColor, workspaceIcon } from './icons.js';

const DRAG_TYPE = 'application/x-mia-meeting';
const OPEN_KEY = 'mia.workspaces.open';
const MAX_NAME = 60;
const CONFIRM_MS = 4000;

const currentId = new URLSearchParams(location.search).get('meeting');
const onReviewPage = document.body.dataset.page === 'after';

let root = null;
let meetings = [];
let workspaces = [];
let message = '';
const open = readOpen();

function readOpen() {
  try {
    return new Set(JSON.parse(localStorage.getItem(OPEN_KEY)) ?? []);
  } catch {
    return new Set(); // storage can be blocked, or hold something else: all workspaces start closed
  }
}

function saveOpen() {
  try {
    localStorage.setItem(OPEN_KEY, JSON.stringify([...open]));
  } catch {
    // a UI preference only
  }
}

function el(tag, className, ...children) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.append(...children);
  return node;
}

function button(className, label, onClick) {
  const node = el('button', className, ...(label ? [label] : []));
  node.type = 'button';
  node.addEventListener('click', onClick);
  return node;
}

// ---------- Data ----------
async function load() {
  try {
    const [found, groups] = await Promise.all([api.getMeetings('archived'), api.getWorkspaces()]);
    meetings = found.items;
    workspaces = groups.items;
    message = '';
  } catch (e) {
    message = `Could not load your minutes: ${e.message}`;
  }
  render();
}

// Pages that show a meeting's workspace listen for this to stay in step with the sidebar.
export async function refreshLibrary() {
  await load();
  document.dispatchEvent(new CustomEvent('library-changed'));
}

export function mountLibrary(container) {
  root = container;
  render();
  load();
}

async function fileMeeting(meetingId, workspaceId) {
  const meeting = meetings.find((item) => item.id === meetingId);
  if (!meeting || (meeting.workspace_id ?? null) === workspaceId) return;
  try {
    await api.assignWorkspace(meetingId, workspaceId);
    if (workspaceId) {
      open.add(workspaceId); // show where it went
      saveOpen();
    }
  } catch (e) {
    message = `Could not move the minutes: ${e.message}`;
  }
  await refreshLibrary();
}

// ---------- Drag and drop ----------
function dropTarget(node, workspaceId) {
  node.addEventListener('dragover', (event) => {
    if (!event.dataTransfer.types.includes(DRAG_TYPE)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    node.classList.add('is-drop');
  });
  node.addEventListener('dragleave', (event) => {
    if (!node.contains(event.relatedTarget)) node.classList.remove('is-drop');
  });
  node.addEventListener('drop', (event) => {
    event.preventDefault();
    node.classList.remove('is-drop');
    const meetingId = event.dataTransfer.getData(DRAG_TYPE);
    if (meetingId) fileMeeting(meetingId, workspaceId);
  });
}

// ---------- Drawing ----------
function minutesItem(meeting) {
  const link = el('a', 'lib__item', el('span', 'lib__title', meeting.topic || 'Untitled meeting'));
  link.href = `/after_meeting.html?meeting=${encodeURIComponent(meeting.id)}`;
  const day = new Date(meeting.ended_at ?? meeting.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' });
  link.title = `${meeting.topic} · ${day}. Drag it onto a workspace to file it.`;
  if (onReviewPage && meeting.id === currentId) link.setAttribute('aria-current', 'page');
  link.draggable = true;
  link.addEventListener('dragstart', (event) => {
    event.dataTransfer.setData(DRAG_TYPE, meeting.id);
    event.dataTransfer.effectAllowed = 'move';
    link.classList.add('is-dragging');
  });
  link.addEventListener('dragend', () => link.classList.remove('is-dragging'));
  return el('li', 'lib__li', link);
}

function workspaceNode(workspace) {
  const items = meetings.filter((meeting) => meeting.workspace_id === workspace.id);
  const isOpen = open.has(workspace.id);

  const toggle = button('ws__toggle', null, () => {
    if (open.has(workspace.id)) open.delete(workspace.id);
    else open.add(workspace.id);
    saveOpen();
    render();
  });
  toggle.setAttribute('aria-expanded', String(isOpen));
  toggle.append(
    el('span', 'ws__chevron', icon('chevron', 14)),
    el('span', 'ws__icon', icon(workspaceIcon(workspace.icon), 18)),
    el('span', 'ws__name', workspace.name),
    el('span', 'ws__count', String(items.length)),
  );

  const edit = button('icon-btn ws__edit', null, () => openDialog(workspace));
  edit.append(icon('edit', 14));
  edit.setAttribute('aria-label', `Edit workspace ${workspace.name}`);

  const list = el('ul', 'lib__list ws__items', ...items.map(minutesItem));
  list.hidden = !isOpen;
  const node = el('div', `ws ws-color--${workspaceColor(workspace.color)}`, el('div', 'ws__row', toggle, edit), list);
  if (isOpen && !items.length) list.append(el('li', 'lib__empty', 'Drag minutes here.'));
  dropTarget(node, workspace.id);
  return node;
}

function render() {
  if (!root) return;
  const loose = meetings.filter((meeting) => !workspaces.some((workspace) => workspace.id === meeting.workspace_id));

  const minutes = el('section', 'lib__section', el('p', 'sidebar__group', 'Minutes'), el('ul', 'lib__list', ...loose.map(minutesItem)));
  if (!loose.length) minutes.append(el('p', 'lib__empty', meetings.length ? 'Drag minutes here to take them out of a workspace.' : 'Confirmed minutes appear here.'));
  dropTarget(minutes, null);

  const add = button('icon-btn', null, () => openDialog(null));
  add.append(icon('plus', 16));
  add.setAttribute('aria-label', 'New workspace');
  const heading = el('div', 'lib__head', el('p', 'sidebar__group', 'Workspaces'), add);

  const parts = [minutes, heading, ...workspaces.map(workspaceNode)];
  if (!workspaces.length) parts.push(el('p', 'lib__empty', 'Create a workspace, then drag minutes into it.'));
  if (message) {
    const note = el('p', 'lib__empty lib__message', message);
    note.setAttribute('role', 'status');
    parts.push(note);
  }
  root.replaceChildren(...parts);
}

// ---------- New / edit workspace ----------
function choices(legend, group, names, selected, draw) {
  const row = el('div', 'pick__row');
  for (const value of names) {
    const input = el('input', 'visually-hidden');
    input.type = 'radio';
    input.name = group;
    input.value = value;
    input.checked = value === selected;
    input.setAttribute('aria-label', value);
    row.append(el('label', 'pick__option', input, el('span', `pick__face ${group === 'color' ? `ws-color--${value}` : ''}`, draw(value))));
  }
  return el('fieldset', 'pick', el('legend', 'field__label', legend), row);
}

function openDialog(workspace) {
  const editing = Boolean(workspace);
  const dialog = el('dialog', 'dialog');
  dialog.setAttribute('aria-labelledby', 'ws-dialog-title');

  const title = el('h2', 'dialog__title', editing ? 'Edit workspace' : 'New workspace');
  title.id = 'ws-dialog-title';
  const nameLabel = el('label', 'field__label', 'Name');
  nameLabel.htmlFor = 'ws-name';
  const name = el('input', 'input');
  Object.assign(name, { id: 'ws-name', maxLength: MAX_NAME, autocomplete: 'off', placeholder: 'e.g. Standup', value: workspace?.name ?? '' });
  // Enter that only commits a Vietnamese IME word (Telex/VNI) must not submit the form.
  name.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && event.isComposing) event.preventDefault();
  });

  const problem = el('p', 'dialog__error', '');
  problem.setAttribute('role', 'alert');
  problem.hidden = true;
  const submit = el('button', 'btn btn--primary', editing ? 'Save' : 'Create');
  submit.type = 'submit';
  const cancel = button('btn', 'Cancel', () => dialog.close());
  const actions = el('div', 'dialog__actions');

  const form = el(
    'form',
    'dialog__form',
    el('div', 'field', nameLabel, name),
    choices('Icon', 'icon', WORKSPACE_ICONS, workspaceIcon(workspace?.icon), (value) => icon(value, 20)),
    choices('Colour', 'color', WORKSPACE_COLORS, workspaceColor(workspace?.color), () => ''),
    problem,
    actions,
  );

  let busy = false;
  const setBusy = (value) => {
    busy = value;
    for (const control of actions.querySelectorAll('button')) control.disabled = value;
  };
  const fail = (text) => {
    problem.textContent = text;
    problem.hidden = false;
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    const body = { name: name.value.trim(), icon: form.elements.icon.value, color: form.elements.color.value };
    if (!body.name) {
      fail('Give the workspace a name.');
      name.focus();
      return;
    }
    setBusy(true);
    try {
      if (editing) await api.updateWorkspace(workspace.id, body);
      else await api.createWorkspace(body);
      dialog.close();
      await refreshLibrary();
    } catch (e) {
      fail(e.message);
    } finally {
      setBusy(false);
    }
  });

  if (editing) {
    // Deleting keeps the minutes; it takes a second click because it cannot be undone.
    let armed = false;
    const remove = button('btn btn--danger', 'Delete workspace', async () => {
      if (!armed) {
        armed = true;
        remove.textContent = 'Click again to delete';
        setTimeout(() => {
          armed = false;
          remove.textContent = 'Delete workspace';
        }, CONFIRM_MS);
        return;
      }
      setBusy(true);
      try {
        await api.deleteWorkspace(workspace.id);
        open.delete(workspace.id);
        saveOpen();
        dialog.close();
        await refreshLibrary();
      } catch (e) {
        fail(e.message);
      } finally {
        setBusy(false);
      }
    });
    actions.append(remove, el('span', 'dialog__spacer'));
    form.insertBefore(el('p', 'dialog__note', 'Deleting a workspace keeps the minutes in it.'), actions);
  } else {
    actions.append(el('span', 'dialog__spacer'));
  }
  actions.append(cancel, submit);

  dialog.append(title, form);
  dialog.addEventListener('close', () => dialog.remove());
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close(); // a click on the dimmed area
  });
  document.body.append(dialog);
  dialog.showModal();
  name.focus();
}
