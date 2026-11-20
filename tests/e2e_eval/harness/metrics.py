"""Metric building blocks: edit distance, WER / CER, entity recall, item matching, P / R / F1."""

import json
import math
import re
import urllib.request

from textnorm import content_words, normalize, phrase_in, tokens


# ---------------------------------------------------------------- edit distance


def levenshtein(a, b) -> int:
    """Edit distance between two sequences (Myers / Hyyrö bit-parallel algorithm)."""
    if len(a) < len(b):
        a, b = b, a
    m = len(a)
    if m == 0:
        return len(b)
    if not b:
        return m
    peq: dict = {}
    for i, c in enumerate(a):
        peq[c] = peq.get(c, 0) | (1 << i)
    mask = (1 << m) - 1
    high = 1 << (m - 1)
    pv, mv, score = mask, 0, m
    for c in b:
        eq = peq.get(c, 0)
        xv = eq | mv
        xh = ((((eq & pv) + pv) & mask) ^ pv) | eq
        ph = mv | (~(xh | pv) & mask)
        mh = pv & xh
        if ph & high:
            score += 1
        elif mh & high:
            score -= 1
        ph = ((ph << 1) | 1) & mask
        mh = (mh << 1) & mask
        pv = mh | (~(xv | ph) & mask)
        mv = ph & xv
    return score


def wer(reference: str, hypothesis: str) -> dict:
    ref, hyp = tokens(reference), tokens(hypothesis)
    d = levenshtein(ref, hyp)
    return {"errors": d, "ref_words": len(ref), "hyp_words": len(hyp),
            "value": (d / len(ref)) if ref else (0.0 if not hyp else None)}


def cer(reference: str, hypothesis: str) -> dict:
    ref, hyp = " ".join(tokens(reference)), " ".join(tokens(hypothesis))
    d = levenshtein(ref, hyp)
    return {"errors": d, "ref_chars": len(ref),
            "value": (d / len(ref)) if ref else (0.0 if not hyp else None)}


def entity_recall(entities: list[dict], hypothesis: str) -> dict:
    """TR3: share of key entities (or one of their alternatives) found in the transcript."""
    found, missing = [], []
    hyp = normalize(hypothesis)
    for e in entities:
        forms = [e["text"], *e.get("alts", [])]
        (found if any(phrase_in(hyp, f) for f in forms) else missing).append(e["text"])
    n = len(entities)
    return {"value": (len(found) / n) if n else None, "found": found, "missing": missing}


def quote_grounded(quote: str, transcript_tokens: list[str], min_ratio: float = 0.8) -> bool:
    """MN8: the quote appears in the transcript, allowing a few word errors.

    A quote made of fragments joined by "..." is grounded when every fragment is.
    """
    fragments = [f for f in re.split(r"\.{3,}|\u2026", quote) if tokens(f)]
    if len(fragments) > 1:
        return all(_fragment_grounded(f, transcript_tokens, min_ratio) for f in fragments)
    return _fragment_grounded(quote, transcript_tokens, min_ratio)


def _fragment_grounded(quote: str, transcript_tokens: list[str], min_ratio: float) -> bool:
    q = tokens(quote)
    if not q or not transcript_tokens:
        return False
    if f" {' '.join(q)} " in f" {' '.join(transcript_tokens)} ":
        return True
    n = len(q)
    slack = max(1, n // 5)  # the transcript may have a few extra or missing words
    for size in range(max(1, n - slack), n + slack + 1):
        for start in range(0, max(1, len(transcript_tokens) - size + 1)):
            window = transcript_tokens[start:start + size]
            if 1 - levenshtein(q, window) / n >= min_ratio:
                return True
    return False


def word_coverage(text: str, reference_tokens: set[str]) -> float:
    """Share of the content words of a text that occur in a reference (used for MN9)."""
    words = content_words(text)
    if not words:
        return 1.0
    ref = {w for w in reference_tokens}
    return len([w for w in words if w in ref]) / len(words)


# ---------------------------------------------------------------- matching


class Matcher:
    """Similarity between a ground-truth item and a system item.

    lexical: Dice coefficient of stemmed content words (no extra package needed).
    embed:   cosine similarity of embeddings from the team's embedding server
             (the same EMBED_URL used by the semantic chunker).
    The threshold tau is calibrated on the first baseline run; manual decisions go
    into ground_truth/adjudication.json.
    """

    DEFAULT_TAU = {"lexical": 0.35, "embed": 0.75}

    def __init__(self, kind: str = "lexical", tau: float | None = None, embed_url: str | None = None):
        self.kind = kind
        self.tau = tau if tau is not None else self.DEFAULT_TAU[kind]
        self.embed_url = embed_url
        self._cache: dict[str, list[float]] = {}

    def _embed(self, texts: list[str]) -> None:
        todo = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if not todo:
            return
        req = urllib.request.Request(
            f"{self.embed_url.rstrip('/')}/embed",
            data=json.dumps({"texts": todo, "is_query": False}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            vectors = json.load(r)["embeddings"]
        self._cache.update(zip(todo, vectors))

    def matrix(self, gt_texts: list[str], sys_texts: list[str]) -> list[list[float]]:
        if self.kind == "embed":
            self._embed(gt_texts + sys_texts)
            return [[_cosine(self._cache[g], self._cache[s]) for s in sys_texts] for g in gt_texts]
        gw = [content_words(g) for g in gt_texts]
        sw = [content_words(s) for s in sys_texts]
        return [[_dice(a, b) for b in sw] for a in gw]

    def sim(self, a: str, b: str) -> float:
        return self.matrix([a], [b])[0][0]


def _dice(a: set, b: set) -> float:
    return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0.0


def _cosine(u, v) -> float:
    dot = sum(x * y for x, y in zip(u, v))
    nu = math.sqrt(sum(x * x for x in u))
    nv = math.sqrt(sum(y * y for y in v))
    return dot / (nu * nv) if nu and nv else 0.0


def assign(sim: list[list[float]], tau: float, forced: dict | None = None) -> dict[int, tuple[int, float]]:
    """One-to-one assignment, highest similarity first. Returns {gt_index: (sys_index, similarity)}.

    forced: {(gt_index, sys_index): True | False} from adjudication.json.
    """
    forced = forced or {}
    pairs = []
    for i, row in enumerate(sim):
        for j, s in enumerate(row):
            decision = forced.get((i, j))
            if decision is True:
                pairs.append((2.0, i, j))  # manual match beats every automatic one
            elif decision is None and s >= tau:
                pairs.append((s, i, j))
    pairs.sort(reverse=True)
    used_gt, used_sys, result = set(), set(), {}
    for s, i, j in pairs:
        if i in used_gt or j in used_sys:
            continue
        used_gt.add(i)
        used_sys.add(j)
        result[i] = (j, min(s, 1.0))
    return result


def prf(sys_matched: int, n_sys: int, gt_matched_required: int, n_required: int) -> dict:
    """P / R / F1 with optional ground-truth items: they count as hits but never as misses."""
    p = sys_matched / n_sys if n_sys else None
    r = gt_matched_required / n_required if n_required else None
    if p is not None and r is not None:
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    elif n_sys == 0 and n_required > 0:
        f1 = 0.0
    else:
        f1 = None
    return {"value": f1, "precision": p, "recall": r, "f1": f1, "tp_sys": sys_matched, "n_sys": n_sys,
            "tp_gt": gt_matched_required, "n_gt": n_required}
