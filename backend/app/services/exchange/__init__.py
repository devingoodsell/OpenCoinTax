"""Exchange adapter registry."""

from app.services.exchange.coinbase import CoinbaseAdapter

EXCHANGE_ADAPTERS: dict[str, type] = {
    "coinbase": CoinbaseAdapter,
}
