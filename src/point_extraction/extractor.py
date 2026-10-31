import json
import os
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from google import genai

def validate_chunks(chunks: list[dict]) -> list[dict]:
    """Validate chunk data, whether it comes from JSON or memory."""
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("Chunks must be a non-empty list.")

    valid_ids = set()

    for index, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict):
            raise ValueError(f"Chunk {index} must be a dictionary.")

        chunk_id = chunk.get("id")
        if not isinstance(chunk_id, int):
            raise ValueError(f"Chunk {index} must have an integer 'id'.")

        if chunk_id in valid_ids:
            raise ValueError(f"Duplicate chunk ID found: {chunk_id}.")
        valid_ids.add(chunk_id)

        if not isinstance(chunk.get("title"), str):
            raise ValueError(f"Chunk {chunk_id} must have a string 'title'.")

        if not isinstance(chunk.get("content"), str):
            raise ValueError(f"Chunk {chunk_id} must have a string 'content'.")

    return chunks


def load_chunks(chunks_path: str | Path) -> list[dict]:
    """Load and validate chunks from a JSON file."""
    chunks_path = Path(chunks_path)

    if not chunks_path.exists():
        raise FileNotFoundError(
            f"Chunk file was not found: {chunks_path}. "
            "Run the text_chunking module first."
        )

    try:
        chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Chunk file contains invalid JSON: {chunks_path}") from exc

    return validate_chunks(chunks)


def build_prompt(chunks: list[dict]) -> str:
    """Build an English prompt for Gemini to extract presentation points."""
    document = "\n\n".join(
        f"CHUNK ID: {chunk['id']}\n"
        f"TITLE: {chunk['title']}\n"
        f"CONTENT:\n{chunk['content']}"
        for chunk in chunks
    )

    return f"""
You are an information extraction assistant that prepares structured presentation points for a presentation progress tracking system.
Your task is to analyze the source document and extract a structured list of concepts and content that a presenter should explain during a presentation.
The extracted points will later be stored in a vector database and retrieved using semantic similarity against meeting transcripts. Therefore, every point must be clear, specific, and independently understandable.

TASK:
Read the source document and extract a structured list of presentation points, including main points and meaningful sub-points that can be tracked independently.

CORE EXTRACTION RULES:
1. Use only information explicitly supported by the source document.
2. Preserve the logical presentation order of the source.
3. Each point must represent a specific concept, piece of information, problem, mechanism, or explanation that the presenter needs to communicate.
4. Do not turn every sentence or bullet into a separate point.
5. Do not combine several independent concepts into one overly broad point.
6. If a point contains important steps, components, properties, or mechanisms that can be explained and tracked independently, create separate sub-points.
7. Each point should represent one coherent idea that can be meaningfully identified in a meeting transcript.
8. Preserve important technical details, terminology, relationships, examples, and complexity information from the source.

SEMANTIC SELF-CONTAINMENT RULES:
9. Every presentation point must be independently understandable, even when retrieved without its parent point, neighboring points, or original document structure.
10. TITLE:
    - Clearly identify the main subject, concept, or entity being discussed.
    - Include the relevant topic or technical concept whenever necessary to make the title understandable on its own.
    - Do not use vague or overly generic titles that only make sense within their parent section.
    - Prefer descriptive titles that communicate both the subject and the main idea.
    - Do not mechanically repeat the document title in every point if the title is already sufficiently clear.
    - However, explicitly include the subject's name when omitting it would make the title ambiguous.

    Example:
    Weak: "Motivation for Efficient Range Queries"
    Better: "Segment Tree: Motivation for Efficient Range Queries"
11. DESCRIPTION:
    - Explain the point clearly enough that someone can understand its meaning without reading the parent point or surrounding content.
    - Explicitly mention the relevant subject, concept, or technical entity instead of relying on implicit context.
    - Describe the actual idea, problem, mechanism, purpose, or information that the presenter needs to explain.
    - Include necessary background information from the source when it is required to understand the point.
    - Avoid vague references such as "this method", "the above concept", "it", or "this structure" when their meaning depends on surrounding points.
    - Do not simply repeat the title or produce a generic summary.
    - Preserve important relationships and technical details.
    - Keep the description informative and focused. Avoid unnecessary repetition or information that is not relevant to the point.
12. Do not rely on parent_title to provide essential context missing from title or description.
13. Assume that each point may be independently embedded, retrieved, and compared against a transcript excerpt by a RAG system. Its title and description must retain their meaning in isolation.

POINT HIERARCHY RULES:
14. Each sub-point must have parent_title equal to the exact title of its immediate parent point.
15. For top-level points, parent_title must be an empty string.
16. Do not use a section heading as parent_title unless that heading is itself represented as a parent point in the extracted list.
17. Keep parent_title exactly consistent with the title of the corresponding parent point.
18. If a parent point contains meaningful content that should be presented independently, include it as a separate point rather than using it only as a container for its sub-points.
19. A large heading that only labels a chapter does not need to become a separate point if it contains no independent content to explain.

SOURCE LINKING RULES:
20. Every point must include source_chunk_ids as an array of integer chunk IDs.
21. Include ALL chunks that substantively support the point.
22. If a point summarizes information from multiple chunks, include all relevant chunk IDs.
23. Do not link a chunk merely because it belongs to the same chapter or section.
24. Do not infer that a chunk supports a point unless its content is relevant.
25. Every source_chunk_id must exist in the provided source document.
26. Prefer the most specific chunks that support the point.

OTHER RULES:
27. Do not add knowledge, explanations, examples, or assumptions that are absent from the source document.
28. Do not generate point IDs or statuses. The Python code will assign them.
29. Write titles and descriptions in the same language as the source document. Preserve established technical terms in their commonly used form when appropriate.
30. Ensure that every extracted point is sufficiently specific to be distinguished from other points in the same document.
31. Do not omit important information simply because it appears in a short chunk.
32. Follow the required output schema exactly. Do not add extra fields or explanatory text outside the structured output.

SOURCE DOCUMENT:
{document}
""".strip()


