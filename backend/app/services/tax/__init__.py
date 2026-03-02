"""Tax engine package — lot management, gain/loss calculation, orchestration."""

from app.services.tax.lot_manager import (
    create_lot,
    get_open_lots,
    source_type_for_tx,
)
from app.services.tax.gain_calculator import (
    resolve_value_usd,
    holding_period,
    process_acquisition,
    process_disposal,
)
from app.services.tax.orchestrator import (
    get_cost_basis_method,
    calculate_for_wallet_asset,
    recalculate_for_wallet_asset,
    recalculate_all,
)

__all__ = [
    "create_lot",
    "get_open_lots",
    "source_type_for_tx",
    "resolve_value_usd",
    "holding_period",
    "process_acquisition",
    "process_disposal",
    "get_cost_basis_method",
    "calculate_for_wallet_asset",
    "recalculate_for_wallet_asset",
    "recalculate_all",
]
