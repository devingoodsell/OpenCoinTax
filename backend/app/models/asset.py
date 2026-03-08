from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_fiat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    coingecko_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    coincap_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decimals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<Asset(id={self.id}, symbol='{self.symbol}')>"
