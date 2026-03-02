"""CSV format presets — column mappings for Koinly, Coinbase, River, and custom formats."""

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class CsvPreset:
    name: str
    # Map our field names -> CSV column header names
    columns: dict[str, str]
    date_format: str | None = None
    # Map raw CSV type values to our TransactionType enum values
    type_map: dict[str, str] = field(default_factory=dict)
    # Optional: infer type from row data when no type column exists
    infer_type: Callable | None = None

    def map_type(self, raw_type: str) -> str:
        """Map a CSV type string to our internal type enum value."""
        normalized = raw_type.strip().lower()
        return self.type_map.get(normalized, normalized)


# ---------------------------------------------------------------------------
# Koinly Universal Format
# ---------------------------------------------------------------------------

KOINLY_TYPE_MAP = {
    "buy": "buy",
    "sell": "sell",
    "trade": "trade",
    "transfer": "transfer",
    "deposit": "deposit",
    "withdrawal": "withdrawal",
    "staking": "staking_reward",
    "staking_reward": "staking_reward",
    "reward": "staking_reward",
    "interest": "interest",
    "airdrop": "airdrop",
    "fork": "fork",
    "mining": "mining",
    "cost": "cost",
    "gift": "gift_sent",
    "gift_sent": "gift_sent",
    "gift_received": "gift_received",
    "lost": "lost",
    "fee": "fee",
    "income": "staking_reward",
}

KOINLY_PRESET = CsvPreset(
    name="koinly_universal",
    columns={
        "date": "Date",
        "from_amount": "Sent Amount",
        "from_asset": "Sent Currency",
        "to_amount": "Received Amount",
        "to_asset": "Received Currency",
        "fee_amount": "Fee Amount",
        "fee_asset": "Fee Currency",
        "net_value_usd": "Net Worth Amount",
        "label": "Label",
        "description": "Description",
        "tx_hash": "TxHash",
    },
    date_format="%Y-%m-%d %H:%M:%S %Z",
    type_map=KOINLY_TYPE_MAP,
)


def _koinly_infer_type(row: dict) -> str:
    """Infer transaction type for Koinly format based on amounts."""
    label = (row.get("Label") or "").strip().lower()
    if label in KOINLY_TYPE_MAP:
        return KOINLY_TYPE_MAP[label]

    sent = row.get("Sent Amount", "").strip()
    received = row.get("Received Amount", "").strip()
    sent_cur = row.get("Sent Currency", "").strip().upper()
    recv_cur = row.get("Received Currency", "").strip().upper()

    if sent and received:
        if sent_cur in ("USD", "EUR", "GBP"):
            return "buy"
        elif recv_cur in ("USD", "EUR", "GBP"):
            return "sell"
        else:
            return "trade"
    elif received:
        return "deposit"
    elif sent:
        return "withdrawal"
    return "deposit"


KOINLY_PRESET.infer_type = _koinly_infer_type


# ---------------------------------------------------------------------------
# Coinbase Format
# ---------------------------------------------------------------------------

COINBASE_TYPE_MAP = {
    "buy": "buy",
    "sell": "sell",
    "send": "withdrawal",
    "receive": "deposit",
    "convert": "trade",
    "advanced trade buy": "buy",
    "advanced trade sell": "sell",
    "staking income": "staking_reward",
    "reward income": "interest",
    "rewards income": "staking_reward",
    "learning reward": "airdrop",
    "coinbase earn": "airdrop",
    "inflation reward": "staking_reward",
    "deposit": "deposit",
    "withdrawal": "withdrawal",
}

# Transaction types that represent internal Coinbase/Pro/GDAX movements — not
# tax events.  Plain "deposit" and "withdrawal" are real fiat bank transfers
# and MUST be imported so USD balances stay accurate.
COINBASE_SKIP_TYPES: set[str] = {
    "pro withdrawal",
    "pro deposit",
    "exchange deposit",
    "exchange withdrawal",
}

