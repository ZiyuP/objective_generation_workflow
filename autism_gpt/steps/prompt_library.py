"""Retrieve similar past prompts from the prompt library."""
from __future__ import annotations

from typing import List, Tuple, TYPE_CHECKING

from ..library_db import PromptLibraryDB

if TYPE_CHECKING:
    from ..schemas import SessionScript

_db = PromptLibraryDB()


def retrieve(session_script: "SessionScript", top_k: int = 3) -> Tuple[List[dict], bool]:
    """Retrieve similar prompts from the library.

    Returns (entries, is_fallback) where is_fallback=True when falling back
    to sample prompts because the user library is empty.
    """
    query_tokens: set = set(
        session_script.skill_type.lower().split()
        + session_script.activity_format.lower().split()
        + session_script.lesson_title.lower().split()
    )

    if _db.is_empty():
        # Fall back to sample prompts
        samples = _db.get_fallback_samples()
        if not samples:
            return ([], False)

        # Score samples using "skill" and "tags" fields (sample schema)
        def score_sample(entry: dict) -> int:
            entry_tokens = set(
                entry.get("skill", "").lower().split()
                + " ".join(entry.get("tags", [])).lower().split()
            )
            return len(query_tokens & entry_tokens)

        scored = [(score_sample(e), e) for e in samples]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [e for _, e in scored[:top_k]]
        return (top, True)

    # DB is not empty — use db.search
    entries = _db.search(query_tokens, top_k)
    return (entries, False)
