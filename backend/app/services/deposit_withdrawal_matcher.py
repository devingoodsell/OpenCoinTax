"""Match orphan deposits with orphan withdrawals and convert to transfers.

When Koinly exports transactions, cross-wallet transfers are exported as
separate withdrawal and deposit records.  The deposit has no from_wallet and
the withdrawal has no to_wallet.  This module pairs them up based on asset,
amount similarity, and temporal proximity, then converts the pair into a
proper transfer so the tax engine can carry cost basis over correctly.
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import and_, text
from sqlalchemy.orm import Session

from app.models import Asset, Transaction


# ---------------------------------------------------------------------------
# Matching parameters
# ---------------------------------------------------------------------------

# Maximum time gap between a deposit and withdrawal to be considered a pair.
MAX_TIME_GAP = timedelta(hours=24)

# Maximum relative difference in amounts (5%).
MAX_AMOUNT_DIFF_PCT = Decimal("0.05")

# Assets that are fiat or stablecoins — skip matching (deposits are real purchases).
_FIAT_SYMBOLS = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF"}

# Minimum USD value to consider for matching (skip dust).
MIN_VALUE_USD = Decimal("1")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_deposit_withdrawal_pairs(
    db: Session,
    *,
    dry_run: bool = True,
) -> list[dict]:
    """Scan for orphan deposit-withdrawal pairs and optionally convert them.

    An "orphan deposit" is type='deposit' with from_wallet_id IS NULL.
    An "orphan withdrawal" is type='withdrawal' with to_wallet_id IS NULL.

    Matching criteria (all must hold):
      - Same asset
      - Amounts within 5% of each other
      - Timestamps within 24 hours
      - Different wallets (deposit.to_wallet != withdrawal.from_wallet)
      - Neither is fiat/stablecoin

    When matched, the deposit is deleted and the withdrawal is converted to a
    transfer (type='transfer', to_wallet_id set, amounts set).

    Returns list of match dicts describing each pair found/converted.
    """
    # Fetch orphan deposits (excluding fiat)
    deposits = (
        db.query(Transaction)
        .filter(
            Transaction.type == "deposit",
            Transaction.from_wallet_id.is_(None),
        )
        .order_by(Transaction.datetime_utc)
        .all()
    )

    # Fetch orphan withdrawals (excluding fiat)
    withdrawals = (
        db.query(Transaction)
        .filter(
            Transaction.type == "withdrawal",
            Transaction.to_wallet_id.is_(None),
        )
        .order_by(Transaction.datetime_utc)
        .all()
    )

    # Build asset symbol cache
    asset_symbols: dict[int, str] = {}
    all_asset_ids = set()
    for tx in deposits:
        if tx.to_asset_id:
            all_asset_ids.add(tx.to_asset_id)
    for tx in withdrawals:
        if tx.from_asset_id:
            all_asset_ids.add(tx.from_asset_id)

    if all_asset_ids:
        for asset in db.query(Asset).filter(Asset.id.in_(all_asset_ids)).all():
            asset_symbols[asset.id] = asset.symbol

    # Filter out fiat
    deposits = [
        d for d in deposits
        if d.to_asset_id and asset_symbols.get(d.to_asset_id, "") not in _FIAT_SYMBOLS
    ]
    withdrawals = [
        w for w in withdrawals
        if w.from_asset_id and asset_symbols.get(w.from_asset_id, "") not in _FIAT_SYMBOLS
    ]

    # Index withdrawals by asset_id for faster lookup
    wd_by_asset: dict[int, list[Transaction]] = {}
    for w in withdrawals:
        wd_by_asset.setdefault(w.from_asset_id, []).append(w)

    matched_wd_ids: set[int] = set()
    matches: list[dict] = []

    for dep in deposits:
        asset_id = dep.to_asset_id
        symbol = asset_symbols.get(asset_id, "???")
        dep_amount = Decimal(dep.to_amount) if dep.to_amount else Decimal("0")

        # Skip dust
        dep_value = Decimal(dep.to_value_usd or dep.net_value_usd or "0")
        if dep_value < MIN_VALUE_USD and dep_amount == 0:
            continue

        candidates = wd_by_asset.get(asset_id, [])
        best_match = None
        best_score = None  # lower is better: (time_diff_seconds, amount_diff_pct)

        for wd in candidates:
            if wd.id in matched_wd_ids:
                continue

            # Must be different wallets
            if dep.to_wallet_id == wd.from_wallet_id:
                continue

            # Time proximity
            time_diff = abs(dep.datetime_utc - wd.datetime_utc)
            if time_diff > MAX_TIME_GAP:
                continue

            # Amount similarity
            wd_amount = Decimal(wd.from_amount) if wd.from_amount else Decimal("0")
            if wd_amount == 0:
                continue

            amount_diff_pct = abs(dep_amount - wd_amount) / wd_amount
            if amount_diff_pct > MAX_AMOUNT_DIFF_PCT:
                continue

            score = (time_diff.total_seconds(), float(amount_diff_pct))
            if best_score is None or score < best_score:
                best_match = wd
                best_score = score

        if best_match is not None:
            matched_wd_ids.add(best_match.id)
            wd_amount = Decimal(best_match.from_amount) if best_match.from_amount else Decimal("0")

            match_info = {
                "deposit_tx_id": dep.id,
                "withdrawal_tx_id": best_match.id,
                "asset": symbol,
                "deposit_wallet_id": dep.to_wallet_id,
                "withdrawal_wallet_id": best_match.from_wallet_id,
                "deposit_amount": str(dep_amount),
                "withdrawal_amount": str(wd_amount),
                "deposit_time": dep.datetime_utc.isoformat(),
                "withdrawal_time": best_match.datetime_utc.isoformat(),
                "time_diff_minutes": round(abs(dep.datetime_utc - best_match.datetime_utc).total_seconds() / 60, 1),
            }
            matches.append(match_info)

            if not dry_run:
                _convert_pair_to_transfer(db, dep, best_match)

    return matches


def find_duplicate_deposit_withdrawal_pairs(
    db: Session,
    *,
    dry_run: bool = True,
) -> list[dict]:
    """Find orphan deposit+withdrawal pairs that duplicate an existing transfer.

    When Koinly exports a transfer as BOTH a 'transfer' record AND separate
    deposit/withdrawal records, the latter are duplicates.  We detect this by
    finding an orphan deposit+withdrawal pair where a transfer with matching
    asset, amount, and similar timestamp already exists.

    Returns list of duplicate dicts.  If dry_run is False, deletes the
    duplicate deposit and withdrawal transactions.
    """
    deposits = (
        db.query(Transaction)
        .filter(
            Transaction.type == "deposit",
            Transaction.from_wallet_id.is_(None),
        )
        .order_by(Transaction.datetime_utc)
        .all()
    )

    withdrawals = (
        db.query(Transaction)
        .filter(
            Transaction.type == "withdrawal",
            Transaction.to_wallet_id.is_(None),
        )
        .order_by(Transaction.datetime_utc)
        .all()
    )

    # Build asset symbol cache
    asset_symbols: dict[int, str] = {}
    all_asset_ids = set()
    for tx in deposits:
        if tx.to_asset_id:
            all_asset_ids.add(tx.to_asset_id)
    for tx in withdrawals:
        if tx.from_asset_id:
            all_asset_ids.add(tx.from_asset_id)

    if all_asset_ids:
        for asset in db.query(Asset).filter(Asset.id.in_(all_asset_ids)).all():
            asset_symbols[asset.id] = asset.symbol

    # For each orphan deposit, check if there's a transfer with same asset, amount, time
    duplicates: list[dict] = []

    for dep in deposits:
        if not dep.to_asset_id or not dep.to_amount:
            continue

        dep_amount = Decimal(dep.to_amount)

        # Look for existing transfer with same asset near same time
        existing_transfers = (
            db.query(Transaction)
            .filter(
                Transaction.type == "transfer",
                Transaction.from_asset_id == dep.to_asset_id,
                Transaction.datetime_utc.between(
                    dep.datetime_utc - MAX_TIME_GAP,
                    dep.datetime_utc + MAX_TIME_GAP,
                ),
            )
            .all()
        )

        for xfer in existing_transfers:
            xfer_amount = Decimal(xfer.from_amount) if xfer.from_amount else Decimal("0")
            if xfer_amount == 0:
                continue

            amount_diff_pct = abs(dep_amount - xfer_amount) / xfer_amount
            if amount_diff_pct > MAX_AMOUNT_DIFF_PCT:
                continue

            # Found a matching transfer. Now find the matching orphan withdrawal.
            for wd in withdrawals:
                if wd.from_asset_id != dep.to_asset_id:
                    continue
                if abs(wd.datetime_utc - dep.datetime_utc) > MAX_TIME_GAP:
                    continue
                wd_amount = Decimal(wd.from_amount) if wd.from_amount else Decimal("0")
                if wd_amount == 0:
                    continue
                if abs(dep_amount - wd_amount) / wd_amount > MAX_AMOUNT_DIFF_PCT:
                    continue
                # Same wallet as the deposit? (Koinly sometimes does deposit+withdrawal to same wallet)
                if dep.to_wallet_id == wd.from_wallet_id:
                    symbol = asset_symbols.get(dep.to_asset_id, "???")
                    duplicates.append({
                        "deposit_tx_id": dep.id,
                        "withdrawal_tx_id": wd.id,
                        "transfer_tx_id": xfer.id,
                        "asset": symbol,
                        "amount": str(dep_amount),
                        "deposit_time": dep.datetime_utc.isoformat(),
                    })

                    if not dry_run:
                        _delete_duplicate_pair(db, dep, wd)
                    break
            break  # Only match one transfer per deposit

    return duplicates


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _convert_pair_to_transfer(
    db: Session,
    deposit: Transaction,
    withdrawal: Transaction,
) -> None:
    """Convert an orphan deposit+withdrawal pair into a single transfer.

    Strategy: keep the withdrawal record and convert it into a transfer.
    Delete the deposit record.  The transfer inherits the withdrawal's
    from_wallet and the deposit's to_wallet.
    """
    # Convert withdrawal → transfer
    withdrawal.type = "transfer"
    withdrawal.to_wallet_id = deposit.to_wallet_id
    withdrawal.to_account_id = deposit.to_account_id
    withdrawal.to_asset_id = deposit.to_asset_id
    withdrawal.to_amount = deposit.to_amount
    withdrawal.to_value_usd = deposit.to_value_usd or withdrawal.from_value_usd

    # Ensure from_amount is set
    if not withdrawal.from_amount and deposit.to_amount:
        withdrawal.from_amount = deposit.to_amount
    if not withdrawal.from_asset_id:
        withdrawal.from_asset_id = deposit.to_asset_id

    # Delete the deposit
    db.delete(deposit)
    db.flush()


def _delete_duplicate_pair(
    db: Session,
    deposit: Transaction,
    withdrawal: Transaction,
) -> None:
    """Delete a duplicate deposit+withdrawal pair.

    Also cleans up any tax lots and lot assignments created from these
    transactions to prevent orphaned records.
    """
    from app.models import TaxLot, LotAssignment

    # Delete lot assignments referencing these transactions
    db.query(LotAssignment).filter(
        LotAssignment.disposal_tx_id.in_([deposit.id, withdrawal.id])
    ).delete(synchronize_session=False)

    # Delete tax lots created by these transactions
    db.query(TaxLot).filter(
        TaxLot.acquisition_tx_id.in_([deposit.id, withdrawal.id])
    ).delete(synchronize_session=False)

    # Delete the transactions themselves
    db.delete(deposit)
    db.delete(withdrawal)
    db.flush()
