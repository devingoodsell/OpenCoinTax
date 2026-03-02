"""Form 8949 report generator.

Queries lot_assignments for a tax year, joins with TaxLot and Transaction
to produce IRS Form 8949 data separated into Part I (short-term) and
Part II (long-term), with checkbox categories based on 1099-DA reporting.

All calculations use decimal.Decimal with ROUND_HALF_UP. Never float.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session, joinedload

from app.models.asset import Asset
from app.models.lot_assignment import LotAssignment
from app.models.tax_lot import TaxLot
from app.models.transaction import Transaction
from app.schemas.report import Form8949Response, Form8949Row
from app.utils.decimal_helpers import ZERO, PENNY, to_decimal as _to_dec


def _checkbox_category(reported_on_1099da: bool, basis_reported_to_irs: bool) -> str:
    """Determine Form 8949 checkbox category.

    IRS Form 8949 instructions:
    - Box A / D: 1099-B (or 1099-DA) received AND basis reported to IRS
    - Box B / E: 1099-B (or 1099-DA) received but basis NOT reported to IRS
    - Box C / F: No 1099-B / 1099-DA received at all

    For short-term: A, B, C  (Part I)
    For long-term:  D, E, F  (Part II)

    We return a generic pair letter that the caller maps per-part:
      "A" -> reported + basis reported   (maps to A for ST, D for LT)
      "B" -> reported + no basis         (maps to B for ST, E for LT)
      "C" -> not reported                (maps to C for ST, F for LT)
    """
    if reported_on_1099da and basis_reported_to_irs:
        return "A"
    elif reported_on_1099da and not basis_reported_to_irs:
        return "B"
    else:
        return "C"


def _map_checkbox_for_part(generic: str, holding_period: str) -> str:
    """Map generic checkbox letter to the actual Form 8949 checkbox.

    Part I (short-term): A, B, C
    Part II (long-term): D, E, F
    """
    if holding_period == "long_term":
        mapping = {"A": "D", "B": "E", "C": "F"}
        return mapping.get(generic, "F")
    # short_term
    return generic


class Form8949Generator:
    """Generates IRS Form 8949 data from lot assignments."""

    def __init__(self, db: Session):
        self.db = db

    def _query_assignments(self, tax_year: int) -> list[LotAssignment]:
        """Load all lot assignments for the given tax year with related data."""
        return (
            self.db.query(LotAssignment)
            .filter(LotAssignment.tax_year == tax_year)
            .join(Transaction, LotAssignment.disposal_tx_id == Transaction.id)
            .join(TaxLot, LotAssignment.tax_lot_id == TaxLot.id)
            .options(
                joinedload(LotAssignment.disposal_tx)
                .joinedload(Transaction.from_asset),
                joinedload(LotAssignment.tax_lot)
                .joinedload(TaxLot.asset),
            )
            .order_by(Transaction.datetime_utc)
            .all()
        )

    def _build_row(self, assignment: LotAssignment) -> Form8949Row:
        """Convert a single LotAssignment into a Form8949Row."""
        tax_lot = assignment.tax_lot
        disposal_tx = assignment.disposal_tx

        # Asset description: "{amount} {symbol}"
        asset = tax_lot.asset
        symbol = asset.symbol if asset else "UNKNOWN"
        amount_dec = _to_dec(assignment.amount)
        description = f"{amount_dec} {symbol}"

        # Dates
        date_acquired = tax_lot.acquired_date
        date_sold = disposal_tx.datetime_utc

        # Amounts
        proceeds = _to_dec(assignment.proceeds_usd).quantize(PENNY, rounding=ROUND_HALF_UP)
        cost_basis = _to_dec(assignment.cost_basis_usd).quantize(PENNY, rounding=ROUND_HALF_UP)
        gain_loss = _to_dec(assignment.gain_loss_usd).quantize(PENNY, rounding=ROUND_HALF_UP)

        # Checkbox category
        generic_checkbox = _checkbox_category(
            disposal_tx.reported_on_1099da,
            disposal_tx.basis_reported_to_irs,
        )
        checkbox = _map_checkbox_for_part(generic_checkbox, assignment.holding_period)

        return Form8949Row(
            description=description,
            date_acquired=date_acquired,
            date_sold=date_sold,
            proceeds=str(proceeds),
            cost_basis=str(cost_basis),
            adjustment_code="",
            adjustment_amount="0.00",
            gain_loss=str(gain_loss),
            holding_period=assignment.holding_period,
            checkbox_category=checkbox,
        )

    def _calculate_totals(self, rows: list[Form8949Row]) -> dict[str, str]:
        """Sum proceeds, cost_basis, adjustment_amount, and gain_loss for rows."""
        total_proceeds = ZERO
        total_cost_basis = ZERO
        total_adjustment = ZERO
        total_gain_loss = ZERO

        for row in rows:
            total_proceeds += _to_dec(row.proceeds)
            total_cost_basis += _to_dec(row.cost_basis)
            total_adjustment += _to_dec(row.adjustment_amount)
            total_gain_loss += _to_dec(row.gain_loss)

        return {
            "proceeds": str(total_proceeds.quantize(PENNY, rounding=ROUND_HALF_UP)),
            "cost_basis": str(total_cost_basis.quantize(PENNY, rounding=ROUND_HALF_UP)),
            "adjustment_amount": str(total_adjustment.quantize(PENNY, rounding=ROUND_HALF_UP)),
            "gain_loss": str(total_gain_loss.quantize(PENNY, rounding=ROUND_HALF_UP)),
        }

    @staticmethod
    def _collapse_rows(rows: list[Form8949Row]) -> list[Form8949Row]:
        """Collapse rows that share the same asset, acquired date, sold date, and box.

        IRS Form 8949 allows aggregating identical-property dispositions that
        share the same dates and checkbox category into a single line.
        """
        from collections import OrderedDict

        groups: OrderedDict[tuple, list[Form8949Row]] = OrderedDict()
        for row in rows:
            # Extract asset symbol from description (e.g. "99.4 ATOM" → "ATOM")
            parts = row.description.split()
            symbol = parts[-1] if len(parts) >= 2 else row.description

            key = (
                symbol,
                row.date_acquired.date(),
                row.date_sold.date(),
                row.checkbox_category,
            )
            groups.setdefault(key, []).append(row)

        collapsed: list[Form8949Row] = []
        for (_symbol, _acq, _sold, _box), group in groups.items():
            if len(group) == 1:
                collapsed.append(group[0])
                continue

            # Sum amounts, proceeds, cost_basis, gain_loss
            total_amount = sum((_to_dec(r.description.split()[0]) for r in group), ZERO)
            total_proceeds = sum((_to_dec(r.proceeds) for r in group), ZERO)
            total_cost_basis = sum((_to_dec(r.cost_basis) for r in group), ZERO)
            total_adjustment = sum((_to_dec(r.adjustment_amount) for r in group), ZERO)
            total_gain_loss = sum((_to_dec(r.gain_loss) for r in group), ZERO)

            collapsed.append(Form8949Row(
                description=f"{total_amount} {_symbol}",
                date_acquired=group[0].date_acquired,
                date_sold=group[0].date_sold,
                proceeds=str(total_proceeds.quantize(PENNY, rounding=ROUND_HALF_UP)),
                cost_basis=str(total_cost_basis.quantize(PENNY, rounding=ROUND_HALF_UP)),
                adjustment_code=group[0].adjustment_code,
                adjustment_amount=str(total_adjustment.quantize(PENNY, rounding=ROUND_HALF_UP)),
                gain_loss=str(total_gain_loss.quantize(PENNY, rounding=ROUND_HALF_UP)),
                holding_period=group[0].holding_period,
                checkbox_category=group[0].checkbox_category,
            ))

        return collapsed

    def generate(self, tax_year: int) -> Form8949Response:
        """Generate the full Form 8949 response for a tax year."""
        assignments = self._query_assignments(tax_year)

        short_term_rows: list[Form8949Row] = []
        long_term_rows: list[Form8949Row] = []

        for assignment in assignments:
            row = self._build_row(assignment)
            if row.holding_period == "short_term":
                short_term_rows.append(row)
            else:
                long_term_rows.append(row)

        # Collapse rows with same asset, acquired date, sold date, and box
        short_term_rows = self._collapse_rows(short_term_rows)
        long_term_rows = self._collapse_rows(long_term_rows)

        return Form8949Response(
            tax_year=tax_year,
            short_term_rows=short_term_rows,
            long_term_rows=long_term_rows,
            short_term_totals=self._calculate_totals(short_term_rows),
            long_term_totals=self._calculate_totals(long_term_rows),
        )

    def generate_csv(self, tax_year: int) -> str:
        """Generate a CSV string for Form 8949 data."""
        response = self.generate(tax_year)
        output = io.StringIO()
        writer = csv.writer(output)

        # Part I: Short-Term
        writer.writerow([f"Form 8949 - Tax Year {tax_year}"])
        writer.writerow([])
        writer.writerow(["Part I - Short-Term Capital Gains and Losses"])
        writer.writerow([
            "(a) Description",
            "(b) Date Acquired",
            "(c) Date Sold",
            "(d) Proceeds",
            "(e) Cost Basis",
            "(f) Code",
            "(g) Adjustment",
            "(h) Gain or Loss",
            "Checkbox",
        ])

        for row in response.short_term_rows:
            writer.writerow([
                row.description,
                row.date_acquired.strftime("%m/%d/%Y"),
                row.date_sold.strftime("%m/%d/%Y"),
                row.proceeds,
                row.cost_basis,
                row.adjustment_code,
                row.adjustment_amount,
                row.gain_loss,
                row.checkbox_category,
            ])

        st = response.short_term_totals
        writer.writerow([
            "TOTALS",
            "",
            "",
            st["proceeds"],
            st["cost_basis"],
            "",
            st["adjustment_amount"],
            st["gain_loss"],
            "",
        ])

        # Part II: Long-Term
        writer.writerow([])
        writer.writerow(["Part II - Long-Term Capital Gains and Losses"])
        writer.writerow([
            "(a) Description",
            "(b) Date Acquired",
            "(c) Date Sold",
            "(d) Proceeds",
            "(e) Cost Basis",
            "(f) Code",
            "(g) Adjustment",
            "(h) Gain or Loss",
            "Checkbox",
        ])

        for row in response.long_term_rows:
            writer.writerow([
                row.description,
                row.date_acquired.strftime("%m/%d/%Y"),
                row.date_sold.strftime("%m/%d/%Y"),
                row.proceeds,
                row.cost_basis,
                row.adjustment_code,
                row.adjustment_amount,
                row.gain_loss,
                row.checkbox_category,
            ])

        lt = response.long_term_totals
        writer.writerow([
            "TOTALS",
            "",
            "",
            lt["proceeds"],
            lt["cost_basis"],
            "",
            lt["adjustment_amount"],
            lt["gain_loss"],
            "",
        ])

        return output.getvalue()
