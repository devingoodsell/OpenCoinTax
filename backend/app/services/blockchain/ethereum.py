"""Ethereum adapter using Etherscan API."""

import asyncio
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.services.blockchain.base import ChainAdapter, RawTransaction
from app.services.blockchain.registry import register_adapter

logger = logging.getLogger(__name__)

ETHERSCAN_BASE = "https://api.etherscan.io/api"
WEI_PER_ETH = Decimal("1000000000000000000")


@register_adapter("ethereum")
class EthereumAdapter(ChainAdapter):
    chain_name = "ethereum"
    native_asset_symbol = "ETH"
    native_asset_name = "Ethereum"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("CRYPTO_TAX_ETHERSCAN_API_KEY", "")

    async def fetch_transactions(
        self, address: str, since: datetime | None = None
    ) -> list[RawTransaction]:
        if not self.api_key:
            raise ValueError(
                "Etherscan API key required. Set CRYPTO_TAX_ETHERSCAN_API_KEY environment variable."
            )

        results: list[RawTransaction] = []
        start_block = 0

        if since:
            start_block = await self._timestamp_to_block(since)

        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1
            while True:
                params = {
                    "module": "account",
                    "action": "txlist",
                    "address": address,
                    "startblock": start_block,
                    "endblock": 99999999,
                    "page": page,
                    "offset": 100,
                    "sort": "asc",
                    "apikey": self.api_key,
                }

                resp = await client.get(ETHERSCAN_BASE, params=params)
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") != "1" or not data.get("result"):
                    break

                txs = data["result"]
                if isinstance(txs, str):
                    break  # Error message

                for tx in txs:
                    raw_tx = self._parse_tx(tx, address)
                    if raw_tx is None:
                        continue
                    if since and raw_tx.datetime_utc <= since:
                        continue
                    results.append(raw_tx)

                if len(txs) < 100:
                    break

                page += 1
                await asyncio.sleep(0.25)  # 5 req/s limit

        return sorted(results, key=lambda t: t.datetime_utc)

    async def _timestamp_to_block(self, dt: datetime) -> int:
        """Estimate the block number for a given timestamp."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "module": "block",
                "action": "getblocknobytime",
                "timestamp": int(dt.timestamp()),
                "closest": "before",
                "apikey": self.api_key,
            }
            resp = await client.get(ETHERSCAN_BASE, params=params)
            data = resp.json()
            if data.get("status") == "1":
                return int(data["result"])
        return 0

    def _parse_tx(self, tx: dict, address: str) -> RawTransaction | None:
        """Parse an Etherscan transaction."""
        if tx.get("isError") == "1":
            return None  # Skip failed txs

        timestamp = int(tx.get("timeStamp", 0))
        if timestamp == 0:
            return None
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        value_wei = Decimal(tx.get("value", "0"))
        amount = value_wei / WEI_PER_ETH

        gas_used = Decimal(tx.get("gasUsed", "0"))
        gas_price = Decimal(tx.get("gasPrice", "0"))
        fee = (gas_used * gas_price) / WEI_PER_ETH

        from_addr = tx.get("from", "").lower()
        to_addr = tx.get("to", "").lower()
        is_sender = from_addr == address.lower()

        return RawTransaction(
            tx_hash=tx["hash"],
            datetime_utc=dt,
            from_address=from_addr,
            to_address=to_addr,
            amount=amount,
            fee=fee if is_sender else Decimal(0),
            asset_symbol="ETH",
            asset_name="Ethereum",
            raw_data=tx,
        )
