"""Integration tests for report generation services (Form 8949, Schedule D, Tax Summary).

Tests the full pipeline: create transactions → run tax engine → generate reports.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.models import (
    Asset, TaxLot, LotAssignment, Transaction, Wallet,
    TransactionType, HoldingPeriod,
)
from app.services.form_8949 import Form8949Generator
from app.services.schedule_d import ScheduleDGenerator
from app.services.report_generator import TaxSummaryGenerator
from app.services.tax_engine import calculate_for_wallet_asset
from app.tests.conftest import make_transaction


TAX_YEAR = 2025
BUY_DATE = datetime(2025, 1, 15)
SELL_DATE_ST = datetime(2025, 6, 15)  # short-term (< 365 days)
SELL_DATE_LT = datetime(2026, 2, 1)   # long-term (> 365 days from a 2024 buy)
LT_BUY_DATE = datetime(2024, 1, 10)   # buy date for long-term lots


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_buy_sell(db, wallet, btc, *, buy_date, buy_amount, buy_usd,
                    sell_date, sell_amount, sell_usd,
                    reported_on_1099da=False, basis_reported_to_irs=False):
    """Create a buy and sell transaction pair."""
    buy_tx = make_transaction(
        db,
        datetime_utc=buy_date,
        tx_type=TransactionType.buy.value,
        to_wallet_id=wallet.id,
        to_amount=buy_amount,
        to_asset_id=btc.id,
        from_amount=buy_usd,
        from_asset_id=_get_usd(db).id,
        to_value_usd=buy_usd,
        from_value_usd=buy_usd,
        net_value_usd=buy_usd,
    )
    sell_tx = make_transaction(
        db,
        datetime_utc=sell_date,
        tx_type=TransactionType.sell.value,
        from_wallet_id=wallet.id,
        from_amount=sell_amount,
        from_asset_id=btc.id,
        to_amount=sell_usd,
        to_asset_id=_get_usd(db).id,
        from_value_usd=sell_usd,
        to_value_usd=sell_usd,
        net_value_usd=sell_usd,
    )
    # Set 1099 flags directly
    sell_tx.reported_on_1099da = reported_on_1099da
    sell_tx.basis_reported_to_irs = basis_reported_to_irs
    db.commit()
    return buy_tx, sell_tx


def _get_usd(db):
    return db.query(Asset).filter(Asset.symbol == "USD").first()


def _run_engine(db, wallet, asset, year=TAX_YEAR):
    calculate_for_wallet_asset(db, wallet.id, asset.id, year)


# ---------------------------------------------------------------------------
# Form 8949 tests
# ---------------------------------------------------------------------------


class TestForm8949Generator:

    def test_empty_year(self, db, seed_assets, seed_wallets, seed_settings):
        """No assignments → empty rows."""
        gen = Form8949Generator(db)
        result = gen.generate(TAX_YEAR)
        assert result.tax_year == TAX_YEAR
        assert result.short_term_rows == []
        assert result.long_term_rows == []
        assert result.short_term_totals["gain_loss"] == "0.00"

    def test_short_term_gain(self, db, seed_assets, seed_wallets, seed_settings):
        """Buy low sell high (short-term) shows up in Part I."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=BUY_DATE, buy_amount="1.0", buy_usd="30000.00",
            sell_date=SELL_DATE_ST, sell_amount="1.0", sell_usd="35000.00",
        )
        _run_engine(db, wallet, btc)

        gen = Form8949Generator(db)
        result = gen.generate(TAX_YEAR)

        assert len(result.short_term_rows) == 1
        assert len(result.long_term_rows) == 0

        row = result.short_term_rows[0]
        assert "BTC" in row.description
        assert row.proceeds == "35000.00"
        assert row.cost_basis == "30000.00"
        assert row.gain_loss == "5000.00"
        assert row.holding_period == "short_term"
        assert row.checkbox_category == "C"  # no 1099-DA

    def test_long_term_loss(self, db, seed_assets, seed_wallets, seed_settings):
        """Buy high, hold > 1 year, sell low → long-term loss in Part II."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=LT_BUY_DATE, buy_amount="0.5", buy_usd="25000.00",
            sell_date=datetime(2025, 3, 1), sell_amount="0.5", sell_usd="20000.00",
        )
        # Must run engine for 2024 first to create the lot from the buy
        _run_engine(db, wallet, btc, year=2024)
        _run_engine(db, wallet, btc)

        gen = Form8949Generator(db)
        result = gen.generate(TAX_YEAR)

        assert len(result.long_term_rows) == 1
        row = result.long_term_rows[0]
        assert row.gain_loss == "-5000.00"
        assert row.holding_period == "long_term"
        assert row.checkbox_category == "F"  # no 1099-DA → maps to F for LT

    def test_checkbox_categories(self, db, seed_assets, seed_wallets, seed_settings):
        """1099-DA flags map correctly: reported+basis→A, reported+no basis→B, none→C."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Box A: reported + basis reported
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=BUY_DATE, buy_amount="0.1", buy_usd="3000.00",
            sell_date=datetime(2025, 3, 1), sell_amount="0.1", sell_usd="3500.00",
            reported_on_1099da=True, basis_reported_to_irs=True,
        )
        # Box B: reported + no basis
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=datetime(2025, 2, 1), buy_amount="0.1", buy_usd="3000.00",
            sell_date=datetime(2025, 4, 1), sell_amount="0.1", sell_usd="3500.00",
            reported_on_1099da=True, basis_reported_to_irs=False,
        )
        # Box C: not reported
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=datetime(2025, 3, 1), buy_amount="0.1", buy_usd="3000.00",
            sell_date=datetime(2025, 5, 1), sell_amount="0.1", sell_usd="3500.00",
            reported_on_1099da=False, basis_reported_to_irs=False,
        )

        _run_engine(db, wallet, btc)

        gen = Form8949Generator(db)
        result = gen.generate(TAX_YEAR)

        checkboxes = sorted([r.checkbox_category for r in result.short_term_rows])
        assert checkboxes == ["A", "B", "C"]

    def test_totals_calculation(self, db, seed_assets, seed_wallets, seed_settings):
        """Totals correctly sum across multiple short-term rows."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        _setup_buy_sell(
            db, wallet, btc,
            buy_date=BUY_DATE, buy_amount="1.0", buy_usd="30000.00",
            sell_date=datetime(2025, 4, 1), sell_amount="1.0", sell_usd="35000.00",
        )
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=datetime(2025, 2, 1), buy_amount="0.5", buy_usd="20000.00",
            sell_date=datetime(2025, 5, 1), sell_amount="0.5", sell_usd="22000.00",
        )
        _run_engine(db, wallet, btc)

        gen = Form8949Generator(db)
        result = gen.generate(TAX_YEAR)

        assert Decimal(result.short_term_totals["proceeds"]) == Decimal("57000.00")
        assert Decimal(result.short_term_totals["cost_basis"]) == Decimal("50000.00")
        assert Decimal(result.short_term_totals["gain_loss"]) == Decimal("7000.00")

    def test_csv_output(self, db, seed_assets, seed_wallets, seed_settings):
        """CSV output contains Part I/II headers and row data."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=BUY_DATE, buy_amount="1.0", buy_usd="30000.00",
            sell_date=SELL_DATE_ST, sell_amount="1.0", sell_usd="35000.00",
        )
        _run_engine(db, wallet, btc)

        gen = Form8949Generator(db)
        csv_str = gen.generate_csv(TAX_YEAR)

        assert f"Form 8949 - Tax Year {TAX_YEAR}" in csv_str
        assert "Part I - Short-Term" in csv_str
        assert "Part II - Long-Term" in csv_str
        assert "35000.00" in csv_str
        assert "TOTALS" in csv_str


