"""Schedule D report generator.

Takes Form 8949 totals and produces Schedule D line items per IRS instructions.

All calculations use decimal.Decimal with ROUND_HALF_UP. Never float.
"""

from decimal import Decimal, ROUND_HALF_UP

from app.schemas.report import Form8949Response, ScheduleDLine, ScheduleDResponse
from app.utils.decimal_helpers import ZERO, PENNY, to_decimal as _to_dec


class ScheduleDGenerator:
    """Generates IRS Schedule D data from Form 8949 totals."""

    def generate(self, form_8949: Form8949Response) -> ScheduleDResponse:
        """Build Schedule D response from Form 8949 data.

        Schedule D line mapping (simplified for crypto):

        Part I - Short-Term:
          Line 1b: Totals from Form 8949, Box A
                   (1099-DA received, basis reported to IRS)
          Line 2:  Totals from Form 8949, Box B
                   (1099-DA received, basis NOT reported to IRS)
          Line 3:  Totals from Form 8949, Box C
                   (No 1099-DA received)
          Line 7:  Net short-term capital gain or loss (sum of 1b + 2 + 3)

        Part II - Long-Term:
          Line 8b: Totals from Form 8949, Box D
                   (1099-DA received, basis reported to IRS)
          Line 9:  Totals from Form 8949, Box E
                   (1099-DA received, basis NOT reported to IRS)
          Line 10: Totals from Form 8949, Box F
                   (No 1099-DA received)
          Line 15: Net long-term capital gain or loss (sum of 8b + 9 + 10)

        Combined:
          Line 16: Net = Line 7 + Line 15
        """
        # Categorize short-term rows by checkbox
        st_box_a = self._subtotal_by_checkbox(form_8949.short_term_rows, "A")
        st_box_b = self._subtotal_by_checkbox(form_8949.short_term_rows, "B")
        st_box_c = self._subtotal_by_checkbox(form_8949.short_term_rows, "C")

        # Categorize long-term rows by checkbox
        lt_box_d = self._subtotal_by_checkbox(form_8949.long_term_rows, "D")
        lt_box_e = self._subtotal_by_checkbox(form_8949.long_term_rows, "E")
        lt_box_f = self._subtotal_by_checkbox(form_8949.long_term_rows, "F")

        # Line 7: net short-term
        net_st_proceeds = (
            _to_dec(st_box_a["proceeds"])
            + _to_dec(st_box_b["proceeds"])
            + _to_dec(st_box_c["proceeds"])
        ).quantize(PENNY, rounding=ROUND_HALF_UP)

        net_st_basis = (
            _to_dec(st_box_a["cost_basis"])
            + _to_dec(st_box_b["cost_basis"])
            + _to_dec(st_box_c["cost_basis"])
        ).quantize(PENNY, rounding=ROUND_HALF_UP)

        net_st_gain_loss = (
            _to_dec(st_box_a["gain_loss"])
            + _to_dec(st_box_b["gain_loss"])
            + _to_dec(st_box_c["gain_loss"])
        ).quantize(PENNY, rounding=ROUND_HALF_UP)

        # Line 15: net long-term
        net_lt_proceeds = (
            _to_dec(lt_box_d["proceeds"])
            + _to_dec(lt_box_e["proceeds"])
            + _to_dec(lt_box_f["proceeds"])
        ).quantize(PENNY, rounding=ROUND_HALF_UP)

        net_lt_basis = (
            _to_dec(lt_box_d["cost_basis"])
            + _to_dec(lt_box_e["cost_basis"])
            + _to_dec(lt_box_f["cost_basis"])
        ).quantize(PENNY, rounding=ROUND_HALF_UP)

        net_lt_gain_loss = (
            _to_dec(lt_box_d["gain_loss"])
            + _to_dec(lt_box_e["gain_loss"])
            + _to_dec(lt_box_f["gain_loss"])
        ).quantize(PENNY, rounding=ROUND_HALF_UP)

        # Line 16: combined net
        combined_net = (net_st_gain_loss + net_lt_gain_loss).quantize(
            PENNY, rounding=ROUND_HALF_UP
        )

        lines = [
            ScheduleDLine(
                line="1b",
                description="Short-term totals from Form 8949, Box A",
                proceeds=st_box_a["proceeds"],
                cost_basis=st_box_a["cost_basis"],
                gain_loss=st_box_a["gain_loss"],
            ),
            ScheduleDLine(
                line="2",
                description="Short-term totals from Form 8949, Box B",
                proceeds=st_box_b["proceeds"],
                cost_basis=st_box_b["cost_basis"],
                gain_loss=st_box_b["gain_loss"],
            ),
            ScheduleDLine(
                line="3",
                description="Short-term totals from Form 8949, Box C",
                proceeds=st_box_c["proceeds"],
                cost_basis=st_box_c["cost_basis"],
                gain_loss=st_box_c["gain_loss"],
            ),
            ScheduleDLine(
                line="7",
                description="Net short-term capital gain or (loss)",
                proceeds=str(net_st_proceeds),
                cost_basis=str(net_st_basis),
                gain_loss=str(net_st_gain_loss),
            ),
            ScheduleDLine(
                line="8b",
                description="Long-term totals from Form 8949, Box D",
                proceeds=lt_box_d["proceeds"],
                cost_basis=lt_box_d["cost_basis"],
                gain_loss=lt_box_d["gain_loss"],
            ),
            ScheduleDLine(
                line="9",
                description="Long-term totals from Form 8949, Box E",
                proceeds=lt_box_e["proceeds"],
                cost_basis=lt_box_e["cost_basis"],
                gain_loss=lt_box_e["gain_loss"],
            ),
            ScheduleDLine(
                line="10",
                description="Long-term totals from Form 8949, Box F",
                proceeds=lt_box_f["proceeds"],
                cost_basis=lt_box_f["cost_basis"],
                gain_loss=lt_box_f["gain_loss"],
            ),
            ScheduleDLine(
                line="15",
                description="Net long-term capital gain or (loss)",
                proceeds=str(net_lt_proceeds),
                cost_basis=str(net_lt_basis),
                gain_loss=str(net_lt_gain_loss),
            ),
            ScheduleDLine(
                line="16",
                description="Net capital gain or (loss) — combine lines 7 and 15",
                proceeds=str((net_st_proceeds + net_lt_proceeds).quantize(
                    PENNY, rounding=ROUND_HALF_UP
                )),
                cost_basis=str((net_st_basis + net_lt_basis).quantize(
                    PENNY, rounding=ROUND_HALF_UP
                )),
                gain_loss=str(combined_net),
            ),
        ]

        return ScheduleDResponse(
            tax_year=form_8949.tax_year,
            lines=lines,
            net_short_term=str(net_st_gain_loss),
            net_long_term=str(net_lt_gain_loss),
            combined_net=str(combined_net),
        )

    @staticmethod
    def _subtotal_by_checkbox(
        rows: list, checkbox: str
    ) -> dict[str, str]:
        """Sum proceeds, cost_basis, and gain_loss for rows matching a checkbox."""
        total_proceeds = ZERO
        total_cost_basis = ZERO
        total_gain_loss = ZERO

        for row in rows:
            if row.checkbox_category == checkbox:
                total_proceeds += _to_dec(row.proceeds)
                total_cost_basis += _to_dec(row.cost_basis)
                total_gain_loss += _to_dec(row.gain_loss)

        return {
            "proceeds": str(total_proceeds.quantize(PENNY, rounding=ROUND_HALF_UP)),
            "cost_basis": str(total_cost_basis.quantize(PENNY, rounding=ROUND_HALF_UP)),
            "gain_loss": str(total_gain_loss.quantize(PENNY, rounding=ROUND_HALF_UP)),
        }
