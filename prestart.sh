#!/usr/bin/env bash
set -euo pipefail

echo "[prestart] Creando/actualizando esquema..."
python -c "from app.database import Base, engine; import app.models; Base.metadata.create_all(bind=engine)"

echo "[prestart] Ejecutando seed (idempotente; sólo si la BD está vacía)..."
SEED_ONLY_IF_EMPTY=1 python -m app.seed

echo "[prestart] Listo."
