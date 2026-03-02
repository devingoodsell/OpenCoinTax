"""Tax engine orchestrator — coordinates lot management and gain calculation."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models import (
    Asset, Transaction, TaxLot, LotAssignment, WalletCostBasisMethod, Setting,
    TransactionType, CostBasisMethod, LotSourceType,
    ACQUISITION_TYPES, DISPOSAL_TYPES, INCOME_TYPES,
)
from app.services.lot_selector import InsufficientLotsError
from app.services.tax.lot_manager import create_lot, get_open_lots
from app.services.tax.gain_calculator import (
    resolve_value_usd,
    process_acquisition,
    process_disposal,
)
from app.utils.decimal_helpers import ZERO, PENNY, to_decimal as _to_dec


def get_cost_basis_method(db: Session, wallet_id: int, tax_year: int) -> str:
    """Get the cost basis method for a wallet, falling back to the global default."""
    override = (
        db.query(WalletCostBasisMethod)
        .filter_by(wallet_id=wallet_id, tax_year=tax_year)
        .first()
    )
    if override:
        return override.cost_basis_method

    setting = db.get(Setting, "default_cost_basis_method")
    return setting.value if setting else CostBasisMethod.fifo.value


def _clear_errors_for_pair(db: Session, wallet_id: int, asset_id: int, tax_year: int):
    """Clear tax errors on transactions for a specific wallet+asset+year scope."""
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.datetime_utc >= datetime(tax_year, 1, 1),
            Transaction.datetime_utc < datetime(tax_year + 1, 1, 1),
            Transaction.has_tax_error == True,
        )
        .filter(
            ((Transaction.to_wallet_id == wallet_id) & (Transaction.to_asset_id == asset_id))
            | ((Transaction.from_wallet_id == wallet_id) & (Transaction.from_asset_id == asset_id))
        )
        .all()
    )
    for tx in txns:
        tx.tax_error = None
        tx.has_tax_error = False


def _tx_sort_priority(tx: Transaction, wallet_id: int, asset_id: int) -> int:
    """Assign sort priority so acquisitions process before disposals for same timestamp."""
    is_inflow = (tx.to_wallet_id == wallet_id and tx.to_asset_id == asset_id)
    is_outflow = (tx.from_wallet_id == wallet_id and tx.from_asset_id == asset_id)

    if is_inflow and not is_outflow:
        return 0
    if is_outflow and not is_inflow:
        return 1
    return 0


def calculate_for_wallet_asset(
    db: Session,
    wallet_id: int,
    asset_id: int,
    tax_year: int,
    method: str | None = None,
) -> dict:
    """Run the full cost basis calculation for a (wallet, asset) pair."""
    if method is None:
        method = get_cost_basis_method(db, wallet_id, tax_year)

    txns = (
        db.query(Transaction)
        .filter(
            Transaction.datetime_utc >= datetime(tax_year, 1, 1),
            Transaction.datetime_utc < datetime(tax_year + 1, 1, 1),
        )
        .filter(
            (
                (Transaction.to_wallet_id == wallet_id)
                & (Transaction.to_asset_id == asset_id)
            )
            |
            (
                (Transaction.from_wallet_id == wallet_id)
                & (Transaction.from_asset_id == asset_id)
            )
        )
        .order_by(Transaction.datetime_utc)
        .all()
    )

    txns.sort(key=lambda tx: (tx.datetime_utc, _tx_sort_priority(tx, wallet_id, asset_id)))

    total_gains = ZERO
    total_losses = ZERO
    total_income = ZERO
    error_count = 0

    for tx in txns:
        tx_type = tx.type

        # --- Withdrawal handling (taxable disposal) ---
        if tx_type == TransactionType.withdrawal.value:
            if tx.from_wallet_id == wallet_id and tx.from_asset_id == asset_id:
                amount = _to_dec(tx.from_amount)
                proceeds = resolve_value_usd(tx.from_value_usd, tx.net_value_usd)
                try:
                    assignments = process_disposal(
                        db, tx, wallet_id, asset_id, amount, proceeds, method, tax_year
                    )
                except InsufficientLotsError as exc:
                    tx.tax_error = str(exc)
                    tx.has_tax_error = True
                    error_count += 1
                    assignments = []
                for a in assignments:
                    gl = Decimal(a.gain_loss_usd)
                    if gl > ZERO:
                        total_gains += gl
                    else:
                        total_losses += abs(gl)
            continue

        # --- Transfer handling ---
        if tx_type == TransactionType.transfer.value:
            if tx.from_wallet_id == wallet_id and tx.from_asset_id == asset_id:
                from app.services.transfer_handler import process_transfer
                try:
                    process_transfer(db, tx, tax_year)
                except (InsufficientLotsError, ValueError) as exc:
                    tx.tax_error = str(exc)
                    tx.has_tax_error = True
                    error_count += 1
            elif tx.to_wallet_id == wallet_id and tx.to_asset_id == asset_id:
                existing = db.query(TaxLot).filter_by(
                    acquisition_tx_id=tx.id, wallet_id=wallet_id
                ).first()
                if not existing:
                    amount = _to_dec(tx.to_amount)
                    cost_basis = _to_dec(tx.from_value_usd or tx.to_value_usd or tx.net_value_usd)
                    fee_usd = _to_dec(tx.fee_value_usd)
                    create_lot(
                        db,
                        wallet_id=wallet_id,
                        asset_id=asset_id,
                        amount=amount,
                        cost_basis_usd=cost_basis + fee_usd,
                        acquired_date=tx.datetime_utc,
                        acquisition_tx_id=tx.id,
                        source_type=LotSourceType.transfer_in.value,
                    )
            continue

        # --- Acquisition into this wallet ---
        if (
            tx_type in {t.value for t in ACQUISITION_TYPES}
            and tx.to_wallet_id == wallet_id
            and tx.to_asset_id == asset_id
        ):
            amount = _to_dec(tx.to_amount)
            value_usd = resolve_value_usd(tx.to_value_usd, tx.net_value_usd)
            process_acquisition(db, tx, wallet_id, asset_id, amount, value_usd)

            if tx_type in {t.value for t in INCOME_TYPES}:
                total_income += value_usd

        # --- Wrapping swap: non-taxable basis carry-over ---
        if tx_type == TransactionType.trade.value:
            from app.services.wrapping_swap_handler import is_wrapping_swap, process_wrapping_swap
            if is_wrapping_swap(db, tx):
                if tx.from_wallet_id == wallet_id and tx.from_asset_id == asset_id:
                    try:
                        process_wrapping_swap(db, tx, tax_year)
                    except (InsufficientLotsError, ValueError) as exc:
                        tx.tax_error = str(exc)
                        tx.has_tax_error = True
                        error_count += 1
                elif tx.to_wallet_id == wallet_id and tx.to_asset_id == asset_id:
                    existing = db.query(TaxLot).filter_by(
                        acquisition_tx_id=tx.id, wallet_id=wallet_id, asset_id=asset_id
                    ).first()
                    if not existing:
                        amount = _to_dec(tx.to_amount)
                        cost_basis = _to_dec(tx.to_value_usd or tx.net_value_usd)
                        create_lot(
                            db,
                            wallet_id=wallet_id,
                            asset_id=asset_id,
                            amount=amount,
                            cost_basis_usd=cost_basis,
                            acquired_date=tx.datetime_utc,
                            acquisition_tx_id=tx.id,
                            source_type=LotSourceType.wrapping_swap.value,
                        )
                continue

        # --- Trade: disposal of from-asset, acquisition of to-asset ---
        if tx_type == TransactionType.trade.value:
            if tx.from_wallet_id == wallet_id and tx.from_asset_id == asset_id:
                amount = _to_dec(tx.from_amount)
                proceeds = resolve_value_usd(tx.from_value_usd, tx.net_value_usd)
                try:
                    assignments = process_disposal(
                        db, tx, wallet_id, asset_id, amount, proceeds, method, tax_year
                    )
                except InsufficientLotsError as exc:
                    tx.tax_error = str(exc)
                    tx.has_tax_error = True
                    error_count += 1
                    assignments = []
                for a in assignments:
                    gl = Decimal(a.gain_loss_usd)
                    if gl > ZERO:
                        total_gains += gl
                    else:
                        total_losses += abs(gl)

            if tx.to_wallet_id == wallet_id and tx.to_asset_id == asset_id:
                amount = _to_dec(tx.to_amount)
                value_usd = resolve_value_usd(tx.to_value_usd, tx.net_value_usd)
                process_acquisition(db, tx, wallet_id, asset_id, amount, value_usd)

            continue

        # --- Disposal from this wallet ---
        if (
            tx_type in {t.value for t in DISPOSAL_TYPES}
            and tx.from_wallet_id == wallet_id
            and tx.from_asset_id == asset_id
        ):
            amount = _to_dec(tx.from_amount)
            proceeds = resolve_value_usd(tx.from_value_usd, tx.net_value_usd)
            try:
                assignments = process_disposal(
                    db, tx, wallet_id, asset_id, amount, proceeds, method, tax_year
                )
            except InsufficientLotsError as exc:
                tx.tax_error = str(exc)
                tx.has_tax_error = True
                error_count += 1
                assignments = []
            for a in assignments:
                gl = Decimal(a.gain_loss_usd)
                if gl > ZERO:
                    total_gains += gl
                else:
                    total_losses += abs(gl)

    db.flush()

    return {
        "wallet_id": wallet_id,
        "asset_id": asset_id,
        "method": method,
        "total_gains": str(total_gains.quantize(PENNY, rounding=ROUND_HALF_UP)),
        "total_losses": str(total_losses.quantize(PENNY, rounding=ROUND_HALF_UP)),
        "net_gain_loss": str((total_gains - total_losses).quantize(PENNY, rounding=ROUND_HALF_UP)),
        "total_income": str(total_income.quantize(PENNY, rounding=ROUND_HALF_UP)),
        "error_count": error_count,
    }


def recalculate_for_wallet_asset(
    db: Session,
    wallet_id: int,
    asset_id: int,
    tax_year: int,
    method: str | None = None,
) -> dict:
    """Delete existing lots/assignments and re-run calculation."""
    existing_assignments = (
        db.query(LotAssignment)
        .filter(LotAssignment.tax_year == tax_year)
        .join(TaxLot, LotAssignment.tax_lot_id == TaxLot.id)
        .filter(TaxLot.wallet_id == wallet_id, TaxLot.asset_id == asset_id)
        .all()
    )
    for a in existing_assignments:
        db.delete(a)

    existing_lots = (
        db.query(TaxLot)
        .filter(TaxLot.wallet_id == wallet_id, TaxLot.asset_id == asset_id)
        .all()
    )
    for lot in existing_lots:
        db.delete(lot)

    _clear_errors_for_pair(db, wallet_id, asset_id, tax_year)
    db.flush()

    return calculate_for_wallet_asset(db, wallet_id, asset_id, tax_year, method)


def _find_pairs_for_year(db: Session, year: int) -> set[tuple[int, int]]:
    """Find all unique (wallet_id, asset_id) pairs with transactions in the given year."""
    fiat_ids = {a.id for a in db.query(Asset.id).filter(Asset.is_fiat == True).all()}

    from_pairs = (
        db.query(
            Transaction.from_wallet_id.label("wallet_id"),
            Transaction.from_asset_id.label("asset_id"),
        )
        .filter(
            Transaction.datetime_utc >= datetime(year, 1, 1),
            Transaction.datetime_utc < datetime(year + 1, 1, 1),
            Transaction.from_wallet_id.isnot(None),
            Transaction.from_asset_id.isnot(None),
        )
    )
    to_pairs = (
        db.query(
            Transaction.to_wallet_id.label("wallet_id"),
            Transaction.to_asset_id.label("asset_id"),
        )
        .filter(
            Transaction.datetime_utc >= datetime(year, 1, 1),
            Transaction.datetime_utc < datetime(year + 1, 1, 1),
            Transaction.to_wallet_id.isnot(None),
            Transaction.to_asset_id.isnot(None),
        )
    )
    all_pairs_query = from_pairs.union(to_pairs).all()
    return {(r.wallet_id, r.asset_id) for r in all_pairs_query if r.asset_id not in fiat_ids}


def _get_transaction_year_range(db: Session) -> list[int]:
    """Get all distinct years that have transactions, sorted ascending."""
    from sqlalchemy import func, extract
    rows = (
        db.query(extract("year", Transaction.datetime_utc).label("yr"))
        .distinct()
        .order_by("yr")
        .all()
    )
    return [int(r.yr) for r in rows if r.yr is not None]


def _order_pairs_by_transfer_deps(
    db: Session, pairs: set[tuple[int, int]], year: int,
) -> list[tuple[int, int]]:
    """Topological sort of (wallet, asset) pairs so transfer sources come first."""
    from collections import defaultdict, deque
    from app.services.wrapping_swap_handler import is_wrapping_swap

    transfers = (
        db.query(Transaction)
        .filter(
            Transaction.type == TransactionType.transfer.value,
            Transaction.datetime_utc >= datetime(year, 1, 1),
            Transaction.datetime_utc < datetime(year + 1, 1, 1),
            Transaction.from_wallet_id.isnot(None),
            Transaction.to_wallet_id.isnot(None),
            Transaction.from_asset_id.isnot(None),
        )
        .all()
    )

    trades = (
        db.query(Transaction)
        .filter(
            Transaction.type == TransactionType.trade.value,
            Transaction.datetime_utc >= datetime(year, 1, 1),
            Transaction.datetime_utc < datetime(year + 1, 1, 1),
            Transaction.from_wallet_id.isnot(None),
            Transaction.to_wallet_id.isnot(None),
            Transaction.from_asset_id.isnot(None),
            Transaction.to_asset_id.isnot(None),
        )
        .all()
    )
    wrapping_swaps = [tx for tx in trades if is_wrapping_swap(db, tx)]

    adj: dict[tuple[int, int], set[tuple[int, int]]] = defaultdict(set)
    in_degree: dict[tuple[int, int], int] = defaultdict(int)
    for p in pairs:
        in_degree.setdefault(p, 0)

    def _add_edge(src: tuple[int, int], dst: tuple[int, int]) -> None:
        if src in pairs and dst in pairs and src != dst and dst not in adj[src]:
            adj[src].add(dst)
            in_degree[dst] = in_degree.get(dst, 0) + 1

    for tx in transfers:
        src = (tx.from_wallet_id, tx.from_asset_id)
        dst = (tx.to_wallet_id, tx.to_asset_id)
        _add_edge(src, dst)

    for tx in wrapping_swaps:
        src = (tx.from_wallet_id, tx.from_asset_id)
        dst = (tx.to_wallet_id, tx.to_asset_id)
        _add_edge(src, dst)

    queue = deque(sorted(p for p in pairs if in_degree.get(p, 0) == 0))
    result: list[tuple[int, int]] = []
    while queue:
        node = queue.popleft()
        result.append(node)
        for neighbor in sorted(adj.get(node, set())):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    visited = set(result)
    for p in sorted(pairs):
        if p not in visited:
            result.append(p)

    return result


def recalculate_all(db: Session, tax_year: int | None = None) -> dict:
    """Recalculate for every (wallet, asset) pair across all years."""
    years = _get_transaction_year_range(db)
    if not years:
        return {"results": [], "errors": [], "error_transaction_count": 0}

    db.query(LotAssignment).delete()
    db.query(TaxLot).delete()

    db.query(Transaction).filter(Transaction.has_tax_error == True).update(
        {"tax_error": None, "has_tax_error": False}, synchronize_session="fetch"
    )
    db.flush()

    all_results = []
    all_errors = []

    for year in years:
        pairs = _find_pairs_for_year(db, year)
        ordered_pairs = _order_pairs_by_transfer_deps(db, pairs, year)
        for wallet_id, asset_id in ordered_pairs:
            try:
                result = calculate_for_wallet_asset(db, wallet_id, asset_id, year)
                all_results.append(result)
            except Exception as exc:
                all_errors.append({
                    "wallet_id": wallet_id, "asset_id": asset_id,
                    "year": year, "error": str(exc),
                })

    db.commit()

    error_transaction_count = (
        db.query(Transaction)
        .filter(Transaction.has_tax_error == True)
        .count()
    )

    return {
        "results": all_results,
        "errors": all_errors,
        "error_transaction_count": error_transaction_count,
    }
