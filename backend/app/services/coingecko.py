"""CoinGecko integration — fetch historical prices for crypto assets.

Uses the free /coins/{id}/history endpoint.  Rate-limits requests to
respect CoinGecko's free-tier constraints.
"""

import logging
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.asset import Asset
from app.models.price_history import PriceHistory
from app.services.api_keys import get_api_key
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)

# Well-known symbol -> CoinGecko ID mapping for auto-population
SYMBOL_TO_COINGECKO: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "XRP": "ripple",
    "XLM": "stellar",
    "ATOM": "cosmos",
    "SOL": "solana",
    "MATIC": "matic-network",
    "POL": "matic-network",
    "ALGO": "algorand",
    "DOT": "polkadot",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "STETH": "staked-ether",
    "USDC": "usd-coin",
    "USDT": "tether",
    "GUSD": "gemini-dollar",
    "DAI": "dai",
    "OMG": "omisego",
    "SHIB": "shiba-inu",
    "BONK": "bonk",
    "MEW": "cat-in-a-dogs-world",
    "FTM": "fantom",
    "NEAR": "near",
    "APT": "aptos",
    "ARB": "arbitrum",
    "OP": "optimism",
    "OSMO": "osmosis",
    "INJ": "injective-protocol",
    "NTRN": "neutron-3",
    "JUNO": "juno-network",
    "STARS": "stargaze",
    "EVMOS": "evmos",
    "LUNA": "terra-luna-2",
    "CRO": "crypto-com-chain",
    "MANA": "decentraland",
    "SAND": "the-sandbox",
    "GRT": "the-graph",
    "FIL": "filecoin",
    "AAVE": "aave",
    "MKR": "maker",
    "COMP": "compound-governance-token",
    "SNX": "havven",
    "SUSHI": "sushi",
    "YFI": "yearn-finance",
    "CRV": "curve-dao-token",
    "BAT": "basic-attention-token",
    "ENJ": "enjincoin",
    "ZEC": "zcash",
    "ETC": "ethereum-classic",
    "DASH": "dash",
    "ZRX": "0x",
    "1INCH": "1inch",
    "RUNE": "thorchain",
    "HBAR": "hedera-hashgraph",
    "ICP": "internet-computer",
    "VET": "vechain",
    "EGLD": "elrond-erd-2",
    "THETA": "theta-token",
    "AXS": "axie-infinity",
    "TRX": "tron",
    "EOS": "eos",
    "XTZ": "tezos",
    "KAVA": "kava",
    "CELO": "celo",
    "ROSE": "oasis-network",
    "ONE": "harmony",
    "FLOW": "flow",
    "IMX": "immutable-x",
    "LDO": "lido-dao",
    "RPL": "rocket-pool",
    "CBETH": "coinbase-wrapped-staked-eth",
    "RETH": "rocket-pool-eth",
    "WBTC": "wrapped-bitcoin",
    "WETH": "weth",
    "STATOM": "stride-staked-atom",
    "STOSMO": "stride-staked-osmo",
    "STRD": "stride",
}


def _coingecko_client_kwargs(db: Session) -> dict:
    """Return base_url and headers for CoinGecko API calls.

    If a coingecko_api_key is configured, use the Pro API endpoint.
    """
    api_key = get_api_key(db, "coingecko_api_key")
    if api_key:
        return {
            "base_url": "https://pro-api.coingecko.com/api/v3",
            "headers": {"x-cg-pro-api-key": api_key},
        }
    return {
        "base_url": settings.coingecko_api_base,
        "headers": {},
    }


def _collect_unmapped_warnings(db: Session) -> list[str]:
    """Collect warnings for non-hidden, non-fiat assets with open lots but no coingecko_id."""
    from app.models import TaxLot

    unmapped = (
        db.query(Asset.symbol)
        .join(TaxLot, TaxLot.asset_id == Asset.id)
        .filter(
            TaxLot.is_fully_disposed == False,
            Asset.is_fiat == False,
            Asset.is_hidden == False,
            ((Asset.coingecko_id == None) | (Asset.coingecko_id == "")),
        )
        .distinct()
        .all()
    )
    symbols = sorted(row[0] for row in unmapped)
    if symbols:
        return [f"No price data available for: {', '.join(symbols)} (missing CoinGecko mapping)"]
    return []


