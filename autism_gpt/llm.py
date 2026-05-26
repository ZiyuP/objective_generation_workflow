"""Anthropic API wrapper with prompt caching support."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"
_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def load_template(name: str) -> str:
    path = Path(__file__).parent.parent / "templates" / name
    return path.read_text(encoding="utf-8")


def call_claude(
    messages: List[Dict[str, Any]],
    system: str,
    max_tokens: int = 4096,
    use_cache: bool = True,
) -> str:
    client = get_client()
    system_block: Any = (
        [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        if use_cache
        else system
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_block,
        messages=messages,
    )
    return response.content[0].text


def extract_json(text: str) -> Any:
    """Pull the first JSON object or array out of an LLM response."""
    # strip markdown fences
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fence:
        text = fence.group(1)
    # Find whichever of { or [ appears first — preserves array vs object intent
    pos_obj = text.find('{')
    pos_arr = text.find('[')
    if pos_obj == -1 and pos_arr == -1:
        raise ValueError(f"No JSON found in response:\n{text[:300]}")
    if pos_arr == -1 or (pos_obj != -1 and pos_obj < pos_arr):
        pairs = [('{', '}')]
    else:
        pairs = [('[', ']')]
    for start_char, end_char in pairs:
        start = text.find(start_char)
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    return json.loads(text[start : i + 1])
    raise ValueError(f"No JSON found in response:\n{text[:300]}")
