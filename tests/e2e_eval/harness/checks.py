"""One function per check type of SPECIAL_CASES.md section 2.

Each returns (status, detail); status is "pass", "fail", "skipped" (the run has no
data for it) or "not_implemented" (the system has no such feature yet).
"""

import wave

from evaluate import Evaluation
from textnorm import normalize, phrase_in

PASS, FAIL, SKIP, TODO = "pass", "fail", "skipped", "not_implemented"
LIVE_TYPES = {"agenda_state", "state_change_within", "no_event_between", "event_exists"}


def _bool(ok: bool, detail: str):
    return (PASS if ok else FAIL), detail


def _targets(ev: Evaluation, target: str, stage: str | None = None) -> list[str] | None:
    out = ev.out
    if target in ("agenda_titles", "dropped_titles"):
        if target == "dropped_titles":
            items = out.dropped()
        elif stage in ("after_confirm_agenda", "end"):
            items = out.final_items()
        else:
            items = out.proposed_items()
        return None if items is None else [str(i.get("title", "")) for i in items]
    m = out.minutes_lists()
    if m is None:
        return None
    if target == "action_items":
        return [str(a.get("task", "")) for a in m["action_items"]]
    if target in ("decisions", "unresolved_issues"):
        return m[target]
    if target == "minutes_items":
        return [m["summary"], *m["decisions"], *m["unresolved_issues"],
                *[str(a.get("task", "")) for a in m["action_items"]]]
    if target == "minutes_text":
        return [ev.minutes_text()]
    raise ValueError(f"unknown target {target}")


def _section_of(ev: Evaluation, gid: str) -> str | None:
    for section in ("action_items", "decisions", "unresolved_issues"):
        if any(g["id"] == gid for g in ev.sc.minutes.get(section, [])):
            return section
    return None


def _gt_text(ev: Evaluation, gid: str) -> str:
    section = _section_of(ev, gid)
    item = next(g for g in ev.sc.minutes[section] if g["id"] == gid)
    return item.get("text") or item.get("task", "")


def _calls(ev: Evaluation, step: str, file: str | None = None) -> list[dict]:
    return [e for e in ev.out.api_log if e.get("step") == step and (file is None or e.get("file") == file)]


# ------------------------------------------------------------------ checks


def http_status(ev, c):
    if ev.out.api_log is None:
        return SKIP, "no api_log.jsonl"
    calls = _calls(ev, c["step"], c.get("file"))
    if not calls:
        return FAIL, f"step {c['step']} {c.get('file') or ''} was not called"
    e = calls[0]
    ok = e.get("status") == c["status"] and (c.get("code") is None or e.get("code") == c["code"])
    return _bool(ok, f"got {e.get('status')} {e.get('code') or ''}".strip())


def no_status(ev, c):
    if ev.out.api_log is None:
        return SKIP, "no api_log.jsonl"
    bad = [e["step"] for e in ev.out.api_log if e.get("status") == c["status"]]
    return _bool(not bad, f"steps with {c['status']}: {bad}" if bad else "none")


def meeting_status(ev, c):
    if ev.out.stages is None or c["stage"] not in ev.out.stages:
        return SKIP, f"status at stage {c['stage']} not recorded"
    got = ev.out.stages[c["stage"]]
    return _bool(got == c["equals"], f"status {got}")


def _hits(texts: list[str], phrases: list[str]) -> list[str]:
    normalized = [normalize(t) for t in texts]
    return [p for p in phrases if any(phrase_in(t, p) for t in normalized)]


def contains(ev, c):
    texts = _targets(ev, c["target"], c.get("stage"))
    if texts is None:
        return SKIP, f"no {c['target']}"
    hits = _hits(texts, c["any_of"])
    return _bool(bool(hits), f"found {hits}" if hits else "none of the phrases found")


def not_contains(ev, c):
    texts = _targets(ev, c["target"], c.get("stage"))
    if texts is None:
        return SKIP, f"no {c['target']}"
    hits = _hits(texts, c["any_of"])
    return _bool(not hits, f"found {hits}" if hits else "none found")


def count_equals(ev, c):
    target = c["target"]
    if target == "action_items" and c.get("where"):
        m = ev.out.minutes_lists()
        if m is None:
            return SKIP, "no minutes"
        field, value = c["where"]["field"], c["where"]["equals"]
        if field == "assignee":
            n = sum(ev.canonical_person(a.get("assignee")) == ev.canonical_person(value) for a in m["action_items"])
        else:
            n = sum(normalize(str(a.get(field))) == normalize(str(value)) for a in m["action_items"])
    else:
        texts = _targets(ev, target)
        if texts is None:
            return SKIP, f"no {target}"
        n = len(texts)
    return _bool(n == c["n"], f"count {n}, expected {c['n']}")


