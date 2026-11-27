// Electron shell. It only starts the Python backend and shows the UI the backend serves,
// so the UI code stays container-independent (CLAUDE.md constraint 8): nothing here is
// imported by src/frontend, and the window has no preload and no Node access.
const { app, BrowserWindow, shell, systemPreferences } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
// `npm run dev`: Vite serves the UI on 5173 and proxies /api and /ws to 8000, so the backend must use 8000.
const DEV_URL = process.env.MIA_DEV_URL || null;
const HEALTH_TIMEOUT_MS = 30_000;
const STOP_TIMEOUT_MS = 10_000;
const LOG_LINES = 40;
// Space for the macOS window buttons; the UI reads it as a CSS variable and is unchanged elsewhere.
// !important: the page declares 0px defaults in its own stylesheet, which would otherwise win by order.
const TITLEBAR_CSS = ':root { --titlebar-h: 38px !important; --traffic-w: 84px !important; }';

let backend = null;
let backendLog = [];
let backendExit = null; // { code, signal } once the process has ended
let window = null;
let baseUrl = null;
let quitting = false;

function findPython() {
  const candidates = [
    process.env.MIA_PYTHON,
    path.join(REPO_ROOT, '.venv', 'bin', 'python'),
    path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe'),
    path.join(REPO_ROOT, '.env', 'bin', 'python'), // this repo's venv is also named .env in places
  ].filter(Boolean);
  return candidates.find((file) => fs.existsSync(file)) ?? 'python3';
}

function freePort() {
  return new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once('error', reject);
    probe.listen(0, '127.0.0.1', () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });
}

function keepLog(chunk) {
  backendLog.push(...chunk.toString().split('\n').filter(Boolean));
  backendLog = backendLog.slice(-LOG_LINES);
}

function startBackend(port) {
  backend = spawn(
    findPython(),
    ['-m', 'uvicorn', 'src.backend.main:app', '--host', '127.0.0.1', '--port', String(port)],
    { cwd: REPO_ROOT, env: process.env, stdio: ['ignore', 'pipe', 'pipe'] },
  );
  backend.stdout.on('data', keepLog);
  backend.stderr.on('data', keepLog);
  backend.once('error', (err) => { backendExit = { code: null, signal: null }; keepLog(`Could not start Python: ${err.message}`); });
  backend.once('exit', (code, signal) => { backendExit = { code, signal }; });
}

async function waitForBackend(port) {
  const deadline = Date.now() + HEALTH_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (backendExit) throw new Error('The backend stopped while starting.');
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/v1/health`);
      if (res.ok) return;
    } catch {
      // not listening yet
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error('The backend did not answer in time.');
}

// SIGTERM first: the backend's lifespan hook saves a recording that is still running.
function stopBackend() {
  if (!backend || backendExit) return Promise.resolve();
  return new Promise((resolve) => {
    const kill = setTimeout(() => backend.kill('SIGKILL'), STOP_TIMEOUT_MS);
    backend.once('exit', () => { clearTimeout(kill); resolve(); });
    backend.kill('SIGTERM');
  });
}

function showError(message) {
  window.loadFile(path.join(__dirname, 'error.html'), {
    query: { message, log: backendLog.join('\n') },
  });
}

function createWindow() {
  const mac = process.platform === 'darwin';
  window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: '#161618',
    titleBarStyle: mac ? 'hiddenInset' : 'default',
    trafficLightPosition: { x: 16, y: 14 },
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });

  // Only the app itself may load in this window; everything else opens in the user's browser.
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  window.webContents.on('will-navigate', (event, url) => {
    const inApp = baseUrl && new URL(url).origin === new URL(baseUrl).origin;
    if (!inApp && !url.startsWith('file:')) {
      event.preventDefault();
      if (/^https?:/.test(url)) shell.openExternal(url);
    }
  });
  // dom-ready runs again for every page, and inserted CSS does not survive a navigation.
  if (mac) window.webContents.on('dom-ready', () => window.webContents.insertCSS(TITLEBAR_CSS));
  window.on('closed', () => { window = null; });
  window.loadFile(path.join(__dirname, 'loading.html'));
}

async function askMicrophone() {
  // The Python child records, but macOS asks on behalf of the app that started it, so ask here once.
  if (process.platform !== 'darwin') return;
  if (systemPreferences.getMediaAccessStatus('microphone') === 'not-determined') {
    await systemPreferences.askForMediaAccess('microphone');
  }
}

async function boot() {
  createWindow();
  try {
    await askMicrophone();
    const port = DEV_URL ? 8000 : await freePort();
    startBackend(port);
    await waitForBackend(port);
    baseUrl = DEV_URL ?? `http://127.0.0.1:${port}/`;
    if (window) window.loadURL(baseUrl);
  } catch (err) {
    if (window) showError(err.message);
  }
}

// Ctrl+C in the terminal or a kill must take the same graceful path as Cmd+Q.
for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(signal, () => app.quit());

// Two apps would fight over one microphone and one backend port.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!window) return;
    if (window.isMinimized()) window.restore();
    window.focus();
  });
  app.whenReady().then(boot);
  app.on('window-all-closed', () => app.quit());
  app.on('activate', () => { if (!window) boot(); });
  app.on('before-quit', (event) => {
    if (quitting || !backend || backendExit) return;
    event.preventDefault();
    quitting = true;
    stopBackend().then(() => app.quit());
  });
}
