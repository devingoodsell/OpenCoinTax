from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, WalletType


class Wallet(Base, TimestampMixin):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="wallet")
    provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    koinly_wallet_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)

    # Relationships
    accounts = relationship("Account", back_populates="wallet", cascade="all, delete-orphan")
    tax_lots = relationship("TaxLot", back_populates="wallet", cascade="all, delete-orphan")
    cost_basis_methods = relationship(
        "WalletCostBasisMethod", back_populates="wallet", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Wallet(id={self.id}, name='{self.name}', type='{self.type}')>"
