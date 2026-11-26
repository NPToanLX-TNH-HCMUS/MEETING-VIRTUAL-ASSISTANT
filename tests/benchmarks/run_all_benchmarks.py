#!/usr/bin/env python3
"""
Master Benchmark Orchestrator: Runs 3-Phase Benchmark Pipeline.
- Phase 1: Pre-meeting Document Ingestion (20 Cases)
- Phase 2: In-meeting Speech-to-Text STT (16 Cases)
- Phase 3: Post-meeting Minutes & Action Items Synthesis (12 Cases)
"""

import argparse
import subprocess
import sys
from pathlib import Path

BENCHMARKS_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCHMARKS_DIR.parents[1]

PHASE_CONFIGS = {
    1: {
        "title": "PHASE 1: Document Ingestion (20 Cases)",
        "script": BENCHMARKS_DIR / "PHASE_1_Document_To_Agenda" / "Ingestion_Agenda_20Cases" / "run_benchmark.py",
    },
    2: {
        "title": "PHASE 2: Speech-to-Text STT (16 Cases)",
        "script": BENCHMARKS_DIR / "PHASE_2_Audio_To_Transcript" / "STT_English_AMI_16Cases" / "run_benchmark.py",
    },
    3: {
        "title": "PHASE 3: Minutes & Action Items Synthesis (12 Cases)",
        "script": BENCHMARKS_DIR / "PHASE_3_Transcript_To_Minutes" / "Minutes_Synthesis_12Cases" / "run_benchmark.py",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        "-p",
        type=int,
        choices=[1, 2, 3],
        help="Run only a specific phase (1, 2, or 3). If omitted, runs all available phases.",
    )
    parser.add_argument("--mock", action="store_true", help="Pass --mock to phases 2 and 3 for offline dry-run")
    parser.add_argument("--sample", "-s", type=str, default=None, help="Run single sample (e.g. S01)")
    args = parser.parse_args()

    phases_to_run = [args.phase] if args.phase else [1, 2, 3]

    print("=" * 80)
    print("MEETING VIRTUAL ASSISTANT - 3-PHASE BENCHMARK SUITE")
    print(f"Target Phases: {phases_to_run}")
    print("=" * 80)

    for p in phases_to_run:
        cfg = PHASE_CONFIGS[p]
        script_path = cfg["script"]
        if not script_path.exists():
            print(f"[Error] Runner script for Phase {p} not found: {script_path}")
            continue

        cmd = [sys.executable, str(script_path)]
        if args.sample:
            cmd.extend(["--sample", args.sample])
        if args.mock and p in (2, 3):
            cmd.append("--mock")

        print(f"\n>>> Executing {cfg['title']} ...")
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print(f"[Warning] Phase {p} finished with non-zero exit code: {res.returncode}")

    print("\n" + "=" * 80)
    print("Master Benchmark Execution Finished.")
    print("=" * 80)


if __name__ == "__main__":
    main()

