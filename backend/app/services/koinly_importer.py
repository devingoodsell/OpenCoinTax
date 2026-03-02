"""Koinly import workflow — preview and confirm operations with DB persistence."""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Account, ImportLog, ImportStatus, Transaction, Wallet
from app.services.csv.transaction_builder import _resolve_asset
from app.services.koinly_parser import (
    ExistingWalletInfo,
    KoinlyPreviewResult,
    ParsedWallet,
    parse_transactions_csv,
    parse_wallets_csv,
)


# ---------------------------------------------------------------------------
# Preview (no DB writes)
# ---------------------------------------------------------------------------


def preview_koinly_import(
    db: Session,
    wallets_content: str,
    transactions_content: str,
) -> KoinlyPreviewResult:
    """Parse both CSV files and return a preview without committing."""
    result = KoinlyPreviewResult()

    # Parse wallets
    parsed_wallets = parse_wallets_csv(wallets_content)
    result.total_wallets = len(parsed_wallets)
    result.new_wallets = len(parsed_wallets)
    result.wallets = parsed_wallets

    # Query all existing (non-archived) wallets for the mapping dropdowns
    existing_wallets = (
        db.query(Wallet)
        .filter(Wallet.is_archived == False)
        .order_by(Wallet.name)
        .all()
    )
    result.existing_wallets_list = [
        ExistingWalletInfo(
            id=w.id,
            name=w.name,
            type=w.type,
            category=w.category,
        )
        for w in existing_wallets
    ]

    # Parse transactions
    parsed_txs = parse_transactions_csv(transactions_content)
    result.total_transactions = len(parsed_txs)

    # Check transaction dedup
    for pt in parsed_txs:
        if pt.status == "error":
            result.error_transactions += 1
            continue
        if pt.status == "warning":
            result.warning_transactions += 1

        if pt.koinly_tx_id:
            existing = (
                db.query(Transaction)
                .filter_by(koinly_tx_id=pt.koinly_tx_id)
                .first()
            )
            if existing:
                pt.is_duplicate = True
                result.duplicate_transactions += 1
                continue

        result.valid_transactions += 1

    result.transactions = parsed_txs

    return result


# ---------------------------------------------------------------------------
# Confirm (writes to DB)
# ---------------------------------------------------------------------------


