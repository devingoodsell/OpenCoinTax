from fastapi.testclient import TestClient

from app.exceptions import (
    AppError,
    ConflictError,
    ExternalServiceError,
    ImportSessionExpiredError,
    NotFoundError,
    ValidationError,
)
from app.main import app

client = TestClient(app)


def test_not_found_error():
    exc = NotFoundError("Wallet", "123")
    assert exc.message == "Wallet 123 not found"
    assert exc.entity == "Wallet"
    assert exc.identifier == "123"


def test_not_found_error_int_id():
    exc = NotFoundError("Transaction", 42)
    assert exc.message == "Transaction 42 not found"
    assert exc.identifier == "42"


def test_validation_error():
    exc = ValidationError("amount", "must be positive")
    assert exc.message == "must be positive"
    assert exc.field == "amount"


def test_conflict_error():
    exc = ConflictError("duplicate import")
    assert exc.message == "duplicate import"


def test_external_service_error():
    exc = ExternalServiceError("CoinGecko", "rate limited")
    assert exc.message == "CoinGecko: rate limited"
    assert exc.service == "CoinGecko"


def test_import_session_expired_error():
    exc = ImportSessionExpiredError("abc-123")
    assert exc.message == "Import session abc-123 has expired"
    assert exc.session_id == "abc-123"


def test_app_error_base():
    exc = AppError("generic error")
    assert exc.message == "generic error"
    assert str(exc) == "generic error"


def test_exception_handler_not_found(monkeypatch):
    """Verify NotFoundError maps to HTTP 404 through the middleware."""
    from app.api import admin

    original_fn = admin.router.routes

    @app.get("/api/_test/not-found")
    def _trigger():
        raise NotFoundError("Widget", "99")

    resp = client.get("/api/_test/not-found")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Widget 99 not found"}


def test_exception_handler_validation(monkeypatch):
    @app.get("/api/_test/validation")
    def _trigger():
        raise ValidationError("email", "invalid format")

    resp = client.get("/api/_test/validation")
    assert resp.status_code == 422
    assert resp.json() == {"detail": "invalid format", "field": "email"}


def test_exception_handler_conflict():
    @app.get("/api/_test/conflict")
    def _trigger():
        raise ConflictError("already exists")

    resp = client.get("/api/_test/conflict")
    assert resp.status_code == 409
    assert resp.json() == {"detail": "already exists"}


def test_exception_handler_external_service():
    @app.get("/api/_test/external")
    def _trigger():
        raise ExternalServiceError("Coinbase", "timeout")

    resp = client.get("/api/_test/external")
    assert resp.status_code == 502
    assert resp.json() == {"detail": "Coinbase: timeout"}


def test_exception_handler_import_expired():
    @app.get("/api/_test/expired")
    def _trigger():
        raise ImportSessionExpiredError("sess-001")

    resp = client.get("/api/_test/expired")
    assert resp.status_code == 410
    assert resp.json() == {"detail": "Import session sess-001 has expired"}


def test_exception_handler_generic_app_error():
    @app.get("/api/_test/generic")
    def _trigger():
        raise AppError("something went wrong")

    resp = client.get("/api/_test/generic")
    assert resp.status_code == 400
    assert resp.json() == {"detail": "something went wrong"}
