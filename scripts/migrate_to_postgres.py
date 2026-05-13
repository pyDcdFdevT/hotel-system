"""Migra datos desde SQLite hacia PostgreSQL sin perder relaciones.

Uso:

    DATABASE_URL=postgresql://... python -m scripts.migrate_to_postgres

Opcional:
    SQLITE_PATH=/data/hotel.db  # ruta explícita de origen SQLite

Notas:
- Preserva IDs originales para mantener claves foráneas.
- Inserta en orden seguro de dependencias.
- Si ya existen filas con el mismo PK en PostgreSQL, usa ON CONFLICT DO NOTHING.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


TABLES_IN_ORDER = [
    "usuarios",
    "tasas_cambio",
    "cuentas_banco",
    "categorias_gasto",
    "habitaciones",
    "productos",
    "recetas",
    "reservas",
    "pedidos",
    "detalles_pedido",
    "movimientos_inventario",
    "gastos",
    "empleados",
    "pagos_nomina",
    "movimientos_cuenta",
    "logs_acceso",
    "favoritos_usuario",
]


def _detect_sqlite_path() -> Path:
    explicit = os.getenv("SQLITE_PATH", "").strip()
    if explicit:
        return Path(explicit)
    data_path = Path("/data/hotel.db")
    if data_path.exists():
        return data_path
    return ROOT / "hotel.db"


def _get_postgres_url() -> str:
    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw:
        raise RuntimeError("DATABASE_URL no está definido.")
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    if not raw.startswith("postgresql"):
        raise RuntimeError("DATABASE_URL debe apuntar a PostgreSQL.")
    return raw


def _load_rows(conn, table_name: str) -> list[dict]:
    rows = conn.execute(text(f'SELECT * FROM "{table_name}"')).mappings().all()
    return [dict(r) for r in rows]


def _insert_rows_pg(conn, table: Table, rows: list[dict]) -> int:
    if not rows:
        return 0

    pk_cols = [c.name for c in table.primary_key.columns]
    inserted = 0
    chunk_size = 500
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        stmt = pg_insert(table).values(chunk)
        if pk_cols:
            stmt = stmt.on_conflict_do_nothing(index_elements=pk_cols)
        try:
            result = conn.execute(stmt)
            if result.rowcount and result.rowcount > 0:
                inserted += result.rowcount
        except IntegrityError:
            # Fallback defensivo: conflicto por otras constraints.
            for row in chunk:
                single_stmt = pg_insert(table).values(row)
                if pk_cols:
                    single_stmt = single_stmt.on_conflict_do_nothing(index_elements=pk_cols)
                try:
                    r = conn.execute(single_stmt)
                    if r.rowcount and r.rowcount > 0:
                        inserted += r.rowcount
                except IntegrityError:
                    continue
    return inserted


def _reset_postgres_sequences(conn, table_names: list[str]) -> None:
    for table_name in table_names:
        try:
            seq = conn.execute(
                text("SELECT pg_get_serial_sequence(:tbl, 'id')"),
                {"tbl": table_name},
            ).scalar()
            if not seq:
                continue
            max_id = conn.execute(
                text(f'SELECT COALESCE(MAX(id), 0) FROM "{table_name}"')
            ).scalar()
            conn.execute(
                text("SELECT setval(:seq, :value, true)"),
                {"seq": seq, "value": int(max_id)},
            )
        except Exception as exc:
            print(f"[migrate] Aviso ajustando secuencia de {table_name}: {exc}")


def main() -> None:
    sqlite_path = _detect_sqlite_path()
    if not sqlite_path.exists():
        raise FileNotFoundError(f"No existe SQLite origen: {sqlite_path}")

    pg_url = _get_postgres_url()
    sqlite_url = f"sqlite:///{sqlite_path}"

    print(f"[migrate] SQLite origen: {sqlite_path}")
    print("[migrate] PostgreSQL destino: DATABASE_URL")

    sqlite_engine = create_engine(sqlite_url, future=True)
    pg_engine = create_engine(pg_url, pool_pre_ping=True, pool_recycle=300, future=True)

    # Garantiza esquema destino.
    from app.database import Base
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=pg_engine)

    src_inspector = inspect(sqlite_engine)
    dest_meta = MetaData()

    with sqlite_engine.connect() as src_conn, pg_engine.begin() as dest_conn:
        for table_name in TABLES_IN_ORDER:
            if not src_inspector.has_table(table_name):
                print(f"[migrate] {table_name}: omitida (no existe en SQLite)")
                continue

            try:
                table = Table(table_name, dest_meta, autoload_with=pg_engine)
            except Exception as exc:
                print(f"[migrate] {table_name}: omitida (no existe en PostgreSQL) → {exc}")
                continue

            rows = _load_rows(src_conn, table_name)
            inserted = _insert_rows_pg(dest_conn, table, rows)
            print(
                f"[migrate] {table_name}: origen={len(rows)} | insertadas={inserted} | "
                f"conflicto/ya existentes={max(len(rows) - inserted, 0)}"
            )

        _reset_postgres_sequences(dest_conn, TABLES_IN_ORDER)

    print("[migrate] Migración completada.")


if __name__ == "__main__":
    main()
