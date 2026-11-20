"""Self-test of the scorer: no backend and no API key needed.

    python tests/e2e_eval/harness/selftest.py

1. The bit-parallel edit distance equals the textbook dynamic programme.
2. Outputs copied from the ground truth score perfectly on every scenario.
3. Outputs with planted mistakes are caught.
Run it after changing the harness or the ground truth.
"""

import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data import Scenario, scenario_ids  # noqa: E402
from metrics import Matcher, levenshtein  # noqa: E402
from score import score_scenario  # noqa: E402

failures = []


def expect(ok: bool, message: str) -> None:
    if not ok:
        failures.append(message)


def dp_distance(a, b) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def perfect_outputs(sc: Scenario, folder: Path) -> None:
    folder.mkdir(parents=True)
    (folder / "transcript.txt").write_text(sc.transcript or "", encoding="utf-8")
    gm = sc.minutes

    def required(x):
        return not x.get("optional")

    minutes = {
        "summary": " ".join(p["text"] + "." for p in gm.get("summary_points", [])),
        "decisions": [x["text"] for x in gm.get("decisions", []) if required(x)],
        "action_items": [{k: x.get(k) for k in ("task", "assignee", "due", "quote")}
                         for x in gm.get("action_items", []) if required(x)],
        "unresolved_issues": [x["text"] for x in gm.get("unresolved_issues", []) if required(x)],
        "markdown": "",
    }
    (folder / "minutes.json").write_text(json.dumps(minutes), encoding="utf-8")
    items = [g for g in sc.agenda.get("items", []) if g.get("required", True)]
    duration = sc.spec["meeting"]["duration_minutes"]
    each = max(1, duration // max(1, len(items)))
    proposal = {"items": [{"id": f"agd_{i:03d}", "title": g["title"], "estimated_minutes": each}
                          for i, g in enumerate(items, 1)], "dropped": []}
    (folder / "agenda_proposal.json").write_text(json.dumps(proposal), encoding="utf-8")
    (folder / "stages.json").write_text(json.dumps({"end": "archived"}), encoding="utf-8")


def main() -> None:
    random.seed(0)
    for _ in range(500):
        a = [random.choice("abc") for _ in range(random.randint(0, 80))]
        b = [random.choice("abc") for _ in range(random.randint(0, 80))]
        expect(levenshtein(a, b) == dp_distance(a, b), f"edit distance wrong for {a} / {b}")

    matcher = Matcher("lexical")
    with tempfile.TemporaryDirectory() as tmp:
        run = Path(tmp)
        for sid in scenario_ids():
            perfect_outputs(Scenario(sid), run / sid)
            r = score_scenario(sid, run / sid, matcher)
            m = r["metrics"]
            for key, want in (("TR1", 0.0), ("TR3", 1.0), ("MN1", 1.0), ("MN4", 1.0), ("MN5", 1.0),
                              ("MN6", 1.0), ("MN8", 1.0), ("MN9", 0), ("MN10", 1.0), ("MN11", 0),
                              ("AG1", 1.0), ("AG3", 0), ("AG4", 1.0), ("AG5", 1.0)):
                got = m.get(key, {}).get("value")
                expect(got is None or abs(got - want) < 1e-9, f"{sid} perfect outputs: {key} = {got}, expected {want}")
            # A check fails on perfect outputs only when it needs something the copy does not have
            for c in r["checks"]:
                expect(c["status"] != "fail" or c["id"] == "S12-05", f"{sid} perfect outputs: {c['id']} failed: {c['detail']}")

        # Planted mistakes on S06
        sc = Scenario("S06")
        folder = run / "S06"
        minutes = json.loads((folder / "minutes.json").read_text(encoding="utf-8"))
        minutes["action_items"][0]["assignee"] = "Hung"            # wrong owner for AI1
        minutes["action_items"][1]["due"] = None                   # missing deadline for AI2
        minutes["action_items"].append({"task": "Order pizza for the demo day", "assignee": "Ann",
                                         "due": None, "quote": "let us order pizza for everyone"})
        minutes["decisions"].append("The team will buy new laptops")
        (folder / "minutes.json").write_text(json.dumps(minutes), encoding="utf-8")
        r = score_scenario("S06", folder, matcher)
        m = r["metrics"]
        expect(m["MN2"]["value"] < 1, "wrong assignee not caught")
        expect(m["MN3"]["value"] < 1, "missing deadline not caught")
        expect(m["MN9"]["value"] == 2, f"invented items: MN9 = {m['MN9']['value']}, expected 2")
        expect(m["MN8"]["value"] < 1, "quote absent from the transcript not caught")
        status = {c["id"]: c["status"] for c in r["checks"]}
        expect(status.get("S06-06") == "pass", "S06-06 (AI1 due date) should still pass")
        shutil.rmtree(folder)

    if failures:
        print("SELF-TEST FAILED")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print(f"Self-test passed ({len(scenario_ids())} scenarios).")


if __name__ == "__main__":
    main()
