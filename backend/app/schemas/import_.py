from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ParsedRow(BaseModel):
    row_number: int
    status: str  # "valid", "warning", "error"
    error_message: str | None = None
    datetime_utc: datetime | None = None
    type: str | None = None
    from_amount: str | None = None
    from_asset: str | None = None
    to_amount: str | None = None
    to_asset: str | None = None
    fee_amount: str | None = None
    fee_asset: str | None = None
    net_value_usd: str | None = None
    label: str | None = None
    description: str | None = None
    tx_hash: str | None = None


class CsvUploadResponse(BaseModel):
    detected_format: str
    total_rows: int
    valid_rows: int
    warning_rows: int
    error_rows: int
    rows: list[ParsedRow]


class ImportConfirmRequest(BaseModel):
    wallet_id: int
    rows: list[int]  # row numbers to import (user may deselect some)


class ImportResultResponse(BaseModel):
    import_log_id: int
    transactions_imported: int
    transactions_skipped: int
    errors: list[str]


class ImportLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    import_type: str
    wallet_id: int | None
    filename: str | None
    status: str
    transactions_imported: int
    transactions_skipped: int
    errors: str | None
    started_at: datetime
    completed_at: datetime | None


class ImportLogListResponse(BaseModel):
    items: list[ImportLogResponse]
    total: int


# ---------------------------------------------------------------------------
# Koinly full-import schemas
# ---------------------------------------------------------------------------


class KoinlyWalletPreview(BaseModel):
    koinly_id: str
    name: str
    koinly_type: str
    mapped_type: str
    blockchain: str | None = None
    is_duplicate: bool


class WalletOption(BaseModel):
    id: int
    name: str
    type: str
    category: str


class KoinlyPreviewResponse(BaseModel):
    total_wallets: int
    new_wallets: int
    existing_wallets: int
    total_transactions: int
    valid_transactions: int
    duplicate_transactions: int
    error_transactions: int
    warning_transactions: int
    wallets: list[KoinlyWalletPreview]
    existing_wallets_list: list[WalletOption]
    errors: list[str]


class KoinlyConfirmRequest(BaseModel):
    wallet_mapping: dict[str, int | str]  # koinly_id → wallet_id or "new"


class KoinlyConfirmResponse(BaseModel):
    wallets_created: int
    wallets_skipped: int
    accounts_created: int
    transactions_imported: int
    transactions_skipped: int
    errors: list[str]
