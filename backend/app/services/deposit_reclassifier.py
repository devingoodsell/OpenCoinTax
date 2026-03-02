"""Reclassify crypto_deposit transactions to staking_reward or interest.

Koinly CSV exports label all incoming-only transactions as 'crypto_deposit',
regardless of whether the user tagged them as rewards/interest in the Koinly UI.
This module uses heuristics to detect the correct type.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Transaction

# Assets whose deposits are almost certainly staking rewards.
# Liquid staking tokens accrue value via rebasing (daily deposits).
STAKING_REWARD_ASSETS: set[str] = {
    "STETH",     # Lido staked ETH
    "STATOM",    # Stride staked ATOM
    "STOSMO",    # Stride staked OSMO
    "STJUNO",    # Stride staked JUNO
    "STLUNA",    # Stride staked LUNA
    "STINJ",     # Stride staked INJ
    "STEVMOS",   # Stride staked EVMOS
    "STCMDX",    # Stride staked CMDX
    "STUMEE",    # Stride staked UMEE
    "STSTARS",   # Stride staked STARS
    "STRD",      # Stride token (staking rewards)
}

# Description keywords that indicate interest income.
INTEREST_KEYWORDS: set[str] = {"interest", "yield", "lending", "earn"}

# Minimum number of deposits of the same asset to the same wallet within a
# calendar year to be considered a "high-frequency staking reward pattern".
# 7+ deposits/year covers weekly or more frequent reward claims.
HIGH_FREQ_THRESHOLD = 7

# Small-value deposits that look like interest/yield accruals.
# If total USD for a (year, wallet, asset) group is under this AND count >= 3,
# treat as interest.
SMALL_VALUE_INTEREST_THRESHOLD_USD = 50.0
SMALL_VALUE_MIN_COUNT = 3


def _asset_symbol_for_tx(db: Session, tx: Transaction) -> str | None:
    """Return the to_asset symbol for a transaction, using raw SQL to avoid model schema issues."""
    if tx.to_asset_id is None:
        return None
    row = db.execute(
        db.bind.execution_options()
        if False else
        __import__("sqlalchemy").text("SELECT symbol FROM assets WHERE id = :id"),
        {"id": tx.to_asset_id},
    ).fetchone()
    return row[0] if row else None


def reclassify_crypto_deposits(db: Session, *, dry_run: bool = True) -> list[dict]:
    """Scan crypto_deposit transactions and reclassify where appropriate.

    Returns a list of change dicts: {id, date, asset, old_type, new_type, reason}.
    If dry_run is True, no DB writes are performed.
    """
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.type == "deposit",
            Transaction.label == "crypto_deposit",
        )
        .order_by(Transaction.datetime_utc)
        .all()
    )

    # Pre-fetch asset symbols
    asset_symbols: dict[int, str] = {}
    for tx in txns:
        if tx.to_asset_id and tx.to_asset_id not in asset_symbols:
            sym = _asset_symbol_for_tx(db, tx)
            if sym:
                asset_symbols[tx.to_asset_id] = sym

    # Count deposits and total USD per (year, wallet_id, asset_id) for pattern detection
    freq: dict[tuple[int, int | None, int | None], int] = defaultdict(int)
    value_totals: dict[tuple[int, int | None, int | None], float] = defaultdict(float)
    for tx in txns:
        year = tx.datetime_utc.year
        key = (year, tx.to_wallet_id, tx.to_asset_id)
        freq[key] += 1
        if tx.to_value_usd:
            try:
                value_totals[key] += float(tx.to_value_usd)
            except (ValueError, TypeError):
                pass

    changes: list[dict] = []

    for tx in txns:
        symbol = asset_symbols.get(tx.to_asset_id, "") if tx.to_asset_id else ""
        new_type: str | None = None
        reason: str = ""

        # Rule 1: Known liquid staking tokens → staking_reward
        if symbol.upper() in STAKING_REWARD_ASSETS:
            new_type = "staking_reward"
            reason = f"liquid staking token ({symbol})"

        # Rule 2: Description contains interest keywords → interest
        elif tx.description and any(kw in tx.description.lower() for kw in INTEREST_KEYWORDS):
            new_type = "interest"
            reason = f"description contains interest keyword ('{tx.description}')"

        # Rule 3: High-frequency deposits (>=7/year) of same asset to same wallet
        # → staking_reward (pattern matches daily/weekly staking accruals)
        elif not new_type:
            year = tx.datetime_utc.year
            key = (year, tx.to_wallet_id, tx.to_asset_id)
            count = freq.get(key, 0)
            if count >= HIGH_FREQ_THRESHOLD:
                new_type = "staking_reward"
                reason = f"high-frequency pattern ({count} deposits/year of {symbol})"

        # Rule 4: Small-value repeated deposits (likely interest/yield accruals)
        # e.g., many tiny USDC deposits from DeFi lending
        if not new_type:
            year = tx.datetime_utc.year
            key = (year, tx.to_wallet_id, tx.to_asset_id)
            count = freq.get(key, 0)
            total_usd = value_totals.get(key, 0.0)
            if count >= SMALL_VALUE_MIN_COUNT and 0 < total_usd < SMALL_VALUE_INTEREST_THRESHOLD_USD:
                new_type = "interest"
                reason = f"small-value repeated deposits ({count}x, ${total_usd:.2f} total of {symbol})"

        if new_type:
            changes.append({
                "id": tx.id,
                "date": tx.datetime_utc.isoformat(),
                "asset": symbol,
                "old_type": tx.type,
                "new_type": new_type,
                "reason": reason,
            })
            if not dry_run:
                tx.type = new_type

    return changes
