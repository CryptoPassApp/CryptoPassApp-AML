import base64
import re
from typing import Any

import httpx

from bot.config import settings

TONAPI_BASE = "https://tonapi.io/v2"
TONCENTER_V3 = "https://toncenter.com/api/v3"
NANO = 1_000_000_000

# EQ.../UQ... — user-friendly (48 символов), 0:... — raw hex; T... — Tron (TRC-20)
ADDRESS_RE = re.compile(r"^(?:EQ|UQ)[A-Za-z0-9_-]{46}$|^0:[0-9a-fA-F]{64}$")
TRON_ADDRESS_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")


def is_valid_ton_address(address: str) -> bool:
    address = address.strip()
    return bool(ADDRESS_RE.match(address))


def is_valid_tron_address(address: str) -> bool:
    address = address.strip()
    return bool(TRON_ADDRESS_RE.match(address))


def detect_network(address: str) -> str | None:
    address = address.strip()
    if ADDRESS_RE.match(address):
        return "ton"
    if TRON_ADDRESS_RE.match(address):
        return "tron"
    return None


def is_supported_address(address: str) -> bool:
    return detect_network(address) is not None


def normalize_address(address: str) -> str:
    return address.strip()


def to_raw_address(address: str) -> str | None:
    """EQ/UQ (base64url) -> 0:hex. Raw-адрес возвращается как есть."""
    addr = normalize_address(address)
    if addr.startswith("0:"):
        return addr.lower()
    if len(addr) == 48 and addr[:2] in ("EQ", "UQ"):
        try:
            data = base64.urlsafe_b64decode(addr + "=" * (-len(addr) % 4))
            if len(data) == 36:
                return "0:" + data[1:33].hex()
        except (ValueError, TypeError):
            return None
    return None


class TonAPIError(Exception):
    pass


class TonAPIClient:
    """Асинхронный клиент TonAPI v2 (https://tonapi.io)."""

    def __init__(self) -> None:
        headers = {"accept": "application/json"}
        if settings.ton_api_key:
            headers["X-API-Key"] = settings.ton_api_key
        self._client = httpx.AsyncClient(
            base_url=TONAPI_BASE, headers=headers, timeout=20.0
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            resp = await self._client.get(path, params=params)
        except httpx.HTTPError as e:
            raise TonAPIError(f"network error: {e}") from e
        if resp.status_code == 404:
            raise TonAPIError("account not found")
        if resp.status_code == 429:
            raise TonAPIError("rate limited")
        if resp.status_code >= 400:
            raise TonAPIError(f"tonapi error {resp.status_code}")
        return resp.json()

    async def get_account(self, address: str) -> dict[str, Any]:
        """Инфо об аккаунте: баланс (в TON), статус, last_activity и т.д."""
        data = await self._get(f"/accounts/{normalize_address(address)}")
        balance = data.get("balance", "0")
        try:
            balance_ton = int(balance) / NANO
        except (TypeError, ValueError):
            balance_ton = 0.0
        return {
            "address": data.get("address", address),
            "status": data.get("status", "uninit"),
            "balance_ton": round(balance_ton, 4),
            "last_activity": data.get("last_activity"),
            "interfaces": data.get("interfaces", []),
            "is_wallet": bool(data.get("is_wallet", False)),
        }

    async def get_transactions(self, address: str, limit: int = 100) -> list[dict[str, Any]]:
        """Последние транзакции, нормализованные к простому виду."""
        data = await self._get(
            f"/blockchain/accounts/{normalize_address(address)}/transactions",
            params={"limit": min(limit, 100)},
        )
        if isinstance(data, dict):
            data = data.get("transactions", [])
        if not isinstance(data, list):
            return []
        txs: list[dict[str, Any]] = []
        for tx in data:
            in_msg = tx.get("in_msg") or {}
            out_msgs = tx.get("out_msgs") or []
            value_in = 0.0
            if in_msg.get("value"):
                try:
                    value_in = int(in_msg["value"]) / NANO
                except (TypeError, ValueError):
                    value_in = 0.0
            value_out = 0.0
            for om in out_msgs:
                try:
                    value_out += int(om.get("value") or 0) / NANO
                except (TypeError, ValueError):
                    pass
            source = in_msg.get("source") or {}
            destination = in_msg.get("destination") or {}
            txs.append(
                {
                    "utime": tx.get("utime", 0),
                    "hash": tx.get("hash", ""),
                    "in_source": source.get("address", "") if isinstance(source, dict) else str(source),
                    "in_destination": destination.get("address", "") if isinstance(destination, dict) else str(destination),
                    "value_in_ton": round(value_in, 4),
                    "value_out_ton": round(value_out, 4),
                    "out_count": len(out_msgs),
                    "is_incoming": value_in > 0 and value_out == 0,
                }
            )
        return txs

    async def get_first_activity(self, address: str) -> int | None:
        """Unix-time самой первой транзакции адреса (истинный возраст кошелька).

        TonAPI не отдаёт транзакции по возрастанию (sort=asc игнорируется),
        поэтому старейшую tx берём из Toncenter v3. При ошибке — None,
        AML-движок тогда оценивает возраст по последним 100 транзакциям.
        """
        raw = to_raw_address(address)
        if raw is None:
            return None
        # Отдельный клиент: self._client содержит X-API-Key от TonAPI,
        # который нельзя отправлять на toncenter.com (чужой сервис → 401/403).
        # httpx при headers=... мержит заголовки, а не заменяет их.
        try:
            async with httpx.AsyncClient(timeout=15.0) as toncenter:
                resp = await toncenter.get(
                    f"{TONCENTER_V3}/transactions",
                    params={"account_id": raw, "limit": 1, "sort": "asc"},
                )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        txs = resp.json().get("transactions", [])
        if not txs:
            return None
        now = txs[0].get("now")
        return int(now) if now else None

    async def get_jettons(self, address: str) -> list[dict[str, Any]]:
        """Джеттоны кошелька: символ, мастер-контракт, верификация, баланс.

        Основа флеш-детектора: TonAPI маркирует каждый джеттон
        верификацией whitelist/graylist/none/blacklist, у подделок
        стейблов мастер не совпадает с настоящим эмитентом.
        """
        data = await self._get(f"/accounts/{normalize_address(address)}/jettons")
        rows = data.get("balances", []) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            jetton = row.get("jetton") or {}
            decimals_raw = jetton.get("decimals")
            try:
                decimals = int(decimals_raw) if decimals_raw is not None else 9
            except (TypeError, ValueError):
                decimals = 9
            try:
                balance = float(int(row.get("balance", "0"))) / (10**decimals)
            except (TypeError, ValueError):
                balance = 0.0
            out.append(
                {
                    "master": str(jetton.get("address") or ""),
                    "symbol": str(jetton.get("symbol") or "").strip(),
                    "name": str(jetton.get("name") or "").strip(),
                    "verification": str(jetton.get("verification") or "none"),
                    "balance": round(balance, 6),
                }
            )
        return out

    async def full_profile(self, address: str) -> dict[str, Any]:
        """Аккаунт + транзакции + джеттоны + первая активность (для AML и паспорта)."""
        account = await self.get_account(address)
        transactions = await self.get_transactions(address, limit=100)
        first_activity = await self.get_first_activity(address)
        try:
            jettons = await self.get_jettons(address)
        except TonAPIError:
            jettons = []  # флеш-детектор не должен ронять весь скан
        return {
            "account": account,
            "transactions": transactions,
            "jettons": jettons,
            "first_activity_utime": first_activity,
            "transactions_more": len(transactions) >= 100,
        }
