"""Tests for blockchain chain adapters with mocked API responses."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.blockchain.bitcoin import BitcoinAdapter
from app.services.blockchain.ethereum import EthereumAdapter
from app.services.blockchain.solana import SolanaAdapter
from app.services.blockchain.cosmos import CosmosAdapter
from app.services.blockchain.litecoin import LitecoinAdapter


# ---------- Bitcoin ----------

class TestBitcoinAdapter:
    @pytest.fixture
    def adapter(self):
        return BitcoinAdapter()

    def test_chain_properties(self, adapter):
        assert adapter.chain_name == "bitcoin"
        assert adapter.native_asset_symbol == "BTC"

    @pytest.mark.asyncio
    async def test_fetch_incoming_tx(self, adapter):
        address = "bc1qtest"
        mock_tx = {
            "txid": "abc123",
            "status": {"confirmed": True, "block_time": 1700000000},
            "vin": [{"prevout": {"scriptpubkey_address": "bc1qsender", "value": 100000}}],
            "vout": [{"scriptpubkey_address": address, "value": 90000}],
            "fee": 10000,
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = [mock_tx]
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.blockchain.bitcoin.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_resp
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            txs = await adapter.fetch_transactions(address)

        assert len(txs) == 1
        assert txs[0].tx_hash == "abc123"
        assert txs[0].to_address == address
        assert txs[0].amount == Decimal("90000") / Decimal("100000000")
        assert txs[0].asset_symbol == "BTC"

    @pytest.mark.asyncio
    async def test_fetch_outgoing_tx(self, adapter):
        address = "bc1qtest"
        mock_tx = {
            "txid": "def456",
            "status": {"confirmed": True, "block_time": 1700000000},
            "vin": [{"prevout": {"scriptpubkey_address": address, "value": 500000}}],
            "vout": [
                {"scriptpubkey_address": "bc1qrecipient", "value": 400000},
                {"scriptpubkey_address": address, "value": 90000},  # change
            ],
            "fee": 10000,
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = [mock_tx]
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.blockchain.bitcoin.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_resp
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            txs = await adapter.fetch_transactions(address)

        assert len(txs) == 1
        assert txs[0].from_address == address
        assert txs[0].fee > 0

    @pytest.mark.asyncio
    async def test_skip_unconfirmed(self, adapter):
        mock_tx = {
            "txid": "unconf",
            "status": {"confirmed": False},
            "vin": [],
            "vout": [],
            "fee": 0,
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = [mock_tx]
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.blockchain.bitcoin.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_resp
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            txs = await adapter.fetch_transactions("bc1qtest")

        assert len(txs) == 0


# ---------- Ethereum ----------

class TestEthereumAdapter:
    @pytest.fixture
    def adapter(self):
        return EthereumAdapter(api_key="test-key")

    def test_chain_properties(self, adapter):
        assert adapter.chain_name == "ethereum"
        assert adapter.native_asset_symbol == "ETH"

    @pytest.mark.asyncio
    async def test_requires_api_key(self):
        adapter = EthereumAdapter(api_key="")
        with pytest.raises(ValueError, match="API key required"):
            await adapter.fetch_transactions("0xtest")

    @pytest.mark.asyncio
    async def test_fetch_incoming_tx(self, adapter):
        address = "0xrecipient"
        mock_tx = {
            "hash": "0xabc",
            "timeStamp": "1700000000",
            "from": "0xsender",
            "to": address,
            "value": "1000000000000000000",  # 1 ETH
            "gasUsed": "21000",
            "gasPrice": "20000000000",
            "isError": "0",
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "1", "result": [mock_tx]}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.blockchain.ethereum.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_resp
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            txs = await adapter.fetch_transactions(address)

        assert len(txs) == 1
        assert txs[0].amount == Decimal("1")
        assert txs[0].fee == Decimal(0)  # Receiver doesn't pay fee

    @pytest.mark.asyncio
    async def test_skip_failed_tx(self, adapter):
        mock_tx = {
            "hash": "0xfail",
            "timeStamp": "1700000000",
            "from": "0xsender",
            "to": "0xrecipient",
            "value": "1000000000000000000",
            "gasUsed": "21000",
            "gasPrice": "20000000000",
            "isError": "1",
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "1", "result": [mock_tx]}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.blockchain.ethereum.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_resp
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            txs = await adapter.fetch_transactions("0xrecipient")

        assert len(txs) == 0


# ---------- Solana ----------

class TestSolanaAdapter:
    @pytest.fixture
    def adapter(self):
        return SolanaAdapter(api_key="test-key")

    def test_chain_properties(self, adapter):
        assert adapter.chain_name == "solana"
        assert adapter.native_asset_symbol == "SOL"

    @pytest.mark.asyncio
    async def test_requires_api_key(self):
        adapter = SolanaAdapter(api_key="")
        with pytest.raises(ValueError, match="API key required"):
            await adapter.fetch_transactions("soltest")

    @pytest.mark.asyncio
    async def test_fetch_sol_transfer(self, adapter):
        address = "7xKXtest"
        mock_tx = {
            "signature": "sig123",
            "timestamp": 1700000000,
            "fee": 5000,
            "type": "TRANSFER",
            "description": "",
            "nativeTransfers": [
                {
                    "fromUserAccount": "sender123",
                    "toUserAccount": address,
                    "amount": 2000000000,  # 2 SOL
                }
            ],
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = [mock_tx]
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.blockchain.solana.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_resp
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            txs = await adapter.fetch_transactions(address)

        assert len(txs) == 1
        assert txs[0].amount == Decimal("2")
        assert txs[0].asset_symbol == "SOL"


# ---------- Cosmos ----------

class TestCosmosAdapter:
    @pytest.fixture
    def adapter(self):
        return CosmosAdapter()

    def test_chain_properties(self, adapter):
        assert adapter.chain_name == "cosmos"
        assert adapter.native_asset_symbol == "ATOM"

    @pytest.mark.asyncio
    async def test_fetch_transfer(self, adapter):
        address = "cosmos1test"
        mock_response = {
            "tx_responses": [
                {
                    "txhash": "COSMOSHASH123",
                    "timestamp": "2024-01-15T12:00:00Z",
                    "logs": [
                        {
                            "events": [
                                {
                                    "type": "transfer",
                                    "attributes": [
                                        {"key": "sender", "value": "cosmos1sender"},
                                        {"key": "recipient", "value": address},
                                        {"key": "amount", "value": "5000000uatom"},
                                    ],
                                }
                            ]
                        }
                    ],
                    "tx": {"auth_info": {"fee": {"amount": [{"denom": "uatom", "amount": "5000"}]}}},
                }
            ],
            "pagination": {"total": "1"},
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.blockchain.cosmos.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_resp
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            txs = await adapter.fetch_transactions(address)

        # 3 event types queried, but deduplicated
        assert len(txs) >= 1
        assert txs[0].asset_symbol == "ATOM"

    def test_parse_amount(self, adapter):
        assert CosmosAdapter._parse_amount("5000000uatom") == Decimal("5")
        assert CosmosAdapter._parse_amount("1000000uatom") == Decimal("1")


# ---------- Litecoin ----------

class TestLitecoinAdapter:
    @pytest.fixture
    def adapter(self):
        return LitecoinAdapter()

    def test_chain_properties(self, adapter):
        assert adapter.chain_name == "litecoin"
        assert adapter.native_asset_symbol == "LTC"

    @pytest.mark.asyncio
    async def test_fetch_incoming_tx(self, adapter):
        address = "LtcTest"
        mock_data = {
            "txs": [
                {
                    "hash": "ltchash123",
                    "confirmed": "2024-01-15T12:00:00Z",
                    "fees": 10000,
                    "inputs": [{"addresses": ["LtcSender"], "output_value": 500000}],
                    "outputs": [{"addresses": [address], "value": 490000}],
                }
            ]
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.blockchain.litecoin.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_resp
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            txs = await adapter.fetch_transactions(address)

        assert len(txs) == 1
        assert txs[0].asset_symbol == "LTC"
        assert txs[0].to_address == address


# ---------- Adapter Registry ----------

class TestAdapterRegistry:
    def test_all_adapters_registered(self):
        from app.services.blockchain import ADAPTERS
        assert "bitcoin" in ADAPTERS
        assert "ethereum" in ADAPTERS
        assert "solana" in ADAPTERS
        assert "cosmos" in ADAPTERS
        assert "litecoin" in ADAPTERS
