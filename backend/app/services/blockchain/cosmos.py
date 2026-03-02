"""Cosmos/ATOM adapter using LCD REST API."""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.services.blockchain.base import ChainAdapter, RawTransaction
from app.services.blockchain.registry import register_adapter

logger = logging.getLogger(__name__)

LCD_BASE = "https://rest.cosmos.directory/cosmoshub"
UATOM_PER_ATOM = Decimal("1000000")


@register_adapter("cosmos")
class CosmosAdapter(ChainAdapter):
    chain_name = "cosmos"
    native_asset_symbol = "ATOM"
    native_asset_name = "Cosmos"

    async def fetch_transactions(
        self, address: str, since: datetime | None = None
    ) -> list[RawTransaction]:
        results: list[RawTransaction] = []

        # Fetch sent transactions
        sent = await self._fetch_events(address, "sender", since)
        results.extend(sent)

        # Fetch received transactions
        received = await self._fetch_events(address, "recipient", since)
        results.extend(received)

        # Fetch staking rewards
        rewards = await self._fetch_events(address, "withdraw_rewards", since)
        results.extend(rewards)

        # Deduplicate by tx_hash (same tx might appear in both sent and received)
        seen = set()
        unique = []
        for tx in sorted(results, key=lambda t: t.datetime_utc):
            if tx.tx_hash not in seen:
                seen.add(tx.tx_hash)
                unique.append(tx)

        return unique

    async def _fetch_events(
        self, address: str, event_type: str, since: datetime | None
    ) -> list[RawTransaction]:
        results: list[RawTransaction] = []
        page = 1

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                if event_type == "withdraw_rewards":
                    events_query = f"withdraw_rewards.validator={address}"
                    # Actually query by delegator
                    events_query = f"withdraw_rewards.delegator='{address}'"
                elif event_type == "sender":
                    events_query = f"transfer.sender='{address}'"
                else:
                    events_query = f"transfer.recipient='{address}'"

                url = f"{LCD_BASE}/cosmos/tx/v1beta1/txs"
                params = {
                    "events": events_query,
                    "pagination.limit": 100,
                    "pagination.offset": (page - 1) * 100,
                    "order_by": "ORDER_BY_ASC",
                }

                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                tx_responses = data.get("tx_responses", [])
                if not tx_responses:
                    break

                for tx_resp in tx_responses:
                    raw_tx = self._parse_tx(tx_resp, address, event_type)
                    if raw_tx is None:
                        continue
                    if since and raw_tx.datetime_utc <= since:
                        continue
                    results.append(raw_tx)

                total = int(data.get("pagination", {}).get("total", 0))
                if page * 100 >= total:
                    break

                page += 1
                await asyncio.sleep(0.5)

        return results

    def _parse_tx(self, tx_resp: dict, address: str, event_type: str) -> RawTransaction | None:
        """Parse a Cosmos LCD tx_response."""
        timestamp_str = tx_resp.get("timestamp", "")
        if not timestamp_str:
            return None

        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except ValueError:
            return None

        tx_hash = tx_resp.get("txhash", "")
        if not tx_hash:
            return None

        # Extract amount from events
        amount = Decimal(0)
        fee = Decimal(0)
        from_addr = None
        to_addr = None

        # Parse logs for transfer events
        logs = tx_resp.get("logs", [])
        for log_entry in logs:
            for event in log_entry.get("events", []):
                if event["type"] == "transfer":
                    attrs = {a["key"]: a["value"] for a in event.get("attributes", [])}
                    if "amount" in attrs:
                        amount = self._parse_amount(attrs["amount"])
                    from_addr = attrs.get("sender")
                    to_addr = attrs.get("recipient")
                elif event["type"] == "withdraw_rewards":
                    attrs = {a["key"]: a["value"] for a in event.get("attributes", [])}
                    if "amount" in attrs:
                        amount = self._parse_amount(attrs["amount"])

        # Parse fee from tx body
        tx_body = tx_resp.get("tx", {})
        auth_info = tx_body.get("auth_info", {})
        fee_obj = auth_info.get("fee", {})
        fee_amounts = fee_obj.get("amount", [])
        for fa in fee_amounts:
            if fa.get("denom") == "uatom":
                fee = Decimal(fa.get("amount", "0")) / UATOM_PER_ATOM

        mapped_type = None
        if event_type == "withdraw_rewards":
            mapped_type = "staking_reward"
            from_addr = None
            to_addr = address

        return RawTransaction(
            tx_hash=tx_hash,
            datetime_utc=dt,
            from_address=from_addr,
            to_address=to_addr,
            amount=amount,
            fee=fee if event_type == "sender" else Decimal(0),
            asset_symbol="ATOM",
            asset_name="Cosmos",
            tx_type=mapped_type,
            raw_data=tx_resp,
        )

    @staticmethod
    def _parse_amount(amount_str: str) -> Decimal:
        """Parse a Cosmos amount string like '5000uatom'."""
        import re
        match = re.match(r"(\d+)uatom", amount_str)
        if match:
            return Decimal(match.group(1)) / UATOM_PER_ATOM
        # Try plain number
        try:
            return Decimal(amount_str) / UATOM_PER_ATOM
        except Exception:
            return Decimal(0)
