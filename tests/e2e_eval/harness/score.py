"""Score a run folder against the ground truth and write the report.

    python tests/e2e_eval/harness/score.py --run tests/e2e_eval/runs/<name>
    python tests/e2e_eval/harness/score.py --run <dir> --scenarios S01 S02 --matcher embed --embed-url http://...

The run folder has one sub-folder per scenario (S01, S02, ...) with the files listed in
data.RunOutputs. Scoring only reads files: it never calls the system, so it can be repeated freely.
Outputs: <run>/<SID>/score.json, <run>/results.csv, <run>/report.md.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from checks import run_check  # noqa: E402
from data import RunOutputs, Scenario, scenario_ids  # noqa: E402
from evaluate import Evaluation  # noqa: E402
from metrics import Matcher  # noqa: E402

# Targets from USE_CASES.md: (direction, threshold). "max" means lower is better.
TARGETS = {
    "SY1": ("min", 1.0),
    "TR1": ("max", 0.15), "TR2": ("max", 0.10), "TR3": ("min", 0.90),
    "MN1": ("min", 0.75), "MN2": ("min", 0.85), "MN3": ("min", 0.80), "MN4": ("min", 0.60),
    "MN5": ("min", 0.70), "MN6": ("min", 0.60), "MN7": ("min", 0.90), "MN8": ("min", 0.95),
    "MN9": ("max", 0), "MN10": ("min", 0.70), "MN11": ("max", 0),
    "AG1": ("min", 0.80), "AG2": ("min", 0.70), "AG3": ("max", 0), "AG4": ("min", 0.80), "AG5": ("min", 1.0),
}
COLUMNS = ["TR1", "TR2", "TR3", "MN1", "MN2", "MN3", "MN4", "MN5", "MN6", "MN7", "MN8", "MN9",
           "MN10", "MN11", "AG1", "AG2", "AG3", "AG4", "AG5", "SY1"]
NAMES = {
    "TR1": "WER", "TR2": "CER", "TR3": "Key-entity recall", "TR4": "Real-time factor",
    "MN1": "Action items F1", "MN2": "Assignee accuracy", "MN3": "Due-date accuracy",
    "MN4": "Action items strict F1", "MN5": "Decisions F1", "MN6": "Unresolved issues F1",
    "MN7": "Abstention accuracy", "MN8": "Grounding rate", "MN9": "Hallucinated items",
    "MN10": "Summary coverage", "MN11": "Forbidden content", "AG1": "Agenda recall (required)",
    "AG2": "Agenda precision", "AG3": "Forbidden agenda items", "AG4": "Carry-over recall",
    "AG5": "Time budget respected", "SY1": "Pipeline completed",
}


def headline(metric: str, data: dict | None):
    """The single number shown for a metric (F1 for P / R / F1 metrics)."""
    return None if data is None else data.get("value")


def meets(metric: str, value) -> bool | None:
    if value is None or metric not in TARGETS:
        return None
    direction, threshold = TARGETS[metric]
    return value <= threshold if direction == "max" else value >= threshold


def fmt(value) -> str:
    if value is None:
        return "–"
    if isinstance(value, int):
        return str(value)
    return f"{value:.2f}"


def score_scenario(sid: str, folder: Path, matcher: Matcher) -> dict:
    scenario = Scenario(sid)
    ev = Evaluation(scenario, RunOutputs(folder), matcher)
    checks = [run_check(ev, c) for c in scenario.expected.get("checks", [])]
    passed = sum(c["status"] == "pass" for c in checks)
    failed = sum(c["status"] == "fail" for c in checks)
    ev.metrics["SY2"] = {"value": passed / (passed + failed) if passed + failed else None,
                         "pass": passed, "fail": failed}
    result = {"scenario": sid, "matcher": {"kind": matcher.kind, "tau": matcher.tau},
              "notes": ev.notes, "metrics": ev.metrics, "checks": checks,
              "matches": {k: {g: {"system_index": j, "similarity": round(s, 3)} for g, (j, s) in v.items()}
                          for k, v in {**ev.matches, "agenda": ev.agenda_matches}.items()}}
    (folder / "score.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def micro(results: list[dict], metric: str) -> dict | None:
    """Pool the counts of a P / R / F1 metric over all scenarios."""
    rows = [r["metrics"][metric] for r in results if metric in r["metrics"]]
    if not rows:
        return None
    tp_s, n_s = sum(x["tp_sys"] for x in rows), sum(x["n_sys"] for x in rows)
    tp_g, n_g = sum(x["tp_gt"] for x in rows), sum(x["n_gt"] for x in rows)
    p = tp_s / n_s if n_s else None
    r = tp_g / n_g if n_g else None
    if p is None or r is None:
        f1 = 0.0 if n_g and not n_s else None
    else:
        f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f1": f1}


def write_report(run: Path, results: list[dict]) -> None:
    with (run / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["scenario", *COLUMNS, "checks_pass", "checks_fail", "checks_skipped", "checks_not_implemented"])
        for r in results:
            counts = {s: sum(c["status"] == s for c in r["checks"]) for s in ("pass", "fail", "skipped", "not_implemented")}
            w.writerow([r["scenario"], *[fmt(headline(m, r["metrics"].get(m))) for m in COLUMNS], *counts.values()])

    by_id = {r["scenario"]: r for r in results}
    info = {}
    if (run / "run_info.json").is_file():
        info = json.loads((run / "run_info.json").read_text(encoding="utf-8"))
    code = (f"Code under test: `{info.get('branch')}` at `{info.get('commit')}`"
            f"{' with local changes in src/' if info.get('dirty') else ''}. ") if info else ""
    lines = [f"# E2E evaluation report — {run.name}", "",
             f"{code}Matcher: {results[0]['matcher']['kind']}, τ = {results[0]['matcher']['tau']}. "
             "Values that miss the target in USE_CASES.md are marked ✗.", "",
             "## 1. Overview", "",
             "| Metric | Overall | Target | Met |", "|---|---|---|---|"]
    for m in ("MN1", "MN4", "MN5", "MN6"):
        agg = micro(results, m)
        if agg:
            ok = meets(m, agg["f1"])
            lines.append(f"| {m} {NAMES[m]} (P / R / F1, pooled) | {fmt(agg['precision'])} / {fmt(agg['recall'])} / "
                         f"{fmt(agg['f1'])} | {TARGETS[m][1]} | {'✓' if ok else '✗' if ok is False else '–'} |")
    for m in ("TR1", "TR2", "TR3", "TR4", "MN2", "MN3", "MN7", "MN8", "MN9", "MN10", "MN11",
              "AG1", "AG2", "AG3", "AG4", "AG5", "SY1"):
        values = [headline(m, r["metrics"].get(m)) for r in results]
        values = [v for v in values if v is not None]
        if not values:
            continue
        overall = sum(values) if m in ("MN9", "MN11", "AG3") else sum(values) / len(values)
        how = "total" if m in ("MN9", "MN11", "AG3") else "mean"
        ok = meets(m, overall)
        lines.append(f"| {m} {NAMES[m]} ({how}) | {fmt(overall)} | {TARGETS.get(m, ('', '–'))[1]} | "
                     f"{'✓' if ok else '✗' if ok is False else '–'} |")
    checks = [c for r in results for c in r["checks"]]
    count = {s: sum(c["status"] == s for c in checks) for s in ("pass", "fail", "skipped", "not_implemented")}
    lines.append(f"| SY2 Expected-behaviour pass rate | {fmt(count['pass'] / (count['pass'] + count['fail']) if count['pass'] + count['fail'] else None)} "
                 f"({count['pass']} pass, {count['fail']} fail; {count['skipped']} skipped, "
                 f"{count['not_implemented']} not implemented) | – | – |")

    degrade = []
    for noisy, clean in (("S05", "S03"), ("S08", "S06")):
        a, b = by_id.get(noisy), by_id.get(clean)
        if a and b and "TR1" in a["metrics"] and "TR1" in b["metrics"]:
            degrade.append(f"{noisy} vs {clean}: {a['metrics']['TR1']['value'] - b['metrics']['TR1']['value']:+.3f}")
    if degrade:
        lines += ["", f"TR5 WER degradation: {'; '.join(degrade)}"]

    lines += ["", "## 2. Per scenario", "",
              "| Scenario | " + " | ".join(COLUMNS) + " | Checks |",
              "|---" * (len(COLUMNS) + 2) + "|"]
    for r in results:
        cells = []
        for m in COLUMNS:
            v = headline(m, r["metrics"].get(m))
            ok = meets(m, v)
            cells.append(fmt(v) + (" ✗" if ok is False else ""))
        c = r["checks"]
        cells.append(f"{sum(x['status'] == 'pass' for x in c)}/{sum(x['status'] in ('pass', 'fail') for x in c)}")
        lines.append(f"| {r['scenario']} | " + " | ".join(cells) + " |")

    lines += ["", "## 3. Failed checks", ""]
    failed = [(r["scenario"], c) for r in results for c in r["checks"] if c["status"] == "fail"]
    lines += [f"- **{c['id']}** ({c['case']}, `{c['type']}`): {c['detail']}" for _, c in failed] or ["None."]
    lines += ["", "## 4. Not run", ""]
    reasons: dict = {}
    for r in results:
        for c in r["checks"]:
            if c["status"] in ("skipped", "not_implemented"):
                reasons.setdefault((c["status"], c["detail"]), []).append(c["id"])
    lines += [f"- {status}, {detail}: {', '.join(ids)}" for (status, detail), ids in sorted(reasons.items())] or ["None."]
    lines += ["", "## 5. Items to review", ""]
    for r in results:
        for item in r["metrics"].get("MN9", {}).get("items", []):
            lines.append(f"- {r['scenario']} possible hallucination ({item['section']}): {item['text']}")
        for q in r["metrics"].get("MN8", {}).get("not_found", []):
            lines.append(f"- {r['scenario']} quote not found in transcript: {q}")
        for note in r["notes"]:
            lines.append(f"- {r['scenario']}: {note}")
    (run / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    sys.stdout.reconfigure(errors="replace")  # Windows consoles without UTF-8
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, type=Path, help="run folder with one sub-folder per scenario")
    ap.add_argument("--scenarios", nargs="*", help="scenario ids (default: every sub-folder found)")
    ap.add_argument("--matcher", choices=["lexical", "embed"], default="lexical")
    ap.add_argument("--tau", type=float, help="matching threshold (default depends on the matcher)")
    ap.add_argument("--embed-url", help="embedding server, needed with --matcher embed")
    args = ap.parse_args()

    if not args.run.is_dir():
        sys.exit(f"Run folder not found: {args.run}")
    known = set(scenario_ids())
    ids = args.scenarios or sorted(p.name for p in args.run.iterdir() if p.is_dir() and p.name in known)
    missing = [sid for sid in ids if not (args.run / sid).is_dir()]
    if missing:
        print(f"No outputs for {', '.join(missing)} in {args.run}: skipped")
    ids = [sid for sid in ids if sid not in missing]
    if not ids:
        sys.exit(f"No scenario folders (S01, S02, ...) in {args.run}")
    matcher = Matcher(args.matcher, args.tau, args.embed_url)
    results = []
    for sid in ids:
        r = score_scenario(sid, args.run / sid, matcher)
        c = r["checks"]
        print(f"{sid}: WER {fmt(headline('TR1', r['metrics'].get('TR1')))}  "
              f"AI strict F1 {fmt(headline('MN4', r['metrics'].get('MN4')))}  "
              f"checks {sum(x['status'] == 'pass' for x in c)}/{sum(x['status'] in ('pass', 'fail') for x in c)}")
        results.append(r)
    write_report(args.run, results)
    print(f"Report: {args.run / 'report.md'}")


if __name__ == "__main__":
    main()
