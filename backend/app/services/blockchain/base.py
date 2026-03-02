"""Base class for blockchain chain adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class RawTransaction:
    """Normalized transaction from a blockchain adapter."""
    tx_hash: str
    datetime_utc: datetime
    from_address: str | None
    to_address: str | None
    amount: Decimal
    fee: Decimal
    asset_symbol: str  # e.g., "BTC", "ETH", "SOL", "ATOM", "LTC"
    asset_name: str  # e.g., "Bitcoin", "Ethereum"
    tx_type: str | None = None  # e.g., "staking_reward" — None means infer from direction
    raw_data: dict = field(default_factory=dict)


class ChainAdapter(ABC):
    """Abstract base for blockchain explorer adapters."""

    @property
    @abstractmethod
    def chain_name(self) -> str:
        """Lowercase chain name (e.g., 'bitcoin')."""
        ...

    @property
    @abstractmethod
    def native_asset_symbol(self) -> str:
        """Native asset symbol (e.g., 'BTC')."""
        ...

    @property
    @abstractmethod
    def native_asset_name(self) -> str:
        """Native asset full name (e.g., 'Bitcoin')."""
        ...

    @abstractmethod
    async def fetch_transactions(
        self, address: str, since: datetime | None = None
    ) -> list[RawTransaction]:
        """Fetch transactions for an address, optionally after a timestamp.

        Args:
            address: The blockchain address to query.
            since: Only return transactions after this time (for incremental sync).

        Returns:
            List of RawTransaction objects sorted by datetime ascending.
        """
        ...
