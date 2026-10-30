import json
import os
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from google import genai


def load_chunks(chunks_path: str | Path) -> list[dict]:
    """Load chunks produced by the text_chunking module."""
    chunks_path = Path(chunks_path)

    if not chunks_path.exists():
        raise FileNotFoundError(
            f"Chunk file was not found: {chunks_path}. "
            "Run the text_chunking module first."
        )

    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))

    if not isinstance(chunks, list) or not chunks:
        raise ValueError("The chunk file is empty or has an invalid format.")

    valid_ids = set()
    for chunk in chunks:
        chunk_id = chunk.get("id")
        if not isinstance(chunk_id, int):
            raise ValueError("Every chunk must have an integer 'id'.")
        valid_ids.add(chunk_id)

    return chunks


def build_prompt(chunks: list[dict]) -> str:
    """Build an English prompt for Gemini to extract presentation points."""
    document = "\n\n".join(
        f"CHUNK ID: {chunk['id']}\n"
        f"TITLE: {chunk['title']}\n"
        f"CONTENT:\n{chunk['content']}"
        for chunk in chunks
    )

    return f"""
You are an assistant that helps track presentation progress.

TASK:
Read the source document and extract a structured list of points that should
be presented. Include main points and meaningful sub-points that can be
tracked independently.

RULES:
1. Use only information explicitly supported by the source document.
2. Preserve the logical presentation order of the source.
3. Each point must describe a specific concept or piece of content that
   the presenter needs to explain.
4. Do not turn every sentence or bullet into a separate point.
5. Do not combine several independent concepts into one overly broad point.
6. If a point contains important steps or components that can be explained
   independently, create separate sub-points.
7. Each sub-point must have parent_title equal to its parent's title.
   For top-level points, parent_title must be an empty string.

SOURCE LINKING RULES:
8. Every point must include source_chunk_ids as an array of integer chunk IDs.
9. Include ALL chunks that substantively support the point.
10. If a point summarizes information from multiple chunks, include all
    relevant chunk IDs.
11. Do not link a chunk merely because it belongs to the same chapter.
12. Do not infer that a chunk supports a point unless its content is relevant.
13. Every source_chunk_id must exist in the provided document.
14. Prefer the most specific chunks that support the point.

OTHER RULES:
15. Do not add knowledge that is absent from the source document.
16. Do not generate point IDs or statuses; the Python code will assign them.
17. Keep parent_title exactly consistent with the title of the parent point.
18. A large heading that only labels a chapter does not need to become a
    separate point if it contains no independent content to explain.
19. Do not overlook important information simply because it appears in a
    short chunk.

SOURCE DOCUMENT:
{document}
""".strip()


