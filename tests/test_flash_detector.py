"""Тесты флеш-детектора: подделки стейблов (с обфускацией), BLACKLIST-джеттоны,
мусорные аирдропы, интеграция с AML-движком. Паттерны символов взяты из
живого пробника (272 джеттона на аккаунте мастера USDT)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.services.aml_engine import analyze_wallet
from bot.services.flash_detector import REAL_USDT_MASTER, analyze_jettons, normalize_symbol


def _j(symbol: str, master: str = "0:fake", *, ver: str = "none", balance: float = 1000.0) -> dict:
    return {
        "symbol": symbol,
        "master": master,
        "verification": ver,
        "balance": balance,
        "name": symbol,
    }


# ---------------------------------------------------------------------------
# Нормализация символов (обфускация скамеров)
# ---------------------------------------------------------------------------

def test_normalize_plain_and_case():
    assert normalize_symbol("USDT") == "usdt"
    assert normalize_symbol("usdt") == "usdt"


def test_normalize_strips_zero_width_and_tag_chars():
    assert normalize_symbol("USDT\u115f") == "usdt"
    assert normalize_symbol("\u115fUSDT\u202f\u200b\u200c\u200b\u200d\u200b\u202f \u200b\u200d") == "usdt"
    assert normalize_symbol("US\u206aD\u206aT") == "usdt"


def test_normalize_rtl_override_reversed_symbol():
    # '\u202eTDSU' — USDT, отображаемое задом наперёд через RTL-оверврайт.
    assert normalize_symbol("\u202eTDSU") == "usdt"


def test_normalize_homoglyphs():
    # Кириллическая Ѕ вместо S, греческая Τ вместо T, тугрик ₮ вместо t.
    assert normalize_symbol("U\u0405DT") == "usdt"
    assert normalize_symbol("USD\u03a4") == "usdt"
    assert normalize_symbol("$USD\u20ae") == "$usdt"


def test_normalize_math_alphanumerics():
    # '\U0001d61c\U0001d61a\U0001d60b\U0001d61b' — математические буквы USDT.
    assert normalize_symbol("\U0001d61c\U0001d61a\U0001d60b\U0001d61b") == "usdt"


# ---------------------------------------------------------------------------
# Детектор
# ---------------------------------------------------------------------------

def test_fake_stablecoin_is_flagged_heavy():
    result = analyze_jettons([_j("USDT", master="EQfakefakefakefakefakefakefakefakefake")])
    assert "fake_stablecoin" in result["flags"]
    assert result["points"] >= 45.0
    assert result["metrics"]["fake_stable_symbols"] == ["USDT"]


def test_real_usdt_master_is_clean():
    result = analyze_jettons(
        [_j("USDT", master=REAL_USDT_MASTER, ver="whitelist", balance=250.0)]
    )
    assert result["flags"] == [] and result["points"] == 0.0


def test_blacklist_jetton_flags_flash():
    result = analyze_jettons([_j("SOME", master="0:abc", ver="blacklist")])
    assert "flash_tokens_received" in result["flags"]
    assert result["points"] >= 40.0
    assert result["metrics"]["blacklist_jettons"] == 1


def test_whitelist_and_zero_balance_are_ignored():
    result = analyze_jettons(
        [
            _j("USDT", master=REAL_USDT_MASTER, ver="whitelist"),
            _j("SCAM", master="0:x", ver="blacklist", balance=0.0),  # нулевой баланс
        ]
    )
    assert result["flags"] == [] and result["points"] == 0.0


def test_dust_airdrops_flagged_only_when_mass():
    one = [_j(f"SCAM{i}", master=f"0:{i}", ver="none", balance=1.0) for i in range(3)]
    assert "scam_airdrops_dust" not in analyze_jettons(one[:2])["flags"]
    result = analyze_jettons(one)
    assert "scam_airdrops_dust" in result["flags"]
    assert result["points"] >= 8.0


def test_obfuscated_fake_usdt_catches_probe_patterns():
    # Реальные паттерны из живого пробника (аккаунт мастера USDT, 272 джеттона).
    patterns = [
        "USDT",            # прямая подделка (66x)
        "$USD\u20ae",
        "USDT-GARN",
        "TUSD",
        "\u054dSDT",
        "\u202eTDSU",      # RTL-реверс
        "U\u0405DT",       # омоглиф
    ]
    jettons = [_j(sym, master="0:fake", ver="none") for sym in patterns]
    result = analyze_jettons(jettons)
    assert "fake_stablecoin" in result["flags"]
    assert result["points"] >= 45.0
    assert result["metrics"]["suspicious_jettons"] >= 3


# ---------------------------------------------------------------------------
# Интеграция с AML-движком
# ---------------------------------------------------------------------------

def _profile_with_jettons(jettons: list[dict]) -> dict:
    return {
        "account": {"balance_ton": 1.0, "status": "uninit"},
        "transactions": [],
        "jettons": jettons,
        "first_activity_utime": None,
        "transactions_more": False,
    }


def test_analyze_wallet_merges_flash_flags():
    profile = _profile_with_jettons(
        [_j("USDT", master="EQfakefakefakefakefakefakefakefakefake", ver="none")]
    )
    result = analyze_wallet(profile)
    assert "fake_stablecoin" in result["flags"]
    assert result["risk_score"] >= 45.0
    assert result["risk_level"] in ("medium", "high", "critical")
    assert result["metrics"]["jettons_count"] == 1
    assert result["metrics"]["fake_stable_symbols"] == ["USDT"]


def test_analyze_wallet_clean_wallet_keeps_low_risk():
    profile = _profile_with_jettons(
        [_j("USDT", master=REAL_USDT_MASTER, ver="whitelist", balance=250.0)]
    )
    result = analyze_wallet(profile)
    assert "fake_stablecoin" not in result["flags"]
    assert result["risk_score"] <= 21.0
