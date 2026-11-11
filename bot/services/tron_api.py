"""Клиент сети Tron (TRC-20) без API-ключа:

- TronGrid (/v1/accounts) — баланс TRX, TRC20-токены, первая транзакция (order_by asc)
- Tronscan (/api/transaction) — последние транзакции в удобном формате

Возвращает профиль той же структуры, что TonAPIClient.full_profile(),
чтобы AML-движок работал с обеими сетями без изменений.
"""

from typing import Any

import httpx

TRONSCAN = "https://apilist.tronscanapi.com"
TRONGRID = "https://api.trongrid.io"

USDT_TRC20 = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


class TronAPIError(Exception):
    pass


class TronAPIClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=20.0,
            headers={"accept": "application/json", "User-Agent": "CryptoPass/1.0"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            resp = await self._client.get(url, params=params)
        except httpx.HTTPError as e:
            raise TronAPIError(f"network error: {e}") from e
        if resp.status_code == 404:
            raise TronAPIError("account not found")
        if resp.status_code == 429:
            raise TronAPIError("rate limited")
        if resp.status_code >= 400:
            raise TronAPIError(f"tron api error {resp.status_code}")
        return resp.json()

    async def get_account(self, address: str) -> dict[str, Any]:
        """Баланс TRX + USDT (TRC-20). Неактивированный адрес = uninit, не ошибка."""
        data = await self._get(f"{TRONGRID}/v1/accounts/{address}")
        accounts = data.get("data") or []
        if not accounts:
            return {"address": address, "status": "uninit", "balance_ton": 0.0}
        acc = accounts[0]
        balance_trx = int(acc.get("balance") or 0) / 1_000_000
        usdt = 0.0
        for token in acc.get("trc20") or []:
            if USDT_TRC20 in token:
                try:
                    usdt = int(token[USDT_TRC20]) / 1e6
                except (TypeError, ValueError):
                    usdt = 0.0
        return {
            "address": address,
            "status": "active",
            "balance_ton": round(balance_trx, 4),
            "usdt_trc20": round(usdt, 2),
        }

    async def get_transactions(self, address: str, limit: int = 100) -> list[dict[str, Any]]:
        """Последние переводы: TRX/TRC10 (api/transfer) + TRC-20 (token_trc20/transfers).

        У /api/transaction события Events часто пусты, а toAddress для контрактных
        вызовов — сам контракт, поэтому берём специализированные эндпоинты и мержим.
        """
        addr_l = address.lower()
        half = max(limit // 2, 25)
        rows: list[dict[str, Any]] = []

        data = await self._get(
            f"{TRONSCAN}/api/transfer",
            params={"sort": "-timestamp", "count": False, "limit": half, "address": address},
        )
        for row in data.get("data") or []:
            token = row.get("tokenInfo") or {}
            try:
                decimals = int(token.get("tokenDecimal") or 6)
            except (TypeError, ValueError):
                decimals = 6
            try:
                amount = float(row.get("amount") or 0) / (10**decimals)
            except (TypeError, ValueError):
                amount = 0.0
            rows.append(
                {
                    "utime": int(row.get("timestamp") or 0) // 1000,
                    "src": row.get("transferFromAddress") or "",
                    "dst": row.get("transferToAddress") or "",
                    "amount": amount,
                }
            )

        data = await self._get(
            f"{TRONSCAN}/api/token_trc20/transfers",
            params={"sort": "-timestamp", "count": False, "limit": half, "relatedAddress": address},
        )
        for row in data.get("token_transfers") or []:
            token = row.get("tokenInfo") or {}
            try:
                decimals = int(token.get("tokenDecimal") or 6)
            except (TypeError, ValueError):
                decimals = 6
            try:
                amount = float(row.get("quant") or 0) / (10**decimals)
            except (TypeError, ValueError):
                amount = 0.0
            rows.append(
                {
                    "utime": int(row.get("block_ts") or 0) // 1000,
                    "src": row.get("from_address") or "",
                    "dst": row.get("to_address") or "",
                    "amount": amount,
                }
            )

        rows.sort(key=lambda r: r["utime"], reverse=True)
        rows = rows[:limit]

        txs: list[dict[str, Any]] = []
        for r in rows:
            vin = vout = 0.0
            src, dst = r["src"], r["dst"]
            if dst.lower() == addr_l:
                vin = r["amount"]
            elif src.lower() == addr_l:
                vout = r["amount"]
            txs.append(
                {
                    "utime": r["utime"],
                    "hash": "",
                    "in_source": src,
                    "in_destination": dst,
                    "value_in_ton": round(vin, 4),
                    "value_out_ton": round(vout, 4),
                    "out_count": 0,
                    "is_incoming": vin > 0 and vout == 0,
                }
            )
        return txs

    async def get_first_activity(self, address: str) -> int | None:
        """Время первой транзакции (истинный возраст) через TronGrid order_by asc."""
        try:
            resp = await self._client.get(
                f"{TRONGRID}/v1/accounts/{address}/transactions",
                params={"limit": 1, "order_by": "block_timestamp,asc"},
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        data = resp.json().get("data") or []
        if not data:
            return None
        ts = data[0].get("block_timestamp")
        return int(ts) // 1000 if ts else None

    async def full_profile(self, address: str) -> dict[str, Any]:
        """Аккаунт + транзакции + первая активность — тот же контракт, что у TonAPI."""
        account = await self.get_account(address)
        try:
            transactions = await self.get_transactions(address, limit=100)
        except TronAPIError:
            transactions = []
        first_activity = await self.get_first_activity(address)
        return {
            "account": account,
            "transactions": transactions,
            "first_activity_utime": first_activity,
            "transactions_more": len(transactions) >= 100,
        }
