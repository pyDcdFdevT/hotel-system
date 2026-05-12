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


def _migrar_productos(engine) -> None:
    """Asegura columnas ``area`` y ``porcion`` en ``productos``."""
    if not _is_sqlite(engine):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        existe = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='productos'")
        ).first()
        if not existe:
            return
        info = conn.execute(text("PRAGMA table_info(productos)")).fetchall()
        columnas = {row[1] for row in info}
        if "area" not in columnas:
            print("[check_db] Migrando productos: añadiendo columna 'area'…")
            conn.execute(
                text(
                    "ALTER TABLE productos ADD COLUMN area VARCHAR(20) "
                    "NOT NULL DEFAULT 'general'"
                )
            )
            # Heurística: bebidas y cervezas → bar; comida/insumo/desayuno → cocina.
            conn.execute(
                text(
                    "UPDATE productos SET area = 'bar' "
                    "WHERE lower(categoria) IN ('bebidas','cervezas','ligeras','rones',"
                    "'whisky','licores','vinos','cockeles','cocteles')"
                )
            )
            conn.execute(
                text(
                    "UPDATE productos SET area = 'cocina' "
                    "WHERE lower(categoria) IN ('comida','insumo','para picar','desayunos',"
                    "'a la carta')"
                )
            )
        if "porcion" not in columnas:
            print("[check_db] Migrando productos: añadiendo columna 'porcion'…")
            conn.execute(text("ALTER TABLE productos ADD COLUMN porcion VARCHAR(20)"))


def _migrar_estados_habitaciones(engine) -> None:
    """Renombra estados legacy y crea las habitaciones 201-210 + 301-303 si faltan."""
    from sqlalchemy import text

    with engine.begin() as conn:
        existe = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='habitaciones'")
        ).first()
        if not existe and _is_sqlite(engine):
            return

        if _is_sqlite(engine):
            info = conn.execute(text("PRAGMA table_info(habitaciones)")).fetchall()
            columnas = {row[1] for row in info}
            if "estado" not in columnas:
                print("[check_db] Migrando habitaciones: añadiendo columna 'estado'…")
                conn.execute(
                    text(
                        "ALTER TABLE habitaciones ADD COLUMN estado VARCHAR(20) "
                        "NOT NULL DEFAULT 'disponible'"
                    )
                )

        # Mapear estados antiguos a los nuevos cinco valores soportados.
        mapping = {
            "mantenimiento": "inhabilitada",
            "bloqueada": "inhabilitada",
            "fuera_servicio": "inhabilitada",
        }
        for viejo, nuevo in mapping.items():
            try:
                result = conn.execute(
                    text("UPDATE habitaciones SET estado = :nuevo WHERE estado = :viejo"),
                    {"viejo": viejo, "nuevo": nuevo},
                )
                if result.rowcount:
                    print(
                        f"[check_db] Estado '{viejo}' migrado a '{nuevo}' "
                        f"en {result.rowcount} habitacion(es)."
                    )
            except Exception as exc:
                print(f"[check_db] Aviso migrando estado {viejo}: {exc}")

        # Habitaciones extra (sólo si no existen): 201-210 y 301-303 inhabilitadas.
        numeros_inhab = [str(n) for n in list(range(201, 211)) + list(range(301, 304))]
        for numero in numeros_inhab:
            try:
                conn.execute(
                    text(
                        "INSERT INTO habitaciones "
                        "(numero, tipo, precio_bs, precio_usd, estado, created_at, updated_at) "
                        "SELECT :numero, 'standard', 8000.00, 20.00, 'inhabilitada', "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                        "WHERE NOT EXISTS ("
                        "  SELECT 1 FROM habitaciones WHERE numero = :numero"
                        ")"
                    ),
                    {"numero": numero},
                )
            except Exception as exc:
                print(f"[check_db] Aviso insertando habitación {numero}: {exc}")


def _migrar_pedidos_habitacion(engine) -> None:
    """Añade columna ``habitacion_numero`` y ``estado_cocina`` a ``pedidos``."""
    if not _is_sqlite(engine):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        existe = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='pedidos'")
        ).first()
        if not existe:
            return
        info = conn.execute(text("PRAGMA table_info(pedidos)")).fetchall()
        columnas = {row[1] for row in info}
        if "habitacion_numero" not in columnas:
            print("[check_db] Migrando pedidos: añadiendo columna 'habitacion_numero'…")
            conn.execute(
                text("ALTER TABLE pedidos ADD COLUMN habitacion_numero VARCHAR(10)")
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_pedidos_habitacion_numero "
                    "ON pedidos (habitacion_numero)"
                )
            )
        if "estado_cocina" not in columnas:
            print("[check_db] Migrando pedidos: añadiendo columna 'estado_cocina'…")
            conn.execute(
                text(
                    "ALTER TABLE pedidos ADD COLUMN estado_cocina VARCHAR(20) "
                    "NOT NULL DEFAULT 'pendiente'"
                )
            )
            # Pedidos viejos que ya están pagados se marcan como entregados
            # para que no aparezcan en la pantalla de cocina.
            conn.execute(
                text(
                    "UPDATE pedidos SET estado_cocina = 'entregado' "
                    "WHERE estado IN ('pagado', 'cargado')"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_pedidos_estado_cocina "
                    "ON pedidos (estado_cocina)"
                )
            )


