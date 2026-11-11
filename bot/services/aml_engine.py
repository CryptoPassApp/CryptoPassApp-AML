"""AML-движок: эвристический анализ транзакций TON-кошелька и вычисление Risk Score.

Это облегчённая эвристика, а не полноценный AML-скоринг уровня Chainalysis.
Списки адресов (миксеры, санкционные и т.д.) подгружаются из data/blocklists.json,
чтобы их можно было обновлять без изменения кода.
"""

import json
import time
from pathlib import Path
from typing import Any

from bot.config import DATA_DIR

BLOCKLISTS_PATH = DATA_DIR / "blocklists.json"

RISK_FLAGS: dict[str, int] = {
    "mixer_interaction": 35,
    "sanctioned_address": 50,
    "p2p_fraud_pattern": 30,
    "high_velocity": 15,
    "new_wallet": 10,
    "darknet_exposure": 45,
    "rug_pull_interaction": 25,
    "flash_tokens_received": 40,
    "fake_stablecoin": 45,
    "exchange_only": -10,
    "old_wallet_clean": -15,
}

FLAG_LABELS: dict[str, str] = {
    "mixer_interaction": "🎰 Взаимодействие с миксерами",
    "sanctioned_address": "🚫 Связь с санкционными адресами",
    "p2p_fraud_pattern": "⚠️ P2P-паттерн мошенничества",
    "high_velocity": "⚡ Аномальная активность (>100 tx/24ч)",
    "new_wallet": "🆕 Кошелёк моложе 7 дней",
    "darknet_exposure": "🕸️ Связь с darknet-адресами",
    "rug_pull_interaction": "🎭 Взаимодействие с rug-pull",
    "flash_tokens_received": "🪙 Получены BLACKLIST-токены (флеш/скам)",
    "fake_stablecoin": "🚨 Фейковый стейблкоин — подделка USD₮ (флеш-атака)",
    "scam_airdrops_dust": "🪫 Массовые скам-аирдропы в кошельке",
    "exchange_only": "🏦 Только CEX-транзакции",
    "old_wallet_clean": "🏛️ Старый кошелёк без флагов",
}

RISK_LEVELS = (
    (0, 20, "clean"),
    (21, 40, "low"),
    (41, 60, "medium"),
    (61, 80, "high"),
    (81, 100, "critical"),
)

DEFAULT_BLOCKLISTS: dict[str, list[str]] = {
    "mixers": [],
    "sanctioned": [],
    "darknet": [],
    "rugpulls": [],
    "exchanges": [],
}

_blocklists_cache: dict[str, list[str]] | None = None


def load_blocklists() -> dict[str, list[str]]:
    global _blocklists_cache
    if _blocklists_cache is not None:
        return _blocklists_cache
    result = {k: list(v) for k, v in DEFAULT_BLOCKLISTS.items()}
    try:
        if BLOCKLISTS_PATH.exists():
            loaded = json.loads(BLOCKLISTS_PATH.read_text(encoding="utf-8"))
            for key in result:
                values = loaded.get(key)
                if isinstance(values, list):
                    result[key] = [str(v).lower() for v in values]
    except (OSError, json.JSONDecodeError):
        pass
    _blocklists_cache = result
    return result


def reset_blocklists_cache() -> None:
    global _blocklists_cache
    _blocklists_cache = None


def risk_level_from_score(score: float) -> str:
    for low, high, level in RISK_LEVELS:
        if low <= score <= high:
            return level
    return "critical" if score > 100 else "clean"


def _contacted_addresses(transactions: list[dict[str, Any]]) -> set[str]:
    peers: set[str] = set()
    for tx in transactions:
        for field in ("in_source", "in_destination"):
            addr = tx.get(field)
            if isinstance(addr, str) and addr:
                peers.add(addr.lower())
    return peers


