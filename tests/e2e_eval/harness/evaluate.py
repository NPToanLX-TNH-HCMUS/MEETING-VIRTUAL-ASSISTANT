"""Compute the metrics of one scenario run (TR, MN, AG, SY) and keep the matches for the checks."""

import re

from data import RunOutputs, Scenario
from metrics import (Matcher, assign, cer, entity_recall, prf, quote_grounded, wer,
                     word_coverage)
from textnorm import content_words, normalize, phrase_in, strip_transcript_labels, tokens

SECTIONS = ("action_items", "decisions", "unresolved_issues")
TRANSCRIBE_STEPS = ("transcribe", "retry:E5")
EMPTY_NAMES = {"", "none", "null", "unknown", "n a", "na", "unassigned", "tbd"}


def _required(item: dict) -> bool:
    return not item.get("optional", False) and item.get("required", True)


class Evaluation:
    def __init__(self, scenario: Scenario, out: RunOutputs, matcher: Matcher):
        self.sc, self.out, self.m = scenario, out, matcher
        self.metrics: dict = {}
        self.notes: list[str] = []
        self.matches: dict = {}  # section -> {gt_id: (sys_index, sim)}
        self.agenda_matches: dict = {}  # gt agenda id -> (sys_index, sim)
        self.sys_transcript = strip_transcript_labels(out.transcript) if out.transcript is not None else None
        self.gt_transcript = strip_transcript_labels(scenario.transcript or "")
        self._transcript()
        self._minutes()
        self._agenda()
        self._system()

    # ------------------------------------------------------------ helpers

    def canonical_person(self, name) -> str | None:
        """Map a name, role or alias to the person's key in scenario.json "aliases".

        An exact alias wins; otherwise the longest alias found inside the name
        ("Tom (tester)" -> Tom). Unknown names are returned normalised.
        """
        if name is None:
            return None
        n = normalize(str(name))
        if n in EMPTY_NAMES:
            return None
        forms = [(normalize(f), normalize(role)) for role, fs in (self.sc.spec.get("aliases") or {}).items()
                 for f in [role, *fs]]
        for form, role in forms:
            if form == n:
                return role
        inside = [(len(form), role) for form, role in forms if form and phrase_in(n, form)]
        return max(inside)[1] if inside else n

    @staticmethod
    def canonical_date(value) -> str | None:
        if value is None:
            return None
        m = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
        return m.group() if m else (None if normalize(str(value)) in EMPTY_NAMES else str(value).strip())

    def _forced(self, section: str, gt_items: list[dict], sys_texts: list[str]) -> dict:
        """Manual decisions from adjudication.json: {"decisions": [{"gt": "D1", "system": "...", "match": true}]}."""
        forced = {}
        gt_index = {g["id"]: i for i, g in enumerate(gt_items)}
        sys_index = {normalize(t): j for j, t in enumerate(sys_texts)}
        for d in self.sc.adjudication.get(section, []):
            i, j = gt_index.get(d.get("gt")), sys_index.get(normalize(d.get("system", "")))
            if i is not None and j is not None:
                forced[(i, j)] = bool(d.get("match"))
        return forced

    # ------------------------------------------------------------ transcript

    def _transcript(self):
        if self.sys_transcript is None:
            self.notes.append("no system transcript: TR metrics skipped")
            return
        self.metrics["TR1"] = wer(self.gt_transcript, self.sys_transcript)
        if self.metrics["TR1"]["ref_words"] == 0 and self.metrics["TR1"]["hyp_words"]:
            self.notes.append(f"the meeting has no speech but the transcript has "
                              f"{self.metrics['TR1']['hyp_words']} words")
        self.metrics["TR2"] = cer(self.gt_transcript, self.sys_transcript)
        self.metrics["TR3"] = entity_recall(self.sc.spec.get("key_entities", []), self.sys_transcript)
        for entry in self.out.api_log or []:
            if (entry.get("step") in TRANSCRIBE_STEPS and entry.get("status") == 200
                    and entry.get("elapsed_s") and self.sc.audio_seconds):
                self.metrics["TR4"] = {"value": entry["elapsed_s"] / self.sc.audio_seconds}

    # ------------------------------------------------------------ minutes

    def _minutes(self):
        sysm = self.out.minutes_lists()
        gt = self.sc.minutes
        if sysm is None:
            self.notes.append("no system minutes: MN metrics skipped")
            return
        self.sys_minutes = sysm

        for section in SECTIONS:
            gt_items = gt.get(section, [])
            if section == "action_items":
                sys_items = sysm["action_items"]
                sys_texts = [str(a.get("task", "")) for a in sys_items]
                task_sim = self.m.matrix([g["task"] for g in gt_items], sys_texts)
                quote_sim = self.m.matrix([g.get("quote", "") for g in gt_items],
                                          [str(a.get("quote", "") or "") for a in sys_items])
                # Two tasks can come from the same sentence, so the quote only lifts the task similarity.
                sim = [[max(t, (t + q) / 2) for t, q in zip(tr, qr)] for tr, qr in zip(task_sim, quote_sim)]
            else:
                sys_texts = sysm[section]
                sim = self.m.matrix([g["text"] for g in gt_items], sys_texts)
            pairs = assign(sim, self.m.tau, self._forced(section, gt_items, sys_texts))
            self.matches[section] = {gt_items[i]["id"]: (j, s) for i, (j, s) in pairs.items()}
            n_req = sum(_required(g) for g in gt_items)
            hit_req = sum(_required(gt_items[i]) for i in pairs)
            key = {"action_items": "MN1", "decisions": "MN5", "unresolved_issues": "MN6"}[section]
            self.metrics[key] = prf(len(pairs), len(sys_texts), hit_req, n_req)

        # MN2 / MN3 / MN4: fields of matched action items
        gt_ai = {g["id"]: g for g in gt.get("action_items", [])}
        ok_assignee = ok_due = 0
        strict_sys = strict_req = 0
        details = []
        for gid, (j, _) in self.matches["action_items"].items():
            g, s = gt_ai[gid], sysm["action_items"][j]
            a_ok = self.canonical_person(g.get("assignee")) == self.canonical_person(s.get("assignee"))
            d_ok = self.canonical_date(g.get("due")) == self.canonical_date(s.get("due"))
            ok_assignee += a_ok
            ok_due += d_ok
            if a_ok and d_ok:
                strict_sys += 1
                strict_req += _required(g)
            details.append({"gt": gid, "system": s.get("task"), "assignee_ok": a_ok, "due_ok": d_ok,
                            "gt_assignee": g.get("assignee"), "sys_assignee": s.get("assignee"),
                            "gt_due": g.get("due"), "sys_due": s.get("due")})
        n_matched = len(self.matches["action_items"])
        self.metrics["MN2"] = {"value": ok_assignee / n_matched if n_matched else None}
        self.metrics["MN3"] = {"value": ok_due / n_matched if n_matched else None}
        n_req = sum(_required(g) for g in gt_ai.values())
        self.metrics["MN4"] = prf(strict_sys, len(sysm["action_items"]), strict_req, n_req)
        self.metrics["MN4"]["pairs"] = details

        # MN7: sections that are empty in the ground truth must stay empty
        considered = correct = 0
        for section in SECTIONS:
            if sum(_required(g) for g in gt.get(section, [])) == 0:
                considered += 1
                unmatched = len(sysm[section]) - len(self.matches[section])
                correct += unmatched == 0
        self.metrics["MN7"] = {"value": correct / considered if considered else None,
                               "sections": considered}

        # MN8: action-item quotes found in the transcript the system worked from
        basis = tokens(self.sys_transcript if self.sys_transcript is not None else self.gt_transcript)
        quotes = [str(a.get("quote") or "") for a in sysm["action_items"]]
        grounded = [q for q in quotes if quote_grounded(q, basis)]
        self.metrics["MN8"] = {"value": len(grounded) / len(quotes) if quotes else None,
                               "not_found": [q for q in quotes if q not in grounded]}

        # MN9: unmatched system items that resemble no ground-truth item (not even at half the
        # threshold) and whose content words are mostly absent from the meeting
        gt_words = content_words(self.gt_transcript)
        gt_texts = [g.get("text") or g.get("task", "") for s in SECTIONS for g in gt.get(s, [])]
        gt_texts += [p["text"] for p in gt.get("summary_points", [])]
        halluc = []
        for section in SECTIONS:
            used = {j for j, _ in self.matches[section].values()}
            for j, item in enumerate(sysm[section]):
                if j in used:
                    continue
                text = item.get("task", "") if isinstance(item, dict) else item
                near = max(self.m.matrix([text], gt_texts)[0], default=0.0) >= self.m.tau / 2
                if not near and word_coverage(text, gt_words) < 0.5:
                    halluc.append({"section": section, "text": text})
        self.metrics["MN9"] = {"value": len(halluc), "items": halluc}

        # MN10: summary key points covered by the summary
        points = gt.get("summary_points", [])
        summary = sysm["summary"]
        covered = []
        if self.m.kind == "embed" and points and summary:
            sentences = [s for s in re.split(r"(?<=[.!?])\s+", summary) if s.strip()]
            sim = self.m.matrix([p["text"] for p in points], sentences)
            covered = [p["id"] for p, row in zip(points, sim) if max(row) >= self.m.tau]
        else:
            words = content_words(summary)
            for p in points:
                pw = content_words(p["text"])
                if pw and len(pw & words) / len(pw) >= 0.5:
                    covered.append(p["id"])
        self.metrics["MN10"] = {"value": len(covered) / len(points) if points else None,
                                "missing": [p["id"] for p in points if p["id"] not in covered]}

        # MN11: forbidden content anywhere in the minutes
        text = normalize(self.minutes_text())
        hits = [f["id"] for f in gt.get("must_not_appear", [])
                if any(phrase_in(text, k) for k in f.get("keywords", []))]
        self.metrics["MN11"] = {"value": len(hits), "items": hits}

    def minutes_text(self) -> str:
        m = self.sys_minutes
        parts = [m["markdown"], m["summary"], *m["decisions"], *m["unresolved_issues"]]
        for a in m["action_items"]:
            parts += [str(a.get("task", "")), str(a.get("quote", "") or "")]
        return "\n".join(parts)

    # ------------------------------------------------------------ agenda

    def _agenda(self):
        items = self.out.proposed_items()
        gt = self.sc.agenda
        if items is None or not gt:
            if items is None:
                self.notes.append("no system agenda: AG metrics skipped")
            return
        gt_items = gt.get("items", [])
        titles = [str(i.get("title", "")) for i in items]
        sim = self.m.matrix([g["title"] for g in gt_items], titles)
        pairs = assign(sim, self.m.tau, self._forced("agenda", gt_items, titles))
        self.agenda_matches = {gt_items[i]["id"]: (j, s) for i, (j, s) in pairs.items()}
        n_req = sum(_required(g) for g in gt_items)
        hit_req = sum(_required(gt_items[i]) for i in pairs)
        res = prf(len(pairs), len(titles), hit_req, n_req)
        self.metrics["AG1"] = {"value": res["recall"], **res}
        self.metrics["AG2"] = {"value": res["precision"]}
        text = normalize("\n".join(f"{i.get('title', '')} {i.get('description') or ''}" for i in items))
        forbidden = [x["id"] for x in gt.get("must_not_include", [])
                     if any(phrase_in(text, k) for k in x.get("keywords", []))]
        self.metrics["AG3"] = {"value": len(forbidden), "items": forbidden}
        carry = gt.get("carry_over", [])
        if carry:
            found = [c for c in carry if c in self.agenda_matches]
            self.metrics["AG4"] = {"value": len(found) / len(carry),
                                   "missing": [c for c in carry if c not in found]}
        ok, detail = self.budget_ok()
        self.metrics["AG5"] = {"value": float(ok), "detail": detail}

    def budget_ok(self) -> tuple[bool, str]:
        items = self.out.proposed_items() or []
        duration = (self.sc.spec.get("meeting") or {}).get("duration_minutes")
        minutes = [i.get("estimated_minutes") or 0 for i in items]
        problems = []
        if duration is not None and sum(minutes) > duration:
            problems.append(f"total {sum(minutes)} > {duration} min")
        if any(m < 1 for m in minutes):
            problems.append("an item has less than 1 minute")
        dropped = self.out.dropped()
        if dropped and any(d.get("reason") != "exceeds_remaining_time" for d in dropped):
            problems.append("a dropped item has another reason")
        return (not problems, "; ".join(problems) or f"total {sum(minutes)} / {duration} min")

    # ------------------------------------------------------------ system

    def _system(self):
        if self.out.stages is not None:
            self.metrics["SY1"] = {"value": float(self.out.stages.get("end") == "archived")}
        if self.out.api_log:
            limited = [e["step"] for e in self.out.api_log if e["step"].startswith("rate_limited:")]
            if limited:
                self.notes.append(f"LLM rate limit, called again after a wait: {', '.join(limited)}")
            down = [e["step"] for e in self.out.api_log if e.get("code") == "LLM_UNAVAILABLE"
                    and not e["step"].startswith(("fault:", "rate_limited:"))]
            if down:
                self.notes.append(f"LLM unavailable at {', '.join(down)}: results of this scenario are "
                                  "incomplete, run it again")
            per_step: dict = {}
            for e in self.out.api_log:
                if e.get("elapsed_s") is not None:
                    per_step[e["step"]] = round(per_step.get(e["step"], 0.0) + e["elapsed_s"], 3)
            self.metrics["SY3"] = {"value": None, "per_step_s": per_step}
