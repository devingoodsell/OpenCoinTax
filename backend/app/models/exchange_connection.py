from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class ExchangeConnection(Base, TimestampMixin):
    """Stored API credentials for an exchange wallet."""

    __tablename__ = "exchange_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    exchange_type: Mapped[str] = mapped_column(String(50), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    wallet = relationship("Wallet")

    def __repr__(self) -> str:
        return (
            f"<ExchangeConnection(id={self.id}, wallet_id={self.wallet_id}, "
            f"exchange_type='{self.exchange_type}')>"
        )
