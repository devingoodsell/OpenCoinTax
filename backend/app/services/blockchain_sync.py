"""Blockchain sync orchestrator — validates, fetches, maps, deduplicates, persists."""

import json
import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.asset import Asset
from app.models.transaction import Transaction
from app.services.address_validator import validate_address
from app.services.blockchain import ADAPTERS
from app.services.blockchain.base import RawTransaction

logger = logging.getLogger(__name__)

# In-memory lock per account to prevent concurrent syncs
_sync_locks: dict[int, threading.Lock] = {}
_sync_in_progress: set[int] = set()


def is_sync_in_progress(account_id: int) -> bool:
    """Check if a sync is currently running for an account."""
    return account_id in _sync_in_progress


async def sync_account(db: Session, account: Account) -> dict:
    """Sync an account's transactions from the blockchain.

    Returns:
        Dict with keys: imported, skipped, errors, error_messages
    """
    # Validate account has address and blockchain
    if not account.address or not account.blockchain:
        raise ValueError("Account must have both address and blockchain set")

    chain = account.blockchain.lower().strip()
    if chain not in ADAPTERS:
        raise ValueError(f"Unsupported blockchain: {account.blockchain}")

    # Validate address
    is_valid, error_msg = validate_address(chain, account.address)
    if not is_valid:
        raise ValueError(f"Invalid address: {error_msg}")

    # Prevent concurrent syncs per account
    if account.id not in _sync_locks:
        _sync_locks[account.id] = threading.Lock()

    lock = _sync_locks[account.id]
    if not lock.acquire(blocking=False):
        raise RuntimeError("Sync already in progress for this account")

    _sync_in_progress.add(account.id)
    try:
        return await _do_sync(db, account, chain)
    finally:
        _sync_in_progress.discard(account.id)
        lock.release()


async def _do_sync(db: Session, account: Account, chain: str) -> dict:
    """Perform the actual sync."""
    result = {"imported": 0, "skipped": 0, "errors": 0, "error_messages": []}

    # Get or create the native asset
    adapter_cls = ADAPTERS[chain]
    adapter = adapter_cls()
    asset = _get_or_create_asset(db, adapter.native_asset_symbol, adapter.native_asset_name)

    # Fetch transactions from blockchain
    since = account.last_synced_at
    try:
        raw_txs = await adapter.fetch_transactions(account.address, since=since)
    except Exception as exc:
        logger.error("Failed to fetch transactions for account %d: %s", account.id, exc)
        raise

    # Map and persist
    for raw_tx in raw_txs:
        try:
            # Deduplication: check if tx_hash already exists for this account
            if _tx_exists(db, raw_tx.tx_hash, account.id):
                result["skipped"] += 1
                continue

            _create_transaction(db, account, raw_tx, asset)
            result["imported"] += 1
        except Exception as exc:
            result["errors"] += 1
            result["error_messages"].append(f"{raw_tx.tx_hash}: {exc}")
            logger.warning("Error importing tx %s: %s", raw_tx.tx_hash, exc)

    # Update last_synced_at on the account
    account.last_synced_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "Account %d sync complete: %d imported, %d skipped, %d errors",
        account.id, result["imported"], result["skipped"], result["errors"],
    )
    return result


def _get_or_create_asset(db: Session, symbol: str, name: str) -> Asset:
    """Get existing asset or create a new one."""
    asset = db.query(Asset).filter(Asset.symbol == symbol).first()
    if asset:
        return asset

    asset = Asset(symbol=symbol, name=name, is_fiat=False)
    db.add(asset)
    db.flush()
    return asset


def _tx_exists(db: Session, tx_hash: str, account_id: int) -> bool:
    """Check if a transaction with this hash already exists for this account."""
    return (
        db.query(Transaction)
        .filter(
            Transaction.tx_hash == tx_hash,
            (Transaction.from_account_id == account_id) | (Transaction.to_account_id == account_id),
        )
        .first()
        is not None
    )


def _create_transaction(
    db: Session, account: Account, raw_tx: RawTransaction, asset: Asset
) -> Transaction:
    """Map a RawTransaction to a Transaction and persist it."""
    # Determine direction and type
    address = account.address.lower() if account.address else ""

    if raw_tx.tx_type:
        tx_type = raw_tx.tx_type
    elif raw_tx.from_address and raw_tx.from_address.lower() == address:
        if raw_tx.to_address and raw_tx.to_address.lower() == address:
            tx_type = "transfer"
        else:
            tx_type = "withdrawal"
    else:
        tx_type = "deposit"

    # Build the transaction with both account and wallet references
    wallet_id = account.wallet_id
    tx = Transaction(
        tx_hash=raw_tx.tx_hash,
        datetime_utc=raw_tx.datetime_utc,
        type=tx_type,
        source="blockchain_sync",
        raw_data=json.dumps(raw_tx.raw_data, default=str),
    )

    # Set wallet and account based on direction
    if tx_type in ("withdrawal", "transfer"):
        tx.from_wallet_id = wallet_id
        tx.from_account_id = account.id
        tx.from_amount = str(raw_tx.amount)
        tx.from_asset_id = asset.id
    if tx_type in ("deposit", "staking_reward", "transfer"):
        tx.to_wallet_id = wallet_id
        tx.to_account_id = account.id
        tx.to_amount = str(raw_tx.amount)
        tx.to_asset_id = asset.id

    # Fee
    if raw_tx.fee > 0:
        tx.fee_amount = str(raw_tx.fee)
        tx.fee_asset_id = asset.id

    db.add(tx)
    db.flush()
    return tx
