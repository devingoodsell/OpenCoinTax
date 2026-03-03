"""Row validation, type coercion, and format-specific post-processing."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.services.csv import ParsedRow
from app.services.csv_presets import CsvPreset, LEDGER_SKIP_TYPES, COINBASE_SKIP_TYPES


def _safe_decimal(value: str | None) -> str | None:
    """Convert a string to a validated decimal string, or None."""
    if not value or value.strip() == "":
        return None
    try:
        cleaned = value.strip().replace(",", "")
        Decimal(cleaned)
        return cleaned
    except InvalidOperation:
        return None


def _parse_date(date_str: str, fmt: str | None = None) -> datetime | None:
    """Try to parse a date string with the given format, or common fallbacks."""
    if not date_str or date_str.strip() == "":
        return None

    date_str = date_str.strip()

    # Try explicit format first
    if fmt:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass

    # Common formats fallback
    for f in [
        "%Y-%m-%d %H:%M:%S %Z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M %Z",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ]:
        try:
            return datetime.strptime(date_str, f)
        except ValueError:
            continue

    return None


def _parse_row(csv_row: dict, row_num: int, preset: CsvPreset, date_format: str | None) -> ParsedRow:
    """Parse a single CSV row using a preset's column mappings."""
    parsed = ParsedRow(row_number=row_num, raw_data=dict(csv_row))

    try:
        # Date
        date_col = preset.columns.get("date")
        if date_col and date_col in csv_row:
            parsed.datetime_utc = _parse_date(csv_row[date_col], date_format or preset.date_format)
            if not parsed.datetime_utc:
                parsed.status = "error"
                parsed.error_message = f"Cannot parse date: '{csv_row[date_col]}'"
                return parsed

        # Type
        type_col = preset.columns.get("type")
        if type_col and type_col in csv_row:
            raw_type = csv_row[type_col].strip()
            parsed.tx_type = preset.map_type(raw_type)
        elif preset.infer_type:
            parsed.tx_type = preset.infer_type(csv_row)

        # Amounts
        for our_field, csv_col in preset.columns.items():
            if csv_col not in csv_row:
                continue
            val = csv_row[csv_col].strip() if csv_row[csv_col] else ""
            if our_field == "from_amount":
                parsed.from_amount = _safe_decimal(val)
            elif our_field == "from_asset":
                parsed.from_asset = val if val else None
            elif our_field == "to_amount":
                parsed.to_amount = _safe_decimal(val)
            elif our_field == "to_asset":
                parsed.to_asset = val if val else None
            elif our_field == "fee_amount":
                parsed.fee_amount = _safe_decimal(val)
            elif our_field == "fee_asset":
                parsed.fee_asset = val if val else None
            elif our_field == "net_value_usd":
                parsed.net_value_usd = _safe_decimal(val)
            elif our_field == "from_value_usd":
                parsed.from_value_usd = _safe_decimal(val)
            elif our_field == "to_value_usd":
                parsed.to_value_usd = _safe_decimal(val)
            elif our_field == "label":
                parsed.label = val if val else None
            elif our_field == "description":
                parsed.description = val if val else None
            elif our_field == "tx_hash":
                parsed.tx_hash = val if val else None
            elif our_field == "koinly_tx_id":
                parsed.koinly_tx_id = val if val else None

        # Validate required fields
        if not parsed.datetime_utc:
            parsed.status = "error"
            parsed.error_message = "Missing date"
        elif not parsed.tx_type:
            parsed.status = "warning"
            parsed.error_message = "Could not determine transaction type"
        elif not (parsed.from_amount or parsed.to_amount):
            parsed.status = "warning"
            parsed.error_message = "No amounts found"

    except Exception as e:
        parsed.status = "error"
        parsed.error_message = str(e)

    return parsed


_FIAT_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF"}


