"""Step 1 – Draft and refine the Objective Brief."""
from __future__ import annotations

from typing import Any, Dict, List

from ..llm import call_claude, extract_json, load_template
from ..schemas import ObjectiveBrief

_SYSTEM = load_template("agent_system.txt")


def draft(idea: str, history: List[Dict[str, Any]]) -> ObjectiveBrief:
    user_msg = load_template("objective_draft.txt").format(idea=idea)
    messages = history + [{"role": "user", "content": user_msg}]
    raw = call_claude(messages, _SYSTEM)
    data = extract_json(raw)
    return ObjectiveBrief(**data)


def revise(
    current: ObjectiveBrief,
    feedback: str,
    history: List[Dict[str, Any]],
) -> ObjectiveBrief:
    user_msg = load_template("objective_revise.txt").format(
        current_json=current.model_dump_json(indent=2),
        feedback=feedback,
    )
    messages = history + [{"role": "user", "content": user_msg}]
    raw = call_claude(messages, _SYSTEM)
    data = extract_json(raw)
    return ObjectiveBrief(**data)
