"""Генерация Web3 Trust Passport: JSON-структура для API и текст для бота."""

import json
from datetime import datetime, timezone
from typing import Any

from bot.services.aml_engine import FLAG_LABELS
from bot.services.trust_score import compute_rank_percentile, radar_axes, trust_label


def build_passport(profile: dict[str, Any], aml: dict[str, Any], lang: str = "ru") -> dict[str, Any]:
    metrics: dict[str, Any] = dict(aml.get("metrics", {}))
    trust_score = float(aml.get("trust_score", 0.0))

    last_activity = ""
    if metrics.get("wallet_age_days") is not None:
        # приблизительная дата первой активности
        first_ts = datetime.now(tz=timezone.utc).timestamp() - int(metrics["wallet_age_days"]) * 86_400
        last_activity = datetime.fromtimestamp(first_ts, tz=timezone.utc).strftime("%Y-%m-%d")

    return {
        "address": (profile.get("account") or {}).get("address", ""),
        "network": str(aml.get("network") or "ton").upper(),
        "trust_score": trust_score,
        "risk_score": aml.get("risk_score", 0.0),
        "risk_level": aml.get("risk_level", "clean"),
        "label": trust_label(trust_score, lang),
        "rank_percentile": compute_rank_percentile(trust_score),
        "flags": aml.get("flags", []),
        "flag_labels": [FLAG_LABELS.get(f, f) for f in aml.get("flags", [])],
        "metrics": metrics,
        "radar": radar_axes(metrics, trust_score),
        "first_seen": last_activity,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "recent_transactions": [
            {
                "date": datetime.fromtimestamp(tx.get("utime", 0), tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M"
                ),
                "direction": "in" if tx.get("is_incoming") else "out",
                "amount_ton": tx.get("value_in_ton") or tx.get("value_out_ton", 0.0),
            }
            for tx in sorted(
                profile.get("transactions", []), key=lambda t: t.get("utime", 0), reverse=True
            )[:5]
        ],
    }


def render_passport_text(passport: dict[str, Any], lang: str = "ru") -> str:
    """Текстовый паспорт для отправки в чат ботом."""
    is_ru = lang == "ru"
    score = passport["trust_score"]
    metrics = passport["metrics"]
    lines = [
        "🪪 *Web3 Trust Passport*",
        "",
        f"`{passport['address']}`",
        "",
        f"⭐ Trust Score: *{score:.0f}/100* — {passport['label']}",
        f"🏆 TOP {passport['rank_percentile']}%",
        "",
    ]
    if is_ru:
        lines += [
            f"📅 Возраст: {metrics.get('wallet_age_days', 0)} дн.",
            f"💎 Баланс: {metrics.get('balance_ton', 0)} TON",
            f"🔄 Транзакций: {metrics.get('transactions_count', 0)}",
            f"📊 Объём: {metrics.get('volume_ton', 0)} TON",
        ]
    else:
        lines += [
            f"📅 Age: {metrics.get('wallet_age_days', 0)} days",
            f"💎 Balance: {metrics.get('balance_ton', 0)} TON",
            f"🔄 Transactions: {metrics.get('transactions_count', 0)}",
            f"📊 Volume: {metrics.get('volume_ton', 0)} TON",
        ]

    if passport["flags"]:
        lines += ["", ("⚠️ Флаги риска:" if is_ru else "⚠️ Risk flags:")]
        lines += [f"• {label}" for label in passport["flag_labels"]]
    else:
        lines += [
            "",
            "✅ " + ("Флагов риска не обнаружено" if is_ru else "No risk flags detected"),
        ]

    return "\n".join(lines)


def passport_to_json(passport: dict[str, Any]) -> str:
    return json.dumps(passport, ensure_ascii=False, default=str)
