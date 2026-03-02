"""Tests for the Fernet encryption service."""

import os

import pytest

from app.services.encryption import encrypt, decrypt, reset_fernet


@pytest.fixture(autouse=True)
def _clean_encryption_state(tmp_path, monkeypatch):
    """Reset fernet and use a temp dir so tests don't pollute real key file."""
    reset_fernet()
    # Point the key file path to tmp_path so auto-generation doesn't
    # create a real file in the project data/ directory.
    monkeypatch.chdir(tmp_path)
    # Clear any env key so tests start clean (unless a test sets one).
    monkeypatch.delenv("CRYPTO_TAX_ENCRYPTION_KEY", raising=False)
    yield
    reset_fernet()


def test_encrypt_decrypt_roundtrip():
    """encrypt then decrypt should return original plaintext."""
    plaintext = "my-secret-api-key-12345"
    ciphertext = encrypt(plaintext)
    assert ciphertext != plaintext
    assert decrypt(ciphertext) == plaintext


def test_different_plaintexts_produce_different_ciphertexts():
    ct1 = encrypt("key-one")
    ct2 = encrypt("key-two")
    assert ct1 != ct2


def test_same_plaintext_produces_different_ciphertexts():
    """Fernet tokens include a timestamp, so encrypting the same value
    twice should yield different ciphertext."""
    ct1 = encrypt("same-value")
    ct2 = encrypt("same-value")
    assert ct1 != ct2
    # But both decrypt to the same value
    assert decrypt(ct1) == "same-value"
    assert decrypt(ct2) == "same-value"


def test_env_var_key(monkeypatch):
    """When CRYPTO_TAX_ENCRYPTION_KEY is set, use it."""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    monkeypatch.setenv("CRYPTO_TAX_ENCRYPTION_KEY", key.decode())
    reset_fernet()

    plaintext = "env-var-secret"
    ciphertext = encrypt(plaintext)
    assert decrypt(ciphertext) == plaintext


def test_file_based_key_generated(tmp_path, monkeypatch):
    """When no env var, a file-based key should be auto-generated."""
    monkeypatch.chdir(tmp_path)
    reset_fernet()

    plaintext = "file-key-secret"
    ciphertext = encrypt(plaintext)
    assert decrypt(ciphertext) == plaintext

    # Verify key file was created
    key_file = tmp_path / "data" / ".encryption_key"
    assert key_file.exists()


def test_file_based_key_persists(tmp_path, monkeypatch):
    """The same file-based key should be reused across reset_fernet calls."""
    monkeypatch.chdir(tmp_path)
    reset_fernet()

    ciphertext = encrypt("persist-test")
    reset_fernet()
    assert decrypt(ciphertext) == "persist-test"


def test_empty_string():
    """Encrypt/decrypt should handle empty strings."""
    ct = encrypt("")
    assert decrypt(ct) == ""


def test_unicode_roundtrip():
    """Encrypt/decrypt should handle unicode strings."""
    plaintext = "api-key-\u00e9\u00e8\u00ea-\u4e16\u754c"
    ct = encrypt(plaintext)
    assert decrypt(ct) == plaintext
