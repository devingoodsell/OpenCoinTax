"""Transaction model creation and database import from parsed CSV rows."""

import json
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models import Account, Asset, Transaction
from app.services.csv import ParsedRow


def import_parsed_rows(
    db: Session,
    rows: list[ParsedRow],
    wallet_id: int,
    source: str = "csv_import",
    import_log_id: int | None = None,
) -> tuple[int, int, list[str]]:
    """Insert parsed rows as transactions. Returns (imported, skipped, errors).

    When source is "ledger_import", performs dedup by tx_hash + asset + amount
    and enriches existing records with Ledger data (fees, account info).
    """
    imported = 0
    skipped = 0
    updated = 0
    errors: list[str] = []
    is_ledger = source == "ledger_import"
    is_coinbase = source == "coinbase_import"

    for row in rows:
        if row.status == "error":
            skipped += 1
            continue
        # For Ledger/Coinbase imports, also skip warning rows (internal transfers, dust)
        if (is_ledger or is_coinbase) and row.status == "warning":
            skipped += 1
            continue

        # Resolve asset IDs
        from_asset_id = _resolve_asset(db, row.from_asset) if row.from_asset else None
        to_asset_id = _resolve_asset(db, row.to_asset) if row.to_asset else None
        fee_asset_id = _resolve_asset(db, row.fee_asset) if row.fee_asset else None

        # Ledger dedup: check for existing transaction by tx_hash + asset + amount
        if is_ledger and row.tx_hash:
            existing = _find_ledger_duplicate(db, row, from_asset_id, to_asset_id)
            if existing:
                _update_existing_from_ledger(
                    db, existing, row, fee_asset_id, wallet_id,
                )
                updated += 1
                continue

        # Determine wallet assignment
        from_wallet = None
        to_wallet = None
        tx_type = row.tx_type or "buy"

        if tx_type in ("buy", "deposit", "staking_reward", "interest", "airdrop",
                        "fork", "mining", "gift_received"):
            to_wallet = wallet_id
        elif tx_type in ("sell", "cost", "gift_sent", "lost", "fee", "withdrawal"):
            from_wallet = wallet_id
        elif tx_type == "trade":
            from_wallet = wallet_id
            to_wallet = wallet_id
        else:
            to_wallet = wallet_id

        # Resolve account from Ledger description for new transactions
        account_id = None
        if is_ledger:
            account_id = _resolve_ledger_account(db, row, wallet_id)

        # If fee is in USD, set fee_value_usd directly
        fee_value_usd = None
        if row.fee_amount and row.fee_asset and row.fee_asset.upper() == "USD":
            fee_value_usd = row.fee_amount

        tx = Transaction(
            datetime_utc=row.datetime_utc,
            type=tx_type,
            from_wallet_id=from_wallet,
            to_wallet_id=to_wallet,
            from_amount=row.from_amount,
            from_asset_id=from_asset_id,
            to_amount=row.to_amount,
            to_asset_id=to_asset_id,
            fee_amount=row.fee_amount,
            fee_asset_id=fee_asset_id,
            fee_value_usd=fee_value_usd,
            from_value_usd=row.from_value_usd,
            to_value_usd=row.to_value_usd,
            net_value_usd=row.net_value_usd,
            label=row.label,
            description=row.description,
            tx_hash=row.tx_hash,
            koinly_tx_id=row.koinly_tx_id,
            source=source,
            raw_data=json.dumps(row.raw_data),
            import_log_id=import_log_id,
        )
        if account_id:
            if tx_type in ("deposit", "staking_reward", "interest", "airdrop",
                           "fork", "mining", "gift_received", "buy"):
                tx.to_account_id = account_id
            elif tx_type in ("withdrawal", "sell", "fee", "cost", "gift_sent", "lost"):
                tx.from_account_id = account_id
            elif tx_type == "trade":
                tx.from_account_id = account_id
                tx.to_account_id = account_id

        db.add(tx)
        imported += 1

    if imported > 0 or updated > 0:
        db.commit()

    # Report updated count as part of imported for the caller
    return imported, skipped + updated, errors


def _resolve_asset(db: Session, symbol: str) -> int:
    """Look up an asset by symbol, creating it if it doesn't exist."""
    asset = db.query(Asset).filter_by(symbol=symbol.upper()).first()
    if asset:
        return asset.id

    # Auto-create unknown asset
    new_asset = Asset(symbol=symbol.upper(), name=symbol.upper(), is_fiat=False)
    db.add(new_asset)
    db.flush()
    return new_asset.id


# ---------------------------------------------------------------------------
# Ledger dedup helpers
# ---------------------------------------------------------------------------

# Map Ledger account names to blockchain identifiers
_LEDGER_ACCOUNT_BLOCKCHAIN: dict[str, str] = {
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",
    "cosmos": "cosmos",
    "solana": "solana",
    "litecoin": "litecoin",
    "polygon": "polygon",
}


