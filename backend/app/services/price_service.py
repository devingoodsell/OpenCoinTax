"""Price Data Service — look up, store, and manage historical crypto prices.

Priority order: manual > import > coingecko = coincap.
All monetary values are stored as strings and computed with decimal.Decimal.
"""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.price_history import PriceHistory
from app.models.transaction import Transaction


# Priority map — lower number = higher priority
SOURCE_PRIORITY = {"manual": 1, "import": 2, "coingecko": 3, "coincap": 3}


class PriceService:
    """Stateless service for querying and storing price data."""

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_price(db: Session, asset_id: int, target_date: date) -> Decimal | None:
        """Return the highest-priority price for an asset on a date.

        Priority: manual > import > coingecko.
        """
        rows = (
            db.query(PriceHistory)
            .filter(
                PriceHistory.asset_id == asset_id,
                PriceHistory.date == target_date,
            )
            .all()
        )
        if not rows:
            return None

        # Pick the row with the best (lowest number) priority
        best = min(rows, key=lambda r: SOURCE_PRIORITY.get(r.source, 99))
        return Decimal(best.price_usd)

    @staticmethod
    def get_prices_batch(
        db: Session,
        asset_id: int,
        start_date: date,
        end_date: date,
    ) -> dict[date, Decimal]:
        """Return {date: Decimal} for every date in [start, end] that has a price."""
        rows = (
            db.query(PriceHistory)
            .filter(
                PriceHistory.asset_id == asset_id,
                PriceHistory.date >= start_date,
                PriceHistory.date <= end_date,
            )
            .all()
        )

        # Group by date, pick best priority per date
        by_date: dict[date, list[PriceHistory]] = {}
        for r in rows:
            by_date.setdefault(r.date, []).append(r)

        result: dict[date, Decimal] = {}
        for d, group in by_date.items():
            best = min(group, key=lambda r: SOURCE_PRIORITY.get(r.source, 99))
            result[d] = Decimal(best.price_usd)

        return result

    @staticmethod
    def get_missing_prices(db: Session, tax_year: int) -> list[dict]:
        """Find all (asset, date) pairs in the tax year that have transactions
        but no price in price_history.

        Returns a list of dicts with keys: asset_id, asset_symbol, date, transaction_count.
        """
        from collections import Counter

        year_start = datetime(tax_year, 1, 1)
        year_end = datetime(tax_year, 12, 31, 23, 59, 59)

        # Load all transactions in the year
        txns = (
            db.query(Transaction)
            .filter(
                Transaction.datetime_utc >= year_start,
                Transaction.datetime_utc <= year_end,
            )
            .all()
        )

        # Collect (asset_id, date) pairs from all asset columns
        pair_counts: Counter[tuple[int, date]] = Counter()
        for tx in txns:
            tx_date = tx.datetime_utc.date() if isinstance(tx.datetime_utc, datetime) else tx.datetime_utc
            for aid in (tx.from_asset_id, tx.to_asset_id, tx.fee_asset_id):
                if aid is not None:
                    pair_counts[(aid, tx_date)] += 1

        if not pair_counts:
            return []

        # Load non-fiat asset ids and build symbol map
        fiat_ids = {a.id for a in db.query(Asset).filter(Asset.is_fiat == True).all()}  # noqa: E712
        asset_map = {a.id: a.symbol for a in db.query(Asset).all()}

        # Filter out fiat assets
        pair_counts = Counter({
            k: v for k, v in pair_counts.items() if k[0] not in fiat_ids
        })

        if not pair_counts:
            return []

        # Find which pairs already have prices
        existing = set()
        for ph in db.query(PriceHistory.asset_id, PriceHistory.date).all():
            existing.add((ph.asset_id, ph.date))

        # Build result for missing pairs
        missing = []
        for (aid, d), count in sorted(pair_counts.items(), key=lambda x: (x[0][1], asset_map.get(x[0][0], ""))):
            if (aid, d) not in existing:
                missing.append({
                    "asset_id": aid,
                    "asset_symbol": asset_map.get(aid, "???"),
                    "date": d,
                    "transaction_count": count,
                })

        return missing

    @staticmethod
    def get_all_missing_prices(db: Session) -> list[dict]:
        """Find all (asset, date) pairs across ALL transactions that have no price.

        Same logic as get_missing_prices but without a year filter.
        Returns a list of dicts with keys: asset_id, asset_symbol, date, transaction_count.
        """
        from collections import Counter

        # Load all transactions (no year filter)
        txns = db.query(Transaction).all()

        # Collect (asset_id, date) pairs from all asset columns
        pair_counts: Counter[tuple[int, date]] = Counter()
        for tx in txns:
            tx_date = tx.datetime_utc.date() if isinstance(tx.datetime_utc, datetime) else tx.datetime_utc
            for aid in (tx.from_asset_id, tx.to_asset_id, tx.fee_asset_id):
                if aid is not None:
                    pair_counts[(aid, tx_date)] += 1

        if not pair_counts:
            return []

        # Load non-fiat asset ids and build symbol map
        fiat_ids = {a.id for a in db.query(Asset).filter(Asset.is_fiat == True).all()}  # noqa: E712
        asset_map = {a.id: a.symbol for a in db.query(Asset).all()}

        # Filter out fiat assets
        pair_counts = Counter({
            k: v for k, v in pair_counts.items() if k[0] not in fiat_ids
        })

        if not pair_counts:
            return []

        # Find which pairs already have prices
        existing = set()
        for ph in db.query(PriceHistory.asset_id, PriceHistory.date).all():
            existing.add((ph.asset_id, ph.date))

        # Build result for missing pairs
        missing = []
        for (aid, d), count in sorted(pair_counts.items(), key=lambda x: (x[0][1], asset_map.get(x[0][0], ""))):
            if (aid, d) not in existing:
                missing.append({
                    "asset_id": aid,
                    "asset_symbol": asset_map.get(aid, "???"),
                    "date": d,
                    "transaction_count": count,
                })

        return missing

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _quantize(value: str | Decimal) -> str:
        """Normalize a price string to 8 decimal places with ROUND_HALF_UP."""
        d = Decimal(str(value))
        return str(d.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))

    @staticmethod
    def set_manual_price(
        db: Session, asset_id: int, target_date: date, price_usd: str | Decimal
    ) -> PriceHistory:
        """Store (or overwrite) a manual price entry."""
        normalized = PriceService._quantize(price_usd)
        existing = (
            db.query(PriceHistory)
            .filter_by(asset_id=asset_id, date=target_date, source="manual")
            .first()
        )
        if existing:
            existing.price_usd = normalized
        else:
            existing = PriceHistory(
                asset_id=asset_id,
                date=target_date,
                price_usd=normalized,
                source="manual",
            )
            db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    @staticmethod
    def store_import_price(
        db: Session, asset_id: int, target_date: date, price_usd: str | Decimal
    ) -> PriceHistory | None:
        """Store an import price — does NOT overwrite manual prices."""
        # If a manual price already exists, skip
        manual = (
            db.query(PriceHistory)
            .filter_by(asset_id=asset_id, date=target_date, source="manual")
            .first()
        )
        if manual:
            return None

        normalized = PriceService._quantize(price_usd)
        existing = (
            db.query(PriceHistory)
            .filter_by(asset_id=asset_id, date=target_date, source="import")
            .first()
        )
        if existing:
            existing.price_usd = normalized
        else:
            existing = PriceHistory(
                asset_id=asset_id,
                date=target_date,
                price_usd=normalized,
                source="import",
            )
            db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    @staticmethod
    def store_coincap_price(
        db: Session, asset_id: int, target_date: date, price_usd: str | Decimal
    ) -> PriceHistory | None:
        """Store a CoinCap price — does NOT overwrite manual, import, or coingecko prices."""
        higher = (
            db.query(PriceHistory)
            .filter(
                PriceHistory.asset_id == asset_id,
                PriceHistory.date == target_date,
                PriceHistory.source.in_(["manual", "import", "coingecko"]),
            )
            .first()
        )
        if higher:
            return None

        normalized = PriceService._quantize(price_usd)
        existing = (
            db.query(PriceHistory)
            .filter_by(asset_id=asset_id, date=target_date, source="coincap")
            .first()
        )
        if existing:
            existing.price_usd = normalized
        else:
            existing = PriceHistory(
                asset_id=asset_id,
                date=target_date,
                price_usd=normalized,
                source="coincap",
            )
            db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    @staticmethod
    def store_coingecko_price(
        db: Session, asset_id: int, target_date: date, price_usd: str | Decimal
    ) -> PriceHistory | None:
        """Store a CoinGecko price — does NOT overwrite manual or import prices."""
        higher = (
            db.query(PriceHistory)
            .filter(
                PriceHistory.asset_id == asset_id,
                PriceHistory.date == target_date,
                PriceHistory.source.in_(["manual", "import"]),
            )
            .first()
        )
        if higher:
            return None

        normalized = PriceService._quantize(price_usd)
        existing = (
            db.query(PriceHistory)
            .filter_by(asset_id=asset_id, date=target_date, source="coingecko")
            .first()
        )
        if existing:
            existing.price_usd = normalized
        else:
            existing = PriceHistory(
                asset_id=asset_id,
                date=target_date,
                price_usd=normalized,
                source="coingecko",
            )
            db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
