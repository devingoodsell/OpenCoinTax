"""Format detection, Coinbase header stripping, and main CSV parsing entry point."""

import csv
import io

from app.services.csv import ParsedRow, ParseResult
from app.services.csv.csv_validator import (
    _parse_row,
    _postprocess_koinly_row,
    _postprocess_ledger_row,
    _postprocess_coinbase_row,
)
from app.services.csv_presets import PRESETS, detect_preset


def _strip_coinbase_header(file_content: str) -> str:
    """Strip Coinbase metadata header lines before the actual CSV data.

    Coinbase CSVs start with:
      (blank line)
      Transactions
      User,"Name",uuid
      ID,Timestamp,Transaction Type,...   <-- actual header

    We skip lines until we find the one starting with "ID,".
    """
    lines = file_content.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip().startswith("ID,"):
            return "".join(lines[i:])
    # If no "ID," header found, return as-is (might not be Coinbase)
    return file_content


def parse_csv(
    file_content: str,
    preset_name: str | None = None,
    date_format: str | None = None,
) -> ParseResult:
    """Parse a CSV string into a list of ParsedRows.

    If preset_name is None, auto-detect the format from headers.
    """
    # Coinbase CSVs have metadata before the header — strip it first
    # Check for the Coinbase header pattern before DictReader sees it
    stripped = file_content
    if "Transaction Type" in file_content and file_content.lstrip().startswith(("\n", "T", "\r")):
        stripped = _strip_coinbase_header(file_content)

    reader = csv.DictReader(io.StringIO(stripped))
    headers = reader.fieldnames or []

    # Detect format
    if preset_name and preset_name in PRESETS:
        preset = PRESETS[preset_name]
        detected = preset_name
    else:
        detected, preset = detect_preset(headers)

    rows: list[ParsedRow] = []
    valid = warning = error = 0

    is_koinly = detected == "koinly_universal"
    is_ledger = detected == "ledger"
    is_coinbase = detected == "coinbase"

    for i, csv_row in enumerate(reader, start=2):  # row 1 = headers
        parsed = _parse_row(csv_row, i, preset, date_format)

        # Koinly-specific post-processing (derive USD values from fiat amounts)
        if is_koinly and parsed.status != "error":
            _postprocess_koinly_row(parsed, csv_row)

        # Ledger-specific post-processing
        if is_ledger and parsed.status != "error":
            _postprocess_ledger_row(parsed, csv_row)

        # Coinbase-specific post-processing
        if is_coinbase and parsed.status != "error":
            _postprocess_coinbase_row(parsed, csv_row)

        rows.append(parsed)
        if parsed.status == "valid":
            valid += 1
        elif parsed.status == "warning":
            warning += 1
        else:
            error += 1

    return ParseResult(
        detected_format=detected,
        total_rows=len(rows),
        valid_rows=valid,
        warning_rows=warning,
        error_rows=error,
        rows=rows,
    )
