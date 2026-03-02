from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(String(1024), nullable=False)

    def __repr__(self) -> str:
        return f"<Setting(key='{self.key}', value='{self.value}')>"


class WalletCostBasisMethod(Base):
    __tablename__ = "wallet_cost_basis_methods"

    wallet_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wallets.id", ondelete="CASCADE"), primary_key=True
    )
    tax_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    cost_basis_method: Mapped[str] = mapped_column(String(20), nullable=False)

    wallet = relationship("Wallet", back_populates="cost_basis_methods")

    def __repr__(self) -> str:
        return (
            f"<WalletCostBasisMethod(wallet_id={self.wallet_id}, "
            f"year={self.tax_year}, method='{self.cost_basis_method}')>"
        )
