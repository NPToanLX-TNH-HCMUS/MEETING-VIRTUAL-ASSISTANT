# CODEBASE CONVENCTION
> [!IMPORTANT]
> This document defines the architectural, styling, and workflow standards for the our project. All members must adhere to these conventions to maintain a clean, scalable, and predictable codebase.
## Team's Member:
| Full Name | Student ID | Role | 
|-----------|------------|------|
| Nguyễn Thành Tài | 25127134 | Vice-Leader | 
| Nguyễn Cao An Bình | 25127183 | Leader | 
| Đoàn Khánh Hưng | 25127195 | Member | 
| Bùi Đăng Khôi | 25127203 | Member | 
| Võ Lê Nam Khánh Ann | 25127274 | Member | 
| Ngô Phước Toàn | 25127522 | Member | 

## Project Architecture & Directory Structure
> [!NOTE]
> `src-layout` structure

```text
root
├── .github/                 
├── docs/                    
├── src/
|   ├── app.py
|   ├── modules_1st/
|   ├── modules_2nd/
|   ├── modules_nth/
|   └── ...
├── tests/
├── tools/
├── pyproject.toml          
└── README.md
```

## Naming Conventions

| Entity | Convention | Example |
| :--- | :--- | :--- |
| **Packages & Modules** | `snake_case` (short, noun-based) | `audio_pipeline.py`, `llm_client.py` |
| **Classes & Exceptions** | `PascalCase` | `SkillRegistry`, `AudioCaptureError` |
| **Functions & Methods** | `snake_case` (verb-based) | `transcribe_stream()`, `dispatch_intent()` |
| **Variables** | `snake_case` | `session_context`, `retry_count` |
| **Constants** | `UPPER_SNAKE_CASE` | `DEFAULT_SAMPLE_RATE = 16000` |
| **Private / Internal** | Leading underscore `_` | `_parse_raw_response()`, `self._client` |
| **Boolean Variables** | Prefix with `is_`, `has_`, `can_`, `should_` | `is_listening`, `has_active_session` |

## Git Workflow & Commit Conventions

### 10.1. Branch Naming
Always branch off `main` using the format `<type>/<short-kebab-description>`:
* `feat/spotify-playback-skill`
* `fix/vad-silence-cutoff`
* `refactor/streaming-tts-pipeline`
* `chore/upgrade-pydantic-v2`
* `docs/update-codebase-conventions`

> [!NOTE]
> For some kind of docs like `meeting_minutes_*.md`, `CONTRACT.md`, `PROJECT_CHARTER.md`, it is not mandatory to create a new branch, just push onto `main`.

### 10.2. Conventional Commits
All commit messages must follow the **Conventional Commits** specification:

```text
<type>(<scope>): <concise summary in imperative mood>

[optional body explaining WHY the change was made and any trade-offs]

[optional footer(s) for issue references or BREAKING CHANGE notices]
```

* **Allowed Types:**
  * `feat`: A new feature, capability, or assistant skill
  * `fix`: A bug fix
  * `refactor`: Code restructuring that neither fixes a bug nor adds a feature
  * `perf`: Performance, memory, or latency improvements (e.g., reducing voice-to-voice latency)
  * `test`: Adding missing tests or refactoring existing tests
  * `chore`: Build scripts, dependency updates, tooling configs (`pyproject.toml`)
  * `docs`: Documentation and docstring updates only
* **Common Scopes:** `core`, `audio`, `brain`, `skills`, `models`, `config`, `ci`
* **Examples:**
  * `feat(skills): add Google Calendar conflict detection skill`
  * `fix(audio): prevent event loop deadlock when microphone disconnects`
  * `perf(brain): stream LLM sentence chunks directly to TTS queue`

### 10.3. Conventional Pull Requests

Provide a comprehensive pull request base on `PULL_REQUEST_TEMPLATE.md` file