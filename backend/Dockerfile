FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bake local database (if present) into /seed for first-run copy
RUN mkdir -p /seed /app/data && \
    if [ -f /app/data/crypto_tax.db ]; then cp /app/data/crypto_tax.db /seed/; fi

ENV CRYPTO_TAX_DB_PATH=/app/data/crypto_tax.db

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
