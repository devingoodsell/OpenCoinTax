"""API key management utilities.

Handles masking, retrieval (DB > env var > None), and recognition of
API key settings.
"""

import os
import re

from sqlalchemy.orm import Session

from app.models import Setting

API_KEY_SETTINGS: set[str] = {
    "etherscan_api_key",
    "helius_api_key",
    "coingecko_api_key",
}

_MASKED_PATTERN = re.compile(r"^.{0,4}[\u2022]+.{0,4}$")

# Mapping from DB setting name to environment variable name
_ENV_VAR_MAP: dict[str, str] = {
    "etherscan_api_key": "CRYPTO_TAX_ETHERSCAN_API_KEY",
    "helius_api_key": "CRYPTO_TAX_HELIUS_API_KEY",
    "coingecko_api_key": "CRYPTO_TAX_COINGECKO_API_KEY",
}


def is_api_key(key: str) -> bool:
    """Return True if the setting name is a recognized API key."""
    return key in API_KEY_SETTINGS


def mask_api_key(value: str) -> str:
    """Mask an API key for safe display.

    Examples:
        "sk-abcdef123456" -> "sk-a\u2022\u2022\u2022\u20223456"
        "abc"             -> "\u2022\u2022\u2022"
        ""                -> ""
    """
    if not value:
        return ""
    if len(value) <= 4:
        return "\u2022" * len(value)
    prefix = value[:4]
    suffix = value[-4:]
    return f"{prefix}\u2022\u2022\u2022\u2022{suffix}"


def is_masked_value(value: str) -> bool:
    """Return True if the value looks like a masked API key (contains bullet chars)."""
    return bool(_MASKED_PATTERN.match(value))


def get_api_key(db: Session, key_name: str) -> str | None:
    """Retrieve an API key: check DB first, then env var, then None."""
    if key_name not in API_KEY_SETTINGS:
        return None

    # Check DB setting first
    row = db.get(Setting, key_name)
    if row and row.value:
        return row.value

    # Fall back to environment variable
    env_var = _ENV_VAR_MAP.get(key_name)
    if env_var:
        val = os.environ.get(env_var)
        if val:
            return val

    return None