def extract_points(
    chunks: list[dict] | str | Path | None = None,
    output_path: str | Path | None = None,
    coverage_path: str | Path | None = None,
    model: str = "gemini-3.8-flash",
    *,
    chunks_path: str | Path = "data/text_chunking.json",
) -> list[dict]:
    """Extract presentation points from in-memory chunks or a JSON file.

    Args:
        chunks: A list of chunks. A string/Path is also accepted as a
            positional shortcut for the JSON input path.
        output_path: Optional path for saving the generated points as JSON.
            The function always returns the points list, whether or not this
            path is provided.
        coverage_path: Optional path for saving the source-chunk coverage report.
        model: Gemini model name.
        chunks_path: JSON input path used when ``chunks`` is not provided.

    Returns:
        A list of extracted presentation points.
    """
    source_file = None

    # Support both direct list input and the previous JSON-file workflow.
    if isinstance(chunks, (str, Path)):
        source_file = str(chunks)
        chunks = load_chunks(chunks)
    elif chunks is None:
        source_file = str(chunks_path)
        chunks = load_chunks(chunks_path)
    else:
        chunks = validate_chunks(chunks)

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY was not found. Add it to your .env file."
        )

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

    output_data = {
        "source_file": source_file,
        "points": points,
    }

    # Build a report showing which source chunks are linked to points.
    if coverage_path is not None:
        # Build a report showing which source chunks are linked to points.
        chunk_to_points = defaultdict(list)

        for point in points:
            for chunk_id in point["source_chunk_ids"]:
                chunk_to_points[chunk_id].append(point["id"])

        coverage_report = {
            "source_file": source_file,
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

        coverage_path = Path(coverage_path)
        coverage_path.parent.mkdir(parents=True, exist_ok=True)
        
        coverage_path.write_text(
            json.dumps(coverage_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"Coverage report: {coverage_path}")


    # Save points to JSON only when output_path is provided.
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # These generated output files are overwritten on each run.
        output_path.write_text(
            json.dumps(output_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Points output: {output_path}")

    print("Point extraction completed.")
    print(f"Total points: {len(points)}")

    for point in points:
        print(
            f"\n{point['id']} | {point['status']}"
            f"\nTitle: {point['title']}"
            f"\nParent: {point['parent_title']}"
            f"\nSource chunks: {point['source_chunk_ids']}"
        )

    return points


if __name__ == "__main__":
    extract_points(
        chunks_path="data/text_chunking.json",
        output_path="data/presentation_points.json",
        coverage_path="data/source_coverage_report.json",
    )