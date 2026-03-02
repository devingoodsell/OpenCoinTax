"""Chain adapter registry — decorator-based registration for blockchain adapters."""

from app.services.blockchain.base import ChainAdapter


class ChainAdapterRegistry:
    """Registry that maps chain names to adapter classes."""

    def __init__(self):
        self._adapters: dict[str, type[ChainAdapter]] = {}

    def register(self, chain_name: str, adapter_cls: type[ChainAdapter]) -> None:
        """Register an adapter class for a chain name.

        Raises ValueError if the chain name is already registered.
        """
        if chain_name in self._adapters:
            raise ValueError(
                f"Adapter for '{chain_name}' is already registered "
                f"({self._adapters[chain_name].__name__})"
            )
        self._adapters[chain_name] = adapter_cls

    def get(self, chain_name: str) -> type[ChainAdapter]:
        """Get the adapter class for a chain name.

        Raises KeyError if the chain is not registered.
        """
        if chain_name not in self._adapters:
            raise KeyError(f"No adapter registered for chain '{chain_name}'")
        return self._adapters[chain_name]

    def __contains__(self, chain_name: str) -> bool:
        return chain_name in self._adapters

    def __getitem__(self, chain_name: str) -> type[ChainAdapter]:
        return self.get(chain_name)

    def chains(self) -> list[str]:
        """Return all registered chain names."""
        return list(self._adapters.keys())

    def __len__(self) -> int:
        return len(self._adapters)


# Global registry instance
_registry = ChainAdapterRegistry()


def register_adapter(chain_name: str):
    """Decorator to register a ChainAdapter subclass for a given chain name.

    Usage:
        @register_adapter("bitcoin")
        class BitcoinAdapter(ChainAdapter):
            ...
    """
    def decorator(cls: type[ChainAdapter]) -> type[ChainAdapter]:
        _registry.register(chain_name, cls)
        return cls
    return decorator


def get_registry() -> ChainAdapterRegistry:
    """Return the global adapter registry."""
    return _registry
