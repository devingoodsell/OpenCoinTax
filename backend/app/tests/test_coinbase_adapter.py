"""Tests for CoinbaseAdapter with mocked HTTP responses."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.exchange.coinbase import CoinbaseAdapter, TYPE_MAP


def _make_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    """Build a mock httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "https://api.coinbase.com/v2/accounts"),
    )


def _accounts_response(accounts: list[dict], next_uri: str | None = None) -> dict:
    return {
        "data": accounts,
        "pagination": {"next_uri": next_uri},
    }


def _txs_response(txs: list[dict], next_uri: str | None = None) -> dict:
    return {
        "data": txs,
        "pagination": {"next_uri": next_uri},
    }


def _make_account(account_id: str, code: str, name: str) -> dict:
    return {
        "id": account_id,
        "currency": {"code": code, "name": name},
    }


def _make_tx(
    tx_id: str,
    tx_type: str,
    amount: str,
    created_at: str,
    status: str = "completed",
    fee_amount: str | None = None,
    network_hash: str | None = None,
    to_address: str | None = None,
    from_address: str | None = None,
) -> dict:
    tx = {
        "id": tx_id,
        "type": tx_type,
        "status": status,
        "created_at": created_at,
        "amount": {"amount": amount, "currency": "BTC"},
    }
    if fee_amount or network_hash:
        network = {}
        if fee_amount:
            network["transaction_fee"] = {"amount": fee_amount, "currency": "BTC"}
        if network_hash:
            network["hash"] = network_hash
        tx["network"] = network
    if to_address:
        tx["to"] = {"address": to_address}
    if from_address:
        tx["from"] = {"address": from_address}
    return tx


@pytest.fixture
def adapter():
    return CoinbaseAdapter(api_key="test-key", api_secret="test-secret")


