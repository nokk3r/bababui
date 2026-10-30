"""Сообщения бэкенда: наружу уходит ключ, текст лежит в static/locales."""

from __future__ import annotations

import json
import re
from functools import lru_cache

from app.config import STATIC_DIR

MARKER = re.compile(r"\[\[([a-z0-9_]+)(?:\|(\{.*?\}))?\]\]")


def msg(key: str, **params) -> str:
    """Маркер вместо текста. Он переживает базу и склейку строк, язык выбирает браузер."""
    if not params:
        return f"[[{key}]]"
    return f"[[{key}|{json.dumps(params, ensure_ascii=False)}]]"


@lru_cache(maxsize=1)
def _source() -> dict[str, str]:
    return json.loads((STATIC_DIR / "locales" / "en.json").read_text(encoding="utf-8"))


def render(text: str) -> str:
    """Английский текст для мест без браузера: CSV и логи."""

    def replace(match: re.Match) -> str:
        template = _source().get(f"server.{match[1]}")
        if template is None:
            return match[0]
        try:
            params = json.loads(match[2]) if match[2] else {}
        except ValueError:
            return match[0]
        for name, value in params.items():
            template = template.replace(f"{{{name}}}", str(value))
        return template

    return MARKER.sub(replace, text or "")
