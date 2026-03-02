"""Tax summary report generator.

Calculates total gains/losses from lot_assignments and income totals from
staking, airdrop, mining, and interest transactions. Also tallies total fees.

All calculations use decimal.Decimal with ROUND_HALF_UP. Never float.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.lot_assignment import LotAssignment
from app.models.price_history import PriceHistory
from app.models.tax_lot import TaxLot
from app.models.transaction import Transaction
from app.models.base import TransactionType, INCOME_TYPES
from app.schemas.tax import EoyAssetBalance, TaxSummaryResponse
from app.services.price_service import PriceService
from app.utils.decimal_helpers import ZERO, PENNY, to_decimal as _to_dec


class TaxSummaryGenerator:
    """Generates a TaxSummaryResponse for a given tax year."""

    def __init__(self, db: Session):
        self.db = db

    def generate(self, tax_year: int) -> TaxSummaryResponse:
        """Build the full tax summary from lot assignments and income transactions."""
        # ---------------------------------------------------------------
        # Capital gains / losses from lot assignments
        # ---------------------------------------------------------------
        assignments = (
            self.db.query(LotAssignment)
            .filter(LotAssignment.tax_year == tax_year)
            .all()
        )

        total_proceeds = ZERO
        total_cost_basis = ZERO
        short_term_gains = ZERO
        short_term_losses = ZERO
        long_term_gains = ZERO
        long_term_losses = ZERO

        for a in assignments:
            proceeds = _to_dec(a.proceeds_usd)
            cost_basis = _to_dec(a.cost_basis_usd)
            gain_loss = _to_dec(a.gain_loss_usd)

            total_proceeds += proceeds
            total_cost_basis += cost_basis

            if a.holding_period == "short_term":
                if gain_loss >= ZERO:
                    short_term_gains += gain_loss
                else:
                    short_term_losses += abs(gain_loss)
            else:
                if gain_loss >= ZERO:
                    long_term_gains += gain_loss
                else:
                    long_term_losses += abs(gain_loss)

        total_gains = (short_term_gains + long_term_gains).quantize(
            PENNY, rounding=ROUND_HALF_UP
        )
        total_losses = (short_term_losses + long_term_losses).quantize(
            PENNY, rounding=ROUND_HALF_UP
        )
        net_gain_loss = (total_gains - total_losses).quantize(
            PENNY, rounding=ROUND_HALF_UP
        )

        # ---------------------------------------------------------------
        # Income from staking, airdrops, forks, mining, interest
        # ---------------------------------------------------------------
        year_start = datetime(tax_year, 1, 1)
        year_end = datetime(tax_year + 1, 1, 1)

        income_types = {t.value for t in INCOME_TYPES} | {TransactionType.fork.value}
        income_txns = (
            self.db.query(Transaction)
            .filter(
                Transaction.datetime_utc >= year_start,
                Transaction.datetime_utc < year_end,
                Transaction.type.in_(income_types),
            )
            .all()
        )

        staking_income = ZERO
        airdrop_income = ZERO
        fork_income = ZERO
        mining_income = ZERO
        interest_income = ZERO
        other_income = ZERO

        for tx in income_txns:
            value = _to_dec(tx.to_value_usd)
            tx_type = tx.type

            if tx_type == TransactionType.staking_reward.value:
                staking_income += value
            elif tx_type == TransactionType.airdrop.value:
                airdrop_income += value
            elif tx_type == TransactionType.fork.value:
                fork_income += value
            elif tx_type == TransactionType.mining.value:
                mining_income += value
            elif tx_type == TransactionType.interest.value:
                interest_income += value
            else:
                other_income += value

        total_income = (
            staking_income + airdrop_income + fork_income
            + mining_income + interest_income + other_income
        ).quantize(PENNY, rounding=ROUND_HALF_UP)

        # ---------------------------------------------------------------
        # Expenses: cost-type disposals + fees
        # ---------------------------------------------------------------
        # Cost-type transactions (cost, gift_sent, lost, fee)
        cost_type_values = {
            TransactionType.cost.value,
            TransactionType.gift_sent.value,
            TransactionType.lost.value,
        }
        cost_txns = (
            self.db.query(Transaction)
            .filter(
                Transaction.datetime_utc >= year_start,
                Transaction.datetime_utc < year_end,
                Transaction.type.in_(cost_type_values),
            )
            .all()
        )
        total_cost_expenses = ZERO
        for tx in cost_txns:
            total_cost_expenses += _to_dec(tx.from_value_usd) or _to_dec(tx.net_value_usd)

        # Transfer fees (fees on transfer transactions)
        transfer_fee_txns = (
            self.db.query(Transaction)
            .filter(
                Transaction.datetime_utc >= year_start,
                Transaction.datetime_utc < year_end,
                Transaction.type == TransactionType.transfer.value,
                Transaction.fee_value_usd.isnot(None),
            )
            .all()
        )
        transfer_fees = ZERO
        for tx in transfer_fee_txns:
            transfer_fees += _to_dec(tx.fee_value_usd)

        # Total fees across all transaction types
        fee_txns = (
            self.db.query(Transaction)
            .filter(
                Transaction.datetime_utc >= year_start,
                Transaction.datetime_utc < year_end,
                Transaction.fee_value_usd.isnot(None),
            )
            .all()
        )
        total_fees = ZERO
        for tx in fee_txns:
            total_fees += _to_dec(tx.fee_value_usd)

        # ---------------------------------------------------------------
        # End-of-year asset balances
        # ---------------------------------------------------------------
        eoy_balances = self._compute_eoy_balances(tax_year, year_end)

        return TaxSummaryResponse(
            tax_year=tax_year,
            total_proceeds=str(total_proceeds.quantize(PENNY, rounding=ROUND_HALF_UP)),
            total_cost_basis=str(total_cost_basis.quantize(PENNY, rounding=ROUND_HALF_UP)),
            total_gains=str(total_gains),
            total_losses=str(total_losses),
            net_gain_loss=str(net_gain_loss),
            short_term_gains=str(short_term_gains.quantize(PENNY, rounding=ROUND_HALF_UP)),
            short_term_losses=str(short_term_losses.quantize(PENNY, rounding=ROUND_HALF_UP)),
            long_term_gains=str(long_term_gains.quantize(PENNY, rounding=ROUND_HALF_UP)),
            long_term_losses=str(long_term_losses.quantize(PENNY, rounding=ROUND_HALF_UP)),
            total_income=str(total_income),
            staking_income=str(staking_income.quantize(PENNY, rounding=ROUND_HALF_UP)),
            airdrop_income=str(airdrop_income.quantize(PENNY, rounding=ROUND_HALF_UP)),
            fork_income=str(fork_income.quantize(PENNY, rounding=ROUND_HALF_UP)),
            mining_income=str(mining_income.quantize(PENNY, rounding=ROUND_HALF_UP)),
            interest_income=str(interest_income.quantize(PENNY, rounding=ROUND_HALF_UP)),
            other_income=str(other_income.quantize(PENNY, rounding=ROUND_HALF_UP)),
            total_cost_expenses=str(total_cost_expenses.quantize(PENNY, rounding=ROUND_HALF_UP)),
            transfer_fees=str(transfer_fees.quantize(PENNY, rounding=ROUND_HALF_UP)),
            total_fees_usd=str(total_fees.quantize(PENNY, rounding=ROUND_HALF_UP)),
            eoy_balances=eoy_balances,
        )

    def _compute_eoy_balances(
        self, tax_year: int, year_end: datetime
    ) -> list[EoyAssetBalance]:
        """Compute end-of-year balances from TaxLot.remaining_amount.

        Uses the tax engine's own remaining_amount which already accounts
        for all lot consumption (sales, transfers, withdrawals, etc.).
        Filters out dust and includes market value as of Dec 31.
        """
        DUST_THRESHOLD = Decimal("0.0000001")
        eoy_date = date(tax_year, 12, 31)

        # Use remaining_amount from tax lots — the tax engine maintains this
        lots = (
            self.db.query(TaxLot)
            .filter(
                TaxLot.acquired_date < year_end,
                TaxLot.is_fully_disposed == False,
            )
            .all()
        )

        # Aggregate by asset_id
        asset_balances: dict[int, Decimal] = {}
        asset_cost_basis: dict[int, Decimal] = {}
        for lot in lots:
            remaining = _to_dec(lot.remaining_amount)
            if remaining <= DUST_THRESHOLD:
                continue
            asset_balances[lot.asset_id] = (
                asset_balances.get(lot.asset_id, ZERO) + remaining
            )
            # Pro-rate cost basis for remaining portion
            acquired = _to_dec(lot.amount)
            lot_basis = _to_dec(lot.cost_basis_usd)
            if acquired > ZERO:
                remaining_basis = (lot_basis * remaining / acquired).quantize(
                    PENNY, rounding=ROUND_HALF_UP
                )
            else:
                remaining_basis = ZERO
            asset_cost_basis[lot.asset_id] = (
                asset_cost_basis.get(lot.asset_id, ZERO) + remaining_basis
            )

        # Look up asset details, filter out fiat and hidden
        result: list[EoyAssetBalance] = []
        for asset_id in sorted(asset_balances.keys()):
            asset = self.db.get(Asset, asset_id)
            if not asset or asset.is_fiat or asset.is_hidden:
                continue
            qty = asset_balances[asset_id]
            basis = asset_cost_basis.get(asset_id, ZERO)
            if qty <= ZERO:
                continue

            # Look up market value on Dec 31, falling back to nearest date
            price = self._get_eoy_price(asset_id, eoy_date)
            if price is not None:
                market_val = (qty * price).quantize(PENNY, rounding=ROUND_HALF_UP)
                market_value_str = str(market_val)
            else:
                market_value_str = None

            result.append(EoyAssetBalance(
                asset_id=asset_id,
                symbol=asset.symbol,
                name=asset.name,
                quantity=str(qty),
                cost_basis_usd=str(basis),
                market_value_usd=market_value_str,
            ))

        # Filter out negligible balances (dust left from rounding)
        VALUE_THRESHOLD = Decimal("1.00")
        result = [
            b for b in result
            if _to_dec(b.market_value_usd) >= VALUE_THRESHOLD
            or (b.market_value_usd is None and _to_dec(b.cost_basis_usd) >= VALUE_THRESHOLD)
        ]

        # Sort by market value (or cost basis if no market value) descending
        def sort_key(b: EoyAssetBalance) -> Decimal:
            if b.market_value_usd:
                return _to_dec(b.market_value_usd)
            return _to_dec(b.cost_basis_usd)
        result.sort(key=sort_key, reverse=True)
        return result

    def _get_eoy_price(self, asset_id: int, eoy_date: date) -> Decimal | None:
        """Get price on eoy_date, falling back to nearest date within 14 days."""
        price = PriceService.get_price(self.db, asset_id, eoy_date)
        if price is not None:
            return price
        # Search within a 14-day window around Dec 31
        start = eoy_date - timedelta(days=14)
        end = eoy_date + timedelta(days=14)
        prices = PriceService.get_prices_batch(self.db, asset_id, start, end)
        if not prices:
            return None
        # Pick the date closest to Dec 31
        closest = min(prices.keys(), key=lambda d: abs((d - eoy_date).days))
        return prices[closest]
