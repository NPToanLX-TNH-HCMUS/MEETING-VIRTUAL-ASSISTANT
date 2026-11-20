"""Create the bad upload files of scenario S11 (special case A7).

    python tests/e2e_eval/scripts/make_s11_files.py

broken.pdf   random bytes with a .pdf name           -> expected 415 UNSUPPORTED_FILE_TYPE
slides.pptx  a real PowerPoint file (type not allowed) -> expected 415 UNSUPPORTED_FILE_TYPE
large.txt    11 MB of text                            -> expected 413 FILE_TOO_LARGE

The files are generated (not stored in the repository) so that the repository stays small; the
random bytes use a fixed seed, so every run gives the same files.
"""

import random
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "scenarios" / "S11_meetingbank_badfiles_en" / "inputs" / "docs"


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    rng = random.Random(11)
    (DOCS / "broken.pdf").write_bytes(bytes(rng.getrandbits(8) for _ in range(20_000)))

    from pptx import Presentation  # python-pptx
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Budget briefing"
    slide.placeholders[1].text = "Mayor's proposed 2017 budget: sidewalks and pedestrian infrastructure"
    deck.save(DOCS / "slides.pptx")

    line = "Denver City Council public comment log, line {:06d}: no comment recorded.\n"
    n = 11 * 1024 * 1024 // len(line.format(0)) + 1
    (DOCS / "large.txt").write_text("".join(line.format(i) for i in range(n)), encoding="utf-8")
    for p in sorted(DOCS.iterdir()):
        print(f"{p.name}: {p.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
