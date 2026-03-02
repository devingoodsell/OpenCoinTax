"""Backward-compatible facade — re-exports from the tax/ package.

All logic has been decomposed into:
- app.services.tax.lot_manager (lot creation and querying)
- app.services.tax.gain_calculator (gain/loss computation)
- app.services.tax.orchestrator (coordination and recalculation)
"""

from app.services.tax.lot_manager import (
    create_lot as _create_lot,
    get_open_lots as _get_open_lots,
    source_type_for_tx as _source_type_for_tx,
)
from app.services.tax.gain_calculator import (
    resolve_value_usd as _resolve_value_usd,
    holding_period as _holding_period,
    process_acquisition as _process_acquisition,
    process_disposal as _process_disposal,
)
from app.services.tax.orchestrator import (
    get_cost_basis_method,
    calculate_for_wallet_asset,
    recalculate_for_wallet_asset,
    recalculate_all,
    _find_pairs_for_year,
    _get_transaction_year_range,
    _order_pairs_by_transfer_deps,
)
from app.utils.decimal_helpers import to_decimal as _to_dec

__all__ = [
    "_create_lot",
    "_get_open_lots",
    "_source_type_for_tx",
    "_resolve_value_usd",
    "_holding_period",
    "_process_acquisition",
    "_process_disposal",
    "_to_dec",
    "get_cost_basis_method",
    "calculate_for_wallet_asset",
    "recalculate_for_wallet_asset",
    "recalculate_all",
    "_find_pairs_for_year",
    "_get_transaction_year_range",
    "_order_pairs_by_transfer_deps",
]
