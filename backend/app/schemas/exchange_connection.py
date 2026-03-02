from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExchangeConnectionCreate(BaseModel):
    exchange_type: str
    api_key: str
    api_secret: str


class ExchangeConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wallet_id: int
    exchange_type: str
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime
