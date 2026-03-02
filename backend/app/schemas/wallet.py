from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.account import AccountResponse


class WalletCreate(BaseModel):
    name: str
    type: str
    provider: str | None = None
    notes: str | None = None


class WalletUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    provider: str | None = None
    notes: str | None = None
    is_archived: bool | None = None


class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    category: str
    provider: str | None
    notes: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class WalletListItemResponse(WalletResponse):
    account_count: int = 0
    transaction_count: int = 0
    total_value_usd: str = "0"
    total_cost_basis_usd: str = "0"


class WalletBalanceItem(BaseModel):
    asset_id: int
    symbol: str
    quantity: str
    cost_basis_usd: str
    current_price_usd: str | None = None
    market_value_usd: str | None = None
    roi_pct: str | None = None


class TransactionSummary(BaseModel):
    total: int = 0
    deposits: int = 0
    withdrawals: int = 0
    trades: int = 0
    transfers: int = 0
    buys: int = 0
    sells: int = 0
    other: int = 0


class WalletDetailResponse(WalletResponse):
    balances: list[WalletBalanceItem] = []
    accounts: list[AccountResponse] = []
    transaction_summary: TransactionSummary = TransactionSummary()
    has_exchange_connection: bool = False
    exchange_last_synced_at: datetime | None = None


class CostBasisMethodUpdate(BaseModel):
    cost_basis_method: str
    tax_year: int