def auto_map_coingecko_ids(db: Session) -> int:
    """Auto-populate coingecko_id for assets using the well-known mapping.

    Returns the number of assets updated.
    """
    updated = 0
    assets = (
        db.query(Asset)
        .filter((Asset.coingecko_id == None) | (Asset.coingecko_id == ""))
        .all()
    )
    for asset in assets:
        cg_id = SYMBOL_TO_COINGECKO.get(asset.symbol.upper())
        if cg_id:
            asset.coingecko_id = cg_id
            updated += 1
            logger.info("Auto-mapped %s -> %s", asset.symbol, cg_id)
    if updated:
        db.commit()
    return updated


def fetch_price(coingecko_id: str, target_date: date) -> Decimal | None:
    """Call CoinGecko /coins/{id}/history for a single date.

    Returns the USD market price as a Decimal, or None on any failure.
    """
    date_str = target_date.strftime("%d-%m-%Y")
    url = f"{settings.coingecko_api_base}/coins/{coingecko_id}/history"
    params = {"date": date_str, "localization": "false"}

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params)

        if resp.status_code == 429:
            logger.warning("CoinGecko rate limit hit for %s on %s", coingecko_id, date_str)
            return None
        if resp.status_code == 404:
            logger.info("CoinGecko 404 for %s on %s", coingecko_id, date_str)
            return None
        resp.raise_for_status()

        data = resp.json()
        usd_price = (
            data.get("market_data", {})
            .get("current_price", {})
            .get("usd")
        )
        if usd_price is None:
            logger.info("No USD price in CoinGecko response for %s on %s", coingecko_id, date_str)
            return None

        return Decimal(str(usd_price))

    except httpx.TimeoutException:
        logger.warning("CoinGecko timeout for %s on %s", coingecko_id, date_str)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("CoinGecko HTTP error %s for %s on %s", exc.response.status_code, coingecko_id, date_str)
        return None
    except Exception:
        logger.exception("Unexpected error fetching CoinGecko price for %s on %s", coingecko_id, date_str)
        return None


def fetch_missing_prices(db: Session, tax_year: int) -> dict:
    """Find all missing prices for a tax year, fetch from CoinGecko, store results.

    Returns {"fetched": int, "failed": int, "already_present": int, "warnings": [...]}.
    """
    warnings = _collect_unmapped_warnings(db)
    missing = PriceService.get_missing_prices(db, tax_year)

    fetched = 0
    failed = 0
    already_present = 0

    for i, item in enumerate(missing):
        asset_id = item["asset_id"]
        target_date = item["date"]

        # Check if coingecko price already stored (never re-fetch)
        existing_cg = (
            db.query(PriceHistory)
            .filter_by(asset_id=asset_id, date=target_date, source="coingecko")
            .first()
        )
        if existing_cg:
            already_present += 1
            continue

        # Look up the asset's coingecko_id
        asset = db.get(Asset, asset_id)
        if not asset or not asset.coingecko_id:
            failed += 1
            logger.info(
                "No coingecko_id for asset %s (%s), skipping",
                asset_id,
                asset.symbol if asset else "unknown",
            )
            continue

        # Rate-limit: wait before each API call (except the first)
        if i > 0:
            time.sleep(settings.coingecko_rate_limit_seconds)

        price = fetch_price(asset.coingecko_id, target_date)
        if price is not None:
            PriceService.store_coingecko_price(db, asset_id, target_date, price)
            fetched += 1
            logger.info(
                "Stored CoinGecko price for %s on %s: %s",
                asset.symbol,
                target_date,
                price,
            )
        else:
            failed += 1
            logger.warning(
                "Failed to fetch CoinGecko price for %s on %s",
                asset.symbol,
                target_date,
            )

    return {"fetched": fetched, "failed": failed, "already_present": already_present, "warnings": warnings}


