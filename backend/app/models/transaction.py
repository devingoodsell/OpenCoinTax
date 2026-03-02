from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    koinly_tx_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    tx_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    datetime_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Source / destination wallets
    from_wallet_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True
    )
    to_wallet_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True
    )

    # Source / destination accounts (for blockchain-synced transactions)
    from_account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    to_account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )

    # Amounts — stored as strings to preserve decimal precision
    from_amount: Mapped[str | None] = mapped_column(String(60), nullable=True)
    from_asset_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("assets.id"), nullable=True
    )
    to_amount: Mapped[str | None] = mapped_column(String(60), nullable=True)
    to_asset_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("assets.id"), nullable=True
    )

    # Fees
    fee_amount: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fee_asset_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("assets.id"), nullable=True
    )
    fee_value_usd: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # USD valuations at time of transaction
    from_value_usd: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_value_usd: Mapped[str | None] = mapped_column(String(30), nullable=True)
    net_value_usd: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Metadata
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_margin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Link to the import that created this transaction (for undo/delete)
    import_log_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("import_logs.id", ondelete="SET NULL"), nullable=True
    )

    # Tax error tracking
    tax_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_tax_error: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 1099-DA tracking
    reported_on_1099da: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    basis_reported_to_irs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    from_wallet = relationship("Wallet", foreign_keys=[from_wallet_id])
    to_wallet = relationship("Wallet", foreign_keys=[to_wallet_id])
    from_account = relationship("Account", foreign_keys=[from_account_id])
    to_account = relationship("Account", foreign_keys=[to_account_id])
    from_asset = relationship("Asset", foreign_keys=[from_asset_id])
    to_asset = relationship("Asset", foreign_keys=[to_asset_id])
    fee_asset = relationship("Asset", foreign_keys=[fee_asset_id])
    import_log = relationship("ImportLog", foreign_keys=[import_log_id])
    lot_assignments = relationship(
        "LotAssignment", back_populates="disposal_tx",
        foreign_keys="LotAssignment.disposal_tx_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_transactions_datetime", "datetime_utc"),
        Index("idx_transactions_wallet_asset", "from_wallet_id", "from_asset_id"),
        Index("idx_transactions_to_wallet_asset", "to_wallet_id", "to_asset_id"),
        Index("idx_transactions_account", "from_account_id"),
        Index("idx_transactions_to_account", "to_account_id"),
        Index("idx_transactions_type", "type"),
        Index("idx_transactions_koinly_id", "koinly_tx_id"),
        Index("idx_transactions_tx_hash", "tx_hash"),
        Index("idx_transactions_has_tax_error", "has_tax_error"),
        Index("idx_transactions_import_log", "import_log_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<Transaction(id={self.id}, type='{self.type}', "
            f"date='{self.datetime_utc}')>"
        )
