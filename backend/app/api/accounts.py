import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Transaction, Wallet
from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from app.services.address_validator import validate_address, detect_blockchain
from app.services.blockchain_sync import sync_account, is_sync_in_progress

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_wallet_or_404(wallet_id: int, db: Session) -> Wallet:
    wallet = db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet


def _get_account_or_404(account_id: int, wallet_id: int, db: Session) -> Account:
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.wallet_id == wallet_id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.get("/{wallet_id}/accounts", response_model=list[AccountResponse])
def list_accounts(
    wallet_id: int,
    include_archived: bool = False,
    db: Session = Depends(get_db),
):
    _get_wallet_or_404(wallet_id, db)
    query = db.query(Account).filter(Account.wallet_id == wallet_id)
    if not include_archived:
        query = query.filter(Account.is_archived == False)
    return query.order_by(Account.name).all()


@router.post("/{wallet_id}/accounts", response_model=AccountResponse, status_code=201)
def create_account(
    wallet_id: int, data: AccountCreate, db: Session = Depends(get_db)
):
    wallet = _get_wallet_or_404(wallet_id, db)

    if wallet.category != "wallet":
        raise HTTPException(
            status_code=400,
            detail="Accounts can only be added to wallets, not exchanges",
        )

    # Validate address (auto-detect blockchain if unknown)
    chain = data.blockchain.lower().strip()
    if chain not in ("bitcoin", "ethereum", "solana", "cosmos", "litecoin"):
        detected = detect_blockchain(data.address)
        if detected:
            chain = detected
    is_valid, error_msg = validate_address(chain, data.address)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid address: {error_msg}")

    account = Account(
        wallet_id=wallet_id,
        name=data.name,
        address=data.address,
        blockchain=chain,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.put(
    "/{wallet_id}/accounts/{account_id}", response_model=AccountResponse
)
def update_account(
    wallet_id: int,
    account_id: int,
    data: AccountUpdate,
    db: Session = Depends(get_db),
):
    account = _get_account_or_404(account_id, wallet_id, db)

    update_data = data.model_dump(exclude_unset=True)

    # Validate address if being updated (auto-detect blockchain if unknown)
    if "address" in update_data and update_data["address"]:
        chain = update_data.get("blockchain", account.blockchain) or ""
        chain = chain.lower().strip()
        if chain not in ("bitcoin", "ethereum", "solana", "cosmos", "litecoin"):
            detected = detect_blockchain(update_data["address"])
            if detected:
                chain = detected
                update_data["blockchain"] = chain
        if chain:
            is_valid, error_msg = validate_address(chain, update_data["address"])
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"Invalid address: {error_msg}")

    # Handle move to a different wallet
    if "wallet_id" in update_data and update_data["wallet_id"] is not None:
        new_wallet_id = update_data["wallet_id"]
        if new_wallet_id != account.wallet_id:
            new_wallet = db.get(Wallet, new_wallet_id)
            if not new_wallet:
                raise HTTPException(status_code=400, detail="Target wallet not found")
            if new_wallet.category != "wallet":
                raise HTTPException(status_code=400, detail="Accounts can only be moved to wallets, not exchanges")
            old_wallet_id = account.wallet_id
            account.wallet_id = new_wallet_id
            # Reassign transactions: update wallet references where account was source/dest
            db.query(Transaction).filter(
                Transaction.from_account_id == account.id,
                Transaction.from_wallet_id == old_wallet_id,
            ).update({"from_wallet_id": new_wallet_id})
            db.query(Transaction).filter(
                Transaction.to_account_id == account.id,
                Transaction.to_wallet_id == old_wallet_id,
            ).update({"to_wallet_id": new_wallet_id})

    for field in ("name", "address", "blockchain", "is_archived"):
        if field in update_data:
            value = update_data[field]
            if field == "blockchain" and value:
                value = value.lower().strip()
            setattr(account, field, value)

    db.commit()
    db.refresh(account)
    return account


@router.delete("/{wallet_id}/accounts/{account_id}")
def delete_account(
    wallet_id: int, account_id: int, db: Session = Depends(get_db)
):
    account = _get_account_or_404(account_id, wallet_id, db)
    db.delete(account)
    db.commit()
    return {"detail": "Account deleted"}


@router.post("/{wallet_id}/accounts/{account_id}/sync")
async def trigger_account_sync(
    wallet_id: int, account_id: int, db: Session = Depends(get_db)
):
    """Sync account transactions from the blockchain."""
    account = _get_account_or_404(account_id, wallet_id, db)

    if not account.address or not account.blockchain:
        raise HTTPException(
            status_code=400,
            detail="Account must have both address and blockchain set to sync",
        )

    if is_sync_in_progress(account.id):
        raise HTTPException(status_code=409, detail="Sync already in progress for this account")

    try:
        result = await sync_account(db, account)
        return {
            "status": "completed",
            "imported": result["imported"],
            "skipped": result["skipped"],
            "errors": result["errors"],
            "error_messages": result.get("error_messages", []),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.exception("Sync failed for account %d", account_id)
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}")


@router.get("/{wallet_id}/accounts/{account_id}/sync-status")
def get_account_sync_status(
    wallet_id: int, account_id: int, db: Session = Depends(get_db)
):
    """Get the sync status for an account."""
    account = _get_account_or_404(account_id, wallet_id, db)
    return {
        "account_id": account.id,
        "last_synced_at": account.last_synced_at.isoformat() if account.last_synced_at else None,
        "sync_in_progress": is_sync_in_progress(account.id),
        "has_address": bool(account.address and account.blockchain),
    }
