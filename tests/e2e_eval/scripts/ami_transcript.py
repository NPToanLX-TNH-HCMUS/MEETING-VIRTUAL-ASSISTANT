"""Draft a ground-truth transcript for an AMI clip from the AMI manual word annotations.

The AMI manual transcript was made by human transcribers, so it is a valid starting
point for the ground truth (it is never taken from our system's output). The draft
must still be checked by listening, as ANNOTATION_GUIDE.md describes.

The clip is described by its row in sources.csv (source file and time ranges). Words
whose midpoint falls inside a range are kept, and their times are shifted to the
clip's own timeline.

Usage (from the repository root):

    python tests/e2e_eval/scripts/ami_transcript.py S01 \
        --annotations D:/CT/audio_raw/ami/ES2002/annotations

Writes scenarios/<folder>/ground_truth/transcript.txt, one sentence per line, so that the
order of the lines follows the audio even when people talk over each other:

    [mm:ss.s] ROLE: text
"""

import argparse
import csv
import glob
import os
import re
from pathlib import Path
from xml.etree import ElementTree as ET

EVAL_DIR = Path(__file__).resolve().parents[1]
NITE = "{http://nite.sourceforge.net/}"
GAP_S = 1.5  # a pause longer than this starts a new line for the same speaker


def roles(annotations: Path, meeting: str) -> dict[str, str]:
    root = ET.parse(annotations / "corpusResources" / "meetings.xml").getroot()
    for m in root:
        if m.get("observation") == meeting:
            return {s.get("nxt_agent"): s.get("role") for s in m}
    raise SystemExit(f"meeting {meeting} not found in meetings.xml")


def clean(token: str) -> str:
    # AMI spells letter-by-letter acronyms as T_V_, V_C_R_ ...
    if re.fullmatch(r"([A-Za-z]_)+", token):
        return token.replace("_", "")
    return token


def load_words(annotations: Path, meeting: str) -> list[dict]:
    words = []
    for f in glob.glob(str(annotations / "words" / f"{meeting}.*.words.xml")):
        speaker = os.path.basename(f).split(".")[1]
        for e in ET.parse(f).getroot():
            if e.tag != "w" or e.get("starttime") is None:
                continue
            words.append({
                "speaker": speaker,
                "start": float(e.get("starttime")),
                "end": float(e.get("endtime")),
                "text": clean(e.text or ""),
                "punc": e.get("punc") == "true",
            })
    return sorted(words, key=lambda w: (w["start"], w["end"]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip_id")
    ap.add_argument("--annotations", type=Path, required=True)
    args = ap.parse_args()

    with open(EVAL_DIR / "sources.csv", newline="", encoding="utf-8") as f:
        row = next(r for r in csv.DictReader(f) if r["clip_id"] == args.clip_id)
    meeting = Path(row["source_file"]).name.split(".")[0]
    segments = [tuple(map(float, p.split("-"))) for p in row["segments"].split(";")]
    role = roles(args.annotations, meeting)

    # shift each kept word to the clip timeline
    kept, offset = [], 0.0
    for part, (a, b) in enumerate(segments):
        for w in load_words(args.annotations, meeting):
            mid = (w["start"] + w["end"]) / 2
            if a <= mid < b:
                kept.append({**w, "start": max(w["start"] - a, 0.0) + offset, "end": min(w["end"], b) - a + offset, "part": part})
        offset += b - a

    # group into sentences: same speaker, same part, short pause, until . ? or !
    lines, open_by_speaker = [], {}
    for w in kept:
        u = open_by_speaker.get(w["speaker"])
        if u and u["part"] == w["part"] and w["start"] - u["end"] <= GAP_S and not u.get("closed"):
            if w["punc"]:
                u["text"] += w["text"]
                u["closed"] = w["text"] in (".", "?", "!")
            else:
                u["text"] += " " + w["text"]
            u["end"] = max(u["end"], w["end"])
        elif not w["punc"]:
            u = {"speaker": w["speaker"], "start": w["start"], "end": w["end"], "text": w["text"], "part": w["part"]}
            open_by_speaker[w["speaker"]] = u
            lines.append(u)

    out = EVAL_DIR / "scenarios" / Path(row["output"]).parts[1] / "ground_truth" / "transcript.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for u in sorted(lines, key=lambda u: u["start"]):
            t = u["start"]
            f.write(f"[{int(t // 60):02d}:{t % 60:04.1f}] {role[u['speaker']]}: {u['text'].strip()}\n")
    print(f"{out.relative_to(EVAL_DIR)}: {len(lines)} lines, {sum(len(u['text'].split()) for u in lines)} words")


if __name__ == "__main__":
    main()
