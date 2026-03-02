"""Deduplication logic — detect duplicate transactions before import."""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import Transaction
from app.services.csv_parser import ParsedRow


@dataclass
class DedupMatch:
    parsed_row: ParsedRow
    existing_tx: Transaction
    match_type: str  # "exact_koinly_id", "exact_tx_hash", "fuzzy"


def check_duplicates(
    db: Session,
    rows: list[ParsedRow],
    wallet_id: int,
) -> tuple[list[ParsedRow], list[DedupMatch]]:
    """Check parsed rows against existing transactions.

    Returns (new_rows, duplicate_matches).
    """
    new_rows: list[ParsedRow] = []
    matches: list[DedupMatch] = []

    for row in rows:
        if row.status == "error":
            new_rows.append(row)
            continue

        match = _find_duplicate(db, row, wallet_id)
        if match:
            matches.append(match)
        else:
            new_rows.append(row)

    return new_rows, matches


def _find_duplicate(db: Session, row: ParsedRow, wallet_id: int) -> DedupMatch | None:
    """Check if a parsed row matches an existing transaction."""
    # 1. Exact match on koinly_tx_id
    if row.koinly_tx_id:
        existing = (
            db.query(Transaction)
            .filter_by(koinly_tx_id=row.koinly_tx_id)
            .first()
        )
        if existing:
            return DedupMatch(parsed_row=row, existing_tx=existing, match_type="exact_koinly_id")

    # 2. Exact match on tx_hash + datetime
    if row.tx_hash and row.datetime_utc:
        existing = (
            db.query(Transaction)
            .filter_by(tx_hash=row.tx_hash, datetime_utc=row.datetime_utc)
            .first()
        )
        if existing:
            return DedupMatch(parsed_row=row, existing_tx=existing, match_type="exact_tx_hash")

    # 3. Fuzzy match: datetime within 60s + same amounts + same wallet
    if row.datetime_utc:
        window_start = row.datetime_utc - timedelta(seconds=60)
        window_end = row.datetime_utc + timedelta(seconds=60)

        candidates = (
            db.query(Transaction)
            .filter(
                Transaction.datetime_utc >= window_start,
                Transaction.datetime_utc <= window_end,
            )
            .filter(
                (Transaction.from_wallet_id == wallet_id)
                | (Transaction.to_wallet_id == wallet_id)
            )
            .all()
        )

        for tx in candidates:
            if _fuzzy_amounts_match(row, tx):
                return DedupMatch(parsed_row=row, existing_tx=tx, match_type="fuzzy")

    return None


def _fuzzy_amounts_match(row: ParsedRow, tx: Transaction) -> bool:
    """Check if amounts match between a parsed row and existing transaction."""
    matches = 0
    checks = 0

    if row.from_amount and tx.from_amount:
        checks += 1
        if row.from_amount == tx.from_amount:
            matches += 1
    if row.to_amount and tx.to_amount:
        checks += 1
        if row.to_amount == tx.to_amount:
            matches += 1

    # Need at least one amount check and all must match
    return checks > 0 and matches == checks
