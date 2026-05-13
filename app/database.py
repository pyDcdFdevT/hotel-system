from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "hotel.db"

# Orden de prioridad:
# 1) DATABASE_URL sólo cuando apunta a PostgreSQL (producción)
# 2) HOTEL_DB_URL (compatibilidad con tests/scripts)
# 3) SQLite local por defecto
RAW_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not (
    RAW_DATABASE_URL.startswith("postgresql")
    or RAW_DATABASE_URL.startswith("postgres://")
):
    RAW_DATABASE_URL = os.getenv("HOTEL_DB_URL", "").strip()


def _normalize_database_url(url: str) -> str:
    """Normaliza variaciones comunes de URL de PostgreSQL."""
    # Algunas plataformas usan `postgres://`, SQLAlchemy espera `postgresql://`.
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


DATABASE_URL = _normalize_database_url(RAW_DATABASE_URL)

if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        future=True,
    )
    print("[DB] Conectando a PostgreSQL")
else:
    SQLITE_URL = DATABASE_URL or f"sqlite:///{DB_PATH}"
    sqlite_path_display = SQLITE_URL.replace("sqlite:///", "", 1)
    engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        future=True,
    )
    print(f"[DB] Conectando a SQLite: {sqlite_path_display}")


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
    expire_on_commit=False,
)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    # PRAGMA aplica sólo en SQLite; en PostgreSQL se ignora.
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        return


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
