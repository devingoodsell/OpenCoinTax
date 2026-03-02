FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

ENV CRYPTO_TAX_DB_PATH=/app/data/crypto_tax.db

EXPOSE 8000

# Run Alembic migrations (creates tables on fresh DB), then start the server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
