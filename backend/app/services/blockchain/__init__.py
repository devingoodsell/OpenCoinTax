"""Blockchain chain adapters for transaction syncing.

Adapters self-register via the @register_adapter decorator.
Importing this module triggers all adapter registrations.
"""

from app.services.blockchain.base import ChainAdapter, RawTransaction
from app.services.blockchain.registry import get_registry

# Import adapters to trigger @register_adapter decorations
from app.services.blockchain.bitcoin import BitcoinAdapter
from app.services.blockchain.ethereum import EthereumAdapter
from app.services.blockchain.solana import SolanaAdapter
from app.services.blockchain.cosmos import CosmosAdapter
from app.services.blockchain.litecoin import LitecoinAdapter

# Backward-compatible ADAPTERS dict backed by the registry
ADAPTERS = get_registry()

__all__ = [
    "ChainAdapter",
    "RawTransaction",
    "ADAPTERS",
    "BitcoinAdapter",
    "EthereumAdapter",
    "SolanaAdapter",
    "CosmosAdapter",
    "LitecoinAdapter",
    "get_registry",
]
