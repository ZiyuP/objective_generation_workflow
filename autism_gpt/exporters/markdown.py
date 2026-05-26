"""Export the approved system prompt to system_prompt.md."""
from __future__ import annotations

from pathlib import Path

from ..schemas import LessonPackage


def export(package: LessonPackage, output_path: str = "system_prompt.md") -> Path:
    out = Path(output_path)
    ss = package.session_script

    lines = [
        "# AutismGPT System Prompt",
        "",
        f"**Lesson:** {ss.lesson_title if ss else 'Unknown'}",
        f"**Lesson ID:** {ss.lesson_id if ss else 'Unknown'}",
        f"**Game:** {ss.game_name if ss else 'Word Mystery Game'}",
        "",
        "---",
        "",
        package.system_prompt or "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
