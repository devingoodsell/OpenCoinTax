from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EoyAssetBalance(BaseModel):
    asset_id: int
    symbol: str
    name: str | None
    quantity: str
    cost_basis_usd: str
    market_value_usd: str | None


class TaxSummaryResponse(BaseModel):
    tax_year: int
    # Capital gains
    total_proceeds: str
    total_cost_basis: str
    total_gains: str
    total_losses: str
    net_gain_loss: str
    short_term_gains: str
    short_term_losses: str
    long_term_gains: str
    long_term_losses: str
    # Income
    total_income: str
    staking_income: str
    airdrop_income: str
    fork_income: str
    mining_income: str
    interest_income: str
    other_income: str
    # Expenses
    total_cost_expenses: str
    transfer_fees: str
    total_fees_usd: str
    # End-of-year balances
    eoy_balances: list[EoyAssetBalance]


class GainLossItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: int
    asset_symbol: str
    amount: str
    date_acquired: datetime
    date_sold: datetime
    proceeds_usd: str
    cost_basis_usd: str
    gain_loss_usd: str
    holding_period: str


class GainLossListResponse(BaseModel):
    items: list[GainLossItem]
    total: int


class TaxLotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wallet_id: int
    asset_id: int
    asset_symbol: str | None = None
    amount: str
    remaining_amount: str
    cost_basis_usd: str
    cost_basis_per_unit: str
    acquired_date: datetime
    source_type: str
    is_fully_disposed: bool


class InvariantCheckResult(BaseModel):
    check_name: str
    status: str  # "pass", "fail", "warning"
    details: str


class InvariantCheckResponse(BaseModel):
    results: list[InvariantCheckResult]
    all_passed: bool


class MethodComparisonItem(BaseModel):
    method: str
    total_gains: str
    total_losses: str
    net_gain_loss: str
    short_term_net: str
    long_term_net: str


class MethodComparisonResponse(BaseModel):
    tax_year: int
    comparisons: list[MethodComparisonItem]