# ---------------------------------------------------------------------------
# Schedule D tests
# ---------------------------------------------------------------------------


class TestScheduleDGenerator:

    def test_empty_form_8949(self):
        """Empty Form 8949 → all zeros on Schedule D."""
        from app.schemas.report import Form8949Response
        form = Form8949Response(
            tax_year=TAX_YEAR,
            short_term_rows=[],
            long_term_rows=[],
            short_term_totals={"proceeds": "0.00", "cost_basis": "0.00",
                               "adjustment_amount": "0.00", "gain_loss": "0.00"},
            long_term_totals={"proceeds": "0.00", "cost_basis": "0.00",
                              "adjustment_amount": "0.00", "gain_loss": "0.00"},
        )
        gen = ScheduleDGenerator()
        result = gen.generate(form)

        assert result.net_short_term == "0.00"
        assert result.net_long_term == "0.00"
        assert result.combined_net == "0.00"
        assert len(result.lines) == 9

    def test_schedule_d_from_8949(self, db, seed_assets, seed_wallets, seed_settings):
        """Schedule D lines reflect Form 8949 totals."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Short-term gain
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=BUY_DATE, buy_amount="1.0", buy_usd="30000.00",
            sell_date=SELL_DATE_ST, sell_amount="1.0", sell_usd="35000.00",
        )
        _run_engine(db, wallet, btc)

        form_gen = Form8949Generator(db)
        form_8949 = form_gen.generate(TAX_YEAR)

        sched_gen = ScheduleDGenerator()
        result = sched_gen.generate(form_8949)

        assert result.net_short_term == "5000.00"
        assert result.net_long_term == "0.00"
        assert result.combined_net == "5000.00"

        # Line 7 should have the net short-term
        line7 = next(l for l in result.lines if l.line == "7")
        assert line7.gain_loss == "5000.00"

        # Line 16 should be the combined
        line16 = next(l for l in result.lines if l.line == "16")
        assert line16.gain_loss == "5000.00"

    def test_mixed_short_long_term(self, db, seed_assets, seed_wallets, seed_settings):
        """Schedule D combines short-term and long-term correctly."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Long-term: buy Jan 2024, sell March 2025 → loss $3000
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=LT_BUY_DATE, buy_amount="0.5", buy_usd="23000.00",
            sell_date=datetime(2025, 3, 1), sell_amount="0.5", sell_usd="20000.00",
        )
        # Short-term: buy Jan 2025, sell June 2025 → gain $5000
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=BUY_DATE, buy_amount="1.0", buy_usd="30000.00",
            sell_date=SELL_DATE_ST, sell_amount="1.0", sell_usd="35000.00",
        )
        # Run engine for 2024 first to create the lot from the 2024 buy
        _run_engine(db, wallet, btc, year=2024)
        _run_engine(db, wallet, btc)

        form_gen = Form8949Generator(db)
        form_8949 = form_gen.generate(TAX_YEAR)

        sched_gen = ScheduleDGenerator()
        result = sched_gen.generate(form_8949)

        assert result.net_short_term == "5000.00"
        assert result.net_long_term == "-3000.00"
        assert result.combined_net == "2000.00"