def count_range(ev, c):
    texts = _targets(ev, c["target"])
    if texts is None:
        return SKIP, f"no {c['target']}"
    return _bool(c["min"] <= len(texts) <= c["max"], f"count {len(texts)}")


def _reference(ev, ref: str) -> str:
    return (ev.sc.spec.get("meeting") or {}).get("topic", "") if ref == "topic" else ref


def count_similar(ev, c):
    texts = _targets(ev, c["target"])
    if texts is None:
        return SKIP, f"no {c['target']}"
    ref = _reference(ev, c["reference"])
    sims = ev.m.matrix([ref], texts)[0] if texts else []
    similar = [t for t, s in zip(texts, sims) if s >= ev.m.tau]
    return _bool(len(similar) == c["n"], f"{len(similar)} similar: {similar}")


def all_similar(ev, c):
    texts = _targets(ev, c["target"])
    if texts is None:
        return SKIP, f"no {c['target']}"
    ref = _reference(ev, c["reference"])
    sims = ev.m.matrix([ref], texts)[0] if texts else []
    off = [t for t, s in zip(texts, sims) if s < ev.m.tau]
    return _bool(not off, f"not similar: {off}" if off else f"{len(texts)} items, all similar")


def action_item_field(ev, c):
    if ev.out.minutes is None:
        return SKIP, "no minutes"
    match = ev.matches["action_items"].get(c["match"])
    if match is None:
        return FAIL, f"{c['match']} not matched to any system action item"
    item = ev.sys_minutes["action_items"][match[0]]
    field, want = c["field"], c["equals"]
    got = item.get(field)
    if field == "assignee":
        ok = ev.canonical_person(got) == ev.canonical_person(want)
    elif field == "due":
        ok = ev.canonical_date(got) == ev.canonical_date(want)
    else:
        ok = normalize(str(got)) == normalize(str(want))
    return _bool(ok, f"{field} = {got!r}, expected {want!r}")


def agenda_item_field(ev, c):
    items = ev.out.final_items()
    if items is None:
        return SKIP, "no agenda"
    item = next((i for i in items if normalize(i.get("title", "")) == normalize(c["title"])), None)
    if item is None:
        return FAIL, f"no agenda item titled {c['title']!r}"
    got = item.get(c["field"])
    return _bool(got == c["equals"], f"{c['field']} = {got!r}")


def item_in_section(ev, c):
    if ev.out.minutes is None:
        return SKIP, "no minutes"
    own = _section_of(ev, c["match"])
    text = _gt_text(ev, c["match"])

    def found(section):
        if section == own:
            return c["match"] in ev.matches[section]
        items = ev.sys_minutes[section]
        texts = [i.get("task", "") if isinstance(i, dict) else i for i in items]
        return bool(texts) and max(ev.m.matrix([text], texts)[0]) >= ev.m.tau

    in_ok, out_ok = found(c["in"]), not found(c["not_in"])
    return _bool(in_ok and out_ok, f"in {c['in']}: {in_ok}; absent from {c['not_in']}: {out_ok}")


def agenda_budget(ev, c):
    if ev.out.proposed_items() is None:
        return SKIP, "no agenda"
    return _bool(*ev.budget_ok())


def metric_at_least(ev, c):
    metric = ev.metrics.get(c["metric"])
    if metric is None or metric.get("value") is None:
        return SKIP, f"{c['metric']} not available"
    return _bool(metric["value"] >= c["value"], f"{c['metric']} = {metric['value']:.3f}")


def _meeting_file(ev, path):
    if ev.out.meeting_dir is None:
        return None
    return ev.out.meeting_dir / path


def file_exists(ev, c):
    p = _meeting_file(ev, c["path"])
    if p is None:
        return SKIP, "no meeting_dir"
    return _bool(p.is_file(), "found" if p.is_file() else "missing")


def file_equals(ev, c):
    p = _meeting_file(ev, c["path"])
    sent = ev.out.sent.get(c["equals_sent"])
    if p is None or sent is None:
        return SKIP, "no meeting_dir or no sent text"
    if not p.is_file():
        return FAIL, "file missing"
    same = p.read_text(encoding="utf-8").strip() == sent.strip()
    return _bool(same, "identical" if same else "differs from the text sent")


def _doc(ev, c):
    if ev.out.docs is None:
        return None
    return ev.out.docs.get(c["file"])


def doc_text_contains(ev, c):
    text = _doc(ev, c)
    if text is None:
        return SKIP, "converted text not recorded"
    return _bool(c["text"] in text, "found" if c["text"] in text else "missing")