def _find_ledger_duplicate(
    db: Session,
    row: ParsedRow,
    from_asset_id: int | None,
    to_asset_id: int | None,
) -> Transaction | None:
    """Find an existing transaction matching a Ledger row by tx_hash + asset + amount.

    Handles the Cosmos multi-claim case where one tx_hash maps to multiple
    transactions by also comparing asset and amount.
    """
    if not row.tx_hash:
        return None

    # Case-insensitive tx_hash match
    candidates = (
        db.query(Transaction)
        .filter(Transaction.tx_hash.ilike(row.tx_hash))
        .all()
    )

    if not candidates:
        return None

    # Single candidate — likely a direct match
    if len(candidates) == 1:
        return candidates[0]

    # Multiple candidates (e.g. Cosmos multi-reward) — match by asset + amount
    asset_id = to_asset_id or from_asset_id
    amount = row.to_amount or row.from_amount

    for tx in candidates:
        tx_asset = tx.to_asset_id or tx.from_asset_id
        tx_amount = tx.to_amount or tx.from_amount

        if tx_asset == asset_id and tx_amount and amount:
            # Allow 1% tolerance for rounding differences
            try:
                diff = abs(Decimal(tx_amount) - Decimal(amount))
                if diff <= abs(Decimal(amount)) * Decimal("0.01"):
                    return tx
            except InvalidOperation:
                if tx_amount == amount:
                    return tx

    return None


def _update_existing_from_ledger(
    db: Session,
    existing: Transaction,
    row: ParsedRow,
    fee_asset_id: int | None,
    wallet_id: int,
) -> None:
    """Enrich an existing transaction with Ledger data (source of truth).

    Updates fees, account links, and description.
    Does NOT change amounts, type, or wallet assignments (preserves transfer pairs).
    """
    # Update fee info from Ledger (more accurate than Koinly)
    if row.fee_amount:
        existing.fee_amount = row.fee_amount
        if fee_asset_id:
            existing.fee_asset_id = fee_asset_id

    # Update USD values from Ledger if we have them and existing doesn't
    if row.net_value_usd and not existing.net_value_usd:
        existing.net_value_usd = row.net_value_usd
    if row.from_value_usd and not existing.from_value_usd:
        existing.from_value_usd = row.from_value_usd
    if row.to_value_usd and not existing.to_value_usd:
        existing.to_value_usd = row.to_value_usd

    # Link to Ledger account
    account_id = _resolve_ledger_account(db, row, wallet_id)
    if account_id:
        # Set account based on which side this wallet is on
        if existing.to_wallet_id == wallet_id and not existing.to_account_id:
            existing.to_account_id = account_id
        if existing.from_wallet_id == wallet_id and not existing.from_account_id:
            existing.from_account_id = account_id

    # Append Ledger account info to description if not already there
    if row.description and row.description.startswith("Account:"):
        if not existing.description or "Account:" not in existing.description:
            if existing.description:
                existing.description = f"{existing.description} | {row.description}"
            else:
                existing.description = row.description

    # Store Ledger raw data alongside existing raw data
    if row.raw_data:
        try:
            existing_raw = json.loads(existing.raw_data) if existing.raw_data else {}
        except (json.JSONDecodeError, TypeError):
            existing_raw = {}
        existing_raw["_ledger"] = row.raw_data
        existing.raw_data = json.dumps(existing_raw)


def _resolve_ledger_account(
    db: Session, row: ParsedRow, wallet_id: int,
) -> int | None:
    """Resolve a Ledger account from the row's description (Account: name | Address: xpub).

    Creates the account if it doesn't exist.
    """
    if not row.description or not row.description.startswith("Account:"):
        return None

    parts = row.description.split(" | ")
    acct_name = None
    address = None
    for part in parts:
        part = part.strip()
        if part.startswith("Account:"):
            acct_name = part[len("Account:"):].strip()
        elif part.startswith("Address:"):
            address = part[len("Address:"):].strip()

    if not acct_name or not address:
        return None

    # Determine blockchain from account name (e.g. "L1-Bitcoin" -> "bitcoin")
    blockchain = "unknown"
    name_lower = acct_name.lower()
    for chain_key, chain_val in _LEDGER_ACCOUNT_BLOCKCHAIN.items():
        if chain_key in name_lower:
            blockchain = chain_val
            break

    # Check if account already exists with this address
    existing = (
        db.query(Account)
        .filter_by(wallet_id=wallet_id, address=address)
        .first()
    )
    if existing:
        return existing.id

    # Also check by name within this wallet
    existing = (
        db.query(Account)
        .filter_by(wallet_id=wallet_id, name=acct_name)
        .first()
    )
    if existing:
        # Update address if missing/different
        if existing.address != address:
            existing.address = address
        return existing.id

    # Create new account
    new_acct = Account(
        wallet_id=wallet_id,
        name=acct_name,
        address=address,
        blockchain=blockchain,
    )
    db.add(new_acct)
    db.flush()
    return new_acct.id
