"""Backward-compatible facade — re-exports from koinly_parser + koinly_importer.

All logic has been decomposed into:
- app.services.koinly_parser (CSV parsing, data classes, type inference)
- app.services.koinly_importer (preview/confirm workflow, DB operations)
"""

from app.services.koinly_parser import (
    KOINLY_WALLET_TYPE_MAP,
    KOINLY_LABEL_TYPE_MAP,
    ParsedWallet,
    ParsedTransaction,
    ExistingWalletInfo,
    KoinlyPreviewResult,
    parse_wallets_csv,
    parse_transactions_csv,
    _infer_type_from_label,
    _refine_crypto_deposit_type,
    _infer_type_from_amounts,
    _derive_usd_values,
)
from app.services.koinly_importer import (
    preview_koinly_import,
    confirm_koinly_import,
    backfill_koinly_usd_values,
)

__all__ = [
    "KOINLY_WALLET_TYPE_MAP",
    "KOINLY_LABEL_TYPE_MAP",
    "ParsedWallet",
    "ParsedTransaction",
    "ExistingWalletInfo",
    "KoinlyPreviewResult",
    "parse_wallets_csv",
    "parse_transactions_csv",
    "_infer_type_from_label",
    "_refine_crypto_deposit_type",
    "_infer_type_from_amounts",
    "_derive_usd_values",
    "preview_koinly_import",
    "confirm_koinly_import",
    "backfill_koinly_usd_values",
]
