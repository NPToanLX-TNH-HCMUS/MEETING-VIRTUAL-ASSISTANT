import json
import re

from pydantic import BaseModel, ValidationError
from .llm import LLMCallError

from ...api.objects import Topics, Topic


def parse_json_list_to_list_of_string(text: str) -> list[str]:
    """Parse a JSON list or recover items from a plain-text response."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return [str(item).strip() for item in result if str(item).strip()]
    except json.JSONDecodeError:
        pass

    items = re.findall(r'"([^"]+)"', cleaned)
    if items:
        return items

    return [
        re.sub(r"^\d+[\.\)]\s*", "", line).strip()
        for line in cleaned.splitlines()
        if line.strip() and not line.strip().startswith(("[", "]"))
    ]

def parse_topics(reply: str, planned_points: list[str], documents: list[dict], duration_minutes: int) -> list[dict]:
    """Model reply (JSON text) -> [{"title", "description", "source", "estimated_minutes"}, ...]."""
    reply = reply.strip()
    if reply.startswith("```"):  # some models wrap the JSON in a ```json fence
        reply = reply.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(reply)
        while isinstance(data, dict) and isinstance(data.get("items"), dict):  # {"items": {"items": [...]}}
            data = data["items"]
        if isinstance(data, dict) and "title" in data:  # one bare item {"title": ..., "source": ...}
            data = [data]
        elif isinstance(data, dict) and "items" not in data:  # list under another key, e.g. {"topics": [...]}
            lists = [v for v in data.values() if isinstance(v, list)]
            data = lists[0] if len(lists) == 1 else data
        if isinstance(data, list):  # a bare [...] list
            data = {"items": data}
        topics = Topics.model_validate(data)
    except (ValueError, ValidationError) as e:
        raise LLMCallError(422, "LLM_BAD_OUTPUT", f"The model did not return the expected JSON: {reply[:200]!r}") from e

    # A small model often mislabels `source`; with only one kind of input there is nothing to decide.
    only_source = "document" if not planned_points else "planned_point" if not documents else None
    items = [
        {"title": t.title.strip(), "description": None, "source": only_source or t.source,
         "estimated_minutes": max(1, t.minutes) if t.minutes else None}
        for t in topics.items
        if t.title.strip()
    ]

    # The prompt asks the model to fit the meeting length; if it did not, shrink every time in proportion.
    total = sum(i["estimated_minutes"] or 0 for i in items)
    if total > duration_minutes:
        for i in items:
            if i["estimated_minutes"]:
                i["estimated_minutes"] = max(1, i["estimated_minutes"] * duration_minutes // total)
    return items