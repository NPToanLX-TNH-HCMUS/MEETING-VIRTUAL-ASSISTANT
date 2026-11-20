"""Check that the dataset is consistent before it is locked or after the ground truth changes.

    python tests/e2e_eval/harness/validate.py            # every scenario
    python tests/e2e_eval/harness/validate.py S01 S06    # some scenarios
    python tests/e2e_eval/harness/validate.py --no-audio # skip SHA-256 of the audio files

Errors are things the harness cannot score correctly; warnings are worth a look.
No backend and no API key are needed. Exit code 1 when there is an error.
"""

import argparse
import csv
import hashlib
import re
import sys
import wave
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from checks import CHECKS  # noqa: E402
from data import E2E_DIR, Scenario, scenario_ids  # noqa: E402
from metrics import quote_grounded  # noqa: E402
from textnorm import normalize, phrase_in, strip_transcript_labels, tokens  # noqa: E402

LINE = re.compile(r"^\[(\d{2}):(\d{2}\.\d)\] ([^:\[\]]{1,40}): (.+)$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATES = {"not_discussed", "in_progress", "discussed", "concluded"}
STEPS = {"create_meeting", "upload_document", "generate_agenda", "confirm_agenda", "start_recording",
         "stop_recording", "transcribe", "generate_minutes", "edit_minutes", "confirm_minutes",
         "pause_recording", "resume_recording"}
STAGES = {"after_agenda", "after_confirm_agenda", "during_pause", "after_stop", "after_minutes", "end",
          "agenda", "minutes"}
TARGETS = {"agenda_titles", "dropped_titles", "decisions", "action_items", "unresolved_issues",
           "minutes_items", "minutes_text"}
METRICS = {f"TR{i}" for i in range(1, 8)} | {f"MN{i}" for i in range(1, 12)} | {f"AG{i}" for i in range(1, 6)} \
    | {f"AT{i}" for i in range(1, 6)} | {f"SY{i}" for i in range(1, 7)}
# Special cases without a check of their own (SPECIAL_CASES.md, section 3): B2 is checked by the
# general checks G1 and G3; B5 by hand (section 7.5); B1 and B3 share one check, TR3 >= 0.9.
GENERAL_ONLY = {"B2"}
MANUAL = {"B5"}
TR3_CASES = {"B1", "B3"}

PARAMS = {  # required parameters per check type (SPECIAL_CASES.md, section 2)
    "http_status": ["step", "status"], "no_status": ["status"], "meeting_status": ["stage", "equals"],
    "contains": ["target", "any_of"], "not_contains": ["target", "any_of"], "count_equals": ["target", "n"],
    "count_range": ["target", "min", "max"], "count_similar": ["target", "reference", "n"],
    "all_similar": ["target", "reference"], "action_item_field": ["match", "field", "equals"],
    "agenda_item_field": ["title", "field", "equals"], "item_in_section": ["match", "in", "not_in"],
    "agenda_budget": [], "metric_at_least": ["metric", "value"], "file_exists": ["path"],
    "file_equals": ["path", "equals_sent"], "doc_text_contains": ["file", "text"],
    "doc_text_not_contains": ["file", "text"], "llm_prompt_contains": ["stage", "text"],
    "llm_prompt_not_contains": ["stage", "text"], "llm_fallback_used": ["stage"],
    "audio_duration": ["path", "equals_s", "tolerance_s"], "agenda_state": ["match", "stage", "equals"],
    "state_change_within": ["match", "to"], "no_event_between": ["event", "from_s", "to_s"],
    "event_exists": ["event", "data"],
}


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def error(self, sid, msg):
        self.errors.append(f"{sid}: {msg}")

    def warn(self, sid, msg):
        self.warnings.append(f"{sid}: {msg}")


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_scenario(sc: Scenario, rep: Report, sources: dict, coverage: dict, hash_audio: bool) -> None:
    sid = sc.id
    spec = sc.spec
    if spec.get("id") != sid:
        rep.error(sid, f"scenario.json id is {spec.get('id')!r}")
    meeting = spec.get("meeting") or {}
    for key in ("topic", "language", "duration_minutes", "planned_points"):
        if key not in meeting:
            rep.error(sid, f"meeting.{key} missing")
    if meeting.get("language") not in ("en", "vi"):
        rep.error(sid, f"meeting.language {meeting.get('language')!r} is not accepted by the API")
    try:
        if datetime.fromisoformat(spec["meeting_date"]).tzinfo is None:
            rep.error(sid, "meeting_date has no UTC offset")
    except (KeyError, ValueError):
        rep.error(sid, f"meeting_date {spec.get('meeting_date')!r} is not ISO 8601")

    # ---- audio
    audio = sc.dir / spec["audio"]["file"]
    seconds = spec["audio"].get("seconds")
    if not audio.is_file():
        rep.error(sid, f"audio missing: {audio.name} (rebuild with scripts/prepare_audio.py)")
        length = seconds or 0.0
    else:
        length = wav_seconds(audio)
        if seconds is None or abs(length - seconds) > 0.05:
            rep.error(sid, f"audio.seconds {seconds} but the file lasts {length:.2f} s")
        row = sources.get(spec["audio"]["file"])
        if row is None:
            rep.error(sid, "no row in sources.csv produces this audio file")
        else:
            if row.get("clip_duration_s") and abs(float(row["clip_duration_s"]) - length) > 0.05:
                rep.error(sid, f"sources.csv clip_duration_s {row['clip_duration_s']} differs from the file")
            if hash_audio and row.get("sha256") and row["sha256"] != sha256(audio):
                rep.error(sid, "audio SHA-256 differs from sources.csv")
    cov = coverage.get(sid)
    if cov is None:
        rep.error(sid, "no row in coverage.csv")
    elif cov.get("clip_seconds"):
        first = re.match(r"[\d.]+", cov["clip_seconds"])
        if first and abs(float(first.group()) - length) > 1.0:
            rep.warn(sid, f"coverage.csv clip_seconds {cov['clip_seconds']} vs audio {length:.2f} s")

    for doc in spec.get("documents", []):
        if not (sc.dir / doc).is_file():
            (rep.warn if sid == "S11" else rep.error)(sid, f"document missing: {doc}")

    # ---- transcript
    text = sc.transcript
    if text is None:
        rep.error(sid, "ground_truth/transcript.txt missing")
        text = ""
    previous = -1.0
    speakers = set()
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        m = LINE.match(line)
        if not m:
            rep.error(sid, f"transcript line {n} does not match '[mm:ss.s] SPEAKER: text': {line[:60]}")
            continue
        t = int(m.group(1)) * 60 + float(m.group(2))
        speakers.add(m.group(3))
        if t < previous:
            rep.warn(sid, f"transcript line {n} goes back in time ({t:.1f} s < {previous:.1f} s)")
        if t > length + 0.5:
            rep.error(sid, f"transcript line {n} at {t:.1f} s is after the end of the audio")
        previous = t
    gt_tokens = tokens(strip_transcript_labels(text))
    gt_norm = " ".join(gt_tokens)

    # ---- key entities and aliases
    for e in spec.get("key_entities", []):
        if not any(phrase_in(gt_norm, f) for f in [e["text"], *e.get("alts", [])]):
            rep.error(sid, f"key entity {e['text']!r} is not in the ground-truth transcript")
    aliases = spec.get("aliases") or {}
    alias_forms = {normalize(f) for role, forms in aliases.items() for f in [role, *forms]}

    # ---- minutes
    gm = sc.minutes
    ids = set()
    for section in ("decisions", "action_items", "unresolved_issues", "summary_points", "must_not_appear"):
        for item in gm.get(section, []):
            if item.get("id") in ids:
                rep.error(sid, f"minutes id {item.get('id')} used twice")
            ids.add(item.get("id"))
            t = item.get("time")
            if t is not None and not 0 <= t <= length + 0.5:
                rep.error(sid, f"{item['id']} time {t} outside the audio")
    for a in gm.get("action_items", []):
        for key in ("task", "assignee", "due", "spoken_due", "quote", "time"):
            if key not in a:
                rep.error(sid, f"{a['id']} has no {key!r} (use null when unknown)")
        if a.get("assignee") is not None and normalize(a["assignee"]) not in alias_forms:
            rep.error(sid, f"{a['id']} assignee {a['assignee']!r} is not in scenario.json aliases")
        if a.get("due") is not None and not DATE.match(str(a["due"])):
            rep.error(sid, f"{a['id']} due {a['due']!r} is not YYYY-MM-DD")
        if a.get("quote") and not quote_grounded(a["quote"], gt_tokens, min_ratio=0.9):
            rep.error(sid, f"{a['id']} quote not found in the transcript: {a['quote'][:60]}")
    gt_minutes_text = normalize(" ".join(x.get("text") or x.get("task", "")
                                         for s in ("decisions", "action_items", "unresolved_issues")
                                         for x in gm.get(s, [])))
    for f in gm.get("must_not_appear", []):
        for k in f.get("keywords", []):
            if phrase_in(gt_minutes_text, k):
                rep.error(sid, f"{f['id']} keyword {k!r} appears in the expected minutes themselves")

    # ---- agenda
    ga = sc.agenda
    agenda_ids = {i["id"] for i in ga.get("items", [])}
    if len(agenda_ids) != len(ga.get("items", [])):
        rep.error(sid, "agenda item id used twice")
    if ga and ga.get("max_total_minutes") not in (None, meeting.get("duration_minutes")):
        rep.warn(sid, f"agenda max_total_minutes {ga.get('max_total_minutes')} != duration {meeting.get('duration_minutes')}")
    spans = []
    for item in ga.get("items", []):
        tr = item.get("tracking") or {}
        if tr.get("final_state") not in STATES:
            rep.error(sid, f"{item['id']} final_state {tr.get('final_state')!r}")
        for a, b in tr.get("spans", []):
            if not 0 <= a < b <= length + 0.5:
                rep.error(sid, f"{item['id']} span {a}-{b} outside the audio or empty")
            spans.append((a, b, item["id"]))
        if tr.get("final_state") == "not_discussed" and tr.get("spans"):
            rep.error(sid, f"{item['id']} is not_discussed but has spans")
        if tr.get("final_state") in ("discussed", "concluded") and not tr.get("spans"):
            rep.error(sid, f"{item['id']} is {tr['final_state']} but has no span")
    for a, b in ga.get("off_agenda", []):
        spans.append((a, b, "off_agenda"))
    spans.sort()
    for (a1, b1, i1), (a2, b2, i2) in zip(spans, spans[1:]):
        if a2 < b1 - 0.05:
            rep.error(sid, f"spans overlap: {i1} {a1}-{b1} and {i2} {a2}-{b2}")
    for c in ga.get("carry_over", []):
        if c not in agenda_ids:
            rep.error(sid, f"carry_over {c} is not an agenda item")
    titles = normalize(" ".join(i["title"] for i in ga.get("items", [])))
    for x in ga.get("must_not_include", []):
        for k in x.get("keywords", []):
            if phrase_in(titles, k):
                rep.error(sid, f"{x['id']} keyword {k!r} appears in the expected agenda titles")

    # ---- expected behaviour
    exp = sc.expected
    if exp.get("scenario_id") != sid:
        rep.error(sid, f"expected_behavior scenario_id is {exp.get('scenario_id')!r}")
    seen = set()
    for c in exp.get("checks", []):
        cid = c.get("id", "?")
        if cid in seen:
            rep.error(sid, f"check id {cid} used twice")
        seen.add(cid)
        if not cid.startswith(sid + "-"):
            rep.error(sid, f"check id {cid} does not start with {sid}-")
        if not re.fullmatch(r"[A-G]\d{1,2}", str(c.get("case", ""))):
            rep.error(sid, f"{cid} case {c.get('case')!r}")
        t = c.get("type")
        if t not in CHECKS:
            rep.error(sid, f"{cid} unknown type {t!r}")
            continue
        for p in PARAMS[t]:
            if p not in c:
                rep.error(sid, f"{cid} ({t}) has no {p!r}")
        if "step" in c and not (c["step"] in STEPS or re.fullmatch(r"(fault|retry):[A-G]\d+(-\w+)?", c["step"])):
            rep.error(sid, f"{cid} step {c['step']!r}")
        if "stage" in c and c["stage"] not in STAGES:
            rep.error(sid, f"{cid} stage {c['stage']!r}")
        if "target" in c and c["target"] not in TARGETS:
            rep.error(sid, f"{cid} target {c['target']!r}")
        if t == "metric_at_least" and c.get("metric") not in METRICS:
            rep.error(sid, f"{cid} metric {c.get('metric')!r}")
        if t in ("action_item_field", "item_in_section") and c.get("match") not in ids:
            rep.error(sid, f"{cid} match {c.get('match')!r} is not a minutes id")
        if t in ("agenda_state", "state_change_within") and c.get("match") not in agenda_ids:
            rep.error(sid, f"{cid} match {c.get('match')!r} is not an agenda id")
        if t == "state_change_within":
            item = next((i for i in ga.get("items", []) if i["id"] == c.get("match")), None)
            if item and c.get("span", 0) >= len((item.get("tracking") or {}).get("spans", [])):
                rep.error(sid, f"{cid} span index {c.get('span', 0)} does not exist")
        for key in ("from_s", "to_s", "equals_s"):
            if c.get(key) is not None and not 0 <= c[key] <= length + 0.5:
                rep.error(sid, f"{cid} {key} {c[key]} outside the audio")
        if t == "doc_text_contains" and not any(Path(d).name == c["file"] for d in spec.get("documents", [])):
            rep.error(sid, f"{cid} file {c['file']!r} is not a document of the scenario")
        if t == "not_contains" and c.get("target") == "agenda_titles":
            for p in c["any_of"]:
                if phrase_in(titles, p):
                    rep.error(sid, f"{cid} phrase {p!r} appears in the expected agenda titles")
        if t == "not_contains" and c.get("target") in ("decisions", "action_items", "minutes_items"):
            for p in c["any_of"]:
                if phrase_in(gt_minutes_text, p):
                    rep.error(sid, f"{cid} phrase {p!r} appears in the expected minutes")
    cases = {c.get("case") for c in exp.get("checks", [])}
    has_tr3 = any(c.get("type") == "metric_at_least" and c.get("metric") == "TR3" for c in exp.get("checks", []))
    for code in spec.get("special_cases", []):
        covered = (code in cases or code in GENERAL_ONLY or code in MANUAL
                   or (code in TR3_CASES and has_tr3))
        if not covered:
            rep.error(sid, f"special case {code} has no check in expected_behavior.json")
    general = cases & {"G1", "G2", "G3"}
    if general != {"G1", "G2", "G3"}:
        rep.error(sid, f"general checks missing: {sorted({'G1', 'G2', 'G3'} - general)}")


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenarios", nargs="*")
    ap.add_argument("--no-audio", action="store_true", help="skip the SHA-256 of the audio files")
    args = ap.parse_args()

    with (E2E_DIR / "sources.csv").open(encoding="utf-8") as f:
        sources = {r["output"]: r for r in csv.DictReader(f)}
    with (E2E_DIR / "coverage.csv").open(encoding="utf-8") as f:
        coverage = {r["scenario_id"]: r for r in csv.DictReader(f)}

    rep = Report()
    ids = args.scenarios or scenario_ids()
    for sid in ids:
        sc = Scenario(sid)
        # sources.csv "output" is relative to tests/e2e_eval; scenario.json "audio.file" to the scenario folder
        own = {str(Path(out).relative_to("scenarios", sc.dir.name)): row for out, row in sources.items()
               if Path(out).parts[:2] == ("scenarios", sc.dir.name)}
        check_scenario(sc, rep, own, coverage, not args.no_audio)
    if not args.scenarios:
        for sid in coverage:
            if sid not in ids:
                rep.error(sid, "row in coverage.csv but no scenario folder")

    for w in rep.warnings:
        print("warning:", w)
    for e in rep.errors:
        print("ERROR:  ", e)
    print(f"{len(ids)} scenarios: {len(rep.errors)} errors, {len(rep.warnings)} warnings")
    sys.exit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()