# ---------------------------------------------------------------------------
# Tax Summary tests
# ---------------------------------------------------------------------------


class TestTaxSummaryGenerator:

    def test_empty_year(self, db, seed_assets, seed_wallets, seed_settings):
        """No transactions → all zeros."""
        gen = TaxSummaryGenerator(db)
        result = gen.generate(TAX_YEAR)
        assert result.tax_year == TAX_YEAR
        assert result.total_proceeds == "0.00"
        assert result.total_gains == "0.00"
        assert result.total_income == "0.00"
        assert result.total_fees_usd == "0.00"

    def test_capital_gains_summary(self, db, seed_assets, seed_wallets, seed_settings):
        """Capital gains from lot assignments are correctly tallied."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=BUY_DATE, buy_amount="2.0", buy_usd="60000.00",
            sell_date=SELL_DATE_ST, sell_amount="2.0", sell_usd="70000.00",
        )
        _run_engine(db, wallet, btc)

        gen = TaxSummaryGenerator(db)
        result = gen.generate(TAX_YEAR)

        assert result.total_proceeds == "70000.00"
        assert result.total_cost_basis == "60000.00"
        assert result.short_term_gains == "10000.00"
        assert result.short_term_losses == "0.00"
        assert result.total_gains == "10000.00"
        assert result.net_gain_loss == "10000.00"

    def test_income_categories(self, db, seed_assets, seed_wallets, seed_settings):
        """Staking, airdrop, mining, and interest income are categorized correctly."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        eth = seed_assets["ETH"]

        # Staking reward
        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1),
            tx_type=TransactionType.staking_reward.value,
            to_wallet_id=wallet.id, to_amount="0.01", to_asset_id=btc.id,
            to_value_usd="500.00",
        )
        # Airdrop
        make_transaction(
            db, datetime_utc=datetime(2025, 4, 1),
            tx_type=TransactionType.airdrop.value,
            to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=eth.id,
            to_value_usd="2000.00",
        )
        # Mining
        make_transaction(
            db, datetime_utc=datetime(2025, 5, 1),
            tx_type=TransactionType.mining.value,
            to_wallet_id=wallet.id, to_amount="0.001", to_asset_id=btc.id,
            to_value_usd="50.00",
        )
        # Interest
        make_transaction(
            db, datetime_utc=datetime(2025, 6, 1),
            tx_type=TransactionType.interest.value,
            to_wallet_id=wallet.id, to_amount="0.5", to_asset_id=eth.id,
            to_value_usd="1000.00",
        )

        gen = TaxSummaryGenerator(db)
        result = gen.generate(TAX_YEAR)

        assert result.staking_income == "500.00"
        assert result.airdrop_income == "2000.00"
        assert result.mining_income == "50.00"
        assert result.interest_income == "1000.00"
        assert result.total_income == "3550.00"

    def test_fee_totals(self, db, seed_assets, seed_wallets, seed_settings):
        """Fees across transactions are summed correctly."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        usd = _get_usd(db)

        make_transaction(
            db, datetime_utc=datetime(2025, 2, 1),
            tx_type=TransactionType.buy.value,
            to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
            from_amount="30000.00", from_asset_id=usd.id,
            to_value_usd="30000.00", from_value_usd="30000.00",
            fee_amount="50.00", fee_asset_id=usd.id, fee_value_usd="50.00",
        )
        make_transaction(
            db, datetime_utc=datetime(2025, 3, 1),
            tx_type=TransactionType.sell.value,
            from_wallet_id=wallet.id, from_amount="0.5", from_asset_id=btc.id,
            to_amount="17000.00", to_asset_id=usd.id,
            from_value_usd="17000.00", to_value_usd="17000.00",
            fee_amount="25.00", fee_asset_id=usd.id, fee_value_usd="25.00",
        )

        gen = TaxSummaryGenerator(db)
        result = gen.generate(TAX_YEAR)

        assert result.total_fees_usd == "75.00"

    def test_long_term_loss_summary(self, db, seed_assets, seed_wallets, seed_settings):
        """Long-term loss is tallied in long_term_losses."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        _setup_buy_sell(
            db, wallet, btc,
            buy_date=LT_BUY_DATE, buy_amount="1.0", buy_usd="50000.00",
            sell_date=datetime(2025, 3, 1), sell_amount="1.0", sell_usd="40000.00",
        )
        _run_engine(db, wallet, btc, year=2024)
        _run_engine(db, wallet, btc)

        gen = TaxSummaryGenerator(db)
        result = gen.generate(TAX_YEAR)

        assert result.long_term_losses == "10000.00"
        assert result.net_gain_loss == "-10000.00"

    def test_fork_income(self, db, seed_assets, seed_wallets, seed_settings):
        """Fork transaction is counted as fork income."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 5, 1),
            tx_type=TransactionType.fork.value,
            to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="300.00",
        )

        gen = TaxSummaryGenerator(db)
        result = gen.generate(TAX_YEAR)

        assert result.fork_income == "300.00"

    def test_eoy_balances(self, db, seed_assets, seed_wallets, seed_settings):
        """End-of-year balances include held lots with market value."""
        from app.models.price_history import PriceHistory
        from datetime import date

        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Buy BTC
        buy_tx = make_transaction(
            db, datetime_utc=datetime(2025, 1, 1),
            tx_type=TransactionType.buy.value,
            to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        _run_engine(db, wallet, btc)

        # Add price for Dec 31
        ph = PriceHistory(
            asset_id=btc.id, date=date(2025, 12, 31),
            price_usd="45000.00", source="coingecko",
        )
        db.add(ph)
        db.commit()

        gen = TaxSummaryGenerator(db)
        result = gen.generate(TAX_YEAR)

        assert len(result.eoy_balances) >= 1
        btc_balance = next(b for b in result.eoy_balances if b.symbol == "BTC")
        assert btc_balance.quantity == "1.0"
        assert btc_balance.market_value_usd == "45000.00"

    def test_eoy_balances_hidden_asset_excluded(self, db, seed_assets, seed_wallets, seed_settings):
        """Hidden assets are excluded from EOY balances."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Buy BTC
        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1),
            tx_type=TransactionType.buy.value,
            to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        _run_engine(db, wallet, btc)

        # Hide BTC
        btc.is_hidden = True
        db.commit()

        gen = TaxSummaryGenerator(db)
        result = gen.generate(TAX_YEAR)

        btc_balances = [b for b in result.eoy_balances if b.symbol == "BTC"]
        assert len(btc_balances) == 0

    def test_eoy_balances_fiat_excluded(self, db, seed_assets, seed_wallets, seed_settings):
        """Fiat assets are excluded from EOY balances."""
        wallet = seed_wallets["Coinbase"]
        usd = _get_usd(db)

        # Create a tx for the lot's acquisition_tx_id
        fiat_tx = make_transaction(
            db, datetime_utc=datetime(2025, 1, 1),
            tx_type=TransactionType.buy.value,
            to_wallet_id=wallet.id, to_amount="10000.0", to_asset_id=usd.id,
            to_value_usd="10000.00",
        )

        lot = TaxLot(
            wallet_id=wallet.id, asset_id=usd.id,
            amount="10000.0", remaining_amount="10000.0",
            cost_basis_usd="10000.00", cost_basis_per_unit="1.00",
            acquired_date=datetime(2025, 1, 1),
            acquisition_tx_id=fiat_tx.id,
            source_type="purchase",
        )
        db.add(lot)
        db.commit()

        gen = TaxSummaryGenerator(db)
        result = gen.generate(TAX_YEAR)

        usd_balances = [b for b in result.eoy_balances if b.symbol == "USD"]
        assert len(usd_balances) == 0

    def test_eoy_balances_fallback_price(self, db, seed_assets, seed_wallets, seed_settings):
        """Fallback price search within 14-day window is used when no exact EOY price."""
        from app.models.price_history import PriceHistory
        from datetime import date

        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1),
            tx_type=TransactionType.buy.value,
            to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        _run_engine(db, wallet, btc)

        # No price on Dec 31, but one on Dec 28
        ph = PriceHistory(
            asset_id=btc.id, date=date(2025, 12, 28),
            price_usd="44000.00", source="coingecko",
        )
        db.add(ph)
        db.commit()

        gen = TaxSummaryGenerator(db)
        result = gen.generate(TAX_YEAR)

        btc_balance = next((b for b in result.eoy_balances if b.symbol == "BTC"), None)
        assert btc_balance is not None
        assert btc_balance.market_value_usd == "44000.00"

    def test_eoy_balances_no_price(self, db, seed_assets, seed_wallets, seed_settings):
        """No price available → market_value_usd is None, shown if cost basis is sufficient."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 1, 1),
            tx_type=TransactionType.buy.value,
            to_wallet_id=wallet.id, to_amount="1.0", to_asset_id=btc.id,
            to_value_usd="30000.00",
        )
        _run_engine(db, wallet, btc)

        gen = TaxSummaryGenerator(db)
        result = gen.generate(TAX_YEAR)

        btc_balance = next((b for b in result.eoy_balances if b.symbol == "BTC"), None)
        # With $30k cost basis but no market price, should still show in results
        assert btc_balance is not None
        assert btc_balance.market_value_usd is None
        assert Decimal(btc_balance.cost_basis_usd) >= Decimal("1.00")

    def test_transfer_fees_counted(self, db, seed_assets, seed_wallets, seed_settings):
        """Transfer fees are separately tallied."""
        wallet_a = seed_wallets["Coinbase"]
        wallet_b = seed_wallets["Ledger"]
        btc = seed_assets["BTC"]

        make_transaction(
            db, datetime_utc=datetime(2025, 4, 1),
            tx_type=TransactionType.transfer.value,
            from_wallet_id=wallet_a.id, to_wallet_id=wallet_b.id,
            from_amount="1.0", from_asset_id=btc.id,
            to_amount="1.0", to_asset_id=btc.id,
            fee_value_usd="15.00",
        )

        gen = TaxSummaryGenerator(db)
        result = gen.generate(TAX_YEAR)

        assert result.transfer_fees == "15.00"


# ---------------------------------------------------------------------------
# Report API endpoint tests
# ---------------------------------------------------------------------------


class TestReportAPI:

    def test_form_8949_endpoint(self, client, db, seed_assets, seed_wallets, seed_settings):
        """GET /api/reports/8949/{year} returns Form 8949 data."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=BUY_DATE, buy_amount="1.0", buy_usd="30000.00",
            sell_date=SELL_DATE_ST, sell_amount="1.0", sell_usd="35000.00",
        )
        _run_engine(db, wallet, btc)

        resp = client.get(f"/api/reports/8949/{TAX_YEAR}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tax_year"] == TAX_YEAR
        assert len(data["short_term_rows"]) == 1
        assert data["short_term_rows"][0]["gain_loss"] == "5000.00"

    def test_form_8949_csv_endpoint(self, client, db, seed_assets, seed_wallets, seed_settings):
        """GET /api/reports/8949/{year}/csv returns CSV content."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=BUY_DATE, buy_amount="1.0", buy_usd="30000.00",
            sell_date=SELL_DATE_ST, sell_amount="1.0", sell_usd="35000.00",
        )
        _run_engine(db, wallet, btc)

        resp = client.get(f"/api/reports/8949/{TAX_YEAR}/csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "Form 8949" in resp.text

    def test_schedule_d_endpoint(self, client, db, seed_assets, seed_wallets, seed_settings):
        """GET /api/reports/schedule-d/{year} returns Schedule D data."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=BUY_DATE, buy_amount="1.0", buy_usd="30000.00",
            sell_date=SELL_DATE_ST, sell_amount="1.0", sell_usd="35000.00",
        )
        _run_engine(db, wallet, btc)

        resp = client.get(f"/api/reports/schedule-d/{TAX_YEAR}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tax_year"] == TAX_YEAR
        assert data["net_short_term"] == "5000.00"
        assert len(data["lines"]) == 9

    def test_tax_summary_endpoint(self, client, db, seed_assets, seed_wallets, seed_settings):
        """GET /api/reports/tax-summary/{year} returns summary data."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        _setup_buy_sell(
            db, wallet, btc,
            buy_date=BUY_DATE, buy_amount="1.0", buy_usd="30000.00",
            sell_date=SELL_DATE_ST, sell_amount="1.0", sell_usd="35000.00",
        )
        _run_engine(db, wallet, btc)

        resp = client.get(f"/api/reports/tax-summary/{TAX_YEAR}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tax_year"] == TAX_YEAR
        assert data["short_term_gains"] == "5000.00"

    def test_turbotax_stub(self, client, seed_assets, seed_wallets, seed_settings):
        """GET /api/reports/turbotax/{year} returns not-implemented stub."""
        resp = client.get(f"/api/reports/turbotax/{TAX_YEAR}")
        assert resp.status_code == 200
        assert "not yet implemented" in resp.json()["detail"]