def _postprocess_koinly_row(parsed: ParsedRow, csv_row: dict) -> None:
    """Apply Koinly-specific post-processing after generic parsing.

    Derives USD values from fiat amounts:
    - Buy (sent fiat, received crypto): net/to/from_value_usd = fiat sent
    - Sell (sent crypto, received fiat): net/from/to_value_usd = fiat received
    """
    from_asset = (parsed.from_asset or "").upper()
    to_asset = (parsed.to_asset or "").upper()

    # Buy: sent fiat → received crypto. The USD value is the fiat sent.
    if parsed.from_amount and from_asset in _FIAT_CURRENCIES:
        if not parsed.net_value_usd:
            parsed.net_value_usd = parsed.from_amount
        if not parsed.to_value_usd:
            parsed.to_value_usd = parsed.from_amount
        if not parsed.from_value_usd:
            parsed.from_value_usd = parsed.from_amount

    # Sell: sent crypto → received fiat. The USD value is the fiat received.
    if parsed.to_amount and to_asset in _FIAT_CURRENCIES:
        if not parsed.net_value_usd:
            parsed.net_value_usd = parsed.to_amount
        if not parsed.from_value_usd:
            parsed.from_value_usd = parsed.to_amount
        if not parsed.to_value_usd:
            parsed.to_value_usd = parsed.to_amount


def _postprocess_ledger_row(parsed: ParsedRow, csv_row: dict) -> None:
    """Apply Ledger Live-specific transformations after generic parsing.

    - Moves amount to from_amount/from_asset for OUT/withdrawal/fee types
    - Skips standalone fee-only rows that duplicate fees on other txs
    - Imports delegation/staking ops as fee transactions
    - Normalizes asset symbols (stETH -> STETH)
    - Stores Account Name and Account xpub in description for later use
    """
    op_type = (csv_row.get("Operation Type") or "").strip().lower()

    # Skip only standalone "fees" rows (duplicates of fees on other txs)
    if op_type in LEDGER_SKIP_TYPES:
        parsed.status = "warning"
        parsed.error_message = f"Skipped: {op_type} (duplicate fee row)"
        return

    # Delegation/staking ops: ensure amount is on the from side (it's a cost)
    if op_type in ("delegate", "undelegate", "opt_in", "withdraw_unbonded"):
        parsed.from_amount = parsed.to_amount
        parsed.from_asset = parsed.to_asset
        parsed.to_amount = None
        parsed.to_asset = None
        if parsed.net_value_usd:
            parsed.from_value_usd = parsed.net_value_usd
            parsed.to_value_usd = None
        parsed.label = op_type
        return

    # For OUT operations, the amount is what was SENT, not received
    if op_type == "out":
        parsed.from_amount = parsed.to_amount
        parsed.from_asset = parsed.to_asset
        parsed.to_amount = None
        parsed.to_asset = None
        # USD value is for disposal
        if parsed.net_value_usd:
            parsed.from_value_usd = parsed.net_value_usd
            parsed.to_value_usd = None
    else:
        # IN/REWARD: amount is received, USD value is for acquisition
        if parsed.net_value_usd:
            parsed.to_value_usd = parsed.net_value_usd

    # Normalize asset symbols (stETH -> STETH)
    if parsed.to_asset:
        parsed.to_asset = parsed.to_asset.upper()
    if parsed.from_asset:
        parsed.from_asset = parsed.from_asset.upper()
    if parsed.fee_asset:
        parsed.fee_asset = parsed.fee_asset.upper()

    # Store account info in description for dedup/enrichment
    acct_name = (csv_row.get("Account Name") or "").strip()
    acct_xpub = (csv_row.get("Account xpub") or "").strip()
    if acct_name:
        parts = [f"Account: {acct_name}"]
        if acct_xpub:
            parts.append(f"Address: {acct_xpub}")
        parsed.description = " | ".join(parts)


