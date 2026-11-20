"""Draft a ground-truth transcript for a MeetingBank clip from its Speechmatics transcript.

MeetingBank transcripts were made by a speech-to-text service (Speechmatics), not by
people, so this file is only a DRAFT: the annotator must listen to the whole clip and
correct every error before the scenario is marked `done` (see ANNOTATION_GUIDE.md).
It never comes from our own system.

Usage (from the repository root):

    python tests/e2e_eval/scripts/mb_transcript.py S10 \
        --transcript "D:/CT/audio_raw/meetingbank/extracted/Audio&Transcripts/Denver/transcripts/denver_80dd7c6d-....mp3.transcript.json"

Writes scenarios/<folder>/ground_truth/transcript.txt, one utterance per line:

    [mm:ss.s] SPEAKER_n: text

Speechmatics times are in units of 100 ns.
"""

import argparse
import csv
import json
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[1]
GAP_S = 1.5
PUNCT = {".", ",", "?", "!", ";", ":"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip_id")
    ap.add_argument("--transcript", type=Path, required=True)
    args = ap.parse_args()

    with open(EVAL_DIR / "sources.csv", newline="", encoding="utf-8") as f:
        row = next(r for r in csv.DictReader(f) if r["clip_id"] == args.clip_id)
    segments = [tuple(map(float, p.split("-"))) for p in row["segments"].split(";")]

    words = []
    for seg in json.load(open(args.transcript, encoding="utf-8"))["segments"]:
        seg_words = seg["nbest"][0]["words"]
        tokens = seg["nbest"][0]["text"].split()
        # the segment text carries punctuation and casing; use it when it lines up word for word
        aligned = len(tokens) == len(seg_words)
        for i, w in enumerate(seg_words):
            start = w["offset"] / 1e7
            text = tokens[i] if aligned else w["text"]
            words.append({"speaker": seg["speaker"], "start": start, "end": start + w["duration"] / 1e7, "text": text})
    words.sort(key=lambda w: w["start"])

    kept, offset = [], 0.0
    for part, (a, b) in enumerate(segments):
        for w in words:
            if a <= (w["start"] + w["end"]) / 2 < b:
                kept.append({**w, "start": max(w["start"] - a, 0.0) + offset, "end": min(w["end"], b) - a + offset, "part": part})
        offset += b - a

    lines, open_by_speaker = [], {}
    for w in kept:
        u = open_by_speaker.get(w["speaker"])
        if u and u["part"] == w["part"] and w["start"] - u["end"] <= GAP_S:
            u["text"] += w["text"] if w["text"] in PUNCT else " " + w["text"]
            u["end"] = max(u["end"], w["end"])
        elif w["text"] not in PUNCT:
            u = {"speaker": w["speaker"], "start": w["start"], "end": w["end"], "text": w["text"], "part": w["part"]}
            open_by_speaker[w["speaker"]] = u
            lines.append(u)

    out = EVAL_DIR / "scenarios" / Path(row["output"]).parts[1] / "ground_truth" / "transcript.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for u in sorted(lines, key=lambda u: u["start"]):
            t = u["start"]
            f.write(f"[{int(t // 60):02d}:{t % 60:04.1f}] SPEAKER_{u['speaker']}: {u['text'].strip()}\n")
    print(f"{out.relative_to(EVAL_DIR)}: {len(lines)} lines, {sum(len(u['text'].split()) for u in lines)} words (DRAFT: correct by listening)")


if __name__ == "__main__":
    main()
