"""Rebuild the scenario audio clips from the raw sources listed in sources.csv.

Audio files are not stored in the repository. Every clip is described by one row of
tests/e2e_eval/sources.csv (source file, time ranges, licence, SHA-256), and this
script rebuilds it with ffmpeg so that every team member gets the same file.

Usage (from the repository root):

    python tests/e2e_eval/scripts/prepare_audio.py --raw-root D:/CT/audio_raw
    python tests/e2e_eval/scripts/prepare_audio.py --raw-root D:/CT/audio_raw --only S01 S13
    python tests/e2e_eval/scripts/prepare_audio.py --raw-root D:/CT/audio_raw --update-hashes
    (--update-hashes also accepts a rebuilt source, for example a synthetic meeting read again)

Row kinds:
    cut      one or more time ranges of a source file, joined in order
    silence  generated silence of `duration_s` seconds
    babble   background babble: one range from each listed source (`source_file` and
             `segments` separated by ';'), each looped or cut to `duration_s`, levelled
             and summed (many voices at once, like a busy cafe)
    mix      speech + noise at a given SNR over the whole clip; `segments` holds
             `speech=<clip_id>;noise=<clip_id>;snr_db=<number>`. Both clips must be
             listed earlier in sources.csv

Optional `level_dbfs`: after building, the clip gets one fixed gain so that its loud parts
(90th percentile of the 100 ms RMS levels) sit at this level, and the rare peaks that would go
over -1 dBFS are softly limited. Used for the AMI clips, whose headset mix is very quiet.

Output format: WAV, 16 kHz, mono, 16-bit PCM. Each joined part gets a 30 ms fade in
and out so that joins do not click. Requires ffmpeg and ffprobe on PATH.
"""

import argparse
import csv
import hashlib
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

EVAL_DIR = Path(__file__).resolve().parents[1]
SOURCES = EVAL_DIR / "sources.csv"
FADE_S = 0.03
FFMPEG_OUT = ["-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
              "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True)
    return float(out.stdout.strip())


def parse_segments(text: str) -> list[tuple[float, float]]:
    segments = []
    for part in text.split(";"):
        start, end = part.split("-")
        segments.append((float(start), float(end)))
    return segments


def build_cut(row: dict, raw_root: Path, out: Path, update_hashes: bool = False) -> None:
    src = raw_root / row["source_file"]
    if not src.is_file():
        sys.exit(f"[{row['clip_id']}] source not found: {src}")
    if row.get("source_sha256") and sha256(src) != row["source_sha256"]:
        if not update_hashes:
            sys.exit(f"[{row['clip_id']}] source SHA-256 does not match: {src}")
        row["source_sha256"] = sha256(src)  # the source was rebuilt on purpose (synthetic meetings)
        print(f"[{row['clip_id']}] source SHA-256 updated: {src.name}")
    filters, labels = [], []
    for i, (start, end) in enumerate(parse_segments(row["segments"])):
        length = end - start
        filters.append(
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,"
            f"afade=t=in:d={FADE_S},afade=t=out:st={length - FADE_S:.3f}:d={FADE_S}[p{i}]")
        labels.append(f"[p{i}]")
    filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[out]")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", ";".join(filters),
         "-map", "[out]", *FFMPEG_OUT, str(out)], check=True)


def decode(path: Path, start: float | None = None, end: float | None = None) -> np.ndarray:
    """Decode any audio file to 16 kHz mono float samples in [-1, 1]."""
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start), "-to", str(end)]
    cmd += ["-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0


def write_wav(out: Path, samples: np.ndarray) -> None:
    pcm = np.clip(np.round(samples * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm.tobytes())


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2))) or 1e-12


def fit(x: np.ndarray, n: int) -> np.ndarray:
    """Loop or cut x to exactly n samples."""
    reps = int(np.ceil(n / len(x)))
    return np.tile(x, reps)[:n]


