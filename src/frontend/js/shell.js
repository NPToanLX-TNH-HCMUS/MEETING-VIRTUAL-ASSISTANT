// The frame every page shares: sidebar, back/forward and the breadcrumb in the top bar.
// A page imports this file for its side effect and calls the exports below when its data changes.
// Markup stays in each HTML file (<aside id="sidebar">, <header class="app-header">); this file
// only fills them, always with textContent, never innerHTML.
import { icon } from './icons.js';
import { mountLibrary } from './library.js';

export { refreshLibrary } from './library.js';

const COLLAPSED_KEY = 'mia.sidebar';

const page = document.body.dataset.page;
const shellEl = document.querySelector('.shell');
let meetingId = new URLSearchParams(location.search).get('meeting');
let recording = false;
let crumbEl = null;
let currentEl = null;

function el(tag, className, ...children) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.append(...children);
  return node;
}

function link(href, name, label, current) {
  const a = el('a', 'sidebar__link', icon(name), el('span', 'sidebar__label', label));
  a.href = href;
  if (current) a.setAttribute('aria-current', 'page');
  return a;
}

function toggleButton(className) {
  const button = el('button', `icon-btn sidebar-toggle ${className}`, icon('sidebar'));
  button.type = 'button';
  button.setAttribute('aria-controls', 'sidebar');
  button.addEventListener('click', () => setSidebarHidden(shellEl.dataset.sidebar !== 'hidden'));
  return button;
}

function setSidebarHidden(hidden) {
  shellEl.dataset.sidebar = hidden ? 'hidden' : 'shown';
  for (const button of document.querySelectorAll('.sidebar-toggle')) {
    button.setAttribute('aria-expanded', String(!hidden));
    button.setAttribute('aria-label', hidden ? 'Show sidebar' : 'Hide sidebar');
    button.title = button.getAttribute('aria-label');
  }
  try {
    localStorage.setItem(COLLAPSED_KEY, hidden ? 'hidden' : 'shown');
  } catch {
    // a UI preference only: the sidebar just opens again next time
  }
}

function renderCurrent() {
  if (!currentEl) return;
  // A confirmed meeting lives in the library below; "current meeting" is for one still being worked on.
  if (!meetingId || page === 'after') {
    currentEl.replaceChildren();
    return;
  }
  const id = encodeURIComponent(meetingId);
  const live = link(`/during.html?meeting=${id}`, 'live', 'Live meeting', page === 'during');
  // The recording state is also written out, so it never depends on colour.
  const rec = el('span', 'sidebar__rec', 'REC');
  rec.hidden = !recording;
  live.append(rec);
  currentEl.replaceChildren(
    el('p', 'sidebar__group', 'Current meeting'),
    live,
    link(`/after_meeting.html?meeting=${id}`, 'review', 'Review minutes', false),
  );
}

function buildSidebar() {
  const sidebar = document.getElementById('sidebar');
  const top = el('div', 'sidebar__top', toggleButton('sidebar-toggle--inside'));
  const fresh = el('a', 'sidebar__new', icon('plus'), el('span', 'sidebar__label', 'New meeting'));
  fresh.href = '/index.html';
  currentEl = el('div', 'sidebar__current');
  const libraryEl = el('div', 'sidebar__library');
  const logo = el('span', 'brand__logo', icon('live', 15));
  sidebar.replaceChildren(
    top,
    fresh,
    // Only this part scrolls, so Settings and the logo stay in view however long the lists get.
    el('nav', 'sidebar__nav', link('/index.html', 'home', 'Home', page === 'home'), currentEl, libraryEl),
    el(
      'div',
      'sidebar__bottom',
      link('/settings.html', 'settings', 'Settings', page === 'settings'),
      el('div', 'sidebar__brand', logo, 'DocuMeet'),
    ),
  );
  renderCurrent();
  mountLibrary(libraryEl);
}

function buildTopbar() {
  const header = document.querySelector('.app-header');
  const history = window.navigation;
  const back = el('button', 'icon-btn', icon('back'));
  back.type = 'button';
  back.setAttribute('aria-label', 'Back');
  back.disabled = history ? !history.canGoBack : false;
  back.addEventListener('click', () => window.history.back());
  const forward = el('button', 'icon-btn', icon('forward'));
  forward.type = 'button';
  forward.setAttribute('aria-label', 'Forward');
  forward.disabled = history ? !history.canGoForward : false;
  forward.addEventListener('click', () => window.history.forward());

  const home = el('a', 'crumb__link', 'Meetings');
  home.href = '/index.html';
  crumbEl = el('span', 'crumb__current', header.dataset.crumb ?? '');
  crumbEl.setAttribute('aria-current', 'page');
  const crumbs = el('nav', 'crumb', home, el('span', 'crumb__sep', '/'), crumbEl);
  crumbs.setAttribute('aria-label', 'Breadcrumb');

  header.prepend(el('div', 'topnav', toggleButton('sidebar-toggle--outside'), back, forward, crumbs));
}

export function setCrumb(text) {
  if (crumbEl) crumbEl.textContent = text;
}

export function setRecording(on) {
  recording = on;
  for (const badge of document.querySelectorAll('.sidebar__rec')) badge.hidden = !on;
}

// The home page learns the meeting id only after it creates the meeting.
export function setMeeting(id) {
  if (id === meetingId) return;
  meetingId = id;
  renderCurrent();
}

buildSidebar();
buildTopbar();
let hidden = false;
try {
  hidden = localStorage.getItem(COLLAPSED_KEY) === 'hidden';
} catch {
  // storage can be blocked
}
setSidebarHidden(hidden);
