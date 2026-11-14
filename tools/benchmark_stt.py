"""Benchmark the repository transcriber against prepared English WAV/reference pairs.

From the repository root, validate inputs without sending requests:
    python -m tools.benchmark_stt --samples "PATH/TO/samples" --case S01 --check
Remove --check to run one case, or replace --case S01 with --all for a batch.
Requires requests, python-dotenv and jiwer in the selected Python environment.
"""

import argparse
import csv
import re
import tempfile
import time
import unicodedata
import wave
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from jiwer import process_characters, process_words

from src.backend.speech_to_text.transcriber import ElevenLabsTranscriber

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["Case", "Model", "Duration_s", "WER_%", "CER_%", "Latency_s", "RTF",
          "S", "D", "I", "Reference_tokens", "Error"]
HEADER = re.compile(r"^\[\d+:\d{2}\.\d+\s*-\s*\d+:\d{2}\.\d+\]\s+[^:\n]+:\s*", re.MULTILINE)


def normalize(text):
    text = unicodedata.normalize("NFC", text.casefold())
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def main():
    parser = argparse.ArgumentParser(description="Benchmark the repository's ElevenLabsTranscriber")
    parser.add_argument("--samples", type=Path, required=True, help="Local folder containing S01 through S16")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case", help="Run one case, e.g. S01")
    selection.add_argument("--all", action="store_true", help="Run all 16 cases; consumes API credits")
    parser.add_argument("--check", action="store_true", help="Validate inputs without calling the API")
    parser.add_argument("--output", type=Path, default=ROOT / "data/stt_benchmark_results")
    args = parser.parse_args()
    samples = args.samples.resolve()
    if not samples.is_dir():
        parser.error(f"Samples folder not found: {samples}")
    names = [f"S{index:02}" for index in range(1, 17)] if args.all else [args.case]
    if any(not re.fullmatch(r"S(?:0[1-9]|1[0-6])", name) for name in names):
        parser.error("--case must be S01 through S16")

    # Validate every selected file before issuing any paid request.
    cases = []
    for name in names:
        folder = samples / name
        audio, reference = folder / "meeting.wav", folder / "ground_truth.txt"
        try:
            truth = HEADER.sub("", reference.read_text(encoding="utf-8-sig")).strip()
            if not normalize(truth):
                raise ValueError("Empty ground truth")
            with wave.open(str(audio), "rb") as stream:
                duration = stream.getnframes() / stream.getframerate()
            if duration <= 0:
                raise ValueError("Empty audio")
        except (OSError, ValueError, wave.Error, EOFError) as exc:
            parser.error(f"{name}: {exc}")
        cases.append((name, audio, truth, duration))
        print(f"[READY] {name}: {duration:.2f}s, {len(normalize(truth).split())} reference tokens")
    if args.check:
        print(f"Validated {len(cases)} case(s). No API requests sent.")
        return

    load_dotenv(ROOT / ".env")
    transcriber = ElevenLabsTranscriber()
    args.output.mkdir(parents=True, exist_ok=True)
    prefix = datetime.now(timezone.utc).strftime("repo_run_%Y%m%d_%H%M%S_UTC_")
    output = Path(tempfile.mkdtemp(prefix=prefix, dir=args.output))
    failures = 0
    with (output / "summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        stream.flush()
        for name, audio, truth, duration in cases:
            target = output / name
            target.mkdir()
            (target / "ground_truth.txt").write_text(truth, encoding="utf-8")
            row = dict.fromkeys(FIELDS, "")
            row.update(Case=name, Model="scribe_v2", Duration_s=round(duration, 3))
            print(f"[RUN] {name} via repository transcriber")
            try:
                start = time.perf_counter()
                segments = transcriber.transcribe_file(audio, output_path=target / "transcript.txt")
                elapsed = time.perf_counter() - start
                # WER/CER compare spoken text, excluding speaker and timing labels.
                prediction = " ".join(segment["Text"] for segment in segments)
                row.update(Latency_s=round(elapsed, 3), RTF=round(elapsed / duration, 4))
                (target / "plain_text.txt").write_text(prediction, encoding="utf-8")
                ref, hyp = normalize(truth), normalize(prediction)
                words, chars = process_words(ref, hyp), process_characters(ref, hyp)
                row.update({"WER_%": round(words.wer * 100, 2), "CER_%": round(chars.cer * 100, 2),
                            "S": words.substitutions, "D": words.deletions, "I": words.insertions,
                            "Reference_tokens": len(ref.split())})
                print(f"[OK] WER={row['WER_%']}%, CER={row['CER_%']}%, time={elapsed:.3f}s")
            except Exception as exc:
                failures += 1
                row["Error"] = str(exc)
                (target / "error.txt").write_text(str(exc), encoding="utf-8")
                print(f"[ERROR] {name}: {exc}")
            writer.writerow(row)
            stream.flush()
    print(f"Results: {output}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