def build_babble(row: dict, raw_root: Path, out: Path) -> None:
    n = int(float(row["duration_s"]) * 16000)
    files = row["source_file"].split(";")
    parts = [p.split("-") for p in row["segments"].split(";")]
    if len(files) != len(parts):
        sys.exit(f"[{row['clip_id']}] source_file and segments must have the same number of entries")
    total = np.zeros(n)
    for f, (a, b) in zip(files, parts):
        x = fit(decode(raw_root / f, float(a), float(b)), n)
        total += x / rms(x)
    write_wav(out, total * (10 ** (-26 / 20)) / rms(total))  # -26 dBFS RMS


def build_mix(row: dict, rows: list[dict], out: Path) -> None:
    spec = dict(p.split("=") for p in row["segments"].split(";"))
    path_of = {r["clip_id"]: EVAL_DIR / r["output"] for r in rows}
    speech = decode(path_of[spec["speech"]])
    noise = fit(decode(path_of[spec["noise"]]), len(speech))
    noise *= rms(speech) / rms(noise) / (10 ** (float(spec["snr_db"]) / 20))
    mixed = speech + noise
    peak = float(np.max(np.abs(mixed)))
    write_wav(out, mixed / peak * 0.98 if peak > 0.98 else mixed)


def level_db(x: np.ndarray) -> float:
    """90th percentile of the 100 ms RMS levels, in dBFS: the level of the loud parts."""
    frames = x[: len(x) // 1600 * 1600].reshape(-1, 1600)
    return float(np.percentile(20 * np.log10(np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-12), 90))


def limit(y: np.ndarray, ceiling: float = 0.891, half: int = 80) -> np.ndarray:
    """Peak limiter: gain is the smallest needed gain within +-5 ms, then smoothed, so it never overshoots."""
    need = np.minimum(1.0, ceiling / np.maximum(np.abs(y), 1e-12))
    if need.min() == 1.0:
        return y
    win = np.lib.stride_tricks.sliding_window_view(np.pad(need, half, constant_values=1.0), 2 * half + 1)
    gain = win.min(axis=1)
    gain = np.convolve(np.pad(gain, half, constant_values=1.0), np.ones(2 * half + 1) / (2 * half + 1), mode="valid")
    return np.clip(y * gain, -ceiling, ceiling)


def set_level(out: Path, target_dbfs: float) -> None:
    x = decode(out)
    write_wav(out, limit(x * 10 ** ((target_dbfs - level_db(x)) / 20)))


def build_silence(row: dict, out: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
         "-t", row["duration_s"], *FFMPEG_OUT, str(out)], check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-root", type=Path, required=True, help="folder that holds the downloaded sources")
    ap.add_argument("--only", nargs="*", help="clip ids to build (default: all)")
    ap.add_argument("--update-hashes", action="store_true",
                    help="write the SHA-256 of the built clips into sources.csv instead of checking them")
    args = ap.parse_args()

    with open(SOURCES, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)

    failed = changed = False
    for row in rows:
        if args.only and row["clip_id"] not in args.only:
            continue
        out = EVAL_DIR / row["output"]
        out.parent.mkdir(parents=True, exist_ok=True)
        if row["kind"] == "cut":
            build_cut(row, args.raw_root, out, args.update_hashes)
        elif row["kind"] == "silence":
            build_silence(row, out)
        elif row["kind"] == "babble":
            build_babble(row, args.raw_root, out)
        elif row["kind"] == "mix":
            build_mix(row, rows, out)
        else:
            sys.exit(f"[{row['clip_id']}] unknown kind: {row['kind']}")
        if row.get("level_dbfs"):
            set_level(out, float(row["level_dbfs"]))

        digest, length = sha256(out), duration(out)
        if length > 290 and row["kind"] in ("cut", "mix"):
            print(f"[{row['clip_id']}] WARNING: {length:.1f} s is over the 290 s limit")
        if args.update_hashes or not row["sha256"]:
            row["sha256"], row["clip_duration_s"] = digest, f"{length:.2f}"
            changed = True
            status = "hash written"
        elif digest == row["sha256"]:
            status = "OK"
        else:
            status = "SHA-256 MISMATCH (different ffmpeg version? compare duration and listen)"
            failed = True
        print(f"[{row['clip_id']}] {out.relative_to(EVAL_DIR)}  {length:.2f} s  {status}")

    if changed:
        with open(SOURCES, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
