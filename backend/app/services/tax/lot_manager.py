"""Tax lot creation and querying."""

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models import TaxLot, TransactionType, LotSourceType
from app.utils.decimal_helpers import ZERO, PENNY


def source_type_for_tx(tx_type: str) -> str:
    """Map transaction type to lot source_type."""
    mapping = {
        TransactionType.buy.value: LotSourceType.purchase.value,
        TransactionType.trade.value: LotSourceType.trade.value,
        TransactionType.deposit.value: LotSourceType.purchase.value,
        TransactionType.staking_reward.value: LotSourceType.income.value,
        TransactionType.interest.value: LotSourceType.income.value,
        TransactionType.airdrop.value: LotSourceType.airdrop.value,
        TransactionType.fork.value: LotSourceType.fork.value,
        TransactionType.mining.value: LotSourceType.income.value,
        TransactionType.gift_received.value: LotSourceType.gift.value,
        TransactionType.transfer.value: LotSourceType.transfer_in.value,
    }
    return mapping.get(tx_type, LotSourceType.purchase.value)


def get_open_lots(db: Session, wallet_id: int, asset_id: int) -> list[TaxLot]:
    """Get all lots with remaining balance for a (wallet, asset) pair."""
    return (
        db.query(TaxLot)
        .filter(
            TaxLot.wallet_id == wallet_id,
            TaxLot.asset_id == asset_id,
            TaxLot.is_fully_disposed == False,
        )
        .order_by(TaxLot.acquired_date)
        .all()
    )


def create_lot(
    db: Session,
    *,
    wallet_id: int,
    asset_id: int,
    amount: Decimal,
    cost_basis_usd: Decimal,
    acquired_date,
    acquisition_tx_id: int,
    source_type: str,
) -> TaxLot:
    """Create a new tax lot."""
    per_unit = ZERO
    if amount > ZERO:
        per_unit = (cost_basis_usd / amount).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

    lot = TaxLot(
        wallet_id=wallet_id,
        asset_id=asset_id,
        amount=str(amount),
        remaining_amount=str(amount),
        cost_basis_usd=str(cost_basis_usd.quantize(PENNY, rounding=ROUND_HALF_UP)),
        cost_basis_per_unit=str(per_unit),
        acquired_date=acquired_date,
        acquisition_tx_id=acquisition_tx_id,
        source_type=source_type,
    )
    db.add(lot)
    db.flush()
    return lot
