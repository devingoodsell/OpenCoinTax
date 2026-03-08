"""CoinCap v3 integration — fetch historical prices older than 1 year.

CoinCap provides 11+ years of daily price history with an API key.
Used as the fallback for dates beyond CoinGecko's free-tier 365-day limit.
"""

import logging
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.asset import Asset
from app.services.api_keys import get_api_key
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)

# Well-known symbol -> CoinCap slug mapping
# CoinCap v3 uses slugs similar to CoinGecko but not identical.
SYMBOL_TO_COINCAP: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "XRP": "xrp",
    "XLM": "stellar",
    "ATOM": "cosmos",
    "SOL": "solana",
    "MATIC": "polygon",
    "POL": "polygon",
    "ALGO": "algorand",
    "DOT": "polkadot",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "AVAX": "avalanche",
    "STETH": "lido-staked-ether",
    "USDC": "usd-coin",
    "USDT": "tether",
    "DAI": "multi-collateral-dai",
    "SHIB": "shiba-inu",
    "NEAR": "near-protocol",
    "APT": "aptos",
    "ARB": "arbitrum",
    "OP": "optimism",
    "INJ": "injective-protocol",
    "LUNA": "terra-luna-v2",
    "CRO": "crypto-com-coin",
    "MANA": "decentraland",
    "SAND": "the-sandbox",
    "GRT": "the-graph",
    "FIL": "filecoin",
    "AAVE": "aave",
    "MKR": "maker",
    "COMP": "compound",
    "SUSHI": "sushiswap",
    "YFI": "yearn-finance",
    "CRV": "curve-dao-token",
    "BAT": "basic-attention-token",
    "ZEC": "zcash",
    "ETC": "ethereum-classic",
    "DASH": "dash",
    "RUNE": "thorchain",
    "HBAR": "hedera-hashgraph",
    "ICP": "internet-computer",
    "VET": "vechain",
    "THETA": "theta-token",
    "AXS": "axie-infinity",
    "TRX": "tron",
    "EOS": "eos",
    "XTZ": "tezos",
    "KAVA": "kava",
    "CELO": "celo",
    "FLOW": "flow",
    "IMX": "immutable-x",
    "LDO": "lido-dao",
    "WBTC": "wrapped-bitcoin",
    "WETH": "weth",
}


def _coincap_headers(db: Session) -> dict[str, str] | None:
    """Return Authorization headers for CoinCap v3, or None if no key configured."""
    api_key = get_api_key(db, "coincap_api_key")
    if not api_key:
        return None
    return {"Authorization": f"Bearer {api_key}"}


def auto_map_coincap_ids(db: Session) -> int:
    """Auto-populate coincap_id for assets using the well-known mapping.

    Returns the number of assets updated.
    """
    updated = 0
    assets = (
        db.query(Asset)
        .filter((Asset.coincap_id == None) | (Asset.coincap_id == ""))  # noqa: E711
        .all()
    )
    for asset in assets:
        cc_id = SYMBOL_TO_COINCAP.get(asset.symbol.upper())
        if cc_id:
            asset.coincap_id = cc_id
            updated += 1
            logger.info("Auto-mapped %s -> CoinCap %s", asset.symbol, cc_id)
    if updated:
        db.commit()
    return updated


def fetch_price_range(
    slug: str,
    from_date: date,
    to_date: date,
    headers: dict[str, str],
) -> dict[date, Decimal] | None:
    """Fetch daily prices from CoinCap v3 for a date range.

    GET /assets/{slug}/history?interval=d1&start={ms}&end={ms}
    Returns {date: price} dict, or None on failure.
    """
    start_ms = int(datetime.combine(from_date, datetime.min.time()).timestamp() * 1000)
    end_ms = int(datetime.combine(to_date, datetime.max.time()).timestamp() * 1000)

    url = f"{settings.coincap_api_base}/assets/{slug}/history"
    params = {"interval": "d1", "start": str(start_ms), "end": str(end_ms)}

    try:
        with httpx.Client(timeout=30.0, headers=headers) as client:
            resp = client.get(url, params=params)

        if resp.status_code == 429:
            logger.warning("CoinCap rate limit hit for %s", slug)
            return None
        if resp.status_code == 404:
            logger.info("CoinCap 404 for %s", slug)
            return None
        if resp.status_code == 401:
            logger.warning("CoinCap 401 — invalid or missing API key")
            return None
        resp.raise_for_status()

        data = resp.json()
        raw_points = data.get("data", [])

        result: dict[date, Decimal] = {}
        for point in raw_points:
            price_val = point.get("priceUsd")
            ts = point.get("time")
            if price_val is None or ts is None:
                continue
            d = datetime.fromtimestamp(ts / 1000).date()
            if d not in result:
                result[d] = Decimal(str(price_val))

        return result

    except httpx.TimeoutException:
        logger.warning("CoinCap timeout for %s", slug)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("CoinCap HTTP error %s for %s", exc.response.status_code, slug)
        return None
    except Exception:
        logger.exception("Unexpected error fetching CoinCap prices for %s", slug)
        return None


