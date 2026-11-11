# Живой прогон AML-сканера с флеш-детектором на реальном адресе.
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bot.services.aml_engine import analyze_wallet
from bot.services.ton_api import TonAPIClient

ADDRESS = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"  # мастер USDT


async def main() -> None:
    client = TonAPIClient()
    try:
        profile = await client.full_profile(ADDRESS)
    finally:
        await client.close()
    aml = analyze_wallet(profile)
    m = aml["metrics"]
    print("flags:", aml["flags"])
    print("risk:", aml["risk_score"], aml["risk_level"], "| trust:", aml["trust_score"])
    print("jettons_count:", m.get("jettons_count"))
    print("suspicious_jettons:", m.get("suspicious_jettons"))
    print("blacklist_jettons:", m.get("blacklist_jettons"))
    syms = m.get("fake_stable_symbols") or []
    safe = [s.encode("ascii", "backslashreplace").decode() for s in syms]
    print("fake_stable_symbols:", safe)


asyncio.run(main())
