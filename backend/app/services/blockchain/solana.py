"""Solana adapter using Helius API."""

import asyncio
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.services.blockchain.base import ChainAdapter, RawTransaction
from app.services.blockchain.registry import register_adapter

logger = logging.getLogger(__name__)

LAMPORTS_PER_SOL = Decimal("1000000000")


@register_adapter("solana")
class SolanaAdapter(ChainAdapter):
    chain_name = "solana"
    native_asset_symbol = "SOL"
    native_asset_name = "Solana"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("CRYPTO_TAX_HELIUS_API_KEY", "")

    async def fetch_transactions(
        self, address: str, since: datetime | None = None
    ) -> list[RawTransaction]:
        if not self.api_key:
            raise ValueError(
                "Helius API key required. Set CRYPTO_TAX_HELIUS_API_KEY environment variable."
            )

        results: list[RawTransaction] = []
        url = f"https://api.helius.xyz/v0/addresses/{address}/transactions"
        before_sig: str | None = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                params: dict = {"api-key": self.api_key, "limit": 100}
                if before_sig:
                    params["before"] = before_sig

                resp = await client.get(url, params=params)
                resp.raise_for_status()
                txs = resp.json()

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

                if hit_since or len(txs) < 100:
                    break

                before_sig = txs[-1].get("signature")
                await asyncio.sleep(0.5)

        return sorted(results, key=lambda t: t.datetime_utc)

    def _parse_tx(self, tx: dict, address: str) -> RawTransaction | None:
        """Parse a Helius parsed transaction."""
        timestamp = tx.get("timestamp")
        if not timestamp:
            return None
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        signature = tx.get("signature", "")
        fee_lamports = Decimal(str(tx.get("fee", 0)))
        fee = fee_lamports / LAMPORTS_PER_SOL

        tx_type = tx.get("type", "UNKNOWN")
        description = tx.get("description", "")

        # Determine SOL transfers from nativeTransfers
        native_transfers = tx.get("nativeTransfers", [])
        from_addr = None
        to_addr = None
        amount = Decimal(0)
        is_sender = False

        for nt in native_transfers:
            if nt.get("fromUserAccount") == address:
                to_addr = nt.get("toUserAccount")
                from_addr = address
                amount += Decimal(str(nt.get("amount", 0))) / LAMPORTS_PER_SOL
                is_sender = True
            elif nt.get("toUserAccount") == address:
                from_addr = nt.get("fromUserAccount")
                to_addr = address
                amount += Decimal(str(nt.get("amount", 0))) / LAMPORTS_PER_SOL

        if amount == 0 and not native_transfers:
            return None

        # Map Helius types to our types
        mapped_type = None
        if tx_type in ("STAKE", "STAKE_SOL"):
            mapped_type = "staking_reward"

        return RawTransaction(
            tx_hash=signature,
            datetime_utc=dt,
            from_address=from_addr,
            to_address=to_addr,
            amount=amount,
            fee=fee if is_sender else Decimal(0),
            asset_symbol="SOL",
            asset_name="Solana",
            tx_type=mapped_type,
            raw_data=tx,
        )
