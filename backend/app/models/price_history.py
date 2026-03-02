from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    price_usd: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)

    asset = relationship("Asset")

    __table_args__ = (
        UniqueConstraint("asset_id", "date", "source", name="uq_price_asset_date_source"),
        Index("idx_price_history_lookup", "asset_id", "date"),
    )

    def __repr__(self) -> str:
        return (
            f"<PriceHistory(asset_id={self.asset_id}, date={self.date}, "
            f"price={self.price_usd})>"
        )
