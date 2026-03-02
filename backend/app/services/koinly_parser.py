"""Koinly CSV parsing — parse wallets and transactions from Koinly CSV exports.

Handles two CSV file formats produced by the koinly-scraper:
  1. koinly_wallets.csv  — wallet records
  2. koinly_transactions.csv — transaction records with wallet references
"""

import csv
import io
from dataclasses import asdict, dataclass, field
from datetime import datetime

from app.services.csv.csv_validator import _safe_decimal, _parse_date


# ---------------------------------------------------------------------------
# Koinly wallet type → our wallet type mapping
# ---------------------------------------------------------------------------

KOINLY_WALLET_TYPE_MAP: dict[str, str] = {
    "exchange": "exchange",
    "blockchain": "hardware",
    "wallet": "software",
    "other": "other",
}

# Extended Koinly label → transaction type mapping (scraper-specific labels)
KOINLY_LABEL_TYPE_MAP: dict[str, str] = {
    # Standard labels (from csv_presets.py)
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
    # Scraper-specific labels
    "crypto_deposit": "deposit",
    "crypto_withdrawal": "withdrawal",
    "realized_gain": "sell",
    "to_pool": "transfer",
    "from_pool": "transfer",
    "margin_fee": "fee",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ParsedWallet:
    koinly_id: str
    name: str
    koinly_type: str
    mapped_type: str
    blockchain: str | None = None
    is_duplicate: bool = False


@dataclass
class ParsedTransaction:
    row_number: int
    status: str = "valid"  # "valid", "warning", "error"
    error_message: str | None = None
    datetime_utc: datetime | None = None
    tx_type: str | None = None
    from_amount: str | None = None
    from_asset: str | None = None
    to_amount: str | None = None
    to_asset: str | None = None
    fee_amount: str | None = None
    fee_asset: str | None = None
    net_value_usd: str | None = None
    from_value_usd: str | None = None
    to_value_usd: str | None = None
    label: str | None = None
    description: str | None = None
    tx_hash: str | None = None
    koinly_tx_id: str | None = None
    from_wallet_koinly_id: str | None = None
    to_wallet_koinly_id: str | None = None
    is_duplicate: bool = False
    raw_data: dict = field(default_factory=dict)


@dataclass
class ExistingWalletInfo:
    id: int
    name: str
    type: str
    category: str


@dataclass
class KoinlyPreviewResult:
    # Wallet counts
    total_wallets: int = 0
    new_wallets: int = 0
    existing_wallets: int = 0
    # Transaction counts
    total_transactions: int = 0
    valid_transactions: int = 0
    duplicate_transactions: int = 0
    error_transactions: int = 0
    warning_transactions: int = 0
    # Parsed data for confirm step
    wallets: list[ParsedWallet] = field(default_factory=list)
    transactions: list[ParsedTransaction] = field(default_factory=list)
    existing_wallets_list: list[ExistingWalletInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        for tx in d["transactions"]:
            if tx.get("datetime_utc") is not None:
                tx["datetime_utc"] = tx["datetime_utc"].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "KoinlyPreviewResult":
        wallets = [ParsedWallet(**w) for w in d.get("wallets", [])]
        txs = []
        for t in d.get("transactions", []):
            if t.get("datetime_utc") and isinstance(t["datetime_utc"], str):
                t = dict(t)
                t["datetime_utc"] = datetime.fromisoformat(t["datetime_utc"])
            txs.append(ParsedTransaction(**t))
        ew = [ExistingWalletInfo(**e) for e in d.get("existing_wallets_list", [])]
        return cls(
            total_wallets=d.get("total_wallets", 0),
            new_wallets=d.get("new_wallets", 0),
            existing_wallets=d.get("existing_wallets", 0),
            total_transactions=d.get("total_transactions", 0),
            valid_transactions=d.get("valid_transactions", 0),
            duplicate_transactions=d.get("duplicate_transactions", 0),
            error_transactions=d.get("error_transactions", 0),
            warning_transactions=d.get("warning_transactions", 0),
            wallets=wallets,
            transactions=txs,
            existing_wallets_list=ew,
            errors=d.get("errors", []),
        )


# ---------------------------------------------------------------------------
# Wallet CSV parsing
# ---------------------------------------------------------------------------


def parse_wallets_csv(content: str) -> list[ParsedWallet]:
    """Parse koinly_wallets.csv into a list of ParsedWallet objects."""
    reader = csv.DictReader(io.StringIO(content))
    wallets: list[ParsedWallet] = []

    for row in reader:
        koinly_id = (row.get("Koinly ID") or "").strip()
        name = (row.get("Name") or "").strip()
        koinly_type = (row.get("Type") or "").strip().lower()
        blockchain = (row.get("Blockchain") or "").strip() or None

        if not koinly_id or not name:
            continue

        mapped_type = KOINLY_WALLET_TYPE_MAP.get(koinly_type, "other")

        wallets.append(ParsedWallet(
            koinly_id=koinly_id,
            name=name,
            koinly_type=koinly_type,
            mapped_type=mapped_type,
            blockchain=blockchain,
        ))

    return wallets


# ---------------------------------------------------------------------------
# Transaction CSV parsing
# ---------------------------------------------------------------------------


def _infer_type_from_label(label: str) -> str | None:
    """Map a Koinly label to our transaction type."""
    normalized = label.strip().lower()
    return KOINLY_LABEL_TYPE_MAP.get(normalized)


# Assets whose crypto_deposit entries are staking rewards, not transfers.
_STAKING_REWARD_ASSETS: set[str] = {
    "STETH", "STATOM", "STOSMO", "STJUNO", "STLUNA", "STINJ",
    "STEVMOS", "STCMDX", "STUMEE", "STSTARS", "STRD",
}

# Description keywords that signal interest income.
_INTEREST_KEYWORDS: set[str] = {"interest", "yield", "lending", "earn"}


def _refine_crypto_deposit_type(parsed: ParsedTransaction) -> None:
    """Upgrade a crypto_deposit to staking_reward or interest when possible.

    Called after initial type inference for transactions labelled crypto_deposit.
    Uses asset symbol and description heuristics.
    """
    if parsed.tx_type != "deposit":
        return

    asset = (parsed.to_asset or "").upper()

    # Known liquid staking tokens → staking_reward
    if asset in _STAKING_REWARD_ASSETS:
        parsed.tx_type = "staking_reward"
        return

    # Description contains interest keywords → interest
    desc = (parsed.description or "").lower()
    if any(kw in desc for kw in _INTEREST_KEYWORDS):
        parsed.tx_type = "interest"
        return


def _infer_type_from_amounts(row: dict) -> str:
    """Infer transaction type from sent/received amounts when label is empty."""
    sent = (row.get("Sent Amount") or "").strip()
    received = (row.get("Received Amount") or "").strip()
    sent_cur = (row.get("Sent Currency") or "").strip().upper()
    recv_cur = (row.get("Received Currency") or "").strip().upper()

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


def _derive_usd_values(parsed: ParsedTransaction) -> None:
    """Derive from_value_usd / to_value_usd from net_value_usd based on tx type."""
    if not parsed.net_value_usd or not parsed.tx_type:
        return

    tx_type = parsed.tx_type
    if tx_type in ("buy", "deposit", "staking_reward", "interest", "airdrop",
                    "fork", "mining", "gift_received"):
        parsed.to_value_usd = parsed.net_value_usd
    elif tx_type in ("sell", "withdrawal", "cost", "gift_sent", "lost", "fee"):
        parsed.from_value_usd = parsed.net_value_usd
    elif tx_type in ("trade", "transfer"):
        parsed.from_value_usd = parsed.net_value_usd
        parsed.to_value_usd = parsed.net_value_usd


def parse_transactions_csv(content: str) -> list[ParsedTransaction]:
    """Parse koinly_transactions.csv into a list of ParsedTransaction objects."""
    reader = csv.DictReader(io.StringIO(content))
    transactions: list[ParsedTransaction] = []

    for i, row in enumerate(reader, start=2):  # row 1 = headers
        parsed = ParsedTransaction(row_number=i, raw_data=dict(row))

        try:
            # Date
            date_str = (row.get("Date") or "").strip()
            parsed.datetime_utc = _parse_date(date_str, "%Y-%m-%d %H:%M:%S %Z")
            if not parsed.datetime_utc:
                parsed.status = "error"
                parsed.error_message = f"Cannot parse date: '{date_str}'"
                transactions.append(parsed)
                continue

            # Label & type
            label = (row.get("Label") or "").strip()
            parsed.label = label if label else None
            if label:
                parsed.tx_type = _infer_type_from_label(label)
            if not parsed.tx_type:
                parsed.tx_type = _infer_type_from_amounts(row)

            # Amounts
            parsed.from_amount = _safe_decimal(row.get("Sent Amount"))
            parsed.from_asset = (row.get("Sent Currency") or "").strip() or None
            parsed.to_amount = _safe_decimal(row.get("Received Amount"))
            parsed.to_asset = (row.get("Received Currency") or "").strip() or None
            parsed.fee_amount = _safe_decimal(row.get("Fee Amount"))
            parsed.fee_asset = (row.get("Fee Currency") or "").strip() or None

            # USD valuation
            net_worth_currency = (row.get("Net Worth Currency") or "").strip().upper()
            if net_worth_currency == "USD":
                parsed.net_value_usd = _safe_decimal(row.get("Net Worth Amount"))

            # Metadata
            parsed.description = (row.get("Description") or "").strip() or None
            parsed.tx_hash = (row.get("TxHash") or "").strip() or None
            parsed.koinly_tx_id = (row.get("Koinly ID") or "").strip() or None

            # Wallet references
            parsed.from_wallet_koinly_id = (row.get("From Wallet ID") or "").strip() or None
            parsed.to_wallet_koinly_id = (row.get("To Wallet ID") or "").strip() or None

            # Validate
            if not (parsed.from_amount or parsed.to_amount):
                parsed.status = "warning"
                parsed.error_message = "No amounts found"

        except Exception as e:
            parsed.status = "error"
            parsed.error_message = str(e)

        # Refine crypto_deposit to staking_reward/interest when heuristics match
        if parsed.status != "error" and parsed.label and parsed.label.lower() == "crypto_deposit":
            _refine_crypto_deposit_type(parsed)

        # Derive per-leg USD values from net_value_usd
        if parsed.status != "error":
            _derive_usd_values(parsed)

        transactions.append(parsed)

    return transactions
