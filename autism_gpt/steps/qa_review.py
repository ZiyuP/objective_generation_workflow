"""QA checklist for the full vocabulary lesson package."""
from __future__ import annotations

from typing import Any, Dict, List

from ..llm import call_claude, extract_json, load_template
from ..schemas import LessonPackage, QACheckItem, QAReview

_SYSTEM = load_template("agent_system.txt")


def run(package: LessonPackage, history: List[Dict[str, Any]]) -> QAReview:
    scenarios_json = (
        "[" + ",".join(s.model_dump_json() for s in package.scenarios) + "]"
    )
    images_json = (
        "[" + ",".join(img.model_dump_json() for img in package.scenario_images) + "]"
    )
    lesson_id = package.session_script.lesson_id if package.session_script else "unknown"

    user_msg = load_template("qa_review.txt").format(
        system_prompt=package.system_prompt or "",
        scenarios_json=scenarios_json,
        images_json=images_json,
        lesson_id=lesson_id,
    )
    messages = history + [{"role": "user", "content": user_msg}]
    raw = call_claude(messages, _SYSTEM, max_tokens=3000)
    data = extract_json(raw)

    def _items(lst: list) -> List[QACheckItem]:
        return [QACheckItem(**it) for it in lst]

    return QAReview(
        lesson_id=data.get("lesson_id", lesson_id),
        prompt_quality=_items(data.get("prompt_quality", [])),
        scenario_clarity=_items(data.get("scenario_clarity", [])),
        image_scenario_match=_items(data.get("image_scenario_match", [])),
        description_length=_items(data.get("description_length", [])),
        tool_use_rules=_items(data.get("tool_use_rules", [])),
        overall_pass=data.get("overall_pass", False),
        reviewer_notes=data.get("reviewer_notes", ""),
    )
