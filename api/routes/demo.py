import copy

from fastapi import APIRouter

from bot.services.aml_engine import FLAG_LABELS
from bot.services.trust_score import radar_axes, trust_label

router = APIRouter(prefix="/api/demo", tags=["demo"])

DEMO_PRESETS = {
    "clean": {
        "address": "EQD_DEMO_CLEAN_000000000000000000000000000000000",
        "trust_score": 94,
        "risk_score": 6,
        "risk_level": "clean",
        "flags": [],
        "balance_ton": 15.42,
        "transactions_count": 847,
        "wallet_age_days": 412,
        "first_seen": "2023-04-15",
        "last_activity": "2024-10-20",
        "story": "Verified P2P trader. Clean history. Recommended for deals.",
    },
    "medium": {
        "address": "EQD_DEMO_MEDIUM_00000000000000000000000000000000",
        "trust_score": 51,
        "risk_score": 49,
        "risk_level": "medium",
        "flags": ["high_velocity", "new_wallet", "p2p_fraud_pattern"],
        "balance_ton": 3.17,
        "transactions_count": 234,
        "wallet_age_days": 23,
        "first_seen": "2024-10-01",
        "last_activity": "2024-10-23",
        "story": "New wallet with suspicious P2P patterns. Proceed with caution.",
    },
    "critical": {
        "address": "EQD_DEMO_CRITICAL_0000000000000000000000000000000",
        "trust_score": 8,
        "risk_score": 92,
        "risk_level": "critical",
        "flags": ["mixer_interaction", "sanctioned_address", "darknet_exposure", "p2p_fraud_pattern"],
        "balance_ton": 0.05,
        "transactions_count": 1203,
        "wallet_age_days": 180,
        "first_seen": "2024-04-25",
        "last_activity": "2024-10-22",
        "story": "BLACKLISTED. Mixer usage + sanctioned address interaction detected.",
    },
}


def enrich(preset: dict) -> dict:
    """Дополняет пресет полями паспорта: радар, метрики, недавние транзакции."""
    data = copy.deepcopy(preset)
    data["label"] = trust_label(data["trust_score"], "en")
    data["flag_labels"] = [FLAG_LABELS.get(f, f) for f in data["flags"]]
    data["rank_percentile"] = max(1, 100 - data["trust_score"])
    metrics = {
        "balance_ton": data["balance_ton"],
        "transactions_count": data["transactions_count"],
        "wallet_age_days": data["wallet_age_days"],
        "volume_ton": round(data["transactions_count"] * (data["balance_ton"] + 0.5), 1),
        "unique_peers": max(3, data["transactions_count"] // 4),
    }
    data["metrics"] = metrics
    data["radar"] = radar_axes(metrics, data["trust_score"])
    data["recent_transactions"] = [
        {"date": "2024-10-23 14:02", "direction": "in", "amount_ton": 12.4},
        {"date": "2024-10-22 09:31", "direction": "out", "amount_ton": 3.1},
        {"date": "2024-10-21 18:47", "direction": "in", "amount_ton": 0.5},
        {"date": "2024-10-20 11:12", "direction": "in", "amount_ton": 27.0},
        {"date": "2024-10-19 22:05", "direction": "out", "amount_ton": 1.2},
    ]
    data["is_demo"] = True
    return data


@router.get("/{preset}")
async def demo_data(preset: str) -> dict:
    if preset not in DEMO_PRESETS:
        return {"error": "unknown preset", "available": list(DEMO_PRESETS.keys())}
    return enrich(DEMO_PRESETS[preset])
