import { api } from './api.js';
import './shell.js';

const $ = (id) => document.getElementById(id);

// What each key is for, written for the person typing it. Names come from the backend; an
// unknown one is still listed, just without a description.
const KEY_INFO = {
  ELEVENLABS_API_KEY: { label: 'ElevenLabs', use: 'Turns speech into text, live and from a recording.' },
  GROQ_API_KEY: { label: 'Groq', use: 'The model that finds agenda items, decisions and tasks, and writes the minutes.' },
  OPENROUTER_API_KEY: { label: 'OpenRouter', use: 'Backup model, used only when Groq fails.' },
};
const SOURCE_TEXT = {
  settings: 'Saved in this app',
  env: 'From the .env file or the environment',
};
const REMOVE_CONFIRM_MS = 4000;

const rows = new Map(); // key name -> { save, remove, input, status, form }

function showError(message) {
  $('error').textContent = message;
  $('error').hidden = false;
}

function say(message) {
  $('keys-status').textContent = message;
}

function setBusy(row, busy) {
  row.busy = busy;
  row.input.disabled = busy;
  row.save.disabled = busy || !row.input.value.trim();
  row.remove.disabled = busy;
}

// Fills the parts of a row that depend on the backend's answer. The typed text is left alone,
// so saving one key never wipes what someone is typing in another row.
function update(row, key) {
  // Written out as well as coloured: a key's state is never shown by colour alone.
  row.status.textContent = key.is_set
    ? [SOURCE_TEXT[key.source] ?? 'Set', key.hint].filter(Boolean).join(' · ')
    : 'Not set';
  row.status.classList.toggle('key__status--set', key.is_set);
  row.remove.hidden = key.source !== 'settings';
  row.remove.textContent = 'Remove';
  row.armed = false;
}

function addRow(key) {
  const info = KEY_INFO[key.name] ?? { label: key.name, use: '' };
  const node = $('tpl-key').content.firstElementChild.cloneNode(true);
  const field = (name) => node.querySelector(`[data-field="${name}"]`);
  const row = {
    input: field('input'),
    save: field('save'),
    remove: field('remove'),
    status: field('status'),
    armed: false,
    busy: false,
  };
  field('label').textContent = info.label;
  field('use').textContent = info.use;
  field('use').hidden = !info.use;
  row.input.setAttribute('aria-label', `${info.label} key`);
  row.remove.setAttribute('aria-label', `Remove the saved ${info.label} key`);

  row.input.addEventListener('input', () => {
    row.save.disabled = row.busy || !row.input.value.trim();
  });

  node.querySelector('form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const value = row.input.value.trim();
    if (!value || row.busy) return;
    setBusy(row, true);
    try {
      apply(await api.saveSettings({ [key.name]: value }));
      row.input.value = ''; // the key is gone from the page as soon as it is saved
      say(`${info.label} key saved.`);
    } catch (e) {
      say('');
      showError(`Could not save the ${info.label} key: ${e.message}`);
    } finally {
      setBusy(row, false);
    }
  });

  // Removing cannot be undone (the key is never shown again), so it takes a second click.
  row.remove.addEventListener('click', async () => {
    if (!row.armed) {
      row.armed = true;
      row.remove.textContent = 'Click again to remove';
      setTimeout(() => {
        row.armed = false;
        row.remove.textContent = 'Remove';
      }, REMOVE_CONFIRM_MS);
      return;
    }
    setBusy(row, true);
    try {
      apply(await api.saveSettings({ [key.name]: null }));
      say(`${info.label} key removed.`);
    } catch (e) {
      say('');
      showError(`Could not remove the ${info.label} key: ${e.message}`);
    } finally {
      setBusy(row, false);
    }
  });

  rows.set(key.name, row);
  $('key-list').append(node);
  return row;
}

function apply(result) {
  $('error').hidden = true;
  for (const key of result.keys) update(rows.get(key.name) ?? addRow(key), key);
}

async function load() {
  try {
    apply(await api.getSettings());
  } catch (e) {
    showError(`Could not load the settings: ${e.message}`);
  }
}

load();
