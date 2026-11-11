"""Smoke-тест проекта CryptoPassApp: импорты + логика сервисов."""

import asyncio
import json
import sys
import time

sys.path.insert(0, ".")

failures = []


def check(name, fn):
    try:
        result = fn()
        print(f"OK   {name}" + (f" -> {result}" if result is not None else ""))
        return result
    except Exception as e:
        print(f"FAIL {name}: {type(e).__name__}: {e}")
        failures.append(name)
        return None


# 1. Импорты всех модулей
check("import bot.config", lambda: __import__("bot.config"))
check("import bot.models", lambda: __import__("bot.models"))
check("import bot.database", lambda: __import__("bot.database"))
check("import bot.i18n", lambda: __import__("bot.i18n"))
check("import bot.keyboards", lambda: __import__("bot.keyboards"))
check("import bot.middleware", lambda: __import__("bot.middleware"))
check("import bot.services.ton_api", lambda: __import__("bot.services.ton_api"))
check("import bot.services.aml_engine", lambda: __import__("bot.services.aml_engine"))
check("import bot.services.trust_score", lambda: __import__("bot.services.trust_score"))
check("import bot.services.passport_generator", lambda: __import__("bot.services.passport_generator"))
check("import bot.services.stars_payment", lambda: __import__("bot.services.stars_payment"))
check("import bot.handlers.start", lambda: __import__("bot.handlers.start"))
check("import bot.handlers.scanner", lambda: __import__("bot.handlers.scanner"))
check("import bot.handlers.passport", lambda: __import__("bot.handlers.passport"))
check("import bot.handlers.subscription", lambda: __import__("bot.handlers.subscription"))
check("import bot.handlers.admin", lambda: __import__("bot.handlers.admin"))
check("import bot.handlers.language", lambda: __import__("bot.handlers.language"))
check("import bot.main", lambda: __import__("bot.main"))
check("import api.dependencies", lambda: __import__("api.dependencies"))
check("import api.routes.demo", lambda: __import__("api.routes.demo"))
check("import api.routes.scan", lambda: __import__("api.routes.scan"))
check("import api.routes.passport", lambda: __import__("api.routes.passport"))
check("import api.routes.user", lambda: __import__("api.routes.user"))
check("import api.routes.admin", lambda: __import__("api.routes.admin"))
check("import api.main", lambda: __import__("api.main"))

# 2. Валидация адресов
from bot.services.ton_api import is_valid_ton_address

check("valid EQ address", lambda: is_valid_ton_address("EQ" + "A" * 46) is True)
check("valid 0: address", lambda: is_valid_ton_address("0:" + "a" * 64) is True)
check("invalid address rejected", lambda: is_valid_ton_address("hello") is False)

# 3. AML-движок на синтетическом профиле
from bot.services.aml_engine import analyze_wallet, risk_level_from_score

now = int(time.time())


