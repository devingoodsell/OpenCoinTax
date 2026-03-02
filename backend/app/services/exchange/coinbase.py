"""Coinbase API v2 adapter for fetching transactions."""

import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.services.blockchain.base import RawTransaction
from app.services.exchange.base import ExchangeAdapter

logger = logging.getLogger(__name__)

COINBASE_API_BASE = "https://api.coinbase.com/v2"

# Map Coinbase transaction types to our types
TYPE_MAP = {
    "buy": "buy",
    "sell": "sell",
    "send": "withdrawal",
    "receive": "deposit",
    "trade": "trade",
    "staking_reward": "staking_reward",
    "interest": "interest",
    "inflation_reward": "staking_reward",
    "advanced_trade_fill": "trade",
    "fiat_deposit": "deposit",
    "fiat_withdrawal": "withdrawal",
}


class CoinbaseAdapter(ExchangeAdapter):
    """Fetches transactions from the Coinbase API v2."""

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def _sign_request(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """Create HMAC-SHA256 signature for Coinbase API."""
        message = timestamp + method.upper() + path + body
        return hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _headers(self, method: str, path: str) -> dict:
        """Build authenticated headers."""
        timestamp = str(int(time.time()))
        signature = self._sign_request(timestamp, method, path)
        return {
            "CB-ACCESS-KEY": self.api_key,
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "CB-VERSION": "2024-01-01",
            "Content-Type": "application/json",
        }

    async def fetch_transactions(
        self, since: datetime | None = None
    ) -> list[RawTransaction]:
        """Fetch all transactions across all Coinbase accounts."""
        all_txs: list[RawTransaction] = []

        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: List all accounts (wallets in Coinbase terms)
            accounts = await self._list_accounts(client)

            # Step 2: Fetch transactions for each account
            for account in accounts:
                account_id = account["id"]
                currency = account.get("currency", {})
                asset_symbol = currency.get("code", "UNKNOWN")
                asset_name = currency.get("name", asset_symbol)

                txs = await self._list_account_transactions(
                    client, account_id, asset_symbol, asset_name, since
                )
                all_txs.extend(txs)

        return all_txs

    async def _list_accounts(self, client: httpx.AsyncClient) -> list[dict]:
        """Paginate through all Coinbase accounts."""
        accounts: list[dict] = []
        path = "/v2/accounts?limit=100"

        while path:
            headers = self._headers("GET", path)
            resp = await client.get(f"https://api.coinbase.com{path}", headers=headers)

            if resp.status_code == 401:
                raise ValueError("Invalid Coinbase API credentials")
            resp.raise_for_status()

            data = resp.json()
            accounts.extend(data.get("data", []))

            pagination = data.get("pagination", {})
            next_uri = pagination.get("next_uri")
            path = next_uri if next_uri else None

        return accounts

    async def _list_account_transactions(
        self,
        client: httpx.AsyncClient,
        account_id: str,
        asset_symbol: str,
        asset_name: str,
        since: datetime | None,
    ) -> list[RawTransaction]:
        """Paginate through transactions for a single Coinbase account."""
        txs: list[RawTransaction] = []
        path = f"/v2/accounts/{account_id}/transactions?limit=100&order=asc"

        while path:
            headers = self._headers("GET", path)
            resp = await client.get(f"https://api.coinbase.com{path}", headers=headers)
            resp.raise_for_status()

            data = resp.json()
            for tx_data in data.get("data", []):
                raw_tx = self._map_transaction(tx_data, asset_symbol, asset_name, since)
                if raw_tx:
                    txs.append(raw_tx)

            pagination = data.get("pagination", {})
            next_uri = pagination.get("next_uri")
            path = next_uri if next_uri else None

        return txs

    def _map_transaction(
        self,
        tx_data: dict,
        asset_symbol: str,
        asset_name: str,
        since: datetime | None,
    ) -> RawTransaction | None:
        """Map a Coinbase transaction to RawTransaction."""
        # Parse datetime
        created_at = tx_data.get("created_at", "")
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            logger.warning("Skipping tx with invalid datetime: %s", created_at)
            return None

        # Apply since filter
        if since and dt <= since:
            return None

        # Skip pending transactions
        if tx_data.get("status") != "completed":
            return None

        # Map type
        cb_type = tx_data.get("type", "")
        tx_type = TYPE_MAP.get(cb_type, cb_type)

        # Extract amount
        amount_data = tx_data.get("amount", {})
        try:
            amount = abs(Decimal(str(amount_data.get("amount", "0"))))
        except Exception:
            amount = Decimal("0")

        # Extract fee if available
        fee = Decimal("0")
        network_data = tx_data.get("network", {})
        if network_data and "transaction_fee" in network_data:
            fee_data = network_data["transaction_fee"]
            try:
                fee = abs(Decimal(str(fee_data.get("amount", "0"))))
            except Exception:
                pass

        # Build tx_hash
        tx_hash = tx_data.get("id", "")
        network_hash = network_data.get("hash")
        if network_hash:
            tx_hash = network_hash

        # Addresses
        to_data = tx_data.get("to", {})
        from_data = tx_data.get("from", {})

        return RawTransaction(
            tx_hash=f"coinbase_{tx_data.get('id', '')}",
            datetime_utc=dt,
            from_address=from_data.get("address") if isinstance(from_data, dict) else None,
            to_address=to_data.get("address") if isinstance(to_data, dict) else None,
            amount=amount,
            fee=fee,
            asset_symbol=asset_symbol,
            asset_name=asset_name,
            tx_type=tx_type,
            raw_data=tx_data,
        )
