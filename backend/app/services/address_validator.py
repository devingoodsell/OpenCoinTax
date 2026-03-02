"""Blockchain address validation per chain."""

import hashlib
import re


SUPPORTED_CHAINS = {"bitcoin", "ethereum", "solana", "cosmos", "litecoin"}

# Bech32 charset
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def detect_blockchain(address: str) -> str | None:
    """Detect the blockchain from an address format. Returns chain name or None."""
    addr = address.strip()
    if not addr:
        return None

    # Bitcoin: 1..., 3..., bc1...
    if addr.lower().startswith("bc1") or (addr[0] in ("1", "3") and 25 <= len(addr) <= 35):
        return "bitcoin"

    # Ethereum: 0x...
    if addr.startswith("0x") and len(addr) == 42:
        return "ethereum"

    # Cosmos: cosmos1...
    if addr.lower().startswith("cosmos1"):
        return "cosmos"

    # Litecoin: ltc1..., L..., M...
    if addr.lower().startswith("ltc1"):
        return "litecoin"
    if addr[0] in ("L", "M") and 26 <= len(addr) <= 35:
        return "litecoin"

    # Solana: base58, 32-44 chars, no prefix overlap with BTC/LTC
    if 32 <= len(addr) <= 44 and re.match(r"^[1-9A-HJ-NP-Za-km-z]+$", addr):
        return "solana"

    return None


def validate_address(blockchain: str, address: str) -> tuple[bool, str]:
    """Validate a blockchain address. Returns (is_valid, error_message).

    If blockchain is unknown/empty, attempts auto-detection from the address format.
    """
    addr = address.strip()
    chain = blockchain.lower().strip()

    # Auto-detect blockchain if unknown or not in supported set
    if chain not in SUPPORTED_CHAINS:
        detected = detect_blockchain(addr)
        if detected:
            chain = detected
        else:
            return False, f"Unsupported blockchain: {blockchain}. Supported: {', '.join(sorted(SUPPORTED_CHAINS))}"

    validators = {
        "bitcoin": _validate_bitcoin,
        "ethereum": _validate_ethereum,
        "solana": _validate_solana,
        "cosmos": _validate_cosmos,
        "litecoin": _validate_litecoin,
    }
    return validators[chain](addr)


def _validate_bitcoin(address: str) -> tuple[bool, str]:
    """Validate Bitcoin address (Legacy, SegWit P2SH, Bech32)."""
    if not address:
        return False, "Address is empty"

    # Bech32 (bc1...)
    if address.lower().startswith("bc1"):
        if not _is_valid_bech32(address.lower(), "bc"):
            return False, "Invalid Bitcoin bech32 address"
        return True, ""

    # Legacy (1...) or P2SH (3...)
    if address[0] in ("1", "3"):
        if not _is_valid_base58check(address):
            return False, "Invalid Bitcoin base58check address"
        return True, ""

    return False, "Bitcoin address must start with 1, 3, or bc1"


def _validate_ethereum(address: str) -> tuple[bool, str]:
    """Validate Ethereum address (0x-prefixed, 40 hex chars)."""
    if not address:
        return False, "Address is empty"
    if not address.startswith("0x"):
        return False, "Ethereum address must start with 0x"
    if len(address) != 42:
        return False, "Ethereum address must be 42 characters (0x + 40 hex)"
    if not re.match(r"^0x[0-9a-fA-F]{40}$", address):
        return False, "Ethereum address contains invalid characters"
    return True, ""


def _validate_solana(address: str) -> tuple[bool, str]:
    """Validate Solana address (base58, 32-44 chars)."""
    if not address:
        return False, "Address is empty"
    if len(address) < 32 or len(address) > 44:
        return False, "Solana address must be 32-44 characters"
    if not re.match(r"^[1-9A-HJ-NP-Za-km-z]+$", address):
        return False, "Solana address contains invalid base58 characters"
    return True, ""


def _validate_cosmos(address: str) -> tuple[bool, str]:
    """Validate Cosmos/ATOM address (bech32 with cosmos1 prefix)."""
    if not address:
        return False, "Address is empty"
    if not address.startswith("cosmos1"):
        return False, "Cosmos address must start with cosmos1"
    if not _is_valid_bech32(address, "cosmos"):
        return False, "Invalid Cosmos bech32 address"
    return True, ""


def _validate_litecoin(address: str) -> tuple[bool, str]:
    """Validate Litecoin address (L/M prefix legacy, ltc1 bech32)."""
    if not address:
        return False, "Address is empty"

    # Bech32 (ltc1...)
    if address.lower().startswith("ltc1"):
        # LTC bech32 addresses: just verify format (hrp + base32 chars)
        addr = address.lower()
        data_part = addr[4:]  # after "ltc1"
        if len(data_part) < 6:
            return False, "Invalid Litecoin bech32 address"
        if not all(c in BECH32_CHARSET for c in data_part):
            return False, "Invalid Litecoin bech32 address"
        return True, ""

    # Legacy (L...) or P2SH (M... or 3...)
    if address[0] in ("L", "M", "3"):
        if len(address) < 26 or len(address) > 35:
            return False, "Invalid Litecoin address length"
        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]+$", address):
            return False, "Invalid Litecoin base58 address"
        return True, ""

    return False, "Litecoin address must start with L, M, 3, or ltc1"


# ---------- Helpers ----------

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _is_valid_base58check(address: str) -> bool:
    """Validate a base58check-encoded address."""
    try:
        # Decode base58
        num = 0
        for char in address:
            idx = _BASE58_ALPHABET.index(char)
            num = num * 58 + idx

        # Convert to bytes (25 bytes for standard addresses)
        combined = num.to_bytes(25, byteorder="big")
        payload = combined[:-4]
        checksum = combined[-4:]

        # Verify checksum (double SHA-256)
        check = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        return checksum == check
    except (ValueError, OverflowError):
        return False


def _bech32_polymod(values: list[int]) -> int:
    """Internal bech32 polymod function."""
    GEN = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    """Expand the HRP for bech32 checksum computation."""
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _is_valid_bech32(address: str, expected_hrp: str) -> bool:
    """Validate a bech32 address."""
    if address != address.lower() and address != address.upper():
        return False  # Mixed case

    address = address.lower()
    pos = address.rfind("1")
    if pos < 1 or pos + 7 > len(address) or len(address) > 90:
        return False

    hrp = address[:pos]
    if hrp != expected_hrp:
        return False

    data_part = address[pos + 1:]
    try:
        data = [BECH32_CHARSET.index(c) for c in data_part]
    except ValueError:
        return False

    if _bech32_polymod(_bech32_hrp_expand(hrp) + data) not in (1, 0x2BC830A3):
        return False

    return True