def backfill_old_prices(db: Session, on_progress: callable = None) -> dict:
    """Fetch historical prices older than 365 days using CoinCap v3.

    Only fetches dates that are missing from the database.
    Returns {"total_stored": int, "assets_processed": int, "assets_skipped": int, "warnings": [...]}.
    """
    headers = _coincap_headers(db)
    if headers is None:
        logger.info("No CoinCap API key configured, skipping old price backfill")
        return {
            "total_stored": 0,
            "assets_processed": 0,
            "assets_skipped": 0,
            "warnings": ["CoinCap API key not configured — older historical prices were not fetched."],
        }

    # Auto-map coincap_ids for known symbols
    auto_map_coincap_ids(db)

    # Get all missing prices across all dates
    all_missing = PriceService.get_all_missing_prices(db)

    # Filter to only dates older than 365 days
    cutoff = date.today() - timedelta(days=365)
    old_missing = [m for m in all_missing if m["date"] < cutoff]

    if not old_missing:
        logger.info("No old missing prices (>365 days) to backfill via CoinCap")
        return {"total_stored": 0, "assets_processed": 0, "assets_skipped": 0, "warnings": []}

    # Group by asset_id -> list of missing dates
    asset_dates: dict[int, list[date]] = {}
    for m in old_missing:
        asset_dates.setdefault(m["asset_id"], []).append(m["date"])

    # Build asset_id -> coincap_id lookup
    asset_map: dict[int, Asset] = {}
    for asset in db.query(Asset).filter(
        Asset.is_fiat == False,  # noqa: E712
        Asset.coincap_id.isnot(None),
        Asset.coincap_id != "",
    ).all():
        asset_map[asset.id] = asset

    total_stored = 0
    assets_processed = 0
    assets_skipped = 0
    warnings: list[str] = []
    api_calls = 0

    asset_total = len(asset_dates)
    for asset_idx, (asset_id, missing_dates) in enumerate(asset_dates.items(), 1):
        asset = asset_map.get(asset_id)
        if not asset:
            assets_skipped += 1
            continue

        # Find the full date range needed for this asset
        min_date = min(missing_dates)
        max_date = max(missing_dates)
        missing_set = set(missing_dates)

        if on_progress:
            on_progress(f"CoinCap: {asset.symbol} ({asset_idx}/{asset_total})")

        logger.info(
            "CoinCap: fetching %s (%s) from %s to %s (%d missing dates)",
            asset.symbol, asset.coincap_id, min_date, max_date, len(missing_dates),
        )

        # CoinCap limits each request to 1 year — chunk the range
        stored_count = 0
        chunk_failed = False
        chunk_start = min_date
        while chunk_start <= max_date:
            chunk_end = min(chunk_start + timedelta(days=364), max_date)

            # Rate-limit between API calls
            if api_calls > 0:
                time.sleep(2.0)

            prices = fetch_price_range(asset.coincap_id, chunk_start, chunk_end, headers)
            api_calls += 1

            if prices is None:
                logger.warning("Failed to fetch CoinCap prices for %s (%s to %s)",
                               asset.symbol, chunk_start, chunk_end)
                chunk_failed = True
                chunk_start = chunk_end + timedelta(days=1)
                continue

            for d, price in prices.items():
                if d in missing_set:
                    result = PriceService.store_coincap_price(db, asset.id, d, price)
                    if result:
                        stored_count += 1

            chunk_start = chunk_end + timedelta(days=1)

        if chunk_failed and stored_count == 0:
            assets_skipped += 1
        else:
            assets_processed += 1
        total_stored += stored_count
        logger.info("CoinCap: stored %d prices for %s", stored_count, asset.symbol)

    return {
        "total_stored": total_stored,
        "assets_processed": assets_processed,
        "assets_skipped": assets_skipped,
        "warnings": warnings,
    }