def confirm_koinly_import(
    db: Session,
    preview: KoinlyPreviewResult,
    wallet_mapping: dict[str, int | str],
) -> tuple[int, int, int, int, int, list[str]]:
    """Commit the previewed import to the database.

    Args:
        wallet_mapping: dict of koinly_id -> existing wallet_id (int) or "new".

    Returns (wallets_created, wallets_skipped, accounts_created,
             txs_imported, txs_skipped, errors).
    """
    errors: list[str] = []

    # Build lookup of parsed wallets by koinly_id
    pw_by_koinly_id: dict[str, ParsedWallet] = {
        pw.koinly_id: pw for pw in preview.wallets
    }

    # Phase 1: Create/resolve wallets and accounts, build lookup maps
    koinly_to_wallet_id: dict[str, int] = {}
    koinly_to_account_id: dict[str, int] = {}
    wallets_created = 0
    wallets_skipped = 0
    accounts_created = 0

    for koinly_id, target in wallet_mapping.items():
        pw = pw_by_koinly_id.get(koinly_id)

        if target == "new":
            # Create a new wallet from the Koinly data
            if not pw:
                errors.append(f"No parsed wallet data for koinly_id={koinly_id}")
                continue
            wallet = Wallet(
                name=pw.name,
                type=pw.mapped_type,
                category=pw.mapped_type if pw.mapped_type == "exchange" else "wallet",
                koinly_wallet_id=koinly_id,
            )
            db.add(wallet)
            db.flush()
            wallet_id = wallet.id
            wallets_created += 1
        else:
            # Use existing wallet
            wallet_id = int(target)
            wallets_skipped += 1

        koinly_to_wallet_id[koinly_id] = wallet_id

        # Check for existing account with this name under the wallet
        existing_account = (
            db.query(Account)
            .filter(Account.wallet_id == wallet_id, Account.name == koinly_id)
            .first()
        )
        if existing_account:
            koinly_to_account_id[koinly_id] = existing_account.id
        else:
            blockchain = (pw.blockchain if pw else None) or "unknown"
            account = Account(
                wallet_id=wallet_id,
                name=koinly_id,
                address="",
                blockchain=blockchain,
            )
            db.add(account)
            db.flush()
            koinly_to_account_id[koinly_id] = account.id
            accounts_created += 1

    # Phase 2: Create import log first so we can link transactions to it
    import_log = ImportLog(
        import_type="koinly_import",
        wallet_id=None,
        filename="koinly_wallets.csv + koinly_transactions.csv",
        status=ImportStatus.processing.value,
        transactions_imported=0,
        transactions_skipped=0,
    )
    db.add(import_log)
    db.flush()

    # Phase 3: Create transactions
    txs_imported = 0
    txs_skipped = 0

    for pt in preview.transactions:
        if pt.status == "error" or pt.is_duplicate:
            txs_skipped += 1
            continue

        # Resolve account and wallet IDs via the koinly mapping
        from_account_id = None
        to_account_id = None
        from_wallet_id = None
        to_wallet_id = None

        if pt.from_wallet_koinly_id:
            from_account_id = koinly_to_account_id.get(pt.from_wallet_koinly_id)
            from_wallet_id = koinly_to_wallet_id.get(pt.from_wallet_koinly_id)
        if pt.to_wallet_koinly_id:
            to_account_id = koinly_to_account_id.get(pt.to_wallet_koinly_id)
            to_wallet_id = koinly_to_wallet_id.get(pt.to_wallet_koinly_id)

        # Resolve asset IDs
        from_asset_id = _resolve_asset(db, pt.from_asset) if pt.from_asset else None
        to_asset_id = _resolve_asset(db, pt.to_asset) if pt.to_asset else None
        fee_asset_id = _resolve_asset(db, pt.fee_asset) if pt.fee_asset else None

        tx = Transaction(
            datetime_utc=pt.datetime_utc,
            type=pt.tx_type or "deposit",
            from_wallet_id=from_wallet_id,
            to_wallet_id=to_wallet_id,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            from_amount=pt.from_amount,
            from_asset_id=from_asset_id,
            to_amount=pt.to_amount,
            to_asset_id=to_asset_id,
            fee_amount=pt.fee_amount,
            fee_asset_id=fee_asset_id,
            net_value_usd=pt.net_value_usd,
            from_value_usd=pt.from_value_usd,
            to_value_usd=pt.to_value_usd,
            label=pt.label,
            description=pt.description,
            tx_hash=pt.tx_hash,
            koinly_tx_id=pt.koinly_tx_id,
            source="koinly_import",
            raw_data=json.dumps(pt.raw_data),
            import_log_id=import_log.id,
        )
        db.add(tx)
        txs_imported += 1

    # Update import log with final counts
    import_log.status = ImportStatus.completed.value
    import_log.transactions_imported = txs_imported
    import_log.transactions_skipped = txs_skipped
    import_log.errors = json.dumps(errors) if errors else None
    import_log.completed_at = datetime.now(timezone.utc)

    db.commit()

    return wallets_created, wallets_skipped, accounts_created, txs_imported, txs_skipped, errors


# ---------------------------------------------------------------------------
# Backfill existing koinly-imported transactions
# ---------------------------------------------------------------------------

# Mapping of tx type -> which USD value field(s) to derive
_ACQUIRE_TYPES = {"buy", "deposit", "staking_reward", "interest", "airdrop",
                  "fork", "mining", "gift_received"}
_DISPOSE_TYPES = {"sell", "withdrawal", "cost", "gift_sent", "lost", "fee"}
_BOTH_TYPES = {"trade", "transfer"}


def backfill_koinly_usd_values(db: Session) -> int:
    """Backfill from_value_usd / to_value_usd on existing koinly_import transactions.

    Only touches rows where net_value_usd is set but the per-leg values are NULL.
    Returns the number of transactions updated.
    """
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.source == "koinly_import",
            Transaction.net_value_usd.isnot(None),
        )
        .all()
    )

    updated = 0
    for tx in txns:
        changed = False
        tx_type = tx.type

        if tx_type in _ACQUIRE_TYPES:
            if tx.to_value_usd is None:
                tx.to_value_usd = tx.net_value_usd
                changed = True
        elif tx_type in _DISPOSE_TYPES:
            if tx.from_value_usd is None:
                tx.from_value_usd = tx.net_value_usd
                changed = True
        elif tx_type in _BOTH_TYPES:
            if tx.from_value_usd is None:
                tx.from_value_usd = tx.net_value_usd
                changed = True
            if tx.to_value_usd is None:
                tx.to_value_usd = tx.net_value_usd
                changed = True

        if changed:
            updated += 1

    db.flush()
    return updated
