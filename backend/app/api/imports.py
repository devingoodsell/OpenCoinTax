import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, ImportLog, ImportStatus, Transaction, TaxLot, LotAssignment
from app.schemas.import_ import (
    CsvUploadResponse,
    ImportConfirmRequest,
    ImportLogListResponse,
    ImportLogResponse,
    ImportResultResponse,
    KoinlyConfirmRequest,
    KoinlyConfirmResponse,
    KoinlyPreviewResponse,
    KoinlyWalletPreview,
    ParsedRow as ParsedRowSchema,
    WalletOption,
)
from app.services.csv_parser import parse_csv, import_parsed_rows, ParsedRow, ParseResult
from app.services.dedup import check_duplicates
from app.services.import_session_service import (
    create_session as create_import_session,
    get_session as get_import_session,
    get_preview_data,
    delete_session as delete_import_session,
)
from app.services.koinly_import import (
    KoinlyPreviewResult,
    confirm_koinly_import,
    preview_koinly_import,
)
from app.services.deposit_withdrawal_matcher import (
    find_deposit_withdrawal_pairs,
    find_duplicate_deposit_withdrawal_pairs,
)
from app.services.tax_engine import recalculate_all

router = APIRouter()


def _flag_existing_duplicates(db: Session, result) -> None:
    """Mark parsed rows as 'duplicate' warnings if they already exist in the DB.

    Uses two strategies:
    1. tx_hash batch matching (fast, exact)
    2. Fuzzy matching: datetime within 60s + same amounts (catches cross-source
       duplicates where Koinly and Coinbase use different tx_hash systems)

    Modifies rows in-place and updates the result counts.
    """
    from datetime import timedelta

    def _mark_duplicate(r):
        r.status = "warning"
        r.error_message = "Skipped: duplicate (already imported)"
        result.valid_rows -= 1
        result.warning_rows += 1

    # --- Phase 1: tx_hash matching ---
    hash_to_rows: dict[str, list] = {}
    for r in result.rows:
        if r.status == "valid" and r.tx_hash:
            hash_to_rows.setdefault(r.tx_hash, []).append(r)

    if hash_to_rows:
        existing_hashes: set[str] = set()
        all_hashes = list(hash_to_rows.keys())

        chunk_size = 500
        for i in range(0, len(all_hashes), chunk_size):
            chunk = all_hashes[i : i + chunk_size]
            matches = (
                db.query(Transaction.tx_hash)
                .filter(Transaction.tx_hash.in_(chunk))
                .all()
            )
            existing_hashes.update(m[0] for m in matches)

        for tx_hash in existing_hashes:
            for r in hash_to_rows.get(tx_hash, []):
                _mark_duplicate(r)

    # --- Phase 2: fuzzy matching for remaining valid rows ---
    # Catches cross-source duplicates (e.g. Koinly-imported tx vs Coinbase CSV)
    # Uses approximate amount matching (within 1%) to handle fee differences
    # (e.g. Coinbase withdrawal 0.50000588 BTC ≈ transfer 0.5 BTC)
    remaining = [r for r in result.rows if r.status == "valid" and r.datetime_utc]
    if not remaining:
        return

    from decimal import Decimal, InvalidOperation

    def _approx_eq(a_str: str, b_dec) -> bool:
        """Check if two amounts are approximately equal (within 1%)."""
        try:
            a = Decimal(a_str)
            b = Decimal(str(b_dec))
        except (InvalidOperation, TypeError):
            return False
        if a == b:
            return True
        if a == 0 or b == 0:
            return False
        ratio = abs(a - b) / max(abs(a), abs(b))
        return ratio < Decimal("0.01")  # within 1%

    # Build asset symbol lookup for asset-aware matching
    _asset_cache: dict[int, str] = {}

    def _get_asset_symbol(asset_id: int | None) -> str | None:
        if asset_id is None:
            return None
        if asset_id not in _asset_cache:
            a = db.query(Asset).filter_by(id=asset_id).first()
            _asset_cache[asset_id] = a.symbol if a else ""
        return _asset_cache[asset_id] or None

    # Fiat asset IDs — fiat amounts often differ between sources (fees included vs not)
    _fiat_ids: set[int] = {
        a.id for a in db.query(Asset).filter(Asset.is_fiat == True).all()
    }
    _fiat_symbols: set[str] = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY"}

    # Known symbol aliases (Coinbase vs Koinly name differences)
    _SYMBOL_ALIASES: dict[str, str] = {
        "CGLD": "CELO",
    }

    def _normalize_symbol(sym: str) -> str:
        s = sym.upper()
        return _SYMBOL_ALIASES.get(s, s)

    def _assets_overlap(r, tx) -> bool:
        """Check if parsed row and existing tx share at least one non-fiat asset."""
        r_assets = set()
        if r.from_asset:
            r_assets.add(_normalize_symbol(r.from_asset))
        if r.to_asset:
            r_assets.add(_normalize_symbol(r.to_asset))

        tx_assets = set()
        for aid in (tx.from_asset_id, tx.to_asset_id):
            sym = _get_asset_symbol(aid)
            if sym:
                tx_assets.add(_normalize_symbol(sym))

        return bool(r_assets & tx_assets)

    def _is_fiat_amount(r_asset: str | None, tx_asset_id: int | None) -> bool:
        """Check if an amount is fiat (USD, EUR, etc.)."""
        if r_asset and r_asset.upper() in _fiat_symbols:
            return True
        if tx_asset_id and tx_asset_id in _fiat_ids:
            return True
        return False

    def _amounts_match(r, tx) -> bool:
        """Check if a parsed row's amounts match an existing transaction.

        For buys/sells, the fiat (USD) amount often differs between Coinbase
        (includes fees) and Koinly (excludes fees). So we only require
        non-fiat amounts to match. If any non-fiat amount matches approximately,
        it's a duplicate.
        """
        # Collect non-fiat amount pairs for direct comparison
        non_fiat_checks = 0
        non_fiat_matches = 0

        # Direct pair matching (from↔from, to↔to)
        if r.from_amount and tx.from_amount:
            is_fiat = _is_fiat_amount(r.from_asset, tx.from_asset_id)
            if not is_fiat:
                non_fiat_checks += 1
                if _approx_eq(r.from_amount, tx.from_amount):
                    non_fiat_matches += 1
        if r.to_amount and tx.to_amount:
            is_fiat = _is_fiat_amount(r.to_asset, tx.to_asset_id)
            if not is_fiat:
                non_fiat_checks += 1
                if _approx_eq(r.to_amount, tx.to_amount):
                    non_fiat_matches += 1

        # If we found non-fiat amounts and they all match, it's a duplicate
        if non_fiat_checks > 0 and non_fiat_matches == non_fiat_checks:
            return True

        # If no direct pairs matched, try cross-matching
        # (e.g. withdrawal from_amount vs transfer to_amount)
        r_amounts = []
        if r.from_amount and not _is_fiat_amount(r.from_asset, None):
            r_amounts.append(r.from_amount)
        if r.to_amount and not _is_fiat_amount(r.to_asset, None):
            r_amounts.append(r.to_amount)

        tx_amounts = []
        if tx.from_amount and tx.from_asset_id not in _fiat_ids:
            tx_amounts.append(tx.from_amount)
        if tx.to_amount and tx.to_asset_id not in _fiat_ids:
            tx_amounts.append(tx.to_amount)

        for ra in r_amounts:
            for ta in tx_amounts:
                if _approx_eq(ra, ta):
                    return True

        # Fallback: if ALL amounts are fiat (e.g. USD deposit), check those too
        if not r_amounts and not tx_amounts:
            all_checks = 0
            all_matches = 0
            if r.from_amount and tx.from_amount:
                all_checks += 1
                if _approx_eq(r.from_amount, tx.from_amount):
                    all_matches += 1
            if r.to_amount and tx.to_amount:
                all_checks += 1
                if _approx_eq(r.to_amount, tx.to_amount):
                    all_matches += 1
            if all_checks > 0 and all_matches == all_checks:
                return True

        return False

    # Find the time range we need to query.
    # Use a 90-minute window: Coinbase records send-initiation time while
    # blockchain records confirmation time (BTC can take 30-60+ min, ATOM ~77 min).
    # Asset + approximate amount matching prevents false positives.
    min_dt = min(r.datetime_utc for r in remaining)
    max_dt = max(r.datetime_utc for r in remaining)
    window = timedelta(minutes=90)

    # Batch-load candidate transactions in the time window
    candidates = (
        db.query(Transaction)
        .filter(
            Transaction.datetime_utc >= min_dt - window,
            Transaction.datetime_utc <= max_dt + window,
        )
        .all()
    )

    if not candidates:
        return

    for r in remaining:
        if r.status != "valid":
            continue
        r_dt = r.datetime_utc
        for tx in candidates:
            # Time must be within 90 minutes
            if abs((tx.datetime_utc - r_dt).total_seconds()) > 5400:
                continue
            # Assets must overlap and amounts must approximately match
            if _assets_overlap(r, tx) and _amounts_match(r, tx):
                _mark_duplicate(r)
                break


