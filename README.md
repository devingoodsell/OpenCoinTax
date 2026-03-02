# Crypto Tax Calculator

A locally-run crypto tax reporting application that calculates capital gains/losses, generates IRS forms (Form 8949, Schedule D), and supports importing data from Coinbase, Ledger, Koinly, and direct blockchain sync.

**All data stays on your machine.** No cloud accounts or third-party services required (except optional CoinGecko price lookups).

## Why This Exists

I was tired of paying for Crypto tax software that charged based on the number of transactions. Especially, when the majority of transactions were rewards. If others find value in it, great! Please use, contribute, or fork as you wish. It was designed for US tax purposes. 

## Prerequisites

- Python 3.13+
- Node.js 20+
- npm 10+

## Quick Start

From the project root (`crypto-tax-app/`), you can use the Makefile shortcuts:

```bash
# Backend
make install          # Create venv and install backend dependencies
make run              # Start the backend API server
make test             # Run backend tests with coverage
make migrate          # Run database migrations
make clean            # Remove __pycache__ and database files

# Frontend
make frontend-install # Install frontend npm dependencies
make frontend-dev     # Start the frontend dev server
make frontend-build   # Production build
make frontend-test    # Run frontend tests with coverage

# Both
make dev              # Start backend + frontend together (requires two terminals)
```
## Individual Service Start

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv

# Install dependencies
./venv/bin/pip install -r requirements.txt

# Run database migrations
./venv/bin/alembic upgrade head

# Start the API server
./venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### 2. Frontend Setup

Open a second terminal:

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

The UI will be available at `http://localhost:5173`. It proxies API requests to the backend automatically.

### 3. Open the App

Navigate to `http://localhost:5173` in your browser.

## Running Tests

### Backend (656 tests, 88% coverage)

```bash
cd backend
./venv/bin/pytest app/tests/ -v
```

With coverage:

```bash
./venv/bin/pytest app/tests/ -v --cov=app --cov-report=term-missing
```

### Frontend (239 tests, 91% coverage)

```bash
cd frontend
npm test
```

With coverage:

```bash
npm run test:coverage
```

## Koinly Scraper

The `koinly-scraper/` directory contains a standalone tool that extracts all wallets and transactions from your Koinly account via their internal API. It outputs CSV files that can be imported into this app using the Koinly CSV import feature.

The scraper runs entirely in your browser console -- paste the script, wait 30-60 seconds, and it downloads your data as CSV and JSON files.

See [koinly-scraper/README.md](koinly-scraper/README.md) for full setup and usage instructions.

## Project Structure

```
crypto-tax-app/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI route handlers
│   │   │   ├── wallets.py
│   │   │   ├── transactions.py
│   │   │   ├── imports.py
│   │   │   ├── tax.py
│   │   │   ├── reports.py
│   │   │   ├── portfolio.py
│   │   │   ├── prices.py
│   │   │   ├── audit.py
│   │   │   ├── accounts.py
│   │   │   ├── assets.py
│   │   │   ├── admin.py
│   │   │   └── settings.py
│   │   ├── exceptions.py     # Domain exception hierarchy
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── utils/            # Shared utilities (decimal helpers)
│   │   ├── services/         # Business logic
│   │   │   ├── tax/                # Tax engine (decomposed)
│   │   │   │   ├── orchestrator.py     # Tax calculation coordinator
│   │   │   │   ├── lot_manager.py      # Lot creation and querying
│   │   │   │   └── gain_calculator.py  # Gain/loss computation
│   │   │   ├── csv/                # CSV parser (decomposed)
│   │   │   │   ├── csv_reader.py       # Format detection and column mapping
│   │   │   │   ├── csv_validator.py    # Row validation and type coercion
│   │   │   │   └── transaction_builder.py # Transaction model creation
│   │   │   ├── blockchain/         # Chain adapter registry
│   │   │   │   ├── registry.py         # Adapter registry with @register_adapter
│   │   │   │   ├── bitcoin.py
│   │   │   │   ├── ethereum.py
│   │   │   │   ├── solana.py
│   │   │   │   ├── cosmos.py
│   │   │   │   └── litecoin.py
│   │   │   ├── lot_selector.py     # FIFO/LIFO/HIFO/Specific ID
│   │   │   ├── form_8949.py        # IRS Form 8949 generator
│   │   │   ├── schedule_d.py       # Schedule D generator
│   │   │   ├── report_generator.py # Tax summary report
│   │   │   ├── csv_parser.py       # CSV import facade
│   │   │   ├── koinly_parser.py    # Koinly CSV parsing
│   │   │   ├── koinly_importer.py  # Koinly preview/confirm workflow
│   │   │   ├── price_service.py    # Price lookup with priority
│   │   │   ├── coingecko.py        # CoinGecko API integration
│   │   │   ├── blockchain_sync.py  # Blockchain address sync
│   │   │   ├── import_session_service.py # DB-backed import sessions
│   │   │   ├── transfer_handler.py # Multi-wallet transfer tracking
│   │   │   ├── wrapping_swap_handler.py  # ETH/WETH non-taxable swaps
│   │   │   ├── staking_handler.py  # Staking reward classification
│   │   │   ├── deposit_reclassifier.py   # Heuristic deposit reclassification
│   │   │   ├── address_validator.py # Address validation
│   │   │   ├── whatif.py           # What-if analysis
│   │   │   ├── balance_reconciler.py
│   │   │   ├── missing_basis_checker.py
│   │   │   └── dedup.py           # Transaction deduplication
│   │   └── tests/            # 656 tests, 88% coverage
│   │       ├── conftest.py         # Fixtures and test DB setup
│   │       ├── factories.py        # Test entity factories
│   │       ├── test_tax/           # Tax engine tests
│   │       └── test_csv/           # CSV parser tests
│   ├── alembic/              # Database migrations
│   ├── data/                 # SQLite database (auto-created)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/client.ts     # Axios API client
│   │   ├── components/       # Shared UI components
│   │   ├── hooks/            # React hooks (useApiQuery, useTableState, useTaxYear)
│   │   ├── utils/format.ts   # Currency and crypto formatting
│   │   └── pages/            # Route pages (decomposed into subdirectories)
│   │       ├── dashboard/         # Dashboard, PortfolioChart, HoldingsSummary
│   │       ├── wallet-detail/     # WalletDetail, Holdings, Transactions, CostBasis
│   │       ├── transaction-detail/ # TransactionDetail, LotAssignments, WhatIf
│   │       ├── import/            # Import, CsvImporter, KoinlyImporter
│   │       ├── reports/           # Reports, Form8949, ScheduleD, TaxSummary
│   │       ├── Transactions.tsx
│   │       ├── Wallets.tsx
│   │       ├── Audit.tsx
│   │       └── Settings.tsx
│   ├── package.json
│   ├── vitest.config.ts
│   └── vite.config.ts
├── koinly-scraper/           # Koinly data extraction tool (see koinly-scraper/README.md)
│   ├── scraper.js            # Browser console script
│   ├── json_to_csv.py        # Reprocess raw JSON into CSVs
│   └── README.md
└── Makefile
```