def synth_profile(age_days=400, txs=50, incoming_median=5.0):
    transactions = []
    for i in range(txs):
        transactions.append({
            "utime": now - i * max(1, age_days * 86400 // txs),
            "hash": f"tx{i}",
            "in_source": f"EQSRC{i:040d}AAAAAAAAAAAAAAAAAAAAAA",
            "in_destination": "EQDEST0000AAAAAAAAAAAAAAAAAAAAAAAAA",
            "value_in_ton": incoming_median if i % 2 == 0 else 0.0,
            "value_out_ton": 0.0 if i % 2 == 0 else 2.0,
            "out_count": 0,
            "is_incoming": i % 2 == 0,
        })
    return {"account": {"address": "EQTEST", "balance_ton": 10.5, "status": "active"}, "transactions": transactions}


def test_clean_wallet():
    r = analyze_wallet(synth_profile(age_days=400, txs=50, incoming_median=5.0))
    assert 0 <= r["risk_score"] <= 100, r
    assert r["trust_score"] + r["risk_score"] == 100, r
    return f"risk={r['risk_score']} level={r['risk_level']} flags={r['flags']}"


def test_new_wallet():
    r = analyze_wallet(synth_profile(age_days=3, txs=30, incoming_median=0.3))
    assert "new_wallet" in r["flags"], r
    return f"risk={r['risk_score']} flags={r['flags']}"


check("AML clean wallet", test_clean_wallet)
check("AML new wallet flag", test_new_wallet)
check("risk levels mapping", lambda: (risk_level_from_score(0), risk_level_from_score(50), risk_level_from_score(95)))

# 4. Trust Score / радар / паспорт
from bot.services.trust_score import radar_axes, trust_label, compute_rank_percentile
from bot.services.passport_generator import build_passport, render_passport_text


def test_passport():
    profile = synth_profile()
    aml = analyze_wallet(profile)
    pp = build_passport(profile, aml, "ru")
    assert 0 <= pp["trust_score"] <= 100
    assert set(pp["radar"].keys()) == {"Age", "Activity", "Volume", "Network", "Compliance"}
    text = render_passport_text(pp, "ru")
    assert "Trust Score" in text
    return f"score={pp['trust_score']} radar=ok text_len={len(text)}"


check("passport build+render", test_passport)
check("trust labels", lambda: trust_label(95, "ru"))
check("rank percentile", lambda: compute_rank_percentile(95))

# 5. i18n
from bot.i18n import t, detect_lang


def test_i18n():
    ru = t("ru", "free_limit_reached", count=3)
    en = t("en", "free_limit_reached", count=3)
    assert "3" in ru and "3" in en and ru != en
    # все ключи ru есть в en
    ru_keys = set(json.load(open("bot/locales/ru.json", encoding="utf-8")))
    en_keys = set(json.load(open("bot/locales/en.json", encoding="utf-8")))
    assert ru_keys == en_keys, f"diff: {ru_keys ^ en_keys}"
    return f"ru={len(ru_keys)} keys, en={len(en_keys)} keys, parity=ok"


check("i18n parity ru/en", test_i18n)
check("lang detect", lambda: detect_lang("ru-RU"))

# 6. Demo-пресеты API
from api.routes.demo import DEMO_PRESETS, enrich


def test_demo():
    for name, preset in DEMO_PRESETS.items():
        e = enrich(preset)
        assert e["trust_score"] + e["risk_score"] == 100, name
        assert len(e["radar"]) == 5, name
    return f"{len(DEMO_PRESETS)} presets ok"


check("demo presets enrich", test_demo)

# 7. Stars payment: тарифы
from bot.services.stars_payment import PLANS, subscription_from_payload


def test_plans():
    assert PLANS["pro_month"]["stars"] == 150
    assert PLANS["pro_year"]["stars"] == 999
    assert subscription_from_payload(json.dumps({"plan": "pro_year"})) == "pro_year"
    assert subscription_from_payload("pro_month") == "pro_month"
    assert subscription_from_payload("garbage") == "pro_month"
    return "plans+payload ok"


check("stars plans/payload", test_plans)

# 8. БД: создание таблиц + CRUD пользователя
import os

from sqlalchemy import select

from bot.database import SessionMaker, init_db
from bot.models import Scan, User


def test_db():
    async def run():
        await init_db()
        async with SessionMaker() as s:
            from sqlalchemy import delete

            await s.execute(delete(Scan).where(Scan.user_id.in_(
                select(User.id).where(User.telegram_id == 999111)
            )))
            await s.execute(delete(User).where(User.telegram_id == 999111))
            await s.commit()

            u = User(telegram_id=999111, username="tester", full_name="Test", language="ru")
            s.add(u)
            await s.commit()
            await s.refresh(u)
            s.add(Scan(user_id=u.id, address="EQ" + "B" * 46, risk_score=10.0,
                       trust_score=90.0, risk_level="clean", flags="[]", raw_data="{}"))
            await s.commit()
            found = (await s.execute(select(User).where(User.telegram_id == 999111))).scalar_one()
            return found.id, found.is_pro_active
    return asyncio.run(run())


check("db init + user/scan insert", test_db)

# 9. initData-валидация (HMAC): корректная и битая подпись
import hashlib
import hmac as hmac_mod

from api.dependencies import validate_init_data


def test_init_data():
    from bot.config import settings
    token = settings.bot_token or "123:ABC"
    settings.bot_token = token
    from urllib.parse import quote
    user_json = json.dumps({"id": 42, "username": "u"})
    pairs = {"user": user_json, "auth_date": "1700000000"}
    dcs = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac_mod.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    good_hash = hmac_mod.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    init_data = f"user={quote(user_json)}&auth_date=1700000000&hash={good_hash}"
    data = validate_init_data(init_data)
    assert data["user"]["id"] == 42
    try:
        validate_init_data(init_data[:-4] + "beef")
        raise AssertionError("bad hash accepted")
    except Exception:
        pass  # ожидаем HTTPException
    return "valid accepted, invalid rejected"


check("initData HMAC validation", test_init_data)

# 10. FastAPI-приложение: живые запросы через TestClient
def test_routes():
    from bot.config import settings
    from fastapi.testclient import TestClient

    from api.main import app
    with TestClient(app) as client:
        health = client.get("/health").json()
        assert health["status"] == "ok"

        demo = client.get("/api/demo/clean").json()
        assert demo["risk_level"] == "clean" and demo["trust_score"] == 94

        bad_preset = client.get("/api/demo/unknown").json()
        assert "error" in bad_preset

        no_auth = client.get("/api/user/me")
        assert no_auth.status_code == 401, no_auth.status_code

        no_admin = client.get("/api/admin/stats")
        assert no_admin.status_code == 403, no_admin.status_code

        admin = client.get("/api/admin/stats", headers={"X-Admin-Token": settings.api_secret_key})
        assert admin.status_code == 200, admin.text
    return "health/demo/auth/admin checks ok"


check("FastAPI live routes", test_routes)

print()
if failures:
    print(f"RESULT: {len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("RESULT: ALL CHECKS PASSED")
