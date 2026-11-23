import json
from pathlib import Path


def append_summary_history(summary_dir, revision, text, created_at):
    summary_dir = Path(summary_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)

    path = summary_dir / "summary_history.json"

    if path.exists():
        history = json.loads(path.read_text(encoding="utf-8"))

        if not isinstance(history, list):
            raise ValueError("Summary history must be a list.")
    else:
        history = []

    entry = {
        "revision": revision,
        "created_at": created_at,
        "text": text,
    }

    history.append(entry)

    temporary_path = summary_dir / "summary_history.tmp"
    temporary_path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)

    return entry