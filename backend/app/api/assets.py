"""Assets endpoints — hide/unhide spam coins."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset

router = APIRouter()


@router.patch("/{asset_id}/hide")
def hide_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset.is_hidden = True
    db.commit()
    return {"detail": "Asset hidden"}


@router.patch("/{asset_id}/unhide")
def unhide_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset.is_hidden = False
    db.commit()
    return {"detail": "Asset unhidden"}


@router.get("/hidden")
def list_hidden_assets(db: Session = Depends(get_db)):
    assets = db.query(Asset).filter(Asset.is_hidden == True).all()
    return [{"id": a.id, "symbol": a.symbol, "name": a.name} for a in assets]
