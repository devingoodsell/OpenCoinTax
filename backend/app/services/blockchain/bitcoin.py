"""Bitcoin adapter using Blockstream.info API."""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.services.blockchain.base import ChainAdapter, RawTransaction
from app.services.blockchain.registry import register_adapter

logger = logging.getLogger(__name__)

BLOCKSTREAM_BASE = "https://blockstream.info/api"
SATS_PER_BTC = Decimal("100000000")


@register_adapter("bitcoin")
class BitcoinAdapter(ChainAdapter):
    chain_name = "bitcoin"
    native_asset_symbol = "BTC"
    native_asset_name = "Bitcoin"

    async def fetch_transactions(
        self, address: str, since: datetime | None = None
    ) -> list[RawTransaction]:
        results: list[RawTransaction] = []
        last_seen_txid: str | None = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                url = f"{BLOCKSTREAM_BASE}/address/{address}/txs"
                if last_seen_txid:
                    url += f"/chain/{last_seen_txid}"

                resp = await client.get(url)
                resp.raise_for_status()
                txs = resp.json()

                if not txs:
                    break

                for tx in txs:
                    raw_tx = self._parse_tx(tx, address)
                    if raw_tx is None:
                        continue
                    if since and raw_tx.datetime_utc <= since:
                        # Reached transactions we already have
                        return sorted(results, key=lambda t: t.datetime_utc)
                    results.append(raw_tx)

                if len(txs) < 25:
                    break

                last_seen_txid = txs[-1]["txid"]
                await asyncio.sleep(0.5)

        return sorted(results, key=lambda t: t.datetime_utc)

    def _parse_tx(self, tx: dict, address: str) -> RawTransaction | None:
        """Parse a Blockstream transaction into a RawTransaction."""
        status = tx.get("status", {})
        if not status.get("confirmed", False):
            return None  # Skip unconfirmed

        block_time = status.get("block_time")
        if not block_time:
            return None

        dt = datetime.fromtimestamp(block_time, tz=timezone.utc)

        # Calculate sent and received amounts
        sent = Decimal(0)
        received = Decimal(0)

        for vin in tx.get("vin", []):
            prevout = vin.get("prevout", {})
            if prevout and prevout.get("scriptpubkey_address") == address:
                sent += Decimal(str(prevout.get("value", 0)))

        for vout in tx.get("vout", []):
            if vout.get("scriptpubkey_address") == address:
                received += Decimal(str(vout.get("value", 0)))

        if sent == 0 and received == 0:
            return None

        # Fee is total inputs - total outputs
        fee_sats = Decimal(str(tx.get("fee", 0)))
        fee = fee_sats / SATS_PER_BTC

        # Net amount (in BTC)
        if sent > 0:
            amount = sent / SATS_PER_BTC
            from_addr = address
            to_addr = self._get_primary_output(tx, address)
        else:
            amount = received / SATS_PER_BTC
            from_addr = self._get_primary_input(tx)
            to_addr = address

        return RawTransaction(
            tx_hash=tx["txid"],
            datetime_utc=dt,
            from_address=from_addr,
            to_address=to_addr,
            amount=amount,
            fee=fee if sent > 0 else Decimal(0),  # Only payer pays fee
            asset_symbol="BTC",
            asset_name="Bitcoin",
            raw_data=tx,
        )

    @staticmethod
    def _get_primary_output(tx: dict, exclude_address: str) -> str | None:
        """Get the primary output address (first non-change output)."""
        for vout in tx.get("vout", []):
            addr = vout.get("scriptpubkey_address")
            if addr and addr != exclude_address:
                return addr
        return None

    @staticmethod
    def _get_primary_input(tx: dict) -> str | None:
        """Get the primary input address."""
        for vin in tx.get("vin", []):
            prevout = vin.get("prevout", {})
            if prevout:
                addr = prevout.get("scriptpubkey_address")
                if addr:
                    return addr
        return None
