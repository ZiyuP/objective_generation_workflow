"""Create and revise the AutismGPT system prompt for the lesson."""
from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING

from ..llm import call_claude, load_template

if TYPE_CHECKING:
    from ..schemas import SessionScript

_SYSTEM = load_template("agent_system.txt")


def _format_library_entries(entries: List[dict]) -> str:
    if not entries:
        return "No similar prompts found in library."
    lines = []
    for i, e in enumerate(entries, 1):
        lines.append(f"--- Example {i}: {e.get('title', 'Untitled')} ---")
        lines.append(e.get("system_prompt", ""))
        lines.append("")
    return "\n".join(lines)


def draft(
    session_script: "SessionScript",
    library_entries: List[dict],
    history: List[Dict[str, Any]],
) -> str:
    user_msg = load_template("system_prompt_create.txt").format(
        session_json=session_script.model_dump_json(indent=2),
        library_examples=_format_library_entries(library_entries),
    )
    messages = history + [{"role": "user", "content": user_msg}]
    return call_claude(messages, _SYSTEM, max_tokens=2048)


def revise(
    current_prompt: str,
    feedback: str,
    history: List[Dict[str, Any]],
) -> str:
    user_msg = load_template("system_prompt_revise.txt").format(
        current_prompt=current_prompt,
        feedback=feedback,
    )
    messages = history + [{"role": "user", "content": user_msg}]
    return call_claude(messages, _SYSTEM, max_tokens=2048)
