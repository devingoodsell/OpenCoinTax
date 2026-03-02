"""Litecoin adapter using Blockcypher API."""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.services.blockchain.base import ChainAdapter, RawTransaction
from app.services.blockchain.registry import register_adapter

logger = logging.getLogger(__name__)

BLOCKCYPHER_BASE = "https://api.blockcypher.com/v1/ltc/main"
LITOSHIS_PER_LTC = Decimal("100000000")


@register_adapter("litecoin")
class LitecoinAdapter(ChainAdapter):
    chain_name = "litecoin"
    native_asset_symbol = "LTC"
    native_asset_name = "Litecoin"

    async def fetch_transactions(
        self, address: str, since: datetime | None = None
    ) -> list[RawTransaction]:
        results: list[RawTransaction] = []
        before_block: int | None = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                url = f"{BLOCKCYPHER_BASE}/addrs/{address}/full"
                params: dict = {"limit": 50}
                if before_block is not None:
                    params["before"] = before_block

                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                txs = data.get("txs", [])
                if not txs:
                    break

                hit_since = False
                for tx in txs:
                    raw_tx = self._parse_tx(tx, address)
                    if raw_tx is None:
                        continue
                    if since and raw_tx.datetime_utc <= since:
                        hit_since = True
                        break
                    results.append(raw_tx)

                if hit_since or len(txs) < 50:
                    break

                # Paginate by block height
                last_block = txs[-1].get("block_height")
                if last_block and last_block != before_block:
                    before_block = last_block
                else:
                    break

                await asyncio.sleep(1.0)  # 200 req/hr limit

        return sorted(results, key=lambda t: t.datetime_utc)

    def _parse_tx(self, tx: dict, address: str) -> RawTransaction | None:
        """Parse a Blockcypher transaction."""
        confirmed = tx.get("confirmed")
        if not confirmed:
            return None

        try:
            dt = datetime.fromisoformat(confirmed.replace("Z", "+00:00"))
        except ValueError:
            return None

        tx_hash = tx.get("hash", "")
        if not tx_hash:
            return None

        fee_litoshis = Decimal(str(tx.get("fees", 0)))
        fee = fee_litoshis / LITOSHIS_PER_LTC

        # Calculate sent and received
        sent = Decimal(0)
        received = Decimal(0)

        for inp in tx.get("inputs", []):
            addresses = inp.get("addresses", [])
            if address in addresses:
                sent += Decimal(str(inp.get("output_value", 0)))

        for out in tx.get("outputs", []):
            addresses = out.get("addresses", [])
            if address in addresses:
                received += Decimal(str(out.get("value", 0)))

        if sent == 0 and received == 0:
            return None

        if sent > 0:
            amount = sent / LITOSHIS_PER_LTC
            from_addr = address
            to_addr = self._get_primary_output(tx, address)
        else:
            amount = received / LITOSHIS_PER_LTC
            from_addr = self._get_primary_input(tx)
            to_addr = address

        return RawTransaction(
            tx_hash=tx_hash,
            datetime_utc=dt,
            from_address=from_addr,
            to_address=to_addr,
            amount=amount,
            fee=fee if sent > 0 else Decimal(0),
            asset_symbol="LTC",
            asset_name="Litecoin",
            raw_data=tx,
        )

    @staticmethod
    def _get_primary_output(tx: dict, exclude_address: str) -> str | None:
        for out in tx.get("outputs", []):
            addresses = out.get("addresses", [])
            for addr in addresses:
                if addr != exclude_address:
                    return addr
        return None

    @staticmethod
    def _get_primary_input(tx: dict) -> str | None:
        for inp in tx.get("inputs", []):
            addresses = inp.get("addresses", [])
            if addresses:
                return addresses[0]
        return None
