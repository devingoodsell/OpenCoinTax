"""Fernet encryption for API keys at rest."""

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_encryption_key() -> bytes:
    """Get encryption key from env var or file."""
    env_key = os.environ.get("CRYPTO_TAX_ENCRYPTION_KEY")
    if env_key:
        return env_key.encode()

    key_path = Path("data/.encryption_key")
    if key_path.exists():
        return key_path.read_bytes().strip()

    # Generate and save a new key
    key = Fernet.generate_key()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    logger.warning(
        "No CRYPTO_TAX_ENCRYPTION_KEY set. Generated file-based key at %s. "
        "Set the env var for production use.",
        key_path,
    )
    return key


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_get_encryption_key())
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns base64-encoded ciphertext."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext string."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def reset_fernet():
    """Reset cached fernet instance (for testing)."""
    global _fernet
    _fernet = None
