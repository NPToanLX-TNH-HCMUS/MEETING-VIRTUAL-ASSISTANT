import json
from pathlib import Path


def clean_heading(line: str) -> str:
    """Remove Markdown heading markers and optional closing markers."""
    heading = line.strip()
    heading = heading.lstrip("#").strip()
    heading = heading.rstrip("#").strip()
    return heading


def chunk_markdown(
    input_path: str | Path = "data/segment_tree.md",
    output_path: str | Path | None = None,
) -> list[dict]:
    """
    Split a Markdown document into chunks using level-2 headings (##).

    Each chunk contains a numeric ID, a plain-text title, and its content.
    The level-1 heading (#) is retained as parent context without Markdown markers.
    """
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input Markdown file was not found: {input_path}")

    content = input_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    chunks = []
    current_parent = ""
    current_heading = ""
    current_chunk = []

    def save_chunk():
        if current_heading and current_chunk:
            chunk_content = "\n".join(current_chunk).strip()
            if chunk_content:
                chunks.append({
                    "id": len(chunks) + 1,
                    "title": current_heading,
                    "content": chunk_content,
                })

    for line in lines:
        stripped = line.strip()

        # Level-1 heading: store it as parent context.
        if stripped.startswith("# ") and not stripped.startswith("## "):
            save_chunk()
            current_chunk = []
            current_parent = clean_heading(stripped)
            current_heading = ""

        # Level-2 heading: start a new chunk.
        elif stripped.startswith("## "):
            save_chunk()
            current_heading = clean_heading(stripped)
            current_chunk = []

            if current_parent:
                current_chunk.append(current_parent)

            current_chunk.append(current_heading)

        # Keep content only when a level-2 heading is active.
        elif current_heading:
            current_chunk.append(line)

    save_chunk()

    if not chunks:
        raise ValueError(
            "No chunks were created. Check that the Markdown file contains "
            "level-2 headings (##) with content."
        )

    print(f"Chunking completed. Total chunks: {len(chunks)}")

# Save chunks to JSON only when output_path is provided.
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(
            json.dumps(chunks, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"Output file: {output_path}")
    return chunks


if __name__ == "__main__":
    chunk_markdown()