def _migrar_reservas_vehiculo(engine) -> None:
    """Añade columnas opcionales del vehículo del huésped a ``reservas``."""
    if not _is_sqlite(engine):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        existe = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='reservas'")
        ).first()
        if not existe:
            return
        info = conn.execute(text("PRAGMA table_info(reservas)")).fetchall()
        columnas = {row[1] for row in info}
        nuevos = (
            ("vehiculo_modelo", "VARCHAR(100)"),
            ("vehiculo_color", "VARCHAR(50)"),
            ("vehiculo_placa", "VARCHAR(20)"),
        )
        for nombre, tipo in nuevos:
            if nombre not in columnas:
                print(f"[check_db] Migrando reservas: añadiendo columna '{nombre}'…")
                conn.execute(
                    text(f"ALTER TABLE reservas ADD COLUMN {nombre} {tipo}")
                )


def _seed_productos_piscina(engine) -> None:
    """Inserta los productos 'Entrada Piscina' si no existen (idempotente)."""
    from sqlalchemy import text

    productos = [
        ("Entrada Piscina - Niño", "<12 años", "3.00"),
        ("Entrada Piscina - Adulto", "12+ años", "4.00"),
    ]

    with engine.begin() as conn:
        existe = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='productos'")
        ).first()
        if not existe and _is_sqlite(engine):
            return

        # Tasa BCV actual para calcular precio_bs (si todavía no existe la
        # tabla `tasas_cambio` usamos el default histórico).
        tasa = 405.35
        try:
            tasa_row = conn.execute(
                text(
                    "SELECT usd_a_ves FROM tasas_cambio "
                    "WHERE tipo = 'bcv' ORDER BY fecha DESC LIMIT 1"
                )
            ).first()
            if tasa_row and tasa_row[0]:
                tasa = float(tasa_row[0])
        except Exception:
            tasa = 405.35

        for nombre, porcion, precio_usd_str in productos:
            ya = conn.execute(
                text("SELECT 1 FROM productos WHERE nombre = :nombre"),
                {"nombre": nombre},
            ).first()
            if ya:
                continue
            precio_usd = float(precio_usd_str)
            precio_bs = round(precio_usd * tasa, 2)
            print(f"[check_db] Insertando producto virtual: {nombre} ({precio_usd_str} USD)")
            conn.execute(
                text(
                    "INSERT INTO productos ("
                    "  nombre, categoria, area, porcion, precio_bs, precio_usd, "
                    "  costo_bs, stock_actual, stock_minimo, unidad, "
                    "  es_para_venta, activo, created_at, updated_at"
                    ") VALUES ("
                    "  :nombre, 'Piscina', 'bar', :porcion, :precio_bs, :precio_usd, "
                    "  0, 999, 0, 'unidad', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {
                    "nombre": nombre,
                    "porcion": porcion,
                    "precio_bs": precio_bs,
                    "precio_usd": precio_usd,
                },
            )


def _actualizar_precio_habitaciones(engine) -> None:
    """Cambia el precio de las habitaciones que aún están en el viejo default ($40)."""
    from sqlalchemy import text

    with engine.begin() as conn:
        existe = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='habitaciones'")
        ).first()
        if not existe and _is_sqlite(engine):
            return
        # Sólo actualizamos habitaciones que coinciden con el default antiguo
        # ($40 USD / Bs 16000); así no pisamos precios que el usuario haya editado.
        result = conn.execute(
            text(
                "UPDATE habitaciones "
                "SET precio_usd = 20.00, precio_bs = 8000.00, "
                "    updated_at = CURRENT_TIMESTAMP "
                "WHERE precio_usd = 40.00 AND precio_bs = 16000.00"
            )
        )
        if result.rowcount:
            print(
                f"[check_db] Habitaciones con precio antiguo actualizadas a $20: "
                f"{result.rowcount} fila(s)"
            )


def main() -> None:
    _ensure_data_dir()

    from app.database import Base, SessionLocal, engine
    import app.models  # noqa: F401  registra las tablas en metadata
    from app.models import Habitacion
    from app.seed import seed

    _migrar_tasas_cambio(engine)
    _renombrar_cuentas(engine)
    _migrar_productos(engine)
    _actualizar_precio_habitaciones(engine)
    _migrar_estados_habitaciones(engine)
    _migrar_pedidos_habitacion(engine)
    _migrar_reservas_vehiculo(engine)
    _seed_productos_piscina(engine)

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
