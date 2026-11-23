"""Text normalisation shared by every metric and check.

Rules (ANNOTATION_GUIDE.md, section 1, "Scoring normalisation"):
lower case; diacritics removed; punctuation removed; contractions expanded;
fillers ("um", "uh", "er", "hmm", "mm-hmm") removed; [inaudible] and other
bracket tags removed; numbers written in words and in digits treated as equal
(both become digits); a decimal point is not a word ("two point five", "2.5"
and "twelve fifty", "12.50" give the same tokens); British and American
spellings, and a few words written as one or two words ("kick-off" /
"kickoff"), treated as equal.
"""

import re
import unicodedata

FILLERS = {"um", "uh", "er", "erm", "uhm", "hmm", "mm", "mhm", "mmhmm", "hm"}

INFORMAL = {"gonna": "going to", "wanna": "want to", "gotta": "got to", "kinda": "kind of", "ok": "okay",
            "dunno": "do not know", "whoohoo": "woohoo"}

# British spellings (AMI annotation) and American spellings (most speech-to-text output) are equal.
SPELLING = {
    "colour": "color", "colours": "colors", "coloured": "colored", "favour": "favor",
    "favourite": "favorite", "behaviour": "behavior", "humour": "humor", "labour": "labor",
    "neighbour": "neighbor", "fulfil": "fulfill", "fulfils": "fulfills", "centre": "center",
    "centres": "centers", "metre": "meter", "metres": "meters", "centimetre": "centimeter",
    "centimetres": "centimeters", "litre": "liter", "programme": "program", "programmes": "programs",
    "catalogue": "catalog", "dialogue": "dialog", "grey": "gray", "licence": "license",
    "practise": "practice", "defence": "defense", "travelling": "traveling", "travelled": "traveled",
    "cancelled": "canceled", "cancelling": "canceling", "modelling": "modeling", "labelled": "labeled",
    "organise": "organize", "organised": "organized", "organisation": "organization",
    "realise": "realize", "realised": "realized", "recognise": "recognize", "recognised": "recognized",
    "prioritise": "prioritize", "prioritised": "prioritized", "summarise": "summarize",
    "summarised": "summarized", "finalise": "finalize", "finalised": "finalized",
    "apologise": "apologize", "analyse": "analyze", "analysed": "analyzed", "minimise": "minimize",
    "maximise": "maximize", "customise": "customize", "emphasise": "emphasize",
}

# Words written as one or two words depending on the writer.
COMPOUNDS = {("kick", "off"): "kickoff", ("all", "right"): "alright", ("e", "mail"): "email",
             ("any", "more"): "anymore", ("on", "line"): "online", ("set", "up"): "setup",
             ("width", "wise"): "widthwise", ("height", "wise"): "heightwise",
             ("straight", "forward"): "straightforward", ("home", "page"): "homepage",
             ("woo", "hoo"): "woohoo"}

PRONOUN_IS = {"it", "that", "what", "there", "here", "he", "she", "who", "where", "how"}

UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
SCALES = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}

STOPWORDS = set(
    """a an the and or but if of to in on at by for with from as is are was were be been
    being it its this that these those there here we you they he she i me my our your their
    his her them us will would shall should can could may might must do does did done have
    has had not no so than then too very just also about into over under up down out off
    again what which who whom when where why how all any each both some such only own same
    other more most let lets get got going go one okay ok yeah yes right well like really
    actually think know mean thing things""".split()
)

_TAG = re.compile(r"\[[^\]]*\]")
_LABEL = re.compile(r"^\s*\[[^\]]*\]\s*(?:[^:\n]{1,40}:\s*)?")
_SPEAKER_ONLY = re.compile(r"^\s*[A-Za-z][\w .\-]{0,30}:\s*$")


