"""Load a scenario (inputs and ground truth) and the outputs of one system run."""

import json
import re
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = E2E_DIR / "scenarios"


def scenario_ids() -> list[str]:
    return sorted(p.name.split("_")[0] for p in SCENARIOS_DIR.iterdir() if (p / "scenario.json").is_file())


def scenario_dir(sid: str) -> Path:
    matches = sorted(SCENARIOS_DIR.glob(f"{sid}_*")) or sorted(SCENARIOS_DIR.glob(sid))
    if not matches:
        raise FileNotFoundError(f"No scenario folder for {sid}")
    return matches[0]


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _read_jsonl(path: Path):
    if not path.is_file():
        return None
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_text(path: Path):
    return path.read_text(encoding="utf-8-sig") if path.is_file() else None


class Scenario:
    """scenario.json plus ground truth; files missing here are taken from the scenario it shares with."""

    def __init__(self, sid: str):
        self.id = sid
        self.dir = scenario_dir(sid)
        self.spec = _read_json(self.dir / "scenario.json")
        shared = self.spec.get("shares_ground_truth_with")
        self.shared_dir = scenario_dir(re.match(r"S\d+", shared).group()) if shared else None

    def gt_path(self, name: str) -> Path | None:
        for base in (self.dir, self.shared_dir):
            if base is not None and (base / "ground_truth" / name).is_file():
                return base / "ground_truth" / name
        return None

    def gt_json(self, name: str):
        p = self.gt_path(name)
        return _read_json(p) if p else None

    @property
    def transcript(self) -> str | None:
        p = self.gt_path("transcript.txt")
        return _read_text(p) if p else None

    @property
    def minutes(self) -> dict:
        return self.gt_json("minutes.json") or {}

    @property
    def agenda(self) -> dict:
        return self.gt_json("agenda.json") or {}

    @property
    def expected(self) -> dict:
        p = self.dir / "ground_truth" / "expected_behavior.json"  # never shared
        return _read_json(p) or {"checks": []}

    @property
    def adjudication(self) -> dict:
        return self.gt_json("adjudication.json") or {}

    @property
    def audio_seconds(self) -> float | None:
        return (self.spec.get("audio") or {}).get("seconds")


class RunOutputs:
    """What the system produced for one scenario. Every file is optional.

    <run>/<SID>/
      transcript.txt         transcript returned by POST /transcribe (or copied from the UI)
      minutes.json           Minutes object (GET /minutes)
      agenda_proposal.json   AgendaProposal (POST /agenda/generate)
      agenda.json            AgendaList after confirmation (GET /agenda)
      api_log.jsonl          {"step", "status", "code", "file", "elapsed_s"} per call
      stages.json            {"after_agenda": "draft", ..., "end": "archived"}
      llm_calls.jsonl        {"stage", "prompt", "response", "provider", "model", "fallback"} per LLM call
      events.jsonl           live events {"event", "t_s", "data"}
      docs/<file>.txt        document text after conversion by the backend
      sent/<step>.md         text the harness sent (for example the edited minutes)
      meeting_dir/           copy of data/<meeting_id>/
      error.txt              traceback when the run of this scenario crashed
    """

    def __init__(self, folder: Path):
        self.dir = folder
        self.transcript = _read_text(folder / "transcript.txt")
        self.minutes = _read_json(folder / "minutes.json")
        self.agenda_proposal = _read_json(folder / "agenda_proposal.json")
        self.agenda = _read_json(folder / "agenda.json")
        self.api_log = _read_jsonl(folder / "api_log.jsonl")
        self.stages = _read_json(folder / "stages.json")
        self.llm_calls = _read_jsonl(folder / "llm_calls.jsonl")
        self.events = _read_jsonl(folder / "events.jsonl")
        self.meeting_dir = folder / "meeting_dir" if (folder / "meeting_dir").is_dir() else None
        docs = folder / "docs"
        # docs/<original file name>.txt, for example docs/previous_minutes.md.txt
        self.docs = {p.name.removesuffix(".txt"): _read_text(p) for p in docs.iterdir()} if docs.is_dir() else None
        sent = folder / "sent"
        self.sent = {p.stem: _read_text(p) for p in sent.iterdir()} if sent.is_dir() else {}

    # -- convenient views ------------------------------------------------

    def proposed_items(self) -> list[dict] | None:
        if self.agenda_proposal is not None:
            return self.agenda_proposal.get("items", [])
        if self.agenda is not None:
            return self.agenda.get("items", [])
        return None

    def final_items(self) -> list[dict] | None:
        if self.agenda is not None:
            return self.agenda.get("items", [])
        return self.proposed_items()

    def dropped(self) -> list[dict] | None:
        return None if self.agenda_proposal is None else self.agenda_proposal.get("dropped", [])

    def minutes_lists(self) -> dict | None:
        if self.minutes is None:
            return None
        m = self.minutes
        return {
            "decisions": [str(x) for x in m.get("decisions", [])],
            "unresolved_issues": [str(x) for x in m.get("unresolved_issues", [])],
            "action_items": [x if isinstance(x, dict) else {"task": str(x)} for x in m.get("action_items", [])],
            "summary": m.get("summary", "") or "",
            "markdown": m.get("markdown", "") or "",
        }
