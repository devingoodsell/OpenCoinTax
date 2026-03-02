"""Tests for the blockchain adapter registry."""

import pytest

from app.services.blockchain.base import ChainAdapter
from app.services.blockchain.registry import ChainAdapterRegistry, get_registry


class TestRegistryHasAllAdapters:
    def test_registry_has_5_adapters(self):
        # Importing blockchain triggers all registrations
        from app.services.blockchain import ADAPTERS
        registry = get_registry()
        assert len(registry) == 5

    def test_all_chain_names_registered(self):
        registry = get_registry()
        expected = {"bitcoin", "ethereum", "solana", "cosmos", "litecoin"}
        assert set(registry.chains()) == expected

    def test_adapters_are_chain_adapter_subclasses(self):
        registry = get_registry()
        for chain in registry.chains():
            adapter_cls = registry.get(chain)
            assert issubclass(adapter_cls, ChainAdapter)


class TestRegistryLookup:
    def test_unknown_chain_raises_error(self):
        registry = get_registry()
        with pytest.raises(KeyError, match="No adapter registered for chain 'dogecoin'"):
            registry.get("dogecoin")

    def test_contains_check(self):
        registry = get_registry()
        assert "bitcoin" in registry
        assert "dogecoin" not in registry

    def test_getitem(self):
        registry = get_registry()
        from app.services.blockchain.bitcoin import BitcoinAdapter
        assert registry["bitcoin"] is BitcoinAdapter


class TestRegistryDuplicateRejection:
    def test_duplicate_registration_raises_error(self):
        test_registry = ChainAdapterRegistry()
        from app.services.blockchain.bitcoin import BitcoinAdapter
        test_registry.register("test_chain", BitcoinAdapter)
        with pytest.raises(ValueError, match="already registered"):
            test_registry.register("test_chain", BitcoinAdapter)


class TestBackwardCompatibility:
    def test_adapters_dict_supports_in(self):
        from app.services.blockchain import ADAPTERS
        assert "bitcoin" in ADAPTERS
        assert "ethereum" in ADAPTERS

    def test_adapters_dict_supports_getitem(self):
        from app.services.blockchain import ADAPTERS
        from app.services.blockchain.bitcoin import BitcoinAdapter
        assert ADAPTERS["bitcoin"] is BitcoinAdapter