def fetch_current_prices(coingecko_ids: list[str]) -> dict[str, Decimal]:
    """Call CoinGecko /simple/price to get current USD prices for multiple coins.

    Returns {coingecko_id: Decimal_price}, empty dict on failure.
    """
    if not coingecko_ids:
        return {}

    ids_param = ",".join(coingecko_ids)
    url = f"{settings.coingecko_api_base}/simple/price"
    params = {"ids": ids_param, "vs_currencies": "usd"}

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params)

        if resp.status_code == 429:
            logger.warning("CoinGecko rate limit hit for batch current prices")
            return {}
        resp.raise_for_status()

        data = resp.json()
        result: dict[str, Decimal] = {}
        for cg_id in coingecko_ids:
            usd_price = data.get(cg_id, {}).get("usd")
            if usd_price is not None:
                result[cg_id] = Decimal(str(usd_price))
        return result

    except httpx.TimeoutException:
        logger.warning("CoinGecko timeout for batch current prices")
        return {}
    except httpx.HTTPStatusError as exc:
        logger.warning("CoinGecko HTTP error %s for batch current prices", exc.response.status_code)
        return {}
    except Exception:
        logger.exception("Unexpected error fetching CoinGecko batch current prices")
        return {}


def refresh_current_prices(db: Session) -> dict:
    """Fetch current prices for all held non-fiat assets and store them.

    Returns {"updated": int, "failed": int, "skipped": int, "mapped": int, "warnings": [...]}.
    """
    from app.models import TaxLot

    # Auto-map coingecko_ids for known symbols first
    mapped = auto_map_coingecko_ids(db)

    # Collect warnings for assets that can't be priced
    warnings = _collect_unmapped_warnings(db)

    # Find all assets with open tax lots, non-fiat, with coingecko_id
    held_assets = (
        db.query(Asset)
        .join(TaxLot, TaxLot.asset_id == Asset.id)
        .filter(
            TaxLot.is_fully_disposed == False,
            Asset.is_fiat == False,
            Asset.coingecko_id.isnot(None),
            Asset.coingecko_id != "",
        )
        .distinct()
        .all()
    )

    if not held_assets:
        return {"updated": 0, "failed": 0, "skipped": 0, "warnings": warnings}

    # Build mapping from coingecko_id to asset
    cg_to_assets: dict[str, list[Asset]] = {}
    for asset in held_assets:
        cg_to_assets.setdefault(asset.coingecko_id, []).append(asset)

    # Fetch current prices in one batch call
    prices = fetch_current_prices(list(cg_to_assets.keys()))

    updated = 0
    failed = 0
    skipped = 0
    today = date.today()

    for cg_id, assets in cg_to_assets.items():
        price = prices.get(cg_id)
        if price is None:
            failed += len(assets)
            for asset in assets:
                logger.warning("No current price from CoinGecko for %s (%s)", asset.symbol, cg_id)
            continue

        for asset in assets:
            stored = PriceService.store_coingecko_price(db, asset.id, today, price)
            if stored:
                updated += 1
                logger.info("Stored current price for %s: %s", asset.symbol, price)
            else:
                skipped += 1

    return {"updated": updated, "failed": failed, "skipped": skipped, "mapped": mapped, "warnings": warnings}


def _fetch_chart_chunk(coingecko_id: str, days: int, retries: int = 2) -> list[tuple[date, Decimal]] | None:
    """Fetch a single chunk of market chart data from CoinGecko.

    Uses the free-tier /market_chart?days=N endpoint.
    Retries once on rate-limit (429) with a short backoff.
    Returns a list of (date, price_usd) tuples, or None on failure.
    """
    url = f"{settings.coingecko_api_base}/coins/{coingecko_id}/market_chart"
    params = {"vs_currency": "usd", "days": str(days)}

    for attempt in range(retries):
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(url, params=params)

            if resp.status_code == 429:
                wait = (attempt + 1) * 10  # 10s, 20s
                logger.info("Rate limited for %s, waiting %ds (attempt %d/%d)", coingecko_id, wait, attempt + 1, retries)
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                logger.info("CoinGecko 404 for %s chart", coingecko_id)
                return None
            resp.raise_for_status()

            data = resp.json()
            raw_prices = data.get("prices", [])

            result: list[tuple[date, Decimal]] = []
            seen_dates: set[date] = set()
            for ts_ms, price_val in raw_prices:
                d = datetime.fromtimestamp(ts_ms / 1000).date()
                if d not in seen_dates:
                    seen_dates.add(d)
                    result.append((d, Decimal(str(price_val))))

            return result

        except httpx.TimeoutException:
            logger.warning("CoinGecko timeout for %s chart (days=%d), skipping", coingecko_id, days)
            return None
        except httpx.HTTPStatusError as exc:
            logger.warning("CoinGecko HTTP error %s for %s chart", exc.response.status_code, coingecko_id)
            return None
        except Exception:
            logger.exception("Unexpected error fetching CoinGecko chart for %s", coingecko_id)
            return None

    logger.warning("Exhausted retries for %s chart, skipping", coingecko_id)
    return None


