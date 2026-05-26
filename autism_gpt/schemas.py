"""Pydantic schemas for AutismGPT lesson creation — topic-agnostic."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class DialogLine(BaseModel):
    speaker: str        # "Nessa" | "Child"  (or whatever the script uses)
    text: str
    is_action: bool = False   # True for function calls like show_rewards()


class SessionRound(BaseModel):
    round_number: int
    round_label: str    # e.g. "Child needs both hints"
    dialog: List[DialogLine]


class SessionScript(BaseModel):
    lesson_id: str
    lesson_title: str
    skill_type: str           # e.g. "social communication", "vocabulary", "emotional regulation"
    activity_format: str      # e.g. "Question Practice", "Word Mystery Game", "Emotion Detective"
    teaching_rationale: str   # why this approach fits the topic and autism
    topic_summary: str        # one sentence: what the child is learning
    intro: List[DialogLine]
    rounds: List[SessionRound]


class LessonScenario(BaseModel):
    scenario_id: str
    lesson_id: str
    title: str
    setup: str                        # what is shown/described to the child
    nessa_prompt: str                 # exactly what Nessa asks
    target_response: str              # what a good response looks like
    small_hint: str                   # indirect / sensory / analogical
    big_hint: str                     # more explicit
    example_correct_response: str     # a concrete perfect answer
    difficulty: str                   # beginner | intermediate | advanced
    tags: List[str] = Field(default_factory=list)


class ScenarioImage(BaseModel):
    scenario_id: str
    image_prompt: str
    style: str
    key_elements: List[str]
    child_description: str    # ≤15 words, starts with "In this picture…"
    color_palette: Optional[str] = None


class QACheckItem(BaseModel):
    category: str
    item: str
    status: str    # pass | fail | warning
    notes: str


class QAReview(BaseModel):
    lesson_id: str
    prompt_quality: List[QACheckItem]
    scenario_clarity: List[QACheckItem]
    image_scenario_match: List[QACheckItem]
    description_length: List[QACheckItem]
    tool_use_rules: List[QACheckItem]
    overall_pass: bool
    reviewer_notes: str


class LessonPackage(BaseModel):
    session_script: Optional[SessionScript] = None
    system_prompt: Optional[str] = None
    scenarios: List[LessonScenario] = Field(default_factory=list)
    scenario_images: List[ScenarioImage] = Field(default_factory=list)
    qa_review: Optional[QAReview] = None
