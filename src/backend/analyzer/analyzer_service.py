import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

from google import genai
from google.genai import types
from pydantic import ValidationError

from .schemas import (
    ContentCategory,
    ExtractedEntity,
    ResolutionStatus,
    TopicBreakdown,
    TranscriptAnalysisPayload,
)

DEFAULT_MODEL_ID = "gemini-3.8-flash"
LOW_TEMPERATURE = 0.1

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ContentAnalyzer")


@dataclass(frozen=True)
class AuditedItem:
    # Why: Using an immutable dataclass ensures validated records cannot be
    # accidentally mutated during downstream Markdown or JSON serialization.
    category: ContentCategory
    summary: str
    speaker: str
    assignee: str
    due_date: str
    status: ResolutionStatus
    audit_notes: str
    evidence_quote: str


class MeetingContentAnalyzer:
    def __init__(
        self,
        api_key: str | None = None,
        model_id: str = DEFAULT_MODEL_ID,
    ) -> None:
        # Why: Supporting constructor injection alongside environment variables
        # enables automated unit testing and multi-model benchmarking without code changes.
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "Missing GEMINI_API_KEY. Set it as an environment variable or pass it explicitly."
            )
        self._client = genai.Client(api_key=resolved_key)
        self._model_id = model_id

    def extract_semantics_via_api(self, transcript_text: str) -> TranscriptAnalysisPayload:
        if not transcript_text or not transcript_text.strip():
            raise ValueError("Input transcript cannot be empty.")

        # Why: Temperature is locked at 0.1 to suppress generative creativity and force
        # strict adherence to verbatim facts present in the transcript.
        system_instruction = (
            "You are an enterprise-grade Meeting Intelligence Analyzer. "
            "Analyze the provided meeting transcript (which may contain English, Vietnamese, "
            "or bilingual code-switching) and output all structured fields strictly in English.\n"
            "Rules:\n"
            "1. Segment the conversation into logical Topics (Section 1, Section 2...) "
            "and summarize key points under each topic.\n"
            "2. Classify notable statements into MAIN_CONTENT, DEADLINE, or IDEA. "
            "Classify any actionable task or assignment directed to an individual as DEADLINE, "
            "even if the deadline/timeframe is unspecified or missing (set due_date to null).\n"
            "3. Never fabricate assignees or deadlines. Leave them null if not explicitly stated."
        )

        logger.info("Sending transcript payload to %s...", self._model_id)
        response = self._client.models.generate_content(
            model=self._model_id,
            contents=transcript_text,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=LOW_TEMPERATURE,
                response_mime_type="application/json",
                response_schema=TranscriptAnalysisPayload,
            ),
        )

        try:
            return TranscriptAnalysisPayload.model_validate_json(response.text)
        except ValidationError as exc:
            logger.error("Schema validation failed on LLM output: %s", exc)
            raise

    def _evaluate_completeness_rules(self, entity: ExtractedEntity) -> AuditedItem:
        # Why: LLMs frequently treat casual mentions of tasks as finalized commitments.
        # This deterministic O(1) Python rule check enforces strict accountability constraints
        # before any item can be marked as CONFIRMED.
        violations: List[str] = []

        if not entity.has_consensus:
            violations.append("Lacks explicit team consensus (tentative/deferred)")

        if entity.category == ContentCategory.DEADLINE:
            if not entity.assignee:
                violations.append("Missing owner (unassigned task)")
            if not entity.due_date:
                violations.append("Missing target deadline")

        status = (
            ResolutionStatus.UNCONFIRMED
            if violations
            else ResolutionStatus.CONFIRMED
        )
        audit_notes = (
            "; ".join(violations)
            if violations
            else "Complete and verified against transcript"
        )

        return AuditedItem(
            category=entity.category,
            summary=entity.summary,
            speaker=entity.speaker or "Unspecified",
            assignee=entity.assignee or "Unassigned",
            due_date=entity.due_date or "TBD",
            status=status,
            audit_notes=audit_notes,
            evidence_quote=entity.evidence_quote,
        )

    def analyze_from_file(
        self,
        input_file_path: str | Path,
        markdown_out_path: str | Path = "meeting_analysis_report.md",
        json_out_path: str | Path = "meeting_analysis_data.json",
    ) -> Dict:
        # Why: Decoupling file I/O from core analysis logic allows the service
        # to process both external text files and in-memory streams seamlessly.
        in_path = Path(input_file_path)
        if not in_path.exists() or not in_path.is_file():
            raise FileNotFoundError(f"Input transcript file not found: {in_path.resolve()}")

        logger.info("Reading transcript from file: %s", in_path.resolve())
        transcript_text = in_path.read_text(encoding="utf-8")

        return self.analyze_and_export(
            transcript_text=transcript_text,
            markdown_out_path=markdown_out_path,
            json_out_path=json_out_path,
        )

    def analyze_and_export(
        self,
        transcript_text: str,
        markdown_out_path: str | Path = "meeting_analysis_report.md",
        json_out_path: str | Path = "meeting_analysis_data.json",
    ) -> Dict:
        raw_payload = self.extract_semantics_via_api(transcript_text)

        logger.info("Running Python rule-based validation loop over %d entities...", len(raw_payload.entities))
        audited_items: List[AuditedItem] = [
            self._evaluate_completeness_rules(item) for item in raw_payload.entities
        ]

        markdown_report = self._build_markdown_report(
            raw_payload.executive_summary,
            raw_payload.topics,
            audited_items,
        )

        md_path = Path(markdown_out_path)
        md_path.write_text(markdown_report, encoding="utf-8")
        logger.info("Markdown report exported to: %s", md_path.resolve())

        # Why: Exporting a structured JSON artifact alongside the human-readable Markdown
        # ensures future compatibility when integrating with external UI modules later.
        structured_export = {
            "model_used": self._model_id,
            "executive_summary": raw_payload.executive_summary,
            "topics": [topic.model_dump() for topic in raw_payload.topics],
            "audited_entities": [asdict(item) for item in audited_items],
        }
        json_path = Path(json_out_path)
        json_path.write_text(
            json.dumps(structured_export, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Structured JSON exported to: %s", json_path.resolve())

        return structured_export

    def _build_markdown_report(
        self,
        executive_summary: str,
        topics: List[TopicBreakdown],
        audited_items: List[AuditedItem],
    ) -> str:
        # Why: Partitioning items into a hash map keyed by ContentCategory enables O(1)
        # group retrieval when rendering distinct report sections.
        buckets: Dict[ContentCategory, List[AuditedItem]] = {
            ContentCategory.MAIN_CONTENT: [],
            ContentCategory.DEADLINE: [],
            ContentCategory.IDEA: [],
        }
        for item in audited_items:
            buckets[item.category].append(item)

        lines: List[str] = [
            "# MEETING INTELLIGENCE — CONTENT ANALYSIS & SUMMARY REPORT",
            "",
            "## 1. EXECUTIVE SUMMARY",
            f"> {executive_summary}",
            "",
            "## 2. HIERARCHICAL TOPIC BREAKDOWN",
        ]

        for topic in topics:
            lines.append(f"### {topic.section_id}: {topic.title}")
            for idx, point in enumerate(topic.key_points):
                point_label = chr(65 + idx)
                lines.append(f"- **Point {point_label}:** {point}")
            lines.append("")

        lines.extend([
            "## 3. CATEGORIZED ENTITIES & PYTHON VALIDATION AUDIT",
            "",
            "### 3.1. Main Discussion Content (`[MAIN_CONTENT]`)",
        ])
        for item in buckets[ContentCategory.MAIN_CONTENT]:
            badge = "[CONFIRMED]" if item.status == ResolutionStatus.CONFIRMED else "[UNCONFIRMED]"
            lines.append(
                f"- **{badge}** {item.summary}  \n"
                f"  *Audit:* {item.audit_notes} | *Evidence:* \"{item.evidence_quote}\""
            )

        lines.extend([
            "",
            "### 3.2. Action Items & Deadlines (`[DEADLINE]`)",
            "| Action Item / Task | Assignee | Deadline | Status | Python Validation Audit |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])
        for item in buckets[ContentCategory.DEADLINE]:
            badge = "CONFIRMED" if item.status == ResolutionStatus.CONFIRMED else "UNCONFIRMED"
            lines.append(
                f"| {item.summary} | {item.assignee} | {item.due_date} | **{badge}** | {item.audit_notes} |"
            )

        lines.extend([
            "",
            "### 3.3. Ideas & Proposals (`[IDEA]`)",
        ])
        for item in buckets[ContentCategory.IDEA]:
            badge = "[ADOPTED]" if item.status == ResolutionStatus.CONFIRMED else "[OPEN PROPOSAL]"
            lines.append(
                f"- **{badge}** *(Proposed by: {item.speaker})* - {item.summary}  \n"
                f"  *Audit:* {item.audit_notes} | *Evidence:* \"{item.evidence_quote}\""
            )

        return "\n".join(lines)
    