COINBASE_PRESET = CsvPreset(
    name="coinbase",
    columns={
        "date": "Timestamp",
        "type": "Transaction Type",
        "to_amount": "Quantity Transacted",
        "to_asset": "Asset",
        "to_value_usd": "Subtotal",
        "fee_amount": "Fees and/or Spread",
        "description": "Notes",
        "coinbase_id": "ID",
    },
    date_format="%Y-%m-%d %H:%M:%S %Z",
    type_map=COINBASE_TYPE_MAP,
)


# ---------------------------------------------------------------------------
# River Format
# ---------------------------------------------------------------------------

RIVER_TYPE_MAP = {
    "purchase": "buy",
    "buy": "buy",
    "sell": "sell",
    "sale": "sell",
    "deposit": "deposit",
    "withdrawal": "withdrawal",
    "referral": "airdrop",
    "interest": "interest",
    "reward": "staking_reward",
}

RIVER_PRESET = CsvPreset(
    name="river",
    columns={
        "date": "Date",
        "type": "Type",
        "to_amount": "Amount (BTC)",
        "to_value_usd": "Amount (USD)",
        "description": "Description",
        "tx_hash": "Transaction ID",
    },
    type_map=RIVER_TYPE_MAP,
)


# ---------------------------------------------------------------------------
# Ledger Live Format
# ---------------------------------------------------------------------------

LEDGER_TYPE_MAP: dict[str, str] = {
    "in": "deposit",
    "out": "withdrawal",
    "fees": "fee",
    "reward": "staking_reward",
    "delegate": "fee",         # delegation tx costs gas, no economic gain/loss
    "undelegate": "fee",       # undelegation tx costs gas
    "opt_in": "fee",           # staking opt-in costs gas
    "withdraw_unbonded": "fee",  # withdraw staking costs gas
}

# Operation types where the CSV row duplicates a fee already on another tx.
# Only standalone "fees" rows are skipped; delegation/staking ops are imported
# as fee transactions so gas costs are properly tracked.
LEDGER_SKIP_TYPES: set[str] = {"fees"}


def _ledger_infer_type(row: dict) -> str:
    """Infer transaction type from Ledger Live operation type."""
    op_type = (row.get("Operation Type") or "").strip().lower()
    return LEDGER_TYPE_MAP.get(op_type, "deposit")


LEDGER_PRESET = CsvPreset(
    name="ledger",
    columns={
        "date": "Operation Date",
        "type": "Operation Type",
        "to_amount": "Operation Amount",
        "to_asset": "Currency Ticker",
        "fee_amount": "Operation Fees",
        "fee_asset": "Currency Ticker",  # fees are in same currency
        "tx_hash": "Operation Hash",
        "net_value_usd": "Countervalue at Operation Date",
        # Extra columns handled by post-processing:
        # "Account Name", "Account xpub"
    },
    date_format="%Y-%m-%dT%H:%M:%S.%fZ",
    type_map=LEDGER_TYPE_MAP,
    infer_type=_ledger_infer_type,
)


# ---------------------------------------------------------------------------
# Preset registry and detection
# ---------------------------------------------------------------------------

PRESETS: dict[str, CsvPreset] = {
    "koinly_universal": KOINLY_PRESET,
    "coinbase": COINBASE_PRESET,
    "river": RIVER_PRESET,
    "ledger": LEDGER_PRESET,
}


def detect_preset(headers: list[str]) -> tuple[str, CsvPreset]:
    """Auto-detect CSV format by matching headers to known presets.

    Returns (format_name, preset). Falls back to Koinly if uncertain.
    """
    header_set = set(h.strip() for h in headers)

    # Ledger Live: has "Operation Date" and "Operation Type"
    if "Operation Date" in header_set and "Operation Type" in header_set:
        return "ledger", LEDGER_PRESET

    # Coinbase: has "Timestamp" and "Transaction Type"
    if "Timestamp" in header_set and "Transaction Type" in header_set:
        return "coinbase", COINBASE_PRESET

    # Koinly: has "Sent Amount" and "Received Amount"
    if "Sent Amount" in header_set and "Received Amount" in header_set:
        return "koinly_universal", KOINLY_PRESET

    # River: has "Amount (BTC)"
    if "Amount (BTC)" in header_set:
        return "river", RIVER_PRESET

    # Default fallback
    return "unknown", KOINLY_PRESET