@router.post("/csv", response_model=CsvUploadResponse)
async def upload_csv(file: UploadFile, db: Session = Depends(get_db)):
    """Accept a CSV file upload, parse it, and return a preview of the rows."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content_bytes = await file.read()
    try:
        file_content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            file_content = content_bytes.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Unable to decode file. Please use UTF-8.")

    result = parse_csv(file_content)

    # Flag rows that already exist in the database as duplicates.
    # Collect tx_hashes from valid rows, batch-query for existing matches,
    # then mark matching rows as warnings so the preview shows them.
    _flag_existing_duplicates(db, result)

    # Persist the parse result in DB so /csv/confirm can retrieve it
    parse_id = create_import_session(db, "csv", result.to_dict())
    db.commit()

    rows_out = []
    for r in result.rows:
        rows_out.append(ParsedRowSchema(
            row_number=r.row_number,
            status=r.status,
            error_message=r.error_message,
            datetime_utc=r.datetime_utc,
            type=r.tx_type,
            from_amount=r.from_amount,
            from_asset=r.from_asset,
            to_amount=r.to_amount,
            to_asset=r.to_asset,
            fee_amount=r.fee_amount,
            fee_asset=r.fee_asset,
            net_value_usd=r.net_value_usd,
            label=r.label,
            description=r.description,
            tx_hash=r.tx_hash,
        ))

    return CsvUploadResponse(
        detected_format=result.detected_format,
        total_rows=result.total_rows,
        valid_rows=result.valid_rows,
        warning_rows=result.warning_rows,
        error_rows=result.error_rows,
        rows=rows_out,
    )


@router.post("/csv/confirm", response_model=ImportResultResponse)
def confirm_csv_import(
    body: ImportConfirmRequest,
    db: Session = Depends(get_db),
):
    """Import previously parsed CSV rows after user confirmation.

    Runs dedup against existing transactions, then inserts new ones.
    """
    wallet_id = body.wallet_id
    selected_row_numbers = set(body.rows)

    # Retrieve the DB-backed import session
    parse_data = None
    parse_key = None

    # Try session_id from body first (if provided), else scan recent sessions
    from app.models.import_session import ImportSession
    sessions = (
        db.query(ImportSession)
        .filter_by(session_type="csv")
        .order_by(ImportSession.created_at.desc())
        .limit(10)
        .all()
    )
    for sess in sessions:
        import json as _json
        data = _json.loads(sess.preview_data)
        available = {r["row_number"] for r in data.get("rows", [])}
        if selected_row_numbers.issubset(available) or not selected_row_numbers:
            parse_data = data
            parse_key = sess.session_token
            break

    if parse_data is None:
        raise HTTPException(
            status_code=404,
            detail="No pending CSV parse found. Please upload the CSV again.",
        )

    parse_result = ParseResult.from_dict(parse_data)

    # Determine source based on detected format
    is_ledger = parse_result.detected_format == "ledger"
    is_coinbase = parse_result.detected_format == "coinbase"
    if is_ledger:
        source = "ledger_import"
    elif is_coinbase:
        source = "coinbase_import"
    else:
        source = "csv_import"

    # Filter to user-selected rows (and only valid/warning rows)
    if selected_row_numbers:
        chosen_rows = [
            r for r in parse_result.rows
            if r.row_number in selected_row_numbers and r.status != "error"
        ]
    else:
        chosen_rows = [r for r in parse_result.rows if r.status != "error"]

    # Dedup check — Ledger imports use tx_hash enrichment in import_parsed_rows,
    # so we skip the general dedup here to avoid false positives.
    # Coinbase and generic CSV imports run full dedup (tx_hash + fuzzy matching).
    if is_ledger:
        new_rows = chosen_rows
        duplicates = []
    else:
        new_rows, duplicates = check_duplicates(db, chosen_rows, wallet_id)

    # Create import log
    import_log = ImportLog(
        import_type=source,
        wallet_id=wallet_id,
        filename=None,
        status=ImportStatus.processing.value,
        transactions_imported=0,
        transactions_skipped=0,
    )
    db.add(import_log)
    db.flush()

    # Import the non-duplicate rows
    try:
        imported, skipped, errors = import_parsed_rows(
            db, new_rows, wallet_id, source=source, import_log_id=import_log.id
        )
    except Exception as exc:
        import_log.status = ImportStatus.failed.value
        import_log.errors = str(exc)
        import_log.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}")

    skipped += len(duplicates)

    import_log.status = ImportStatus.completed.value
    import_log.transactions_imported = imported
    import_log.transactions_skipped = skipped
    import_log.errors = json.dumps(errors) if errors else None
    import_log.completed_at = datetime.now(timezone.utc)
    db.commit()

    # Clean up the import session
    if parse_key:
        delete_import_session(db, parse_key)
        db.commit()

    return ImportResultResponse(
        import_log_id=import_log.id,
        transactions_imported=imported,
        transactions_skipped=skipped,
        errors=errors,
    )


@router.get("/logs", response_model=ImportLogListResponse)
def list_import_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(ImportLog).order_by(ImportLog.started_at.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return ImportLogListResponse(
        items=[ImportLogResponse.model_validate(i) for i in items],
        total=total,
    )


@router.delete("/logs/{log_id}")
def delete_import(log_id: int, db: Session = Depends(get_db)):
    """Delete an import and all transactions it created.

    Also cleans up associated tax lots and lot assignments, then
    triggers a full tax recalculation.
    """
    import_log = db.query(ImportLog).filter_by(id=log_id).first()
    if not import_log:
        raise HTTPException(status_code=404, detail="Import log not found")

    # Find all transactions linked to this import
    txs = db.query(Transaction).filter_by(import_log_id=log_id).all()
    tx_ids = [tx.id for tx in txs]

    deleted_count = len(tx_ids)

    if tx_ids:
        # Delete lot assignments where the disposal tx is from this import
        db.query(LotAssignment).filter(
            LotAssignment.disposal_tx_id.in_(tx_ids)
        ).delete(synchronize_session=False)

        # Delete tax lots created by transactions from this import
        db.query(TaxLot).filter(
            TaxLot.acquisition_tx_id.in_(tx_ids)
        ).delete(synchronize_session=False)

        # Delete the transactions themselves
        db.query(Transaction).filter(
            Transaction.id.in_(tx_ids)
        ).delete(synchronize_session=False)

    # Delete the import log
    db.delete(import_log)
    db.commit()

    # Recalculate tax after removing transactions
    if deleted_count > 0:
        try:
            recalculate_all(db)
        except Exception:
            pass  # Don't fail the delete if recalc has issues

    return {
        "deleted": True,
        "transactions_deleted": deleted_count,
        "import_log_id": log_id,
    }


# ---------------------------------------------------------------------------
# Koinly full-import endpoints
# ---------------------------------------------------------------------------


async def _decode_upload(file: UploadFile) -> str:
    """Read and decode an uploaded file to a string."""
    content_bytes = await file.read()
    try:
        return content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return content_bytes.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Unable to decode file. Please use UTF-8.")


@router.post("/koinly", response_model=KoinlyPreviewResponse)
async def upload_koinly(
    wallets_file: UploadFile = File(...),
    transactions_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload Koinly wallet + transaction CSVs and return a preview."""
    wallets_content = await _decode_upload(wallets_file)
    transactions_content = await _decode_upload(transactions_file)

    preview = preview_koinly_import(db, wallets_content, transactions_content)

    # Persist preview in DB for confirmation
    preview_id = create_import_session(db, "koinly", preview.to_dict())
    db.commit()

    wallet_previews = [
        KoinlyWalletPreview(
            koinly_id=w.koinly_id,
            name=w.name,
            koinly_type=w.koinly_type,
            mapped_type=w.mapped_type,
            blockchain=w.blockchain,
            is_duplicate=w.is_duplicate,
        )
        for w in preview.wallets
    ]

    existing_wallets_list = [
        WalletOption(id=ew.id, name=ew.name, type=ew.type, category=ew.category)
        for ew in preview.existing_wallets_list
    ]

    return KoinlyPreviewResponse(
        total_wallets=preview.total_wallets,
        new_wallets=preview.new_wallets,
        existing_wallets=preview.existing_wallets,
        total_transactions=preview.total_transactions,
        valid_transactions=preview.valid_transactions,
        duplicate_transactions=preview.duplicate_transactions,
        error_transactions=preview.error_transactions,
        warning_transactions=preview.warning_transactions,
        wallets=wallet_previews,
        existing_wallets_list=existing_wallets_list,
        errors=preview.errors,
    )