def _postprocess_coinbase_row(parsed: ParsedRow, csv_row: dict) -> None:
    """Apply Coinbase-specific transformations after generic parsing.

    - Skips internal Pro/Exchange transfers (but NOT fiat Deposit/Withdrawal)
    - Strips $ prefix from USD values
    - Handles negative quantities for Send/Sell/Convert
    - Parses Convert notes to extract to_asset/to_amount
    - Sets proper from/to amounts and USD values based on type
    - Stores Coinbase transaction ID for dedup
    """
    raw_type = (csv_row.get("Transaction Type") or "").strip().lower()

    # Skip only internal Pro/Exchange transfers
    if raw_type in COINBASE_SKIP_TYPES:
        parsed.status = "warning"
        parsed.error_message = f"Skipped: {raw_type} (internal/fiat transfer)"
        return

    # Store Coinbase ID as tx_hash for dedup
    coinbase_id = (csv_row.get("ID") or "").strip()
    if coinbase_id:
        parsed.tx_hash = coinbase_id

    # Clean dollar signs from USD values
    def _strip_dollar(val: str | None) -> str | None:
        if not val:
            return None
        cleaned = val.strip().replace("$", "").replace(",", "")
        if not cleaned:
            return None
        try:
            Decimal(cleaned)
            return cleaned
        except InvalidOperation:
            return None

    subtotal = _strip_dollar(csv_row.get("Subtotal"))
    total = _strip_dollar(csv_row.get("Total (inclusive of fees and/or spread)"))
    fee_raw = _strip_dollar(csv_row.get("Fees and/or Spread"))

    # The quantity may be negative for disposal types
    qty = parsed.to_amount
    asset = parsed.to_asset

    # Fee amount: strip the $ sign
    if fee_raw:
        fee_val = abs(Decimal(fee_raw))
        parsed.fee_amount = str(fee_val) if fee_val > 0 else None
    else:
        parsed.fee_amount = None

    # Fee asset is always USD for Coinbase
    if parsed.fee_amount:
        parsed.fee_asset = "USD"

    tx_type = parsed.tx_type

    if tx_type in ("sell", "withdrawal"):
        # Disposal: amount is negative in CSV, move to from side
        if qty:
            parsed.from_amount = str(abs(Decimal(qty)))
        else:
            parsed.from_amount = None
        parsed.from_asset = asset
        parsed.to_amount = None
        parsed.to_asset = None
        # USD value for disposal
        if subtotal:
            parsed.from_value_usd = str(abs(Decimal(subtotal)))
        parsed.to_value_usd = None

    elif tx_type == "trade":
        # Convert: from_amount/asset from the row, to_amount/asset from Notes
        if qty:
            parsed.from_amount = str(abs(Decimal(qty)))
        parsed.from_asset = asset
        if subtotal:
            parsed.from_value_usd = str(abs(Decimal(subtotal)))
        parsed.to_value_usd = None

        # Parse "Converted X ASSET to Y ASSET" from Notes
        notes = (csv_row.get("Notes") or "").strip()
        to_amt, to_sym = _parse_coinbase_convert_notes(notes)
        parsed.to_amount = to_amt
        parsed.to_asset = to_sym

        # For fee: Coinbase embeds the spread in the conversion rate
        # The "Fees and/or Spread" includes the spread
        fee_val_raw = _strip_dollar(csv_row.get("Fees and/or Spread"))
        if fee_val_raw:
            fee_abs = abs(Decimal(fee_val_raw))
            parsed.fee_amount = str(fee_abs) if fee_abs > 0 else None
            parsed.fee_asset = "USD" if parsed.fee_amount else None

    elif tx_type in ("buy", "deposit", "staking_reward", "interest", "airdrop"):
        # Acquisition: amount is positive, on the to side
        if qty:
            parsed.to_amount = str(abs(Decimal(qty)))
        if subtotal:
            parsed.to_value_usd = str(abs(Decimal(subtotal)))
        parsed.from_amount = None
        parsed.from_asset = None
        parsed.from_value_usd = None

        # For buy: from side is USD
        if tx_type == "buy":
            if total:
                parsed.from_amount = str(abs(Decimal(total)))
                parsed.from_asset = "USD"
                parsed.from_value_usd = parsed.from_amount

    else:
        # Fallback: treat as acquisition
        if qty:
            try:
                parsed.to_amount = str(abs(Decimal(qty)))
            except InvalidOperation:
                pass
        if subtotal:
            try:
                parsed.to_value_usd = str(abs(Decimal(subtotal)))
            except InvalidOperation:
                pass


def _parse_coinbase_convert_notes(notes: str) -> tuple[str | None, str | None]:
    """Parse 'Converted X ASSET to Y ASSET2' from Coinbase Notes field.

    Returns (to_amount, to_asset) or (None, None).
    """
    import re
    # Pattern: "Converted 0.19147282 ETH to 490.571706 USDC"
    match = re.search(r"to\s+([\d.,]+)\s+(\w+)", notes, re.IGNORECASE)
    if match:
        amount_str = match.group(1).replace(",", "")
        symbol = match.group(2).upper()
        try:
            Decimal(amount_str)
            return amount_str, symbol
        except InvalidOperation:
            return None, None
    return None, None
