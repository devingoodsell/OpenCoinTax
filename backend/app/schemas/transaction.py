from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TransactionCreate(BaseModel):
    datetime_utc: datetime
    type: str
    from_wallet_id: int | None = None
    to_wallet_id: int | None = None
    from_amount: str | None = None
    from_asset_id: int | None = None
    to_amount: str | None = None
    to_asset_id: int | None = None
    fee_amount: str | None = None
    fee_asset_id: int | None = None
    fee_value_usd: str | None = None
    from_value_usd: str | None = None
    to_value_usd: str | None = None
    net_value_usd: str | None = None
    label: str | None = None
    description: str | None = None
    source: str = "manual"


class TransactionUpdate(BaseModel):
    datetime_utc: datetime | None = None
    type: str | None = None
    from_wallet_id: int | None = None
    to_wallet_id: int | None = None
    from_amount: str | None = None
    from_asset_id: int | None = None
    to_amount: str | None = None
    to_asset_id: int | None = None
    fee_amount: str | None = None
    fee_asset_id: int | None = None
    fee_value_usd: str | None = None
    from_value_usd: str | None = None
    to_value_usd: str | None = None
    net_value_usd: str | None = None
    label: str | None = None
    description: str | None = None


class LotAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tax_lot_id: int
    amount: str
    cost_basis_usd: str
    proceeds_usd: str
    gain_loss_usd: str
    holding_period: str
    cost_basis_method: str
    acquired_date: datetime | None = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    koinly_tx_id: str | None
    tx_hash: str | None
    datetime_utc: datetime
    type: str
    from_wallet_id: int | None
    to_wallet_id: int | None
    from_account_id: int | None
    to_account_id: int | None
    from_amount: str | None
    from_asset_id: int | None
    to_amount: str | None
    to_asset_id: int | None
    fee_amount: str | None
    fee_asset_id: int | None
    fee_value_usd: str | None
    from_value_usd: str | None
    to_value_usd: str | None
    net_value_usd: str | None
    label: str | None
    description: str | None
    source: str
    tax_error: str | None = None
    has_tax_error: bool = False
    reported_on_1099da: bool
    basis_reported_to_irs: bool
    created_at: datetime
    updated_at: datetime
    # Resolved names from relationships
    from_wallet_name: str | None = None
    to_wallet_name: str | None = None
    from_account_name: str | None = None
    to_account_name: str | None = None
    from_asset_symbol: str | None = None
    to_asset_symbol: str | None = None
    fee_asset_symbol: str | None = None


class TransactionDetailResponse(TransactionResponse):
    lot_assignments: list[LotAssignmentResponse] = []


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int
