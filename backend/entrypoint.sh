#!/bin/sh
set -e

# On first run, seed the volume with the local database if one was baked in
if [ ! -f /app/data/crypto_tax.db ] && [ -f /seed/crypto_tax.db ]; then
    echo "Seeding database from local copy..."
    cp /seed/crypto_tax.db /app/data/crypto_tax.db
fi

# Run migrations and start the server
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
