# MEETING-VIRTUAL-ASSISTANT
Computational Thinking Project

## Requirements
- Python >= 3.13
- Node.js (for the front end dev server)

## Quick Start
Run the backend and the front end in two terminals. Both commands start from the repo root.

### 1. Backend (FastAPI, port 8000)
Create and activate a virtual environment, then install:

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
pip install -e .
```

Copy `.env.example` to `.env` and fill in the API keys you need (`ELEVENLABS_API_KEY`, `OPENROUTER_API_KEY`, ...):

```bash
cp .env.example .env             # Windows: copy .env.example .env
```

Start the server from the repo root:

```bash
uvicorn src.api.api:app --reload --port 8000
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