def fetch_price_range(
    coingecko_id: str, from_date: date, to_date: date
) -> list[tuple[date, Decimal]] | None:
    """Fetch daily prices using the free-tier /market_chart endpoint.

    CoinGecko free tier supports up to 365 days. For longer ranges,
    fetches the last 365 days (the chart uses forward-fill for older dates).
    Returns a list of (date, price_usd) tuples, or None on failure.
    """
    total_days = min((to_date - from_date).days + 1, 365)
    return _fetch_chart_chunk(coingecko_id, total_days)


def backfill_historical_prices(db: Session, deadline_seconds: float = 240) -> dict:
    """Fetch daily historical prices for all held assets from their earliest lot date.

    Uses the CoinGecko /market_chart endpoint for efficient bulk fetching.
    Auto-maps CoinGecko IDs for known symbols before fetching.
    Stops processing new assets once deadline_seconds has elapsed.
    Returns {"total_stored": int, "assets_processed": int, "assets_failed": int,
             "assets_skipped": int, "assets_mapped": int, "warnings": [...]}.
    """
    from app.models import TaxLot

    wall_start = time.monotonic()

    # Auto-map coingecko_ids for known symbols first
    mapped = auto_map_coingecko_ids(db)
    logger.info("Auto-mapped %d assets to CoinGecko IDs", mapped)

    # Collect warnings for assets that can't be priced
    warnings = _collect_unmapped_warnings(db)

    # Find all non-fiat assets with lots (open or closed) and a coingecko_id
    held_assets = (
        db.query(Asset)
        .join(TaxLot, TaxLot.asset_id == Asset.id)
        .filter(
            Asset.is_fiat == False,
            Asset.coingecko_id.isnot(None),
            Asset.coingecko_id != "",
        )
        .distinct()
        .all()
    )

    if not held_assets:
        return {"total_stored": 0, "assets_processed": 0, "assets_failed": 0,
                "assets_skipped": 0, "assets_mapped": mapped, "warnings": warnings}

    total_stored = 0
    assets_processed = 0
    assets_failed = 0
    assets_skipped = 0
    today = date.today()

    for i, asset in enumerate(held_assets):
        # Check deadline before starting a new asset
        elapsed = time.monotonic() - wall_start
        if elapsed >= deadline_seconds:
            remaining = len(held_assets) - i
            assets_skipped += remaining
            logger.info("Backfill deadline reached (%.0fs), skipping %d remaining assets", elapsed, remaining)
            break

        # Rate-limit between API calls (skip the first)
        if i > 0:
            time.sleep(max(6.0, settings.coingecko_rate_limit_seconds))

        # Fetch up to the last 365 days of daily prices (free tier limit)
        start = today - timedelta(days=364)
        logger.info("Backfilling prices for %s (%s) from %s [%d/%d, %.0fs elapsed]",
                     asset.symbol, asset.coingecko_id, start, i + 1, len(held_assets), elapsed)
        prices = fetch_price_range(asset.coingecko_id, start, today)

        if prices is None:
            assets_failed += 1
            logger.warning("Failed to fetch price range for %s", asset.symbol)
            continue

        stored_count = 0
        for d, price in prices:
            result = PriceService.store_coingecko_price(db, asset.id, d, price)
            if result:
                stored_count += 1

        total_stored += stored_count
        assets_processed += 1
        logger.info("Stored %d prices for %s", stored_count, asset.symbol)

    return {
        "total_stored": total_stored,
        "assets_processed": assets_processed,
        "assets_failed": assets_failed,
        "assets_skipped": assets_skipped,
        "assets_mapped": mapped,
        "warnings": warnings,
    }
