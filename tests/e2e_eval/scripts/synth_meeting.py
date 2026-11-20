"""Build a synthetic meeting from a dialogue script, and derive its ground truth.

S06 and S07 are not recorded by people: their dialogue is written in
`scenarios/<folder>/ground_truth/script.json` (with every planted special case), read
aloud by text-to-speech voices, and assembled into one meeting. Because the dialogue
is written first, the transcript and the timing of every line are known exactly.

Three steps:

1. tts       (on a machine with internet; needs `pip install edge-tts`)
             reads every line with its speaker's voice -> one MP3 per line
2. assemble  (needs ffmpeg and numpy)
             places the lines one after another with the pauses and overlaps written in
             the script, adds a quiet room tone -> one WAV + a timing file
3. gt        writes ground_truth/transcript.txt, fills the tracking spans in
             agenda.json and the `time` of every minutes item from the timing file

Usage (from the repository root):

    python tests/e2e_eval/scripts/synth_meeting.py tts S06 --out D:/CT/audio_raw/synthetic/S06
    python tests/e2e_eval/scripts/synth_meeting.py assemble S06 --lines D:/CT/audio_raw/synthetic/S06 \
        --out D:/CT/audio_raw/synthetic/S06_meeting.wav
    python tests/e2e_eval/scripts/synth_meeting.py gt S06 --timing D:/CT/audio_raw/synthetic/S06_meeting.timing.json

When a few lines are read again, keep the start times of the earlier build so that the times
in the ground truth (and the pause times of S12) stay valid:

    python tests/e2e_eval/scripts/synth_meeting.py assemble S06 --lines D:/CT/audio_raw/synthetic/S06 \
        --out D:/CT/audio_raw/synthetic/S06_meeting.wav --keep-times D:/CT/audio_raw/synthetic/S06_meeting.old.timing.json

Script format (script.json):

    {"scenario": "S06", "voices": {"Ann": {"voice": "en-SG-LunaNeural", "rate": "+0%"}, ...},
     "final_states": {"I1": "discussed", ...},
     "lines": [{"id": "L01", "speaker": "Ann", "text": "...", "item": "I3",
                "gap": 0.6, "overlap": 0.0, "cases": ["F5"]}, ...]}

`gap` is the silence before the line (seconds); `overlap` makes the line start that many
seconds before the previous line ends (two people talking at once). `item` is the
agenda item the line is about, "off" for off-agenda talk, or null.
"""

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[1]
SR = 16000
DEFAULT_GAP = 0.5


def scenario_dir(sid: str) -> Path:
    hits = sorted((EVAL_DIR / "scenarios").glob(f"{sid}_*"))
    if not hits:
        sys.exit(f"no scenario folder for {sid}")
    return hits[0]


def load_script(sid: str) -> dict:
    return json.load(open(scenario_dir(sid) / "ground_truth" / "script.json", encoding="utf-8"))


# ---------------------------------------------------------------- tts
async def tts(sid: str, out: Path) -> None:
    import edge_tts  # pip install edge-tts

    script = load_script(sid)
    out.mkdir(parents=True, exist_ok=True)
    for line in script["lines"]:
        target = out / f"{line['id']}.mp3"
        if target.exists() and target.stat().st_size > 0:
            continue
        v = script["voices"][line["speaker"]]
        for attempt in range(5):
            try:
                await edge_tts.Communicate(line["text"], v["voice"], rate=v.get("rate", "+0%"),
                                           pitch=v.get("pitch", "+0Hz")).save(str(target))
                break
            except Exception as exc:  # network hiccup: retry
                if attempt == 4:
                    raise
                print(f"  retry {line['id']}: {exc}")
                await asyncio.sleep(3)
        print(f"{line['id']} {line['speaker']}: {line['text'][:60]}")
    print(f"Done: {len(script['lines'])} lines in {out}")


# ---------------------------------------------------------------- assemble
def decode(path: Path):
    import numpy as np

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         check=True, capture_output=True).stdout
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    # trim the leading and trailing silence that TTS adds
    loud = np.flatnonzero(np.abs(x) > 0.01)
    return x[loud[0]:loud[-1] + 1] if len(loud) else x


MIN_GAP = 0.15  # shortest pause kept between two lines when start times are kept


