from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LotAssignment(Base):
    __tablename__ = "lot_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    disposal_tx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    tax_lot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tax_lots.id", ondelete="CASCADE"), nullable=False
    )

    # Amounts — stored as strings for decimal precision
    amount: Mapped[str] = mapped_column(String(60), nullable=False)
    cost_basis_usd: Mapped[str] = mapped_column(String(30), nullable=False)
    proceeds_usd: Mapped[str] = mapped_column(String(30), nullable=False)
    gain_loss_usd: Mapped[str] = mapped_column(String(30), nullable=False)

    holding_period: Mapped[str] = mapped_column(String(20), nullable=False)
    cost_basis_method: Mapped[str] = mapped_column(String(20), nullable=False)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    disposal_tx = relationship(
        "Transaction", back_populates="lot_assignments",
        foreign_keys=[disposal_tx_id],
    )
    tax_lot = relationship("TaxLot", back_populates="lot_assignments")

    __table_args__ = (
        Index("idx_lot_assignments_disposal", "disposal_tx_id"),
        Index("idx_lot_assignments_lot", "tax_lot_id"),
        Index("idx_lot_assignments_year", "tax_year"),
    )

    def __repr__(self) -> str:
        return (
            f"<LotAssignment(id={self.id}, disposal_tx={self.disposal_tx_id}, "
            f"lot={self.tax_lot_id}, gain_loss={self.gain_loss_usd})>"
        )