def strip_transcript_labels(text: str) -> str:
    """Remove '[mm:ss] SPEAKER:' prefixes and lines that only name a speaker."""
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith("["):
            line = _LABEL.sub("", line, count=1)
        elif _SPEAKER_ONLY.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def _expand_contractions(text: str) -> str:
    text = re.sub(r"\bwon't\b", "will not", text)
    text = re.sub(r"\bcan't\b", "can not", text)
    text = re.sub(r"\bcannot\b", "can not", text)
    text = re.sub(r"\blet's\b", "let us", text)
    text = re.sub(r"n't\b", " not", text)
    text = re.sub(r"'re\b", " are", text)
    text = re.sub(r"'m\b", " am", text)
    text = re.sub(r"'ll\b", " will", text)
    text = re.sub(r"'ve\b", " have", text)
    text = re.sub(r"'d\b", " would", text)
    text = re.sub(
        r"\b(" + "|".join(PRONOUN_IS) + r")'s\b", lambda m: m.group(1) + " is", text
    )
    return text


def _numbers_to_digits(tokens: list[str]) -> list[str]:
    out, i = [], 0
    while i < len(tokens):
        if not (tokens[i] in UNITS or tokens[i] in TENS or tokens[i].isdigit()):
            out.append(tokens[i])
            i += 1
            continue
        total = current = 0
        last = None
        j = i
        while j < len(tokens):
            w = tokens[j]
            if w in UNITS:
                if last in ("unit", "digit") or (last == "tens" and UNITS[w] >= 10):
                    break
                current += UNITS[w]
                last = "unit"
            elif w in TENS:
                if last in ("unit", "tens", "digit"):
                    break
                current += TENS[w]
                last = "tens"
            elif w.isdigit():
                if last is not None:
                    break
                current += int(w)
                last = "digit"
            elif w == "hundred" and last in ("unit", "digit"):
                current *= 100
                last = "hundred"
            elif (
                w == "and"
                and last == "hundred"
                and j + 1 < len(tokens)
                and (tokens[j + 1] in UNITS or tokens[j + 1] in TENS)
            ):
                pass  # "one hundred and five"
            elif w in SCALES and last in ("unit", "tens", "digit", "hundred"):
                total += current * SCALES[w]
                current = 0
                last = "scale"
            else:
                break
            j += 1
        out.append(str(total + current))
        i = j
    return out


def tokens(text: str) -> list[str]:
    """Normalised word tokens of a text."""
    if not text:
        return []
    text = _TAG.sub(" ", text)
    text = _strip_accents(text).lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = _expand_contractions(text)
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # 50,000,000 -> 50000000
    text = text.replace("%", " percent ").replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)  # remaining apostrophes, punctuation
    words = []
    for w in text.split():
        for part in INFORMAL.get(w, w).split():
            if part not in FILLERS:
                words.append(SPELLING.get(part, part))
    merged = []
    for w in words:
        if merged and (merged[-1], w) in COMPOUNDS:
            merged[-1] = COMPOUNDS[(merged[-1], w)]
        else:
            merged.append(w)
    digits = _numbers_to_digits(merged)
    # "2.5" loses its dot with the punctuation; drop the spoken "point" as well.
    return [w for k, w in enumerate(digits)
            if not (w == "point" and k + 1 < len(digits) and digits[k + 1].isdigit())]


def normalize(text: str) -> str:
    return " ".join(tokens(text))


def contains_phrase(text: str, phrase: str) -> bool:
    """Whole-word phrase search after normalisation."""
    return phrase_in(normalize(text), phrase)


def phrase_in(normalized_text: str, phrase: str) -> bool:
    """Same as contains_phrase, for a text normalised once and searched many times."""
    p = normalize(phrase)
    return bool(p) and f" {p} " in f" {normalized_text} "


def _stem(w: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


def content_words(text: str) -> set[str]:
    """Stemmed tokens without stopwords: used by the lexical matcher."""
    return {_stem(w) for w in tokens(text) if w not in STOPWORDS}
