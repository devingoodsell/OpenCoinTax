from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import wallets, accounts, exchanges, transactions, imports, tax, reports, prices, settings, audit, portfolio, admin, assets
from app.database import _get_defaults
from app.exceptions import (
    AppError,
    NotFoundError,
    ValidationError,
    ConflictError,
    ExternalServiceError,
    ImportSessionExpiredError,
)


def _run_migrations():
    """Run lightweight schema migrations for SQLite.

    Adds columns that may be missing from older databases.
    """
    engine, _ = _get_defaults()
    with engine.connect() as conn:
        # Check if import_log_id column exists on transactions
        result = conn.exec_driver_sql("PRAGMA table_info(transactions)")
        columns = {row[1] for row in result}
        if "import_log_id" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE transactions ADD COLUMN import_log_id INTEGER "
                "REFERENCES import_logs(id) ON DELETE SET NULL"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS idx_transactions_import_log "
                "ON transactions(import_log_id)"
            )
            conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
    yield


app = FastAPI(
    title="Crypto Tax Calculator",
    description="Local crypto tax reporting — Form 8949, Schedule D, Tax Summary",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": exc.message})


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.message, "field": exc.field})


@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError):
    return JSONResponse(status_code=409, content={"detail": exc.message})


@app.exception_handler(ExternalServiceError)
async def external_service_handler(request: Request, exc: ExternalServiceError):
    return JSONResponse(status_code=502, content={"detail": exc.message})


@app.exception_handler(ImportSessionExpiredError)
async def import_session_expired_handler(request: Request, exc: ImportSessionExpiredError):
    return JSONResponse(status_code=410, content={"detail": exc.message})


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=400, content={"detail": exc.message})


# Register routers
app.include_router(wallets.router, prefix="/api/wallets", tags=["Wallets"])
app.include_router(accounts.router, prefix="/api/wallets", tags=["Accounts"])
app.include_router(exchanges.router, prefix="/api/wallets", tags=["Exchanges"])
app.include_router(transactions.router, prefix="/api/transactions", tags=["Transactions"])
app.include_router(imports.router, prefix="/api/import", tags=["Import"])
app.include_router(tax.router, prefix="/api/tax", tags=["Tax Engine"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(prices.router, prefix="/api/prices", tags=["Prices"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(audit.router, prefix="/api/audit", tags=["Audit"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(assets.router, prefix="/api/assets", tags=["Assets"])


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
