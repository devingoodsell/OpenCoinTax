from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Setting

router = APIRouter()


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(Setting).all()
    return {row.key: row.value for row in rows}


@router.put("")
def update_settings(data: dict[str, str], db: Session = Depends(get_db)):
    for key, value in data.items():
        existing = db.get(Setting, key)
        if existing:
            existing.value = value
        else:
            db.add(Setting(key=key, value=value))
    db.commit()
    return {"detail": "Settings updated"}
