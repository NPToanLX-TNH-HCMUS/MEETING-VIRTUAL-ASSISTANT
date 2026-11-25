# MEETING-VIRTUAL-ASSISTANT
Computational Thinking Project

## Requirements
- Python >= 3.13
- Node.js (for the front end dev server)

## Quick Start
Use the web UI (steps 1 and 2: backend and front end in two terminals, both from the repo root) or the desktop app (steps 1 and 3).

### 1. Backend (FastAPI, port 8000)
Create and activate a virtual environment, then install:

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
pip install -e .
```

Give the app its API keys (`ELEVENLABS_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`). Either paste them in the app under **Settings** (the gear-like "Settings" link at the bottom of the sidebar; they are saved in `data/settings.json` and take effect at once), or put them in a `.env` file. A key saved in Settings replaces the same key in `.env`. To use a `.env` file:

```bash
cp .env.example .env             # Windows: copy .env.example .env
```

Start the server from the repo root:

```bash
uvicorn src.backend.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/docs

### 2. Front end (Vite, port 5173)

```bash
cd src/frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` and `/ws` to the backend on `127.0.0.1:8000`, so start the backend first.

Production build: `npm run build` (output in `src/frontend/dist/`), check it with `npm run preview`.

### 3. Desktop app (Electron)
The same UI in its own window. The app starts the backend for you, so step 1 must be done first (the virtual environment in `.venv`, `pip install -e .`, and `.env`) but you do **not** run `uvicorn` yourself.

```bash
cd src/desktop
npm install                      # once
npm start                        # builds the UI, starts the backend, opens the window
```

- Quit the app normally (Cmd+Q on macOS): the backend stops too, and a recording in progress is saved first.
- The app looks for Python in `.venv` in the repo root. Set `MIA_PYTHON` to use another interpreter.
- Meeting data goes to `data/` in the repo root. Set `MIA_DATA_DIR` to move it.
- macOS asks for microphone access the first time. If you pressed "Don't Allow", turn it on under System Settings > Privacy & Security > Microphone.
- UI work with hot reload: run `npm run dev` in `src/frontend` and `npm run dev` in `src/desktop`; the window then shows `http://localhost:5173`.
- If the window shows "DocuMeet couldn't start", the lines under it are the backend's last output; the usual cause is that `pip install -e .` was not run in `.venv`.

The backend also serves the built UI at http://127.0.0.1:8000/ once `src/frontend/dist/` exists, so `uvicorn` alone is enough to use the app in a browser after `npm run build`.

## Your data
Everything is kept in the `data/` folder in the repo root (set `MIA_DATA_DIR` to move it). It is not committed to git.

- **Confirmed minutes** are saved when you press "Confirm and save minutes" (`data/<meeting id>/archive.json`, plus `minutes_final.md`). They are still there after you quit the app, listed under **Minutes** in the sidebar, and you can keep editing them on their page.
- **Workspaces** (`data/workspaces.json`) group minutes. Press **+** next to Workspaces to create one with a name, icon and colour, then drag a minutes item onto it. On a minutes page, the **Workspace** menu does the same without dragging. Deleting a workspace keeps its minutes.
- **API keys** entered in Settings are in `data/settings.json`.
- A meeting you never confirmed is **not** saved: it is gone when the app quits.
