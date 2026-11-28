# MEETING-VIRTUAL-ASSISTANT
Computational Thinking Project

## Requirements
- Python >= 3.13
- Node.js >= 22 (for the front end dev server / build)
- Docker Desktop *(optional — for running in Docker or VS Code Dev Container)*

## Quick Start
Use the web UI (steps 1 and 2: backend and front end in two terminals, both from the repo root), the desktop app (steps 1 and 3), Docker (step 4), or VS Code Dev Container (step 5).

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

### 4. Docker (single container, port 8000)
Runs the FastAPI backend and the built Vite UI together in one container, connected to your external Supabase database and storage.

1. Create `.env` from the template and fill in `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_API_KEY` (and your AI keys, or enter them later in **Settings**):
   ```bash
   cp .env.example .env             # Windows: copy .env.example .env
   ```
2. Build and start the container from the repo root:
   ```bash
   docker compose up --build -d
   ```
3. Open http://localhost:8000/ (health check: http://localhost:8000/api/v1/health).

Common commands:
```bash
docker compose ps                  # check container status (healthy)
docker compose logs -f app         # follow backend logs
docker compose down                # stop container (keeps the meeting_data volume)
```

- Persistent files (`/app/data`, including `settings.json` and active meeting artifacts) are stored in the Docker volume `meeting_data`. Pass `-v` to `docker compose down -v` only if you want to wipe that volume.
- Because the backend records audio via `sounddevice` (PortAudio), live host microphone capture is not available inside standard Windows/macOS Docker Desktop containers; use the local/Electron setup above for live recording.

### 5. VS Code Dev Container (development)
Provides a reproducible Linux development environment with Python 3.13, Node.js 22, PortAudio/PulseAudio, `pytest`, and `ruff` pre-installed (`.devcontainer/`).

Prerequisites: **Docker Desktop** and the VS Code **Dev Containers** extension (`ms-vscode-remote.remote-containers`).

1. Open the repository in VS Code, press `Ctrl+Shift+P` (`Cmd+Shift+P` on macOS), and run **`Dev Containers: Reopen in Container`**.
2. Wait for the image to build and `postCreateCommand` to finish (`pip install -e ".[dev]"` and `npm --prefix src/frontend ci`).
3. Ensure `.env` exists in the repo root (`cp .env.example .env`).
4. Start the app inside the container (ports `8000` and `5173` are forwarded automatically):
   ```bash
   # Terminal 1 — Backend (port 8000)
   uvicorn src.backend.main:app --reload --host 0.0.0.0 --port 8000

   # Terminal 2 — Front end with hot reload (port 5173)
   npm --prefix src/frontend run dev -- --host
   ```
   Or build the UI once (`npm --prefix src/frontend run build`) and open http://localhost:8000/ directly.
5. Run the unit test suite inside the container:
   ```bash
   pulseaudio --start --exit-idle-time=-1
   pytest tests/unit
   ```
6. To leave the Dev Container and return to your local machine, run **`Dev Containers: Reopen Folder Locally`** from the Command Palette.

- *Windows troubleshooting:* If opening the Dev Container fails with `stat .../ubuntu.sock: no such file or directory`, disable **`Dev > Containers: Mount Wayland Socket`** (`"dev.containers.mountWaylandSocket": false`) in VS Code Settings, or enable Ubuntu WSL integration in Docker Desktop.

## Your data
Everything is kept in the `data/` folder in the repo root (set `MIA_DATA_DIR` to move it). It is not committed to git.

- **Confirmed minutes** are saved when you press "Confirm and save minutes": the database (`DATABASE_URL`) holds the meeting, and the meeting folder is uploaded to Supabase Storage. They are still there after you quit the app, listed under **Minutes** in the sidebar, and you can keep editing them on their page.
- **Workspaces** (in the database) group minutes. A database created before workspaces existed needs `src/backend/database/add_workspaces.sql` run once. Press **+** next to Workspaces to create one with a name, icon and colour, then drag a minutes item onto it. On a minutes page, the **Workspace** menu does the same without dragging. Deleting a workspace keeps its minutes.
- **API keys** entered in Settings are in `data/settings.json`.
- A meeting you never confirmed is **not** saved: it is gone when the app quits.
