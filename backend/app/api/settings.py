from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Setting
from app.services.api_keys import is_api_key, is_masked_value, mask_api_key

router = APIRouter()


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(Setting).all()
    result = {}
    for row in rows:
        if is_api_key(row.key):
            result[row.key] = mask_api_key(row.value)
        else:
            result[row.key] = row.value
    return result


@router.put("")
def update_settings(data: dict[str, str], db: Session = Depends(get_db)):
    for key, value in data.items():
        # Skip API key updates if the value is still masked (user didn't change it)
        if is_api_key(key) and is_masked_value(value):
            continue

        existing = db.get(Setting, key)
        if existing:
            existing.value = value
        else:
            db.add(Setting(key=key, value=value))
    db.commit()
    return {"detail": "Settings updated"}
