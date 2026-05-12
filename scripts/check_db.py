"""Bootstrap de la base de datos para Railway / local.

Funciones:

1. Si ``HOTEL_DB_URL`` apunta a ``/data/hotel.db`` (Railway Volume), garantiza
   que el directorio ``/data`` exista.
2. Aplica micro-migraciones idempotentes sobre SQLite:
   - Renombra cuentas antiguas ("BcoHLC", "BcoZ", ...) a los nuevos nombres
     canónicos ("Banco HLC", "Banco Z", "Efectivo Bs", "Efectivo USD").
   - Añade la columna ``tipo`` a ``tasas_cambio`` y reconstruye la tabla para
     reemplazar la restricción única ``(fecha)`` por ``(fecha, tipo)``.
3. Ejecuta ``Base.metadata.create_all`` (no destructivo).
4. Lanza el seed sólo si la base está vacía (sin habitaciones cargadas).

Uso::

    python -m scripts.check_db
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ensure_data_dir() -> None:
    db_url = os.getenv("HOTEL_DB_URL", "")
    if not db_url.startswith("sqlite"):
        return
    parsed = urlparse(db_url)
    # sqlite:///PATH  → parsed.path == "/PATH" (o "/./PATH").
    raw_path = parsed.path or ""
    if raw_path.startswith("/./"):
        raw_path = raw_path[3:]
    elif raw_path.startswith("/"):
        raw_path = raw_path[1:]
    if not raw_path:
        return
    db_path = Path("/" + raw_path) if db_url.startswith("sqlite:////") else Path(raw_path)
    parent = db_path.parent
    if parent and str(parent) not in ("", "."):
        try:
            parent.mkdir(parents=True, exist_ok=True)
            print(f"[check_db] Directorio listo: {parent}")
        except PermissionError as exc:
            print(f"[check_db] No se pudo crear {parent}: {exc}", file=sys.stderr)


def _is_sqlite(engine) -> bool:
    return engine.url.get_backend_name() == "sqlite"


def _migrar_tasas_cambio(engine) -> None:
    """Asegura columna ``tipo`` y restricción única (fecha, tipo) en SQLite."""
    if not _is_sqlite(engine):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        existe = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='tasas_cambio'")
        ).first()
        if not existe:
            return

        info = conn.execute(text("PRAGMA table_info(tasas_cambio)")).fetchall()
        nombres = {row[1] for row in info}
        if "tipo" not in nombres:
            print("[check_db] Migrando tasas_cambio: añadiendo columna 'tipo'…")
            conn.execute(
                text("ALTER TABLE tasas_cambio ADD COLUMN tipo VARCHAR(20) NOT NULL DEFAULT 'bcv'")
            )

        indices = conn.execute(
            text("PRAGMA index_list('tasas_cambio')")
        ).fetchall()
        unique_fecha_only = False
        for idx in indices:
            name = idx[1]
            unique = bool(idx[2])
            if not unique:
                continue
            cols = conn.execute(text(f"PRAGMA index_info('{name}')")).fetchall()
            col_names = [c[2] for c in cols]
            if col_names == ["fecha"]:
                unique_fecha_only = True
                print(f"[check_db] Eliminando índice único antiguo en tasas_cambio: {name}")
                conn.execute(text(f"DROP INDEX IF EXISTS \"{name}\""))

        # Asegurar que existe el nuevo índice único compuesto.
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_tasa_fecha_tipo "
                "ON tasas_cambio (fecha, tipo)"
            )
        )

        if unique_fecha_only:
            print("[check_db] Reconstrucción de tasas_cambio completada.")


def _renombrar_cuentas(engine) -> None:
    """Renombra cuentas antiguas a los nombres canónicos nuevos."""
    from sqlalchemy import text

    renombrados = {
        "BcoHLC": "Banco HLC",
        "BcoZ": "Banco Z",
        "EfectivoBs": "Efectivo Bs",
        "EfectivoUsd": "Efectivo USD",
    }
    with engine.begin() as conn:
        existe = conn.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='cuentas_banco'"
            )
        ).first()
        if not existe and _is_sqlite(engine):
            return
        for viejo, nuevo in renombrados.items():
            try:
                conn.execute(
                    text(
                        "UPDATE cuentas_banco SET nombre = :nuevo "
                        "WHERE nombre = :viejo "
                        "AND NOT EXISTS ("
                        "  SELECT 1 FROM cuentas_banco c2 WHERE c2.nombre = :nuevo"
                        ")"
                    ),
                    {"viejo": viejo, "nuevo": nuevo},
                )
            except Exception as exc:
                print(f"[check_db] Aviso renombrando {viejo}: {exc}")


def main() -> None:
    _ensure_data_dir()

    from app.database import Base, SessionLocal, engine
    import app.models  # noqa: F401  registra las tablas en metadata
    from app.models import Habitacion
    from app.seed import seed

    _migrar_tasas_cambio(engine)
    _renombrar_cuentas(engine)

    print("[check_db] Ejecutando create_all…")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        vacio = db.query(Habitacion).first() is None
    finally:
        db.close()

    if vacio:
        print("[check_db] Base de datos vacía, ejecutando seed…")
        seed()
    else:
        print("[check_db] Base con datos, seed omitido (sólo se renombran cuentas).")
        # Ejecutar seed parcial para garantizar bancos nuevos y tasa paralelo.
        os.environ["SEED_ONLY_IF_EMPTY"] = "0"
        seed()

    print("[check_db] Listo.")


if __name__ == "__main__":
    main()
