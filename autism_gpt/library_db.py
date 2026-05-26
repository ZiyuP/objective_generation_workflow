"""Persistent JSON-backed prompt library database."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set

_DEFAULT_PATH = Path(__file__).parent.parent / "data" / "prompt_library" / "prompts.json"
_SAMPLE_PATH = Path(__file__).parent / "prompt_library" / "sample_prompts.json"


def _now() -> str:
    """Return current UTC time as 'YYYY-MM-DD HH:MM UTC'."""
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _parse_tags(tags) -> List[str]:
    """Handle both 'tag1, tag2' string and list input."""
    if tags is None:
        return []
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    return [str(t).strip() for t in tags if str(t).strip()]


class PromptLibraryDB:
    """Persistent JSON-backed prompt library."""

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load(self) -> List[dict]:
        """Read JSON from file every call (no in-memory caching)."""
        try:
            text = self.path.read_text(encoding="utf-8").strip()
            if not text:
                return []
            return json.loads(text)
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, entries: List[dict]) -> None:
        """Write JSON to file."""
        self.path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_all(self) -> List[dict]:
        """Return all prompt entries."""
        return self._load()

    def get_by_id(self, id: str) -> Optional[dict]:
        """Return entry with matching id, or None."""
        for entry in self._load():
            if entry.get("id") == id:
                return entry
        return None

    def add(self, entry: dict) -> dict:
        """Add a new entry; generate id and timestamps, normalize tags."""
        entries = self._load()
        now = _now()
        new_entry = {
            "id": uuid.uuid4().hex[:8],
            "title": entry.get("title", ""),
            "objective_type": entry.get("objective_type", ""),
            "skill_type": entry.get("skill_type", ""),
            "tags": _parse_tags(entry.get("tags", [])),
            "notes": entry.get("notes", ""),
            "system_prompt": entry.get("system_prompt", ""),
            "created_at": now,
            "updated_at": now,
        }
        entries.append(new_entry)
        self._save(entries)
        return new_entry

    def update(self, id: str, updates: dict) -> Optional[dict]:
        """Update fields of entry with given id; set updated_at."""
        entries = self._load()
        for i, entry in enumerate(entries):
            if entry.get("id") == id:
                for key, value in updates.items():
                    if key == "tags":
                        entries[i]["tags"] = _parse_tags(value)
                    elif key not in ("id", "created_at"):
                        entries[i][key] = value
                entries[i]["updated_at"] = _now()
                self._save(entries)
                return entries[i]
        return None

    def delete(self, id: str) -> bool:
        """Delete entry with given id. Returns True if deleted."""
        entries = self._load()
        new_entries = [e for e in entries if e.get("id") != id]
        if len(new_entries) == len(entries):
            return False
        self._save(new_entries)
        return True

    def bulk_add(self, entries: List[dict]) -> List[dict]:
        """Add multiple entries at once."""
        added = []
        for entry in entries:
            added.append(self.add(entry))
        return added

    def search(self, query_tokens: Set[str], top_k: int = 3) -> List[dict]:
        """Score entries by token overlap; if nothing scores > 0 return first top_k entries."""
        entries = self._load()
        if not entries:
            return []

        def score_entry(entry: dict) -> int:
            entry_text = " ".join([
                entry.get("title", ""),
                entry.get("skill_type", ""),
                entry.get("objective_type", ""),
                " ".join(entry.get("tags", [])),
            ]).lower()
            entry_tokens = set(entry_text.split())
            lower_query = {t.lower() for t in query_tokens}
            return len(lower_query & entry_tokens)

        scored = [(score_entry(e), e) for e in entries]
        scored.sort(key=lambda x: x[0], reverse=True)

        best_score = scored[0][0] if scored else 0
        if best_score > 0:
            return [e for s, e in scored[:top_k] if s > 0]
        # Nothing scored > 0, return first top_k entries
        return [e for _, e in scored[:top_k]]

    def is_empty(self) -> bool:
        """Return True if no entries exist."""
        return len(self._load()) == 0

    def get_fallback_samples(self) -> List[dict]:
        """Load sample_prompts.json and add _is_fallback=True to each entry."""
        try:
            text = _SAMPLE_PATH.read_text(encoding="utf-8")
            samples = json.loads(text)
            return [{**entry, "_is_fallback": True} for entry in samples]
        except Exception:
            return []
