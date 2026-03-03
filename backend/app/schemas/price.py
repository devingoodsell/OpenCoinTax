"""Pydantic schemas for the Price Data Service (Epic 8)."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class PriceHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    date: date
    price_usd: str
    source: str


class ManualPriceRequest(BaseModel):
    asset_id: int
    date: date
    price_usd: str


class MissingPriceItem(BaseModel):
    asset_id: int
    asset_symbol: str
    date: date
    transaction_count: int


class FetchMissingResponse(BaseModel):
    fetched: int
    failed: int
    already_present: int
    warnings: list[str] = []


class RefreshCurrentResponse(BaseModel):
    updated: int
    failed: int
    skipped: int
    warnings: list[str] = []


class BackfillResponse(BaseModel):
    total_stored: int
    assets_processed: int
    assets_failed: int
    assets_skipped: int = 0
    assets_mapped: int
    warnings: list[str] = []
