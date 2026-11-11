"""Загрузчик локалей ru/en + хелпер t()."""

import json
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).resolve().parent / "locales"

_cache: dict[str, dict[str, str]] = {}


def _load(lang: str) -> dict[str, str]:
    if lang not in _cache:
        path = LOCALES_DIR / f"{lang}.json"
        try:
            _cache[lang] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _cache[lang] = {}
    return _cache[lang]


def t(lang: str, key: str, **kwargs: Any) -> str:
    template = _load(lang).get(key) or _load("en").get(key) or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template
    return template


def detect_lang(language_code: str | None) -> str:
    return "ru" if (language_code or "").lower().startswith("ru") else "en"
