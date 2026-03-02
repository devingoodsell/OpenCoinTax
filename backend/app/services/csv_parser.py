"""Backward-compatible facade — re-exports from the csv/ package.

All logic has been decomposed into:
- app.services.csv.csv_reader (format detection and CSV file reading)
- app.services.csv.csv_validator (row validation, type coercion, post-processing)
- app.services.csv.transaction_builder (Transaction model creation and DB import)
"""

from app.services.csv import ParsedRow, ParseResult
from app.services.csv.csv_reader import parse_csv, _strip_coinbase_header
from app.services.csv.csv_validator import (
    _safe_decimal,
    _parse_date,
    _parse_row,
    _postprocess_ledger_row,
    _postprocess_coinbase_row,
    _parse_coinbase_convert_notes,
)
from app.services.csv.transaction_builder import (
    import_parsed_rows,
    _resolve_asset,
    _find_ledger_duplicate,
    _update_existing_from_ledger,
    _resolve_ledger_account,
    _LEDGER_ACCOUNT_BLOCKCHAIN,
)

__all__ = [
    "ParsedRow",
    "ParseResult",
    "parse_csv",
    "import_parsed_rows",
    "_safe_decimal",
    "_parse_date",
    "_parse_row",
    "_strip_coinbase_header",
    "_postprocess_ledger_row",
    "_postprocess_coinbase_row",
    "_parse_coinbase_convert_notes",
    "_resolve_asset",
    "_find_ledger_duplicate",
    "_update_existing_from_ledger",
    "_resolve_ledger_account",
    "_LEDGER_ACCOUNT_BLOCKCHAIN",
]
