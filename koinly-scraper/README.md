# Koinly Scraper

Extracts all wallets and transactions from your Koinly account via their internal API. Outputs CSV files for import into the Crypto tax planning app.

## Quick Start (Browser Script)

This is the recommended approach. It runs entirely in your browser, captures auth tokens automatically, and finishes in about 30 seconds.

1. Log into [Koinly](https://app.koinly.io)
2. Navigate to the **Transactions** page (`/p/transactions`)
3. Open DevTools: `F12` (or `Cmd+Option+I` on Mac)
4. Go to the **Console** tab
5. Paste the entire contents of `scraper.js` and press Enter
6. Wait for it to finish (~30-60 seconds depending on transaction count)

The script will download four files to your browser:

| File | Description |
|------|-------------|
| `koinly_wallets.csv` | All wallets with IDs, names, types, and blockchains |
| `koinly_transactions.csv` | All transactions with wallet names, amounts, currencies, fees, tx hashes |
| `raw_wallets.json` | Raw API response for wallets (for reprocessing) |
| `raw_transactions.json` | Raw API response for transactions (for reprocessing) |

## How It Works

Koinly's frontend (app.koinly.io) is a React SPA that fetches data from a separate API server (api.koinly.io). The scraper:

1. Monkey-patches `XMLHttpRequest.setRequestHeader` to intercept `X-Auth-Token` and `X-Portfolio-Token` headers
2. Triggers a pagination click to force the SPA to make an API call
3. Captures the auth tokens from that call
4. Calls `api.koinly.io/api/wallets` and `api.koinly.io/api/transactions` directly using those tokens
5. Paginates through all transaction pages (100 per page) with a 500ms delay between requests

## Reprocessing Raw JSON

If you need to regenerate the CSVs from the raw JSON files (e.g., to filter by tax year or change the output format):

```bash
python json_to_csv.py --input-dir ~/Downloads
```

Or specify files individually:

```bash
python json_to_csv.py \
  --transactions ~/Downloads/raw_transactions.json \
  --wallets ~/Downloads/raw_wallets.json \
  --output-dir ./output \
  --tax-year 2025
```

This produces:

| File | Description |
|------|-------------|
| `output/wallets.csv` | Wallet list |
| `output/transactions.csv` | All transactions |
| `output/transactions_2025.csv` | Filtered to 2025 tax year |
| `output/summary.json` | Stats: type counts, wallet activity, date ranges |

## Python API Scraper (Alternative)

If you prefer running the scraper as a standalone Python script instead of in the browser:

1. Log into Koinly in your browser
2. Open DevTools > Network tab
3. Click around to trigger an API call to `api.koinly.io`
4. Find the request and copy the `X-Auth-Token` and `X-Portfolio-Token` header values
5. Create `auth.json` from the template:

```bash
cp auth.example.json auth.json
```

6. Paste your tokens into `auth.json`:

```json
{
  "x_auth_token": "YOUR_TOKEN_HERE",
  "x_portfolio_token": "YOUR_TOKEN_HERE"
}
```

7. Run:

```bash
pip install httpx
python scrape.py
```

## Transaction CSV Columns

| Column | Description |
|--------|-------------|
| Date | UTC timestamp |
| Sent Amount / Sent Currency | What left a wallet (e.g., `1000` / `USD` for a buy) |
| Received Amount / Received Currency | What entered a wallet (e.g., `0.01` / `BTC`) |
| Fee Amount / Fee Currency | Transaction fee if any |
| Net Worth Amount | USD value at time of transaction |
| Label | Koinly transaction type (e.g., `crypto_deposit`, `exchange`, `transfer`) |
| From Wallet / To Wallet | Wallet names (e.g., `Coinbase`, `Ledger - Bitcoin (BTC)`) |
| TxHash | On-chain transaction hash |
| Koinly ID | Internal Koinly transaction ID |

## Notes

- Auth tokens expire when your Koinly session ends. You will need to re-capture them each time.
- The API returns all transactions including ones Koinly may filter in the UI (e.g., internal transfers marked as duplicates). The API total may be higher than what the Transactions page shows.
- Rate limiting: the scraper uses a 500ms delay between requests. If you get 429 errors, increase `REQUEST_DELAY_MS` in `scraper.js` or `DELAY` in the inline script.

## Files

```
koinly-scraper/
  scraper.js          # Browser console script (recommended)
  scrape.py           # Standalone Python API scraper
  json_to_csv.py      # Reprocess raw JSON into CSVs
  process_csv.py      # Legacy CSV post-processor
  auth.example.json   # Auth token template for scrape.py
```
