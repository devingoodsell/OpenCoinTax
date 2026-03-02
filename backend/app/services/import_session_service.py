"""Import session service — CRUD for DB-backed import sessions.

Replaces the in-memory `_pending_parses` / `_pending_koinly_previews` dicts
with persistent storage so sessions survive process restarts.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.import_session import ImportSession

# Default session lifetime: 30 minutes
DEFAULT_TTL_MINUTES = 30


def create_session(
    db: Session,
    session_type: str,
    preview_data: dict | list,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> str:
    """Create a new import session and return its token."""
    token = uuid.uuid4().hex
    now = datetime.now(timezone.utc)

    session = ImportSession(
        session_token=token,
        session_type=session_type,
        preview_data=json.dumps(preview_data, default=str),
        created_at=now,
        expires_at=now + timedelta(minutes=ttl_minutes),
    )
    db.add(session)
    db.flush()
    return token


def get_session(
    db: Session,
    token: str,
    session_type: str | None = None,
) -> ImportSession | None:
    """Retrieve a non-expired import session by token.

    Returns None if the session doesn't exist, is expired, or doesn't
    match the expected session_type (when provided).
    """
    q = db.query(ImportSession).filter_by(session_token=token)
    if session_type:
        q = q.filter_by(session_type=session_type)

    session = q.first()
    if session is None:
        return None

    now = datetime.now(timezone.utc)
    # Handle naive datetimes from SQLite
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if now > expires:
        # Expired — clean up and return None
        db.delete(session)
        db.flush()
        return None

    return session


def get_preview_data(
    db: Session,
    token: str,
    session_type: str | None = None,
) -> dict | list | None:
    """Retrieve and parse the preview data JSON for a session."""
    session = get_session(db, token, session_type)
    if session is None:
        return None
    return json.loads(session.preview_data)


def delete_session(db: Session, token: str) -> bool:
    """Delete an import session by token. Returns True if found and deleted."""
    session = db.query(ImportSession).filter_by(session_token=token).first()
    if session is None:
        return False
    db.delete(session)
    db.flush()
    return True


def cleanup_expired(db: Session) -> int:
    """Delete all expired import sessions. Returns the number deleted."""
    now = datetime.now(timezone.utc)
    count = (
        db.query(ImportSession)
        .filter(ImportSession.expires_at < now)
        .delete(synchronize_session=False)
    )
    db.flush()
    return count
