import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Crypto Tax Calculator"
    db_path: str = str(Path(__file__).parent.parent / "data" / "crypto_tax.db")
    base_currency: str = "USD"
    default_cost_basis_method: str = "fifo"
    default_tax_year: int = 2025
    long_term_threshold_days: int = 365
    coingecko_api_base: str = "https://api.coingecko.com/api/v3"
    coingecko_rate_limit_seconds: float = 2.0
    max_upload_size_mb: int = 50

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    class Config:
        env_prefix = "CRYPTO_TAX_"


settings = Settings()