## Features

### Data Import
- **CSV Import** -- Drag-and-drop CSV files from Coinbase, Ledger, or Koinly exports. Auto-detects format, previews rows, deduplicates before importing.
- **Blockchain Sync** -- Connect wallet addresses for Bitcoin, Ethereum, Solana, Cosmos (ATOM), and Litecoin. Click "Sync" to pull transactions directly from the blockchain. Supports incremental sync.
- **Koinly Scraper** -- Extract your full transaction history from Koinly's API for import into this app. See [koinly-scraper/README.md](koinly-scraper/README.md).

### Tax Calculation
- **Cost Basis Methods** -- FIFO, LIFO, HIFO, and Specific Identification. Configurable per-wallet.
- **Holding Period** -- Automatically classifies short-term (<=365 days) vs long-term (>365 days).
- **Transfer Tracking** -- Cost basis and acquisition date carry over through wallet-to-wallet transfers.
- **Wrapping Swaps** -- ETH/WETH, BTC/WBTC, and similar wrapping swaps are treated as non-taxable events with basis carry-over.
- **Fee Handling** -- Buy fees increase cost basis; sell fees reduce proceeds; transfer fees added to basis.
- **Income Recognition** -- Staking rewards, interest, airdrops, forks, and mining income tracked at FMV.

### Reports
- **Form 8949** -- Parts I (short-term) and II (long-term) with correct checkbox categories (A/B/C for ST, D/E/F for LT based on 1099 reporting).
- **Schedule D** -- Summary totals computed from Form 8949 data.
- **Tax Summary** -- Total capital gains/losses, income by category, fee totals.
- **CSV Export** -- Download Form 8949 as CSV for TurboTax or other software.

### Analysis
- **What-If Analysis** -- Compare FIFO vs LIFO vs HIFO outcomes for any sell before committing.
- **Method Comparison** -- Side-by-side gain/loss totals across all cost basis methods for a tax year.
- **Specific ID Override** -- Manually select which lots to sell against.

### Audit
- **Balance Reconciliation** -- Compares expected balances (from transactions) against tax lot balances.
- **Missing Cost Basis** -- Flags purchase lots with $0 cost basis (excludes airdrops, forks, gifts).
- **Orphan Deposits** -- Detects deposits with no matching outbound transaction.
- **Invariant Checks** -- Validates gain/loss math, no negative lot balances, no double-spend.