def analyze_wallet(profile: dict[str, Any]) -> dict[str, Any]:
    """Принимает результат TonAPIClient.full_profile() и возвращает AML-результат."""
    account: dict[str, Any] = profile.get("account", {})
    transactions: list[dict[str, Any]] = profile.get("transactions", [])

    now = int(time.time())
    flags: list[str] = []
    blocklists = load_blocklists()

    contacted = _contacted_addresses(transactions)

    # ── Флеш/фейк-токены (джеттоны): детерминированная проверка мастеров ──
    # Подделка стейбла (мастер != настоящий USDT) и BLACKLIST-джеттоны —
    # сигнатура флеш-атаки; очки приходят из детектора (45/40/8).
    from bot.services.flash_detector import analyze_jettons

    flash = analyze_jettons(profile.get("jettons") or [])
    flags.extend(flash["flags"])
    flash_pts = float(flash["points"])

    # Списковые флаги (данные из data/blocklists.json)
    if contacted & set(blocklists["mixers"]):
        flags.append("mixer_interaction")
    if contacted & set(blocklists["sanctioned"]):
        flags.append("sanctioned_address")
    if contacted & set(blocklists["darknet"]):
        flags.append("darknet_exposure")
    if contacted & set(blocklists["rugpulls"]):
        flags.append("rug_pull_interaction")

    # ── Непрерывные компоненты риска (вместо жёстких целых весов) ──

    # Скорость: доля от 100 tx/24ч -> плавно 0..15 очков; ярлык только при >100
    day_ago = now - 86_400
    recent = [tx for tx in transactions if tx.get("utime", 0) >= day_ago]
    recent_24h = len(recent)
    velocity_pts = 15.0 * min(1.0, recent_24h / 100.0)
    if recent_24h > 100:
        flags.append("high_velocity")

    # P2P-паттерн: доля мелких (<1) входящих переводов -> плавно 0..30 очков
    incoming = [tx for tx in transactions if tx.get("is_incoming")]
    small_ratio = 0.0
    if len(incoming) >= 10:
        small = sum(1 for tx in incoming if 0 < tx.get("value_in_ton", 0.0) < 1.0)
        small_ratio = small / len(incoming)
        if small_ratio >= 0.5:
            flags.append("p2p_fraud_pattern")
    p2p_pts = 30.0 * small_ratio

    # Возраст: первая транзакция в блокчейне (Toncenter/TonGrid), фолбэк — последняя сотня
    first_activity = profile.get("first_activity_utime")
    if first_activity:
        age_days = int(max(0, (now - int(first_activity)) // 86_400))
    elif transactions:
        oldest = min(tx.get("utime", 0) for tx in transactions)
        age_days = int(max(0, (now - oldest) // 86_400))
    else:
        age_days = 0
    has_flags = bool([f for f in flags if RISK_FLAGS.get(f, 0) > 0])

    # Возрастная кривая: 10 очков сразу после создания, линейный спад до 90 дней
    if 0 < age_days <= 7:
        flags.append("new_wallet")
        age_pts = 10.0
    elif age_days <= 90:
        age_pts = 10.0 * (1.0 - max(0, age_days - 7) / 83.0)
    else:
        age_pts = 0.0

    if age_days >= 365 and not has_flags:
        flags.append("old_wallet_clean")

    # Только обменники (если список exchanges заполнен)
    exchange_set = set(blocklists["exchanges"])
    if exchange_set and contacted and contacted <= exchange_set:
        flags.append("exchange_only")

    # ── Итог: тяжёлые списковые флаги + флеш-очки + непрерывные компоненты − бонусы ──
    hard_pts = sum(
        RISK_FLAGS[f]
        for f in ("mixer_interaction", "sanctioned_address", "darknet_exposure", "rug_pull_interaction")
        if f in flags
    )
    risk_score = hard_pts + flash_pts + velocity_pts + p2p_pts + age_pts
    if "old_wallet_clean" in flags:
        risk_score -= 15.0
    if "exchange_only" in flags:
        risk_score -= 10.0
    risk_score = round(max(0.0, min(100.0, risk_score)), 1)
    trust_score = round(100.0 - risk_score, 1)
    risk_level = risk_level_from_score(risk_score)

    volume_ton = round(
        sum(tx.get("value_in_ton", 0.0) + tx.get("value_out_ton", 0.0) for tx in transactions), 2
    )

    return {
        "risk_score": risk_score,
        "trust_score": trust_score,
        "risk_level": risk_level,
        "flags": sorted(set(flags)),
        "metrics": {
            "balance_ton": account.get("balance_ton", 0.0),
            "transactions_count": len(transactions),
            "transactions_more": bool(profile.get("transactions_more", False)),
            "wallet_age_days": age_days,
            "volume_ton": volume_ton,
            "status": account.get("status", "uninit"),
            "unique_peers": len(_contacted_addresses(transactions)),
            "recent_24h": recent_24h,
            "small_incoming_ratio": round(small_ratio, 2),
            "jettons_count": flash["metrics"]["jettons_count"],
            "suspicious_jettons": flash["metrics"]["suspicious_jettons"],
            "blacklist_jettons": flash["metrics"]["blacklist_jettons"],
            "fake_stable_symbols": flash["metrics"]["fake_stable_symbols"],
        },
    }