@router.post("/koinly/confirm", response_model=KoinlyConfirmResponse)
def confirm_koinly(body: KoinlyConfirmRequest, db: Session = Depends(get_db)):
    """Commit the most recent Koinly import preview to the database."""
    from app.models.import_session import ImportSession
    import json as _json

    # Find the most recent koinly import session
    sess = (
        db.query(ImportSession)
        .filter_by(session_type="koinly")
        .order_by(ImportSession.created_at.desc())
        .first()
    )
    if sess is None:
        raise HTTPException(
            status_code=404,
            detail="No pending Koinly import found. Please upload the CSV files again.",
        )

    preview_key = sess.session_token
    preview = KoinlyPreviewResult.from_dict(_json.loads(sess.preview_data))
    delete_import_session(db, preview_key)

    # Validate that all Koinly wallets have a mapping
    koinly_ids_in_wallets = {pw.koinly_id for pw in preview.wallets}
    missing = koinly_ids_in_wallets - set(body.wallet_mapping.keys())
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing wallet mapping for Koinly IDs: {', '.join(sorted(missing))}",
        )

    try:
        wallets_created, wallets_skipped, accounts_created, txs_imported, txs_skipped, errors = (
            confirm_koinly_import(db, preview, body.wallet_mapping)
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Koinly import failed: {exc}")

    # Auto-match orphan deposit-withdrawal pairs as transfers
    if txs_imported > 0:
        try:
            find_duplicate_deposit_withdrawal_pairs(db, dry_run=False)
            find_deposit_withdrawal_pairs(db, dry_run=False)
            db.commit()
        except Exception:
            pass  # Don't fail the import if matching has issues

    # Auto-run tax calculation across all years
    if txs_imported > 0:
        try:
            recalculate_all(db)
        except Exception:
            pass  # Don't fail the import if tax calc has issues

    return KoinlyConfirmResponse(
        wallets_created=wallets_created,
        wallets_skipped=wallets_skipped,
        accounts_created=accounts_created,
        transactions_imported=txs_imported,
        transactions_skipped=txs_skipped,
        errors=errors,
    )


@router.post("/match-deposits")
def match_deposit_withdrawals(
    dry_run: bool = Query(True, description="Preview matches without applying changes"),
    db: Session = Depends(get_db),
):
    """Match orphan deposits with withdrawals and convert to transfers.

    Run with dry_run=true (default) to preview matches, then dry_run=false to apply.
    After applying, triggers a full tax recalculation.
    """
    duplicates = find_duplicate_deposit_withdrawal_pairs(db, dry_run=dry_run)
    matches = find_deposit_withdrawal_pairs(db, dry_run=dry_run)

    if not dry_run:
        db.commit()
        try:
            recalculate_all(db)
        except Exception:
            pass

    return {
        "dry_run": dry_run,
        "duplicate_pairs_found": len(duplicates),
        "transfer_pairs_found": len(matches),
        "duplicates": duplicates,
        "matches": matches,
    }
