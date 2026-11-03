from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class ContentCategory(str, Enum):
    MAIN_CONTENT = "MAIN_CONTENT"
    DEADLINE = "DEADLINE"
    IDEA = "IDEA"

class ResolutionStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"

class TopicBreakdown(BaseModel):
    section_id: str = Field(description= "Sequential topic identifier (e.g., 'Section 1', 'Section 2').")
    title: str = Field(description= "Consise title summarizing the discussion topic.")
    key_points: List[str] = Field(description= "List of core takeaways discussed under this topic (mapped to A, B, C).")

class ExtractedEntity(BaseModel):
    category: ContentCategory = Field(description="Classification label: MAIN_CONTENT, DEADLINE, or IDEA.")
    summary: str = Field(description="Concise, actionable summary of the statement, task, or idea.")
    speaker: Optional[str] = Field(default=None, description="Name of the participant who initiated the statement, if identifiable.")
    assignee: Optional[str] = Field(default=None, description="Participant explicitly assigned to execute the task (MUST be null if unassigned).")
    due_date: Optional[str] = Field(default=None, description="Explicit deadline or target timeframe mentioned in the transcript.")
    has_consensus: bool = Field(description="True if the group explicitly agreed on this item; False if tentative or deferred.")
    evidence_quote: str = Field(description="Verbatim quote from the transcript serving as provenance evidence.")

class TranscriptAnalysisPayload(BaseModel):
    executive_summary: str = Field(description="High-level 2-to-3 sentence overview of the entire meeting segment.")
    topics: List[TopicBreakdown] = Field(description="Chronological breakdown of discussion topics and key points.")
    entities: List[ExtractedEntity] = Field(description="Extracted items categorized into MAIN_CONTENT, DEADLINE, and IDEA.")