def assemble(sid: str, lines_dir: Path, out: Path, keep_times: Path | None = None) -> None:
    """Place the lines one after another.

    keep_times: a timing file of an earlier build. Every line keeps its earlier start time, so
    that the ground-truth times stay valid when a few lines are read again; a line moves only
    when the line before it became too long to fit.
    """
    import wave

    import numpy as np

    script = load_script(sid)
    old = {x["id"]: x for x in json.load(open(keep_times, encoding="utf-8"))["lines"]} if keep_times else {}
    clips, timing, t = [], [], 0.0
    prev_end = 0.0
    moved = []
    for line in script["lines"]:
        x = decode(lines_dir / f"{line['id']}.mp3")
        x = x / (np.sqrt(np.mean(x ** 2)) or 1e-12) * 10 ** (-20 / 20)  # level every voice to -20 dBFS RMS
        if line["id"] in old:
            start = old[line["id"]]["start"]
            if not line.get("overlap") and start < prev_end + MIN_GAP:
                start = prev_end + MIN_GAP
            if abs(start - old[line["id"]]["start"]) > 0.005:
                moved.append(f"{line['id']} {old[line['id']]['start']:.2f} -> {start:.2f} s")
        elif line.get("overlap"):
            start = max(prev_end - float(line["overlap"]), 0.0)
        else:
            start = prev_end + float(line.get("gap", DEFAULT_GAP))
        end = start + len(x) / SR
        clips.append((start, x))
        timing.append({"id": line["id"], "speaker": line["speaker"], "start": round(start, 2), "end": round(end, 2)})
        prev_end = max(prev_end, end)
        t = max(t, end)

    total = np.zeros(int((t + 0.8) * SR))
    for start, x in clips:
        i = int(start * SR)
        total[i:i + len(x)] += x
    rng = np.random.default_rng(int(sid[1:]))
    total += rng.normal(0, 10 ** (-55 / 20), len(total))  # quiet room tone instead of digital silence
    peak = float(np.max(np.abs(total)))
    if peak > 0.98:
        total *= 0.98 / peak
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.clip(np.round(total * 32767), -32768, 32767).astype("<i2").tobytes())
    timing_path = out.with_suffix(".timing.json")
    json.dump({"scenario": sid, "duration": round(len(total) / SR, 2), "lines": timing},
              open(timing_path, "w", encoding="utf-8"), indent=1)
    print(f"{out}: {len(total) / SR:.1f} s, {len(timing)} lines; timing in {timing_path.name}")
    if keep_times:
        print(f"Start times kept from {keep_times.name}; moved: {', '.join(moved) or 'none'}")
    if len(total) / SR > 290:
        print("WARNING: longer than 290 s; shorten the script or the gaps")


# ---------------------------------------------------------------- gt
def gt(sid: str, timing_path: Path) -> None:
    script = load_script(sid)
    timing = {x["id"]: x for x in json.load(open(timing_path, encoding="utf-8"))["lines"]}
    lines = script["lines"]
    gt_dir = scenario_dir(sid) / "ground_truth"

    with open(gt_dir / "transcript.txt", "w", encoding="utf-8") as f:
        for line in sorted(lines, key=lambda l: timing[l["id"]]["start"]):
            t = timing[line["id"]]["start"]
            f.write(f"[{int(t // 60):02d}:{t % 60:04.1f}] {line['speaker']}: {line['text']}\n")

    # spans: consecutive lines about the same item form one span
    spans, off, current = {}, [], None
    for line in lines:
        item, tm = line.get("item"), timing[line["id"]]
        if current and current[0] == item:
            current[2] = tm["end"]
        else:
            if current and current[0]:
                (off if current[0] == "off" else spans.setdefault(current[0], [])).append([current[1], current[2]])
            current = [item, tm["start"], tm["end"]]
    if current and current[0]:
        (off if current[0] == "off" else spans.setdefault(current[0], [])).append([current[1], current[2]])

    agenda_path = gt_dir / "agenda.json"
    agenda = json.load(open(agenda_path, encoding="utf-8"))
    for item in agenda["items"]:
        item["tracking"] = {"final_state": script["final_states"].get(item["id"], "not_discussed"),
                            "spans": spans.get(item["id"], [])}
    agenda["off_agenda"] = off
    json.dump(agenda, open(agenda_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    minutes_path = gt_dir / "minutes.json"
    minutes = json.load(open(minutes_path, encoding="utf-8"))
    for section in ("decisions", "action_items", "unresolved_issues"):
        for entry in minutes[section]:
            if entry.get("line"):
                entry["time"] = timing[entry["line"]]["start"]
    json.dump(minutes, open(minutes_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"{gt_dir.relative_to(EVAL_DIR)}: transcript, tracking spans and item times written")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("tts"); a.add_argument("sid"); a.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("assemble"); b.add_argument("sid"); b.add_argument("--lines", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--keep-times", type=Path, help="timing file of an earlier build: keep its start times")
    c = sub.add_parser("gt"); c.add_argument("sid"); c.add_argument("--timing", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "tts":
        asyncio.run(tts(args.sid, args.out))
    elif args.cmd == "assemble":
        assemble(args.sid, args.lines, args.out, args.keep_times)
    else:
        gt(args.sid, args.timing)


if __name__ == "__main__":
    main()
