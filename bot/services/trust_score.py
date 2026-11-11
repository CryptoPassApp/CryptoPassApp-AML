"""Trust Score и метрики Web3-паспорта."""

from typing import Any


def compute_trust_score(risk_score: float) -> float:
    return round(max(0.0, min(100.0, 100.0 - risk_score)), 1)


def trust_label(score: float, lang: str = "ru") -> str:
    labels = {
        "ru": {
            "excellent": "Отличная репутация",
            "good": "Хорошая репутация",
            "medium": "Средняя репутация",
            "low": "Низкая репутация",
            "bad": "Опасный кошелёк",
        },
        "en": {
            "excellent": "Excellent reputation",
            "good": "Good reputation",
            "medium": "Medium reputation",
            "low": "Low reputation",
            "bad": "Dangerous wallet",
        },
    }
    if score >= 80:
        return labels[lang]["excellent"]
    if score >= 60:
        return labels[lang]["good"]
    if score >= 40:
        return labels[lang]["medium"]
    if score >= 20:
        return labels[lang]["low"]
    return labels[lang]["bad"]


def radar_axes(metrics: dict[str, Any], trust_score: float) -> dict[str, float]:
    """5 осей радара паспорта: 0–100 по каждой.

    Age — возраст кошелька, Activity — активность, Volume — объём,
    Network — широта сети контактов, Compliance — чистота от флагов риска.
    """
    age_days = float(metrics.get("wallet_age_days", 0))
    tx_count = float(metrics.get("transactions_count", 0))
    volume = float(metrics.get("volume_ton", 0.0))
    peers = float(metrics.get("unique_peers", 0))
    risk = max(0.0, min(100.0, 100.0 - trust_score))

    return {
        "Age": min(100.0, age_days / 730 * 100),
        "Activity": min(100.0, tx_count / 500 * 100),
        "Volume": min(100.0, volume / 1000 * 100),
        "Network": min(100.0, peers / 200 * 100),
        "Compliance": max(0.0, 100.0 - risk * 1.2),
    }


def compute_rank_percentile(trust_score: float) -> int:
    """Условный ранг «TOP X%» — грубая аппроксимация распределения."""
    if trust_score >= 90:
        return 5
    if trust_score >= 75:
        return 15
    if trust_score >= 60:
        return 35
    if trust_score >= 40:
        return 65
    return 90
