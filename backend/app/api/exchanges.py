"""Exchange API connection and sync endpoints."""

import json
import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Wallet, Transaction, Asset
from app.models.exchange_connection import ExchangeConnection
from app.schemas.exchange_connection import ExchangeConnectionCreate, ExchangeConnectionResponse
from app.services.encryption import encrypt, decrypt
from app.services.exchange import EXCHANGE_ADAPTERS

logger = logging.getLogger(__name__)

router = APIRouter()

# Concurrent sync prevention
_exchange_sync_locks: dict[int, threading.Lock] = {}
_exchange_sync_in_progress: set[int] = set()


def _get_wallet_or_404(wallet_id: int, db: Session) -> Wallet:
    wallet = db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet


@router.post(
    "/{wallet_id}/exchange-connection",
    response_model=ExchangeConnectionResponse,
    status_code=201,
)
def create_exchange_connection(
    wallet_id: int,
    data: ExchangeConnectionCreate,
    db: Session = Depends(get_db),
):
    wallet = _get_wallet_or_404(wallet_id, db)

    if wallet.category != "exchange":
        raise HTTPException(
            status_code=400,
            detail="API connections can only be added to exchanges",
        )

    # Check if connection already exists
    existing = (
        db.query(ExchangeConnection)
        .filter(ExchangeConnection.wallet_id == wallet_id)
        .first()
    )
    if existing:
        # Update existing connection
        existing.exchange_type = data.exchange_type
        existing.api_key_encrypted = encrypt(data.api_key)
        existing.api_secret_encrypted = encrypt(data.api_secret)
        db.commit()
        db.refresh(existing)
        return existing

    conn = ExchangeConnection(
        wallet_id=wallet_id,
        exchange_type=data.exchange_type,
        api_key_encrypted=encrypt(data.api_key),
        api_secret_encrypted=encrypt(data.api_secret),
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


@router.delete("/{wallet_id}/exchange-connection")
def delete_exchange_connection(
    wallet_id: int, db: Session = Depends(get_db)
):
    _get_wallet_or_404(wallet_id, db)
    conn = (
        db.query(ExchangeConnection)
        .filter(ExchangeConnection.wallet_id == wallet_id)
        .first()
    )
    if not conn:
        raise HTTPException(status_code=404, detail="No exchange connection found")
    db.delete(conn)
    db.commit()
    return {"detail": "Exchange connection deleted"}


@router.post("/{wallet_id}/exchange-sync")
async def trigger_exchange_sync(
    wallet_id: int, db: Session = Depends(get_db)
):
    """Sync transactions from exchange API."""
    wallet = _get_wallet_or_404(wallet_id, db)

    if wallet.category != "exchange":
        raise HTTPException(status_code=400, detail="Only exchanges can be synced via API")

    conn = (
        db.query(ExchangeConnection)
        .filter(ExchangeConnection.wallet_id == wallet_id)
        .first()
    )
    if not conn:
        raise HTTPException(
            status_code=400,
            detail="No API connection configured for this exchange",
        )

    # Concurrent sync prevention
    if wallet_id in _exchange_sync_in_progress:
        raise HTTPException(status_code=409, detail="Sync already in progress")

    if wallet_id not in _exchange_sync_locks:
        _exchange_sync_locks[wallet_id] = threading.Lock()

    lock = _exchange_sync_locks[wallet_id]
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Sync already in progress")

    _exchange_sync_in_progress.add(wallet_id)
    try:
        adapter_cls = EXCHANGE_ADAPTERS.get(conn.exchange_type)
        if not adapter_cls:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported exchange type: {conn.exchange_type}",
            )

        api_key = decrypt(conn.api_key_encrypted)
        api_secret = decrypt(conn.api_secret_encrypted)
        adapter = adapter_cls(api_key=api_key, api_secret=api_secret)

        since = conn.last_synced_at
        raw_txs = await adapter.fetch_transactions(since=since)

        result = {"imported": 0, "skipped": 0, "errors": 0, "error_messages": []}

        for raw_tx in raw_txs:
            try:
                # Deduplication via tx_hash + wallet_id
                existing = (
                    db.query(Transaction)
                    .filter(
                        Transaction.tx_hash == raw_tx.tx_hash,
                        (Transaction.from_wallet_id == wallet_id)
                        | (Transaction.to_wallet_id == wallet_id),
                    )
                    .first()
                )
                if existing:
                    result["skipped"] += 1
                    continue

                # Get or create asset
                asset = (
                    db.query(Asset)
                    .filter(Asset.symbol == raw_tx.asset_symbol)
                    .first()
                )
                if not asset:
                    asset = Asset(
                        symbol=raw_tx.asset_symbol,
                        name=raw_tx.asset_name,
                        is_fiat=False,
                    )
                    db.add(asset)
                    db.flush()

                # Create transaction
                tx = Transaction(
                    tx_hash=raw_tx.tx_hash,
                    datetime_utc=raw_tx.datetime_utc,
                    type=raw_tx.tx_type or "deposit",
                    source="exchange_sync",
                    raw_data=json.dumps(raw_tx.raw_data, default=str),
                )

                tx_type = raw_tx.tx_type or "deposit"
                if tx_type in ("withdrawal", "sell", "transfer"):
                    tx.from_wallet_id = wallet_id
                    tx.from_amount = str(raw_tx.amount)
                    tx.from_asset_id = asset.id
                if tx_type in ("deposit", "buy", "staking_reward", "interest", "trade", "transfer"):
                    tx.to_wallet_id = wallet_id
                    tx.to_amount = str(raw_tx.amount)
                    tx.to_asset_id = asset.id

                if raw_tx.fee > 0:
                    tx.fee_amount = str(raw_tx.fee)
                    tx.fee_asset_id = asset.id

                db.add(tx)
                db.flush()
                result["imported"] += 1

            except Exception as exc:
                result["errors"] += 1
                result["error_messages"].append(f"{raw_tx.tx_hash}: {exc}")
                logger.warning("Error importing exchange tx %s: %s", raw_tx.tx_hash, exc)

        # Update last_synced_at
        conn.last_synced_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "status": "completed",
            "imported": result["imported"],
            "skipped": result["skipped"],
            "errors": result["errors"],
            "error_messages": result["error_messages"],
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Exchange sync failed for wallet %d", wallet_id)
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}")
    finally:
        _exchange_sync_in_progress.discard(wallet_id)
        lock.release()
