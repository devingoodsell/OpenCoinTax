from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class TaxLot(Base):
    __tablename__ = "tax_lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id"), nullable=False
    )

    # Amounts — stored as strings for decimal precision
    amount: Mapped[str] = mapped_column(String(60), nullable=False)
    remaining_amount: Mapped[str] = mapped_column(String(60), nullable=False)

    # Cost basis
    cost_basis_usd: Mapped[str] = mapped_column(String(30), nullable=False)
    cost_basis_per_unit: Mapped[str] = mapped_column(String(30), nullable=False)

    # Provenance
    acquired_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    acquisition_tx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)

    is_fully_disposed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        default=lambda: __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
    )

    # Relationships
    wallet = relationship("Wallet", back_populates="tax_lots")
    asset = relationship("Asset")
    acquisition_tx = relationship("Transaction", foreign_keys=[acquisition_tx_id])
    lot_assignments = relationship(
        "LotAssignment", back_populates="tax_lot", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_tax_lots_wallet_asset", "wallet_id", "asset_id"),
        Index(
            "idx_tax_lots_remaining",
            "wallet_id", "asset_id", "is_fully_disposed",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TaxLot(id={self.id}, asset_id={self.asset_id}, "
            f"amount={self.amount}, remaining={self.remaining_amount})>"
        )
