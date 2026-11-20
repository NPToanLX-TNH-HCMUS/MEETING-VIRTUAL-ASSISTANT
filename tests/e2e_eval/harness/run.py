"""Run scenarios through the real backend, then score them.

    python tests/e2e_eval/harness/run.py --scenarios S13
    python tests/e2e_eval/harness/run.py --scenarios S01 S02 --name baseline
    python tests/e2e_eval/harness/run.py --all

Run from the repo root, with the project's virtual environment and .env (ELEVENLABS_API_KEY,
GROQ_API_KEY, OPENROUTER_API_KEY). Every call goes through the FastAPI app in this process
(fastapi.testclient), so no server needs to be started.

Only the microphone and the clock are replaced: the recorder copies the scenario's meeting.wav
instead of recording, and the date is frozen at the scenario's meeting_date. Speech-to-text and the LLM are the real services and use their quota
(about one minute of ElevenLabs audio per minute of meeting).

The live path (WebSocket, pause / resume, live agenda tracking) is not run: its checks are
reported as not implemented. For a scenario with pauses (S12), the recorder keeps only the parts of
the audio outside the pauses, so the recording matches the ground truth.

Outputs: tests/e2e_eval/runs/<name>/<SID>/ (see data.RunOutputs), then score.py writes report.md.
"""

import argparse
import contextlib
import json
import os
import shutil
import sys
import time
import traceback
import wave
from datetime import datetime, timedelta
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
REPO = HARNESS.parents[2]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(REPO))

from data import E2E_DIR, Scenario, scenario_ids  # noqa: E402
from metrics import Matcher  # noqa: E402

LLM_STAGE = {"generate_agenda": "agenda", "fault:E4": "agenda", "retry:E4": "agenda",
             "generate_minutes": "minutes"}


class FrozenClock:
    """Replaces utils.now() so the meeting happens on the scenario's meeting_date (ANNOTATION_GUIDE.md, section 7).

    Relative deadlines ("next Monday") are then resolved from the same date as in the ground truth.
    The clock moves forward by the length of the audio when the recording stops.
    """

    def __init__(self):
        self.start = None
        self.offset_s = 0.0

    def __call__(self) -> str:
        return (self.start + timedelta(seconds=self.offset_s)).isoformat(timespec="seconds")


CLOCK = FrozenClock()


def recorded_segments(live_actions: list[dict], length: float) -> list[tuple[float, float]] | None:
    """Parts of the audio a microphone would record, given the pause / resume / stop times of scenario.json.

    None when the scenario has no pause or stop: the whole file is recorded.
    """
    actions = sorted((a for a in live_actions if a.get("action") in ("pause", "resume", "stop")),
                     key=lambda a: a["at_s"])
    if not actions:
        return None
    segments, start = [], 0.0
    for a in actions:
        if a["action"] == "pause" and start is not None:
            segments.append((start, a["at_s"]))
            start = None
        elif a["action"] == "resume" and start is None:
            start = a["at_s"]
        elif a["action"] == "stop":
            if start is not None:
                segments.append((start, a["at_s"]))
            return segments
    if start is not None:
        segments.append((start, length))
    return segments


def write_segments(source: Path, target: str, segments: list[tuple[float, float]]) -> float:
    """Copy only the given time ranges of a WAV file; returns the recorded length in seconds."""
    with wave.open(str(source)) as src:
        params, rate = src.getparams(), src.getframerate()
        frames = []
        for a, b in segments:
            src.setpos(int(a * rate))
            frames.append(src.readframes(int((b - a) * rate)))
    data = b"".join(frames)
    with wave.open(target, "wb") as dst:
        dst.setparams(params)
        dst.writeframes(data)
    return len(data) / (params.sampwidth * params.nchannels * rate)


class FakeRecorder:
    """Stands in for audio.recorder.Recorder: 'records' the scenario's audio file.

    When scenario.json has pauses (S12), only the parts outside the pauses are recorded, as a
    microphone would; the ground truth of such a scenario covers only those parts.
    """

    source: Path | None = None
    segments: list[tuple[float, float]] | None = None

    def __init__(self):
        self._recording = False

    @property
    def is_recording(self):
        return self._recording

    @property
    def elapsed(self):
        return 0.0

    def start(self):
        self._recording = True

    def stop(self, path="record.wav"):
        if not self._recording:
            return 0.0
        if self.segments:
            write_segments(self.source, path, self.segments)
        else:
            shutil.copyfile(self.source, path)
        self._recording = False
        return 0.0

    def get_audio_level(self):
        return {"level": 0, "dbfs": -60}


