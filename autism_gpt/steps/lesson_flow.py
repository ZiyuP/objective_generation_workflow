"""Generate and revise the teaching approach + session script (Step 2)."""
from __future__ import annotations

from typing import Any, Dict, List

from ..llm import call_claude, extract_json, load_template
from ..schemas import DialogLine, SessionRound, SessionScript

_SYSTEM = load_template("agent_system.txt")


def draft(idea: str, history: List[Dict[str, Any]]) -> SessionScript:
    user_msg = load_template("lesson_flow_draft.txt").format(idea=idea)
    messages = history + [{"role": "user", "content": user_msg}]
    raw = call_claude(messages, _SYSTEM, max_tokens=4096)
    return _parse(extract_json(raw))


def revise(
    current: SessionScript,
    feedback: str,
    history: List[Dict[str, Any]],
) -> SessionScript:
    user_msg = load_template("lesson_flow_revise.txt").format(
        current_json=current.model_dump_json(indent=2),
        feedback=feedback,
    )
    messages = history + [{"role": "user", "content": user_msg}]
    raw = call_claude(messages, _SYSTEM, max_tokens=4096)
    return _parse(extract_json(raw))


def _parse(data: dict) -> SessionScript:
    def _lines(raw: list) -> List[DialogLine]:
        return [DialogLine(**l) for l in raw]

    rounds = [
        SessionRound(
            round_number=r["round_number"],
            round_label=r["round_label"],
            dialog=_lines(r["dialog"]),
        )
        for r in data["rounds"]
    ]
    return SessionScript(
        lesson_id=data["lesson_id"],
        lesson_title=data["lesson_title"],
        skill_type=data.get("skill_type", ""),
        activity_format=data.get("activity_format", ""),
        teaching_rationale=data.get("teaching_rationale", ""),
        topic_summary=data.get("topic_summary", ""),
        intro=_lines(data.get("intro", [])),
        rounds=rounds,
    )
