"""Tests for import_session_service — DB-backed import session CRUD."""

import json
from datetime import datetime, timedelta, timezone

from app.models.import_session import ImportSession
from app.services.import_session_service import (
    create_session,
    get_session,
    get_preview_data,
    delete_session,
    cleanup_expired,
)


class TestCreateSession:
    def test_creates_session(self, db):
        token = create_session(db, "csv", {"rows": [1, 2, 3]})
        db.commit()

        assert isinstance(token, str)
        assert len(token) == 32  # uuid4 hex

        sess = db.query(ImportSession).filter_by(session_token=token).first()
        assert sess is not None
        assert sess.session_type == "csv"
        assert json.loads(sess.preview_data) == {"rows": [1, 2, 3]}

    def test_tokens_are_unique(self, db):
        t1 = create_session(db, "csv", {})
        t2 = create_session(db, "koinly", {})
        db.commit()
        assert t1 != t2


class TestGetSession:
    def test_retrieves_valid_session(self, db):
        token = create_session(db, "csv", {"test": True})
        db.commit()

        sess = get_session(db, token)
        assert sess is not None
        assert sess.session_token == token

    def test_returns_none_for_unknown_token(self, db):
        assert get_session(db, "nonexistent") is None

    def test_returns_none_for_expired_session(self, db):
        token = create_session(db, "csv", {}, ttl_minutes=0)
        db.commit()

        # Force the expires_at to be in the past
        sess = db.query(ImportSession).filter_by(session_token=token).first()
        sess.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()

        result = get_session(db, token)
        assert result is None

        # Session should be cleaned up
        assert db.query(ImportSession).filter_by(session_token=token).first() is None

    def test_filters_by_type(self, db):
        token = create_session(db, "csv", {})
        db.commit()

        assert get_session(db, token, "csv") is not None
        assert get_session(db, token, "koinly") is None


class TestGetPreviewData:
    def test_returns_parsed_data(self, db):
        data = {"detected_format": "koinly", "rows": [{"row": 1}]}
        token = create_session(db, "csv", data)
        db.commit()

        result = get_preview_data(db, token)
        assert result == data

    def test_returns_none_for_missing(self, db):
        assert get_preview_data(db, "missing") is None


class TestDeleteSession:
    def test_deletes_existing(self, db):
        token = create_session(db, "csv", {})
        db.commit()

        assert delete_session(db, token) is True
        db.commit()

        assert db.query(ImportSession).filter_by(session_token=token).first() is None

    def test_returns_false_for_missing(self, db):
        assert delete_session(db, "nonexistent") is False


class TestCleanupExpired:
    def test_removes_expired_sessions(self, db):
        # Create an expired session
        token1 = create_session(db, "csv", {}, ttl_minutes=0)
        db.commit()
        sess1 = db.query(ImportSession).filter_by(session_token=token1).first()
        sess1.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()

        # Create a valid session
        token2 = create_session(db, "csv", {}, ttl_minutes=60)
        db.commit()

        count = cleanup_expired(db)
        db.commit()

        assert count == 1
        assert db.query(ImportSession).filter_by(session_token=token1).first() is None
        assert db.query(ImportSession).filter_by(session_token=token2).first() is not None

    def test_no_expired_returns_zero(self, db):
        create_session(db, "csv", {}, ttl_minutes=60)
        db.commit()

        assert cleanup_expired(db) == 0