@pytest.mark.asyncio
async def test_fetch_buy_transaction(adapter):
    """A buy transaction should map correctly."""
    accounts_resp = _accounts_response(
        [_make_account("acct-1", "BTC", "Bitcoin")]
    )
    txs_resp = _txs_response([
        _make_tx("tx-1", "buy", "0.5", "2024-06-15T12:00:00Z"),
    ])

    async def mock_get(url, **kwargs):
        if "/accounts?" in url or url.endswith("/accounts"):
            return _make_response(accounts_resp)
        return _make_response(txs_resp)

    with patch("app.services.exchange.coinbase.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await adapter.fetch_transactions()

    assert len(result) == 1
    tx = result[0]
    assert tx.tx_hash == "coinbase_tx-1"
    assert tx.tx_type == "buy"
    assert tx.amount == Decimal("0.5")
    assert tx.asset_symbol == "BTC"
    assert tx.asset_name == "Bitcoin"


@pytest.mark.asyncio
async def test_fetch_send_maps_to_withdrawal(adapter):
    """Coinbase 'send' type should map to 'withdrawal'."""
    accounts_resp = _accounts_response([_make_account("acct-1", "ETH", "Ethereum")])
    txs_resp = _txs_response([
        _make_tx("tx-2", "send", "-1.5", "2024-07-01T10:00:00Z",
                 to_address="0xabc123"),
    ])

    async def mock_get(url, **kwargs):
        if "/accounts?" in url:
            return _make_response(accounts_resp)
        return _make_response(txs_resp)

    with patch("app.services.exchange.coinbase.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await adapter.fetch_transactions()

    assert len(result) == 1
    assert result[0].tx_type == "withdrawal"
    assert result[0].amount == Decimal("1.5")  # abs value
    assert result[0].to_address == "0xabc123"


@pytest.mark.asyncio
async def test_skip_pending_transactions(adapter):
    """Pending transactions should be skipped."""
    accounts_resp = _accounts_response([_make_account("acct-1", "BTC", "Bitcoin")])
    txs_resp = _txs_response([
        _make_tx("tx-3", "buy", "1.0", "2024-08-01T10:00:00Z", status="pending"),
    ])

    async def mock_get(url, **kwargs):
        if "/accounts?" in url:
            return _make_response(accounts_resp)
        return _make_response(txs_resp)

    with patch("app.services.exchange.coinbase.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await adapter.fetch_transactions()

    assert len(result) == 0


@pytest.mark.asyncio
async def test_since_filter(adapter):
    """Transactions before 'since' should be filtered out."""
    since = datetime(2024, 7, 1, tzinfo=timezone.utc)

    accounts_resp = _accounts_response([_make_account("acct-1", "BTC", "Bitcoin")])
    txs_resp = _txs_response([
        _make_tx("tx-old", "buy", "0.1", "2024-06-15T12:00:00Z"),
        _make_tx("tx-new", "buy", "0.2", "2024-07-15T12:00:00Z"),
    ])

    async def mock_get(url, **kwargs):
        if "/accounts?" in url:
            return _make_response(accounts_resp)
        return _make_response(txs_resp)

    with patch("app.services.exchange.coinbase.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await adapter.fetch_transactions(since=since)

    assert len(result) == 1
    assert result[0].tx_hash == "coinbase_tx-new"


@pytest.mark.asyncio
async def test_fee_extraction(adapter):
    """Network fee should be extracted when present."""
    accounts_resp = _accounts_response([_make_account("acct-1", "BTC", "Bitcoin")])
    txs_resp = _txs_response([
        _make_tx("tx-fee", "send", "-0.5", "2024-08-01T10:00:00Z",
                 fee_amount="0.0001", network_hash="abc123hash"),
    ])

    async def mock_get(url, **kwargs):
        if "/accounts?" in url:
            return _make_response(accounts_resp)
        return _make_response(txs_resp)

    with patch("app.services.exchange.coinbase.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await adapter.fetch_transactions()

    assert len(result) == 1
    assert result[0].fee == Decimal("0.0001")


@pytest.mark.asyncio
async def test_pagination(adapter):
    """Should follow pagination across multiple pages."""
    accounts_page1 = _accounts_response(
        [_make_account("acct-1", "BTC", "Bitcoin")],
        next_uri="/v2/accounts?limit=100&starting_after=acct-1",
    )
    accounts_page2 = _accounts_response(
        [_make_account("acct-2", "ETH", "Ethereum")],
    )
    txs_btc = _txs_response([
        _make_tx("tx-btc", "buy", "1.0", "2024-06-01T10:00:00Z"),
    ])
    txs_eth = _txs_response([
        _make_tx("tx-eth", "receive", "5.0", "2024-06-02T10:00:00Z"),
    ])

    call_count = {"accounts": 0}

    async def mock_get(url, **kwargs):
        if "/accounts?" in url or "/accounts" in url.split("?")[0].split("/")[-1:]:
            if "starting_after" in url:
                return _make_response(accounts_page2)
            call_count["accounts"] += 1
            if call_count["accounts"] <= 1 and "starting_after" not in url and "transactions" not in url:
                return _make_response(accounts_page1)
            return _make_response(accounts_page2)
        if "acct-1" in url:
            return _make_response(txs_btc)
        if "acct-2" in url:
            return _make_response(txs_eth)
        return _make_response(txs_btc)

    with patch("app.services.exchange.coinbase.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await adapter.fetch_transactions()

    assert len(result) == 2
    symbols = {tx.asset_symbol for tx in result}
    assert symbols == {"BTC", "ETH"}


@pytest.mark.asyncio
async def test_invalid_credentials_raises(adapter):
    """401 response should raise ValueError."""
    resp_401 = _make_response({"errors": [{"message": "invalid"}]}, status_code=401)

    async def mock_get(url, **kwargs):
        return resp_401

    with patch("app.services.exchange.coinbase.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(ValueError, match="Invalid Coinbase API credentials"):
            await adapter.fetch_transactions()


@pytest.mark.asyncio
async def test_type_mapping_comprehensive():
    """All TYPE_MAP entries should be present."""
    expected_types = {
        "buy": "buy",
        "sell": "sell",
        "send": "withdrawal",
        "receive": "deposit",
        "trade": "trade",
        "staking_reward": "staking_reward",
        "interest": "interest",
        "inflation_reward": "staking_reward",
        "advanced_trade_fill": "trade",
        "fiat_deposit": "deposit",
        "fiat_withdrawal": "withdrawal",
    }
    assert TYPE_MAP == expected_types


@pytest.mark.asyncio
async def test_staking_reward_type(adapter):
    """staking_reward transactions should be mapped correctly."""
    accounts_resp = _accounts_response([_make_account("acct-1", "SOL", "Solana")])
    txs_resp = _txs_response([
        _make_tx("tx-stake", "staking_reward", "0.05", "2024-09-01T10:00:00Z"),
    ])

    async def mock_get(url, **kwargs):
        if "/accounts?" in url:
            return _make_response(accounts_resp)
        return _make_response(txs_resp)

    with patch("app.services.exchange.coinbase.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await adapter.fetch_transactions()

    assert len(result) == 1
    assert result[0].tx_type == "staking_reward"
    assert result[0].asset_symbol == "SOL"


def test_sign_request(adapter):
    """_sign_request should produce a valid HMAC-SHA256 hex digest."""
    sig = adapter._sign_request("1234567890", "GET", "/v2/accounts")
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA256 hex digest is 64 chars


def test_headers_structure(adapter):
    """_headers should include all required Coinbase API headers."""
    headers = adapter._headers("GET", "/v2/accounts")
    assert "CB-ACCESS-KEY" in headers
    assert "CB-ACCESS-SIGN" in headers
    assert "CB-ACCESS-TIMESTAMP" in headers
    assert "CB-VERSION" in headers
    assert headers["CB-ACCESS-KEY"] == "test-key"
