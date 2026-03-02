from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AccountCreate(BaseModel):
    name: str
    address: str
    blockchain: str


class AccountUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    blockchain: str | None = None
    is_archived: bool | None = None
    wallet_id: int | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wallet_id: int
    name: str
    address: str
    blockchain: str
    last_synced_at: datetime | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
