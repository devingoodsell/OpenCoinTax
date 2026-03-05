"""Shared model utilities — column types, mixins, enums."""

import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ---------------------------------------------------------------------------
# Reusable column type aliases (DRY — used across every model)
# ---------------------------------------------------------------------------

# Crypto amounts: 18 decimal places (Ethereum wei precision)
CryptoAmount = lambda **kw: mapped_column(
    type_=String(60), nullable=kw.get("nullable", True)
)

# USD amounts: 2 decimal places
UsdAmount = lambda **kw: mapped_column(
    type_=String(30), nullable=kw.get("nullable", True)
)

# Per-unit cost basis: 8 decimal places
PerUnitAmount = lambda **kw: mapped_column(
    type_=String(30), nullable=kw.get("nullable", True)
)


class TimestampMixin:
    """Auto-managed created_at / updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WalletType(str, enum.Enum):
    exchange = "exchange"
    hardware = "hardware"
    software = "software"
    defi = "defi"
    other = "other"


class TransactionType(str, enum.Enum):
    buy = "buy"
    sell = "sell"
    trade = "trade"
    transfer = "transfer"
    deposit = "deposit"
    withdrawal = "withdrawal"
    staking_reward = "staking_reward"
    interest = "interest"
    airdrop = "airdrop"
    fork = "fork"
    mining = "mining"
    cost = "cost"
    gift_sent = "gift_sent"
    gift_received = "gift_received"
    lost = "lost"
    fee = "fee"


class CostBasisMethod(str, enum.Enum):
    fifo = "fifo"
    lifo = "lifo"
    hifo = "hifo"
    specific_id = "specific_id"


class HoldingPeriod(str, enum.Enum):
    short_term = "short_term"
    long_term = "long_term"


class LotSourceType(str, enum.Enum):
    purchase = "purchase"
    trade = "trade"
    income = "income"
    transfer_in = "transfer_in"
    gift = "gift"
    fork = "fork"
    airdrop = "airdrop"
    wrapping_swap = "wrapping_swap"


class ImportStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class TransactionSource(str, enum.Enum):
    koinly_import = "koinly_import"
    csv_import = "csv_import"
    ledger_import = "ledger_import"
    coinbase_import = "coinbase_import"
    blockchain_sync = "blockchain_sync"
    manual = "manual"


# Acquisition types — transactions that create tax lots
ACQUISITION_TYPES = frozenset({
    TransactionType.buy,
    TransactionType.deposit,
    TransactionType.staking_reward,
    TransactionType.interest,
    TransactionType.airdrop,
    TransactionType.fork,
    TransactionType.mining,
    TransactionType.gift_received,
})

# Disposal types — transactions that consume tax lots
DISPOSAL_TYPES = frozenset({
    TransactionType.sell,
    TransactionType.cost,
    TransactionType.gift_sent,
    TransactionType.lost,
    TransactionType.fee,
})

# Income types — ordinary income (not capital gains)
INCOME_TYPES = frozenset({
    TransactionType.staking_reward,
    TransactionType.interest,
    TransactionType.airdrop,
    TransactionType.mining,
})

# Wrapping pairs — asset swaps treated as non-taxable (basis carry-over)
WRAPPING_PAIRS: frozenset[frozenset[str]] = frozenset({
    frozenset({"ETH", "STETH"}),
    frozenset({"ETH", "WETH"}),
    frozenset({"BTC", "WBTC"}),
})

# Stablecoin symbols — pegged 1:1 to USD, excluded from capital gains tracking
STABLECOIN_SYMBOLS: frozenset[str] = frozenset({"USDC", "USDT", "GUSD"})
