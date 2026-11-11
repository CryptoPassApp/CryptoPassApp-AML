"""Детектор флеш/фейк-токенов в кошельке (TON jettons).

«Флеш-токен» — джеттон, притворяющийся крупным стейблкоином (USD₮/USDC),
выпущенный СКОРИМ ОТ НАСТОЯЩЕГО мастером: в кошельке выглядит как баланс,
продать нельзя (нет ликвидности на DEX). Проверка детерминированная:

* у настоящего USDT на TON один конкретный мастер-контракт;
* TonAPI маркирует каждый джеттон верификацией whitelist/graylist/none/blacklist;
* скамеры обфусцируют символ: нулевые символы (U+200B..), RTL-оверврайты
  ('\u202eTDSU' = USDT задом наперёд), омоглифы (кириллическая Ѕ вместо S,
  греческая Τ вместо T), tag-символы (U+E0000..). Нормализация снимает это.

Пустой блоклист не нужен: поля verification + сравнение мастеров работают
без каких-либо списков.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

# Настоящий USDT на TON (master-контракт Jetton USDT).
REAL_USDT_MASTER = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"

# Верификация от TonAPI приходит в нижнем регистре: whitelist/graylist/none/blacklist.
_VER_CLEAN = 0.0
_VER_BLACKLIST = "blacklist"
_VER_NONE = "none"
_VER_GRAYLIST = "graylist"

# Порог «мусорных аирдропов»: одиночный скам-джеттон — шум TON-экосистемы
# (их прилетает всем), сотня — целенаправленное обмывание.
DUST_AIRDROP_MIN_TOKENS = 3

# Символы, которые скамеры подделывают (сравнение после нормализации).
_STABLE_ALIASES = ("usdt", "usdc", "usd", "tusd", "usdb")

# Невидимые/обфусцирующие символы: soft hyphen, combining marks, RTL/LRM-управляющие,
# zero-width, tag-символы (U+E0000-U+E007F), hangul filler (U+115F/U+1160).
_INVISIBLE_RE = re.compile(
    "[" "\u00ad\u034f\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u206f\ufeff"
    "\u115f\u1160\U000e0000-\U000e007f" "]"
)

# Частые омоглифы в фейковых тикерах -> латинские эквиваленты.
_HOMOGLYPHS = str.maketrans({
    "\u0405": "s", "\u0455": "s",          # кириллическая Ѕ/ѕ
    "\u0422": "t", "\u0442": "t",          # кириллическая Т/т
    "\u03a4": "t", "\u03c4": "t",          # греческая Tau
    "\u0415": "e", "\u0435": "e",          # кириллическая Е/е
    "\u0395": "e", "\u03b5": "e",          # греческая epsilon
    "\u041e": "o", "\u043e": "o",          # кириллическая О/о
    "\u039f": "o", "\u03bf": "o",          # греческая omicron
    "\u0410": "a", "\u0430": "a",          # кириллическая А/а
    "\u0420": "p", "\u0440": "p",          # кириллическая Р/р
    "\u0421": "c", "\u0441": "c",          # кириллическая С/с
    "\u20ae": "t",                          # ₮ (tugrik sign) -> t
})


def normalize_symbol(raw: str) -> str:
    """Снимает обфускацию тикера: 'U\u0405DT'/'\u202eTDSU'/'USDT\u115f' -> 'usdt'."""
    s = unicodedata.normalize("NFKD", raw or "")
    s = _INVISIBLE_RE.sub("", s)
    s = s.translate(_HOMOGLYPHS)
    s = s.strip().lower()
    # RTL-оверврайт мог перевернуть порядок символов — проверяем и реверс.
    if not _looks_stable(s):
        s = s[::-1]
    return s


def _looks_stable(normalized: str) -> bool:
    return any(
        alias == normalized or normalized.startswith(alias) or alias in normalized
        for alias in _STABLE_ALIASES
    )


def _is_stable_impersonation(symbol: str, master: str) -> bool:
    """Символ мимикрирует под стейбл, а мастер — не настоящий эмитент."""
    if master == REAL_USDT_MASTER:
        return False
    normalized = normalize_symbol(symbol)
    return bool(normalized) and _looks_stable(normalized)


def _to_float(balance: Any) -> float:
    try:
        return float(balance or 0.0)
    except (TypeError, ValueError):
        return 0.0


def analyze_jettons(jettons: list[dict[str, Any]]) -> dict[str, Any]:
    """Анализ джеттонов кошелька -> флаги, очки риска, метрики.

    Возвращает {"flags": [...], "points": float, "metrics": {...}}:
    * fake_stablecoin — джеттон-подделка стейбла (signature флеш-атаки), +45;
    * flash_tokens_received — BLACKLIST-джеттон от TonAPI, +40;
    * scam_airdrops_dust — >=3 непроверенных мусорных токенов, +8.
    Whitelist и настоящий USDT флагов не дают.
    """
    flags: list[str] = []
    points = 0.0
    suspicious: list[str] = []
    blacklist_hits: list[str] = []
    none_count = 0
    total = len(jettons or [])

    for row in jettons or []:
        verification = str(row.get("verification") or _VER_NONE).strip().lower()
        symbol = str(row.get("symbol") or row.get("name") or "").strip()
        master = str(row.get("master") or "")
        balance = _to_float(row.get("balance"))
        if balance <= 0:
            continue  # нулевой баланс не считается «полученным»
        if verification == "whitelist":
            continue

        if _is_stable_impersonation(symbol, master):
            if "fake_stablecoin" not in flags:
                flags.append("fake_stablecoin")
                points += 45.0
            suspicious.append(symbol)

        if verification == _VER_BLACKLIST:
            if "flash_tokens_received" not in flags:
                flags.append("flash_tokens_received")
                points += 40.0
            blacklist_hits.append(symbol)
        elif verification in (_VER_NONE, _VER_GRAYLIST):
            none_count += 1

    if none_count >= DUST_AIRDROP_MIN_TOKENS:
        flags.append("scam_airdrops_dust")
        points += 8.0

    suspicious = sorted(set(suspicious))[:5]
    return {
        "flags": flags,
        "points": round(points, 1),
        "metrics": {
            "jettons_count": total,
            "suspicious_jettons": len(set(blacklist_hits)) + none_count,
            "blacklist_jettons": len(set(blacklist_hits)),
            "fake_stable_symbols": suspicious,
        },
    }