def doc_text_not_contains(ev, c):
    text = _doc(ev, c)
    if text is None:
        return SKIP, "converted text not recorded"
    return _bool(c["text"] not in text, "absent" if c["text"] not in text else "present")


def llm_prompt_contains(ev, c, negate=False):
    if ev.out.llm_calls is None:
        return SKIP, "LLM calls not recorded"
    prompts = [x.get("prompt", "") for x in ev.out.llm_calls if x.get("stage") == c["stage"]]
    if not prompts:
        return FAIL, f"no LLM call at stage {c['stage']}"
    hit = any(c["text"] in p for p in prompts)
    return _bool(hit != negate, "present" if hit else "absent")


def llm_prompt_not_contains(ev, c):
    return llm_prompt_contains(ev, c, negate=True)


def llm_fallback_used(ev, c):
    if ev.out.llm_calls is None:
        return SKIP, "LLM calls not recorded"
    used = any(x.get("fallback") for x in ev.out.llm_calls if x.get("stage") == c["stage"])
    return _bool(used, "fallback answered" if used else "fallback not used")


def audio_duration(ev, c):
    p = _meeting_file(ev, c["path"])
    if p is None or not p.is_file():
        return SKIP, "recording not available"
    with wave.open(str(p)) as w:
        seconds = w.getnframes() / w.getframerate()
    return _bool(abs(seconds - c["equals_s"]) <= c["tolerance_s"], f"{seconds:.1f} s")


def _events(ev, name):
    return [e for e in ev.out.events if e.get("event") == name]


def agenda_state(ev, c):
    match = ev.agenda_matches.get(c["match"])
    if match is None:
        return FAIL, f"{c['match']} not matched to a system agenda item"
    sys_id = ev.out.proposed_items()[match[0]].get("id")
    item = next((i for i in ev.out.final_items() if i.get("id") == sys_id), None)
    if item is None:
        return FAIL, f"agenda item {sys_id} was removed before the meeting"
    want = c["equals"] if isinstance(c["equals"], list) else [c["equals"]]
    return _bool(item.get("state") in want, f"state {item.get('state')}")


def state_change_within(ev, c):
    match = ev.agenda_matches.get(c["match"])
    if match is None:
        return FAIL, f"{c['match']} not matched to a system agenda item"
    sys_id = ev.out.proposed_items()[match[0]].get("id")
    gt = next(g for g in ev.sc.agenda["items"] if g["id"] == c["match"])
    start, end = gt["tracking"]["spans"][c.get("span", 0)]
    tol = c.get("tolerance_s", 30)
    times = [e["t_s"] for e in _events(ev, "agenda.item_state")
             if (e.get("data") or {}).get("item_id") == sys_id and (e.get("data") or {}).get("state") == c["to"]]
    ok = any(start - tol <= t <= end + tol for t in times)
    return _bool(ok, f"changes at {times}, window {start - tol:.0f}-{end + tol:.0f} s")


def no_event_between(ev, c):
    lo, hi = c.get("from_s"), c.get("to_s")
    bad = [e["t_s"] for e in _events(ev, c["event"])
           if (lo is None or e["t_s"] >= lo) and (hi is None or e["t_s"] <= hi)]
    return _bool(not bad, f"events at {bad}" if bad else "none")


def event_exists(ev, c):
    want = c.get("data") or {}
    ok = any(all((e.get("data") or {}).get(k) == v for k, v in want.items()) for e in _events(ev, c["event"]))
    return _bool(ok, "found" if ok else "not found")


CHECKS = {fn.__name__: fn for fn in (
    http_status, no_status, meeting_status, contains, not_contains, count_equals, count_range,
    count_similar, all_similar, action_item_field, agenda_item_field, item_in_section, agenda_budget,
    metric_at_least, file_exists, file_equals, doc_text_contains, doc_text_not_contains,
    llm_prompt_contains, llm_prompt_not_contains, llm_fallback_used, audio_duration, agenda_state,
    state_change_within, no_event_between, event_exists,
)}


def run_check(ev: Evaluation, c: dict) -> dict:
    live = c["type"] in LIVE_TYPES or str(c.get("case", "")).startswith("F")
    if live and ev.out.events is None:
        status, detail = TODO, "needs the live path (no live events recorded)"
    elif c["type"] not in CHECKS:
        status, detail = TODO, f"check type {c['type']} not supported by the harness"
    else:
        try:
            status, detail = CHECKS[c["type"]](ev, c)
        except Exception as exc:  # a broken check must not stop the report
            status, detail = FAIL, f"harness error: {type(exc).__name__}: {exc}"
    return {"id": c["id"], "case": c.get("case"), "type": c["type"], "status": status, "detail": detail}
