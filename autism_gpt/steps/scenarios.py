"""Generate practice scenarios, image prompts, and child descriptions."""
from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING

from ..llm import call_claude, extract_json, load_template
from ..schemas import LessonScenario, ScenarioImage

if TYPE_CHECKING:
    from ..schemas import SessionScript

_SYSTEM = load_template("agent_system.txt")


def create_scenarios(
    session_script: "SessionScript",
    history: List[Dict[str, Any]],
    count: int = 6,
) -> List[LessonScenario]:
    """Generate practice scenarios adapted to the lesson's activity format."""
    user_msg = load_template("scenario_create.txt").format(
        session_json=session_script.model_dump_json(indent=2),
        count=count,
    )
    messages = history + [{"role": "user", "content": user_msg}]
    raw = call_claude(messages, _SYSTEM, max_tokens=4096)
    data = extract_json(raw)
    items = data if isinstance(data, list) else data.get("scenarios", list(data.values())[0])
    return [LessonScenario(**s) for s in items]


def create_scenario_images(
    scenarios: List[LessonScenario],
    session_script: "SessionScript",
    history: List[Dict[str, Any]],
) -> List[ScenarioImage]:
    """Generate image prompts and child-friendly descriptions for each scenario."""
    scenarios_json = "[" + ",".join(s.model_dump_json() for s in scenarios) + "]"
    user_msg = load_template("image_create.txt").format(
        scenarios_json=scenarios_json,
        activity_format=session_script.activity_format,
        topic_summary=session_script.topic_summary,
    )
    messages = history + [{"role": "user", "content": user_msg}]
    raw = call_claude(messages, _SYSTEM, max_tokens=4096)
    data = extract_json(raw)
    items = data if isinstance(data, list) else data.get("scenario_images", list(data.values())[0])
    return [ScenarioImage(**img) for img in items]
