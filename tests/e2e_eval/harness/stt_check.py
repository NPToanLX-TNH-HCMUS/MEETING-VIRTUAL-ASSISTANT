"""Cross-check ground-truth transcripts against an independent speech-to-text run.

Each audio file is sent once to ElevenLabs (the same model and settings as the app);
the raw answer is cached in runs/<name>/<SID>.stt.json, so a second run costs nothing.
The STT words are aligned with the ground-truth words, and every place where the two
disagree is listed with its time. Where both agree, the ground truth is very likely
right; only the listed places need to be checked by ear.

    python tests/e2e_eval/harness/stt_check.py                      # S01-S05, S09-S11
    python tests/e2e_eval/harness/stt_check.py --scenarios S06 S07  # any scenarios
    python tests/e2e_eval/harness/stt_check.py --cached-only        # no API call

Needs ELEVENLABS_API_KEY (environment or .env). Writes runs/<name>/stt_check.md.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
E2E = HARNESS.parent
REPO = E2E.parents[1]
sys.path.insert(0, str(HARNESS))

from textnorm import tokens  # noqa: E402

API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL_ID = "scribe_v2"
DEFAULT_SCENARIOS = ["S01", "S02", "S03", "S04", "S05", "S09", "S10", "S11"]
LINE = re.compile(r"^\[(\d{2}):(\d{2}\.\d)\] ([^:\[\]]{1,40}): (.+)$")
GAP_S = 0.7          # a pause that ends an STT chunk
MERGE_TOKENS = 3     # differences closer than this are reported as one place
CONTEXT = 4          # words of agreed text shown around a difference


def scenario_dir(sid: str) -> Path:
    found = sorted((E2E / "scenarios").glob(f"{sid}_*"))
    if not found:
        sys.exit(f"No scenario folder for {sid}")
    return found[0]


def gt_transcript(folder: Path) -> Path:
    path = folder / "ground_truth" / "transcript.txt"
    if path.is_file() and path.stat().st_size:
        return path
    spec = json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
    other = spec.get("shares_ground_truth_with")
    if not other:
        sys.exit(f"{folder.name}: no ground-truth transcript")
    return gt_transcript(scenario_dir(other))


def gt_tokens(path: Path) -> tuple[list[str], list[float], list[bool]]:
    """Tokens of the ground truth, the start time of their line, and whether the line has [inaudible]."""
    words, times, unclear = [], [], []
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = LINE.match(raw.strip())
        if not m:
            continue
        start = int(m[1]) * 60 + float(m[2])
        for w in tokens(m[4]):
            words.append(w)
            times.append(start)
            unclear.append("[inaudible]" in m[4])
    return words, times, unclear


def stt_tokens(result: dict) -> tuple[list[str], list[float]]:
    """Tokens of the STT answer with an approximate start time each.

    Words are tokenised in chunks split at pauses, so that spoken numbers ("twenty five")
    are normalised like the ground truth; each token gets the time of the word at the
    same relative position in its chunk.
    """
    chunks, current, last_end = [], [], None
    for item in result.get("words", []):
        if item.get("type") != "word":
            continue
        s = item.get("start")
        if current and s is not None and last_end is not None and s - last_end > GAP_S:
            chunks.append(current)
            current = []
        start = s if s is not None else (last_end or 0.0)
        current.append((start, item.get("text", "")))
        last_end = item.get("end") if item.get("end") is not None else last_end
    if current:
        chunks.append(current)
    words, times = [], []
    for chunk in chunks:
        toks = tokens(" ".join(text for _, text in chunk))
        for k, w in enumerate(toks):
            words.append(w)
            times.append(chunk[min(len(chunk) - 1, k * len(chunk) // max(1, len(toks)))][0] or 0.0)
    return words, times


def transcribe(audio: Path, key: str) -> dict:
    import requests

    with audio.open("rb") as f:
        response = requests.post(
            API_URL,
            headers={"xi-api-key": key},
            files={"file": (audio.name, f, "audio/wav")},
            data={"model_id": MODEL_ID, "language_code": "eng", "diarize": "true",
                  "timestamps_granularity": "word", "tag_audio_events": "false"},
            timeout=600,
        )
    if not response.ok:
        sys.exit(f"ElevenLabs returned HTTP {response.status_code} for {audio}")
    return response.json()


def mmss(t: float) -> str:
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def compare(sid: str, result: dict) -> tuple[dict, list[dict]]:
    folder = scenario_dir(sid)
    ref, ref_t, unclear = gt_tokens(gt_transcript(folder))
    hyp, hyp_t = stt_tokens(result)
    ops = [op for op in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_opcodes() if op[0] != "equal"]
    groups = []
    for op in ops:
        if groups and op[1] - groups[-1][-1][2] <= MERGE_TOKENS:
            groups[-1].append(op)
        else:
            groups.append([op])
    places, errors = [], 0
    for g in groups:
        i1, j1 = g[0][1], g[0][3]
        i2, j2 = g[-1][2], g[-1][4]
        errors += sum(max(o[2] - o[1], o[4] - o[3]) for o in g)
        # STT times are per word, ground-truth times per line: prefer the STT time.
        if j1 < len(hyp_t):
            t = hyp_t[j1]
        elif hyp_t:
            t = hyp_t[-1]
        else:
            t = ref_t[min(i1, len(ref_t) - 1)] if ref_t else 0.0
        places.append({
            "time": t,
            "gt": " ".join(ref[i1:i2]),
            "stt": " ".join(hyp[j1:j2]),
            "before": " ".join(ref[max(0, i1 - CONTEXT):i1]),
            "after": " ".join(ref[i2:i2 + CONTEXT]),
            "size": max(i2 - i1, j2 - j1),
            "inaudible": any(unclear[max(0, i1 - 1):i2 + 1]),
        })
    stats = {"gt_words": len(ref), "stt_words": len(hyp), "places": len(places),
             "wer_approx": round(errors / len(ref), 3) if ref else None}
    return stats, places


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenarios", nargs="*", default=DEFAULT_SCENARIOS)
    ap.add_argument("--name", default="stt_check", help="folder under tests/e2e_eval/runs")
    ap.add_argument("--cached-only", action="store_true", help="never call the API")
    ap.add_argument("--min-size", type=int, default=1, help="hide places with fewer differing words")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env")
    except ImportError:
        pass
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()

    out = E2E / "runs" / args.name
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# STT cross-check of the ground-truth transcripts", "",
             f"Model `{MODEL_ID}`. A place = ground truth and STT disagree there; listen to it.",
             "Places next to an `[inaudible]` line are marked (i); STT often hears words there.", "",
             "| Scenario | GT words | STT words | ≈ WER | Places |", "|---|---|---|---|---|"]
    details = []
    for sid in args.scenarios:
        cache = out / f"{sid}.stt.json"
        if cache.is_file():
            result = json.loads(cache.read_text(encoding="utf-8"))
        elif args.cached_only:
            print(f"{sid}: no cached STT, skipped")
            continue
        else:
            if not key:
                sys.exit("ELEVENLABS_API_KEY is not set")
            audio = scenario_dir(sid) / "inputs" / "audio" / "meeting.wav"
            print(f"{sid}: transcribing {audio.name} ...", flush=True)
            result = transcribe(audio, key)
            cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        stats, places = compare(sid, result)
        shown = [p for p in places if p["size"] >= args.min_size]
        print(f"{sid}: WER ≈ {stats['wer_approx']}, {len(shown)} places")
        lines.append(f"| {sid} | {stats['gt_words']} | {stats['stt_words']} | {stats['wer_approx']} | {len(shown)} |")
        details += ["", f"## {sid}", "", "| Time | Ground truth | STT heard | Context |", "|---|---|---|---|"]
        for p in shown:
            mark = " (i)" if p["inaudible"] else ""
            details.append(f"| {mmss(p['time'])}{mark} | {p['gt'] or '—'} | {p['stt'] or '—'} | …{p['before']} **[ ]** {p['after']}… |")
    (out / "stt_check.md").write_text("\n".join(lines + details) + "\n", encoding="utf-8")
    print(f"Report: {out / 'stt_check.md'}")


if __name__ == "__main__":
    main()
