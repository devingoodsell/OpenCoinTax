"""Base class for exchange adapters."""

from abc import ABC, abstractmethod
from datetime import datetime

from app.services.blockchain.base import RawTransaction


class ExchangeAdapter(ABC):
    """Abstract base class for exchange API adapters."""

    @abstractmethod
    async def fetch_transactions(
        self, since: datetime | None = None
    ) -> list[RawTransaction]:
        """Fetch transactions from the exchange API.

        Args:
            since: Only fetch transactions after this datetime.

        Returns:
            List of RawTransaction objects.
        """
        ...
