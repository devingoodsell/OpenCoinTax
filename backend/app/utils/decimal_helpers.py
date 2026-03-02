from decimal import Decimal, ROUND_HALF_UP

ZERO = Decimal("0")
PENNY = Decimal("0.01")


def to_decimal(value: str | Decimal | int | float | None) -> Decimal:
    """Convert a value to Decimal, defaulting to 0 for None or empty string."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    s = str(value)
    if s == "":
        return ZERO
    return Decimal(s)


def quantize_usd(value: Decimal) -> Decimal:
    """Round a Decimal to 2 decimal places using ROUND_HALF_UP."""
    return value.quantize(PENNY, rounding=ROUND_HALF_UP)