def extract_points(
    chunks_path: str | Path = "data/text_chunking.json",
    output_path: str | Path = "data/presentation_points.json",
    coverage_path: str | Path = "data/source_coverage_report.json",
    model: str = "gemini-3.8-flash",
) -> dict:
    """Use Gemini to extract presentation points and validate source links."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY was not found. Add it to your .env file."
        )

    chunks = load_chunks(chunks_path)
    client = genai.Client(api_key=api_key)
    prompt = build_prompt(chunks)

    schema = {
        "type": "object",
        "properties": {
            "points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "parent_title": {"type": "string"},
                        "source_chunk_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": [
                        "title",
                        "description",
                        "parent_title",
                        "source_chunk_ids",
                    ],
                },
            },
        },
        "required": ["points"],
    }

    print("Starting Gemini API request...", flush=True)

    response = client.interactions.create(
        model=model,
        input=prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": schema,
        },
    )

    print("Gemini API response received!", flush=True)

    try:
        result = json.loads(response.output_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Gemini returned an invalid JSON response.") from exc

    points = result.get("points", [])
    if not points:
        raise ValueError("Gemini did not return any presentation points.")

    chunk_by_id = {chunk["id"]: chunk for chunk in chunks}
    valid_chunk_ids = set(chunk_by_id)

    # Validate points and their source references before assigning IDs.
    for index, point in enumerate(points, start=1):
        title = point.get("title", "").strip()
        description = point.get("description", "").strip()
        parent_title = point.get("parent_title", "")
        source_ids = point.get("source_chunk_ids")

        if not title:
            raise ValueError(f"Point {index} has no title.")

        if not description:
            raise ValueError(f"Point {index} has no description.")

        if not isinstance(parent_title, str):
            raise ValueError(f"Point {index} has an invalid parent_title.")

        if not isinstance(source_ids, list) or not source_ids:
            raise ValueError(
                f"Point {index} has no valid source_chunk_ids: {title}"
            )

        if any(not isinstance(chunk_id, int) for chunk_id in source_ids):
            raise ValueError(
                f"Point {index} contains a non-integer chunk ID: {title}"
            )

        if len(source_ids) != len(set(source_ids)):
            raise ValueError(f"Point {index} contains duplicate chunk IDs.")

        invalid_ids = [
            chunk_id for chunk_id in source_ids
            if chunk_id not in valid_chunk_ids
        ]
        if invalid_ids:
            raise ValueError(
                f"Point '{title}' references unknown chunk IDs: {invalid_ids}"
            )

        # Normalize whitespace in fields returned by the model.
        point["title"] = title
        point["description"] = description
        point["parent_title"] = parent_title.strip()
        point["source_chunk_ids"] = source_ids

    # Assign numeric point IDs and initial statuses.
    for point_id, point in enumerate(points, start=1):
        point["id"] = point_id
        point["status"] = "pending"

    # Resolve parent IDs by matching parent titles to earlier points.
    previous_points_by_title = defaultdict(list)

    for point in points:
        parent_title = point["parent_title"]

        if not parent_title:
            point["parent_id"] = None
        else:
            possible_parents = previous_points_by_title.get(parent_title, [])
            if not possible_parents:
                raise ValueError(
                    f"Parent point '{parent_title}' was not found for "
                    f"point '{point['title']}'. Check the hierarchy or "
                    "parent_title returned by Gemini."
                )
            point["parent_id"] = possible_parents[-1]["id"]

        previous_points_by_title[point["title"]].append(point)

    # Build a report showing which source chunks are linked to points.
    chunk_to_points = defaultdict(list)
    for point in points:
        for chunk_id in point["source_chunk_ids"]:
            chunk_to_points[chunk_id].append(point["id"])

    coverage_report = {
        "source_file": str(chunks_path),
        "total_chunks": len(chunks),
        "total_points": len(points),
        "covered_chunks": 0,
        "uncovered_chunks": [],
        "chunks": [],
    }

    for chunk in chunks:
        linked_points = chunk_to_points.get(chunk["id"], [])
        is_covered = bool(linked_points)

        if is_covered:
            coverage_report["covered_chunks"] += 1
        else:
            coverage_report["uncovered_chunks"].append(chunk["id"])

        coverage_report["chunks"].append({
            "chunk_id": chunk["id"],
            "title": chunk["title"],
            "covered": is_covered,
            "point_ids": linked_points,
        })

    output_path = Path(output_path)
    coverage_path = Path(coverage_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "source_file": str(chunks_path),
        "points": points,
    }

    # These generated output files are overwritten on each run.
    output_path.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    coverage_path.write_text(
        json.dumps(coverage_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Point extraction completed.")
    print(f"Total points: {len(points)}")
    print(f"Points output: {output_path}")
    print(f"Coverage report: {coverage_path}")

    for point in points:
        print(
            f"\n{point['id']} | {point['status']}"
            f"\nTitle: {point['title']}"
            f"\nParent: {point['parent_title']}"
            f"\nSource chunks: {point['source_chunk_ids']}"
        )

    return output_data


if __name__ == "__main__":
    extract_points()