@contextlib.contextmanager
def env_override(**values):
    """Temporarily replace environment variables (used to simulate a missing API key)."""
    old = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class ScenarioRun:
    def __init__(self, client, app, sid: str, out_dir: Path):
        self.client, self.app = client, app
        self.sc = Scenario(sid)
        self.out = out_dir
        self.meeting_id = None
        self.log, self.llm_calls, self.stages = [], [], {}
        self.current_step = None

    # ------------------------------------------------------------ plumbing

    def call(self, step: str, method: str, path: str, file: str | None = None, **kwargs):
        url = f"/api/v1/meetings/{self.meeting_id}{path}" if self.meeting_id else f"/api/v1/meetings{path}"
        self.current_step = step
        started = time.perf_counter()
        try:
            r = self.client.request(method, url, **kwargs)
            status, body = r.status_code, (r.json() if r.content else None)
        except Exception as exc:  # an unhandled server error should not stop the run
            status, body = 500, {"error": {"code": "HARNESS_EXCEPTION", "message": repr(exc)}}
        elapsed = time.perf_counter() - started
        code = None
        if isinstance(body, dict) and status >= 400:
            err = body.get("error") or body.get("detail") or {}
            code = err.get("code") if isinstance(err, dict) else None
        self.log.append({"step": step, "method": method, "path": path, "file": file,
                         "status": status, "code": code, "elapsed_s": round(elapsed, 3),
                         "response": body if status >= 400 else None})
        print(f"  {step:<22} {status} {code or ''} ({elapsed:.1f} s)")
        return status, body

    def status(self) -> str | None:
        r = self.client.get(f"/api/v1/meetings/{self.meeting_id}")
        return r.json().get("status") if r.status_code == 200 else None

    def record_stage(self, stage: str):
        self.stages[stage] = self.status()

    def session(self):
        return self.app.state.ctx.session(self.meeting_id)

    def fault(self, fault_id: str, at: str):
        """Fault-injection entries of scenario.json that apply at this point."""
        return [f for f in self.sc.spec.get("fault_injection", [])
                if f["id"] == fault_id and (f.get("after_step") == at or f.get("at_step") == at)]

    # ------------------------------------------------------------ pipeline

    def run(self):
        spec = self.sc.spec
        meeting = spec["meeting"]
        FakeRecorder.source = self.sc.dir / spec["audio"]["file"]
        FakeRecorder.segments = recorded_segments(spec.get("live_actions", []), spec["audio"].get("seconds") or 0.0)
        CLOCK.start = datetime.fromisoformat(spec["meeting_date"])
        CLOCK.offset_s = 0.0

        status, body = self.call("create_meeting", "POST", "", json=meeting)
        if status != 201:
            return
        self.meeting_id = body["id"]

        for doc in spec.get("documents", []):
            path = self.sc.dir / doc
            if not path.is_file():
                print(f"  missing input {path.name}: run scripts/make_s11_files.py first")
                continue
            with path.open("rb") as f:
                self.call("upload_document", "POST", "/documents", file=path.name,
                          files={"file": (path.name, f.read())})
        self.save_documents()

        if self.fault("E4", "generate_agenda"):
            with env_override(GROQ_API_KEY="", OPENROUTER_API_KEY=""):
                self.call("fault:E4", "POST", "/agenda/generate")
            status, proposal = self.call("retry:E4", "POST", "/agenda/generate")
        else:
            status, proposal = self.call("generate_agenda", "POST", "/agenda/generate")
        self.record_stage("after_agenda")
        if status == 200:
            self.write("agenda_proposal.json", proposal)

        if self.fault("E2", "generate_agenda"):
            self.call("fault:E2", "POST", "/recording/start")

        items = proposal.get("items", []) if status == 200 else []
        edits = [{"id": i["id"], "title": i["title"], "estimated_minutes": i["estimated_minutes"],
                  "order": i["order"]} for i in items]
        edits = self.apply_agenda_edits(edits)
        status, agenda = self.call("confirm_agenda", "PUT", "/agenda", json={"items": edits})
        self.record_stage("after_confirm_agenda")
        if status == 200:
            self.write("agenda.json", agenda)

        self.call("start_recording", "POST", "/recording/start")
        CLOCK.offset_s = spec["audio"].get("seconds") or 0.0
        self.call("stop_recording", "POST", "/recording/stop")
        self.record_stage("after_stop")

        if self.fault("E1", "stop_recording"):
            self.call("fault:E1", "POST", "/minutes/generate")

        if self.fault("E5", "transcribe"):
            with env_override(ELEVENLABS_API_KEY=""):
                self.call("fault:E5", "POST", "/transcribe")
            status, body = self.call("retry:E5", "POST", "/transcribe")
        else:
            status, body = self.call("transcribe", "POST", "/transcribe")
        if status == 200:
            (self.out / "transcript.txt").write_text(body.get("transcript", ""), encoding="utf-8")

        primary_down = any(f.get("step") == "generate_minutes" for f in self.sc.spec.get("fault_injection", []))
        with env_override(GROQ_API_KEY="") if primary_down else contextlib.nullcontext():
            status, minutes = self.call("generate_minutes", "POST", "/minutes/generate")
        self.record_stage("after_minutes")

        edit = (spec.get("user_actions") or {}).get("minutes_edits")
        if edit and status == 200:
            text = minutes["markdown"].rstrip("\n") + "\n\n" + edit["append_line"] + "\n"
            self.write_text("sent/edit_minutes.md", text)
            self.call("edit_minutes", "PUT", "/minutes", json={"markdown": text})

        self.call("confirm_minutes", "POST", "/minutes/confirm")
        status, minutes = self.call("read_minutes", "GET", "/minutes")
        if status == 200:
            self.write("minutes.json", minutes)

        if self.fault("E3", "confirm_minutes"):
            self.call("fault:E3-confirm", "POST", "/minutes/confirm")
            self.call("fault:E3-edit", "PUT", "/minutes", json={"markdown": "edited after archive"})
        self.record_stage("end")

    def apply_agenda_edits(self, edits: list[dict]) -> list[dict]:
        change = (self.sc.spec.get("user_actions") or {}).get("agenda_edits")
        if not change:
            return edits
        matcher = Matcher("lexical")
        remove = change.get("remove", [])
        kept = [e for e in edits
                if not remove or max(row[0] for row in matcher.matrix(remove, [e["title"]])) < 0.5]
        if len(kept) == len(edits) and remove:
            print(f"  agenda edit: no proposed item looks like {remove}; nothing removed")
        for add in change.get("add", []):
            kept.append({"id": None, "title": add["title"], "estimated_minutes": add.get("estimated_minutes", 5),
                         "order": len(kept) + 1})
        for order, e in enumerate(kept, start=1):
            e["order"] = order
        self.write("sent/confirm_agenda.json", {"items": kept})
        return kept

    # ------------------------------------------------------------ outputs

    def write(self, name: str, data):
        self.write_text(name, json.dumps(data, indent=2, ensure_ascii=False))

    def write_text(self, name: str, text: str):
        path = self.out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def save_documents(self):
        if not self.meeting_id:
            return
        for doc in self.session().get("documents", []):
            self.write_text(f"docs/{doc['filename']}.txt", doc.get("text", ""))

    def finish(self, data_root: Path):
        with (self.out / "api_log.jsonl").open("w", encoding="utf-8") as f:
            for entry in self.log:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        with (self.out / "llm_calls.jsonl").open("w", encoding="utf-8") as f:
            for entry in self.llm_calls:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.write("stages.json", self.stages)
        if self.meeting_id and (data_root / self.meeting_id).is_dir():
            shutil.move(str(data_root / self.meeting_id), str(self.out / "meeting_dir"))
        shutil.rmtree(data_root, ignore_errors=True)


