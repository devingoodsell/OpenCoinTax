"""CSV parsing package — format detection, row validation, and transaction import.

Modules:
- csv_reader: Format detection and CSV file reading
- csv_validator: Row validation, type coercion, format-specific post-processing
- transaction_builder: Transaction model creation and database import
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class ParsedRow:
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
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["datetime_utc"] is not None:
            d["datetime_utc"] = d["datetime_utc"].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ParsedRow":
        if d.get("datetime_utc") and isinstance(d["datetime_utc"], str):
            d = dict(d)
            d["datetime_utc"] = datetime.fromisoformat(d["datetime_utc"])
        return cls(**d)


@dataclass
class ParseResult:
    detected_format: str
    total_rows: int
    valid_rows: int
    warning_rows: int
    error_rows: int
    rows: list[ParsedRow]

    def to_dict(self) -> dict:
        return {
            "detected_format": self.detected_format,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "warning_rows": self.warning_rows,
            "error_rows": self.error_rows,
            "rows": [r.to_dict() for r in self.rows],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ParseResult":
        return cls(
            detected_format=d["detected_format"],
            total_rows=d["total_rows"],
            valid_rows=d["valid_rows"],
            warning_rows=d["warning_rows"],
            error_rows=d["error_rows"],
            rows=[ParsedRow.from_dict(r) for r in d["rows"]],
        )


from app.services.csv.csv_reader import parse_csv
from app.services.csv.csv_validator import _safe_decimal, _parse_date
from app.services.csv.transaction_builder import import_parsed_rows

__all__ = [
    "ParsedRow",
    "ParseResult",
    "parse_csv",
    "import_parsed_rows",
    "_safe_decimal",
    "_parse_date",
]