### Price Data
- **Priority System** -- Manual prices override import prices, which override CoinGecko prices.
- **CoinGecko Integration** -- Automatically fetch missing historical prices (free API, rate-limited).
- **Manual Entry** -- Set or override any asset's price for any date.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET/POST/PUT/DELETE` | `/api/wallets` | Wallet CRUD |
| `GET/POST/PUT/DELETE` | `/api/transactions` | Transaction CRUD |
| `POST` | `/api/import/csv` | Upload and parse CSV |
| `POST` | `/api/import/csv/confirm` | Confirm CSV import |
| `POST` | `/api/import/koinly` | Upload and parse Koinly CSV |
| `POST` | `/api/import/koinly/confirm` | Confirm Koinly import |
| `GET` | `/api/import/logs` | Import history |
| `POST` | `/api/wallets/{id}/sync` | Sync wallet from blockchain |
| `GET` | `/api/wallets/{id}/sync-status` | Check sync status |
| `POST` | `/api/tax/recalculate` | Run tax engine |
| `GET` | `/api/tax/summary/{year}` | Tax year summary |
| `GET` | `/api/tax/gains/{year}` | Capital gains list |
| `GET` | `/api/tax/lots` | Tax lot inventory |
| `POST` | `/api/tax/validate` | Run invariant checks |
| `GET` | `/api/tax/compare-methods/{year}` | Compare cost basis methods |
| `GET` | `/api/tax/whatif/{tx_id}` | What-if analysis |
| `POST` | `/api/tax/specific-id/{tx_id}` | Apply specific ID selection |
| `GET` | `/api/reports/8949/{year}` | Form 8949 JSON |
| `GET` | `/api/reports/8949/{year}/csv` | Form 8949 CSV download |
| `GET` | `/api/reports/schedule-d/{year}` | Schedule D |
| `GET` | `/api/reports/tax-summary/{year}` | Tax summary |
| `GET` | `/api/portfolio/daily-values` | Portfolio daily values |
| `GET` | `/api/portfolio/holdings` | Current holdings |
| `GET` | `/api/portfolio/stats` | Portfolio statistics |
| `GET` | `/api/prices/{asset_id}/{date}` | Get price |
| `POST` | `/api/prices/manual` | Set manual price |
| `GET` | `/api/prices/missing/{year}` | List missing prices |
| `POST` | `/api/prices/fetch-missing` | Fetch from CoinGecko |
| `POST` | `/api/prices/refresh` | Refresh current prices |
| `POST` | `/api/prices/backfill` | Backfill historical prices |
| `GET` | `/api/audit/reconciliation` | Balance reconciliation |
| `GET` | `/api/audit/missing-basis` | Missing cost basis report |
| `GET` | `/api/audit/summary` | Audit overview |
| `POST` | `/api/assets/{id}/hide` | Hide asset |
| `POST` | `/api/assets/{id}/unhide` | Unhide asset |
| `GET/PUT` | `/api/settings` | App settings |
| `POST` | `/api/admin/reset` | Reset database |

## Configuration

Environment variables (prefix with `CRYPTO_TAX_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `CRYPTO_TAX_DB_PATH` | `data/crypto_tax.db` | SQLite database file path |
| `CRYPTO_TAX_DEFAULT_COST_BASIS_METHOD` | `fifo` | Default lot selection method |
| `CRYPTO_TAX_DEFAULT_TAX_YEAR` | `2025` | Default tax year |
| `CRYPTO_TAX_COINGECKO_RATE_LIMIT_SECONDS` | `2.0` | Delay between CoinGecko API calls |
| `CRYPTO_TAX_ETHERSCAN_API_KEY` | *(none)* | API key for Ethereum sync ([get one free](https://etherscan.io/apis)) |
| `CRYPTO_TAX_HELIUS_API_KEY` | *(none)* | API key for Solana sync ([get one free](https://helius.dev)) |

## Blockchain Sync

Sync transaction history directly from the blockchain for Bitcoin, Ethereum, Solana, Cosmos (ATOM), and Litecoin.

### Supported Chains

| Chain | Explorer API | API Key Required |
|-------|-------------|-----------------|
| Bitcoin | Blockstream.info | No |
| Ethereum | Etherscan | Yes |
| Solana | Helius | Yes |
| Cosmos (ATOM) | Cosmos LCD | No |
| Litecoin | Blockcypher | No |

### Usage

1. Create a wallet and set the **Blockchain** and **Address** fields
2. Open the wallet detail page
3. Click **Sync** to pull transactions from the blockchain
4. First sync fetches full history; subsequent syncs only fetch new transactions

### API Key Setup

For Ethereum and Solana, set API keys as environment variables before starting the backend:

```bash
export CRYPTO_TAX_ETHERSCAN_API_KEY="your-key-here"
export CRYPTO_TAX_HELIUS_API_KEY="your-key-here"
```

Bitcoin, Cosmos, and Litecoin work without any API keys.

## Tech Stack

- **Backend:** Python 3.13, FastAPI, SQLAlchemy, SQLite, Alembic
- **Frontend:** React 19, TypeScript, Vite 7, Tailwind CSS v4, React Router v7, Recharts
- **Testing:** pytest (656 tests, 88% coverage), Vitest (239 tests, 91% coverage)

## License

This project is licensed under the [MIT License](LICENSE).