def main():
    sys.stdout.reconfigure(errors="replace")  # Windows consoles without UTF-8
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenarios", nargs="*", default=[])
    ap.add_argument("--all", action="store_true", help="run every scenario")
    ap.add_argument("--name", help="run name (default: date and time)")
    ap.add_argument("--no-score", action="store_true", help="only run, do not score")
    args = ap.parse_args()
    ids = scenario_ids() if args.all else args.scenarios
    if not ids:
        sys.exit("Give --scenarios S01 ... or --all")

    os.chdir(REPO)
    from fastapi.testclient import TestClient

    from src.backend import main as backend
    from src.backend.api import during_meeting
    from src.backend.context.app_context import AppContext
    from src.backend.utils import llm

    from src.backend.api import post_meeting, pre_meeting

    during_meeting.Recorder = FakeRecorder  # no microphone: the scenario's audio file is used
    for module in (pre_meeting, during_meeting, post_meeting):
        module.now = CLOCK  # the meeting takes place on the scenario's meeting_date

    run_dir = E2E_DIR / "runs" / (args.name or datetime.now().strftime("%Y-%m-%d_%H%M"))
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Run folder: {run_dir}")

    real_request = llm._request_text
    current = {"run": None}

    def logged_request(provider, model, prompt, *rest):
        run = current["run"]
        entry = {"step": run.current_step, "stage": LLM_STAGE.get(run.current_step, run.current_step),
                 "provider": provider, "model": model, "prompt": prompt,
                 "fallback": provider == "openrouter"}
        try:
            text = real_request(provider, model, prompt, *rest)
            entry.update(ok=True, response=text)
            return text
        except Exception as exc:
            entry.update(ok=False, fallback=False, error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            run.llm_calls.append(entry)

    llm._request_text = logged_request  # observe the LLM calls; the answers are not changed

    for sid in ids:
        print(f"{sid}:")
        out = run_dir / sid
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        data_root = out / "_data"
        backend.app.state.ctx = AppContext(data_root=data_root)
        with TestClient(backend.app, raise_server_exceptions=False) as client:
            run = ScenarioRun(client, backend.app, sid, out)
            current["run"] = run
            try:
                run.run()
            except Exception:  # a harness or backend crash: record it and go on with the next scenario
                (out / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
                print(f"  harness error, see {out / 'error.txt'}")
            finally:
                run.finish(data_root)

    if not args.no_score:
        import subprocess
        subprocess.run([sys.executable, str(HARNESS / "score.py"), "--run", str(run_dir), "--scenarios", *ids],
                       check=False)


if __name__ == "__main__":
    main()
