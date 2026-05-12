from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models import TasaCambio, today


TASA_FALLBACK_BCV = Decimal("405.35")
TASA_FALLBACK_PARALELO = Decimal("415.00")

TIPOS_VALIDOS = {"bcv", "paralelo"}


def _fallback(tipo: str) -> Decimal:
    return TASA_FALLBACK_PARALELO if tipo == "paralelo" else TASA_FALLBACK_BCV


def _normalizar_tipo(tipo: Optional[str]) -> str:
    if not tipo:
        return "bcv"
    valor = tipo.lower().strip()
    if valor not in TIPOS_VALIDOS:
        raise ValueError(f"Tipo de tasa inválido '{tipo}'. Use: {sorted(TIPOS_VALIDOS)}")
    return valor


def _obtener(db: Session, tipo: str, fecha: Optional[date_type]) -> Decimal:
    fecha = fecha or today()
    registro = (
        db.query(TasaCambio)
        .filter(TasaCambio.fecha == fecha, TasaCambio.tipo == tipo)
        .order_by(TasaCambio.id.desc())
        .first()
    )
    if registro and registro.usd_a_ves and registro.usd_a_ves > 0:
        return Decimal(registro.usd_a_ves)

    ultima = (
        db.query(TasaCambio)
        .filter(TasaCambio.fecha <= fecha, TasaCambio.tipo == tipo)
        .order_by(TasaCambio.fecha.desc(), TasaCambio.id.desc())
        .first()
    )
    if ultima and ultima.usd_a_ves and ultima.usd_a_ves > 0:
        return Decimal(ultima.usd_a_ves)
    return _fallback(tipo)


def _actualizar(db: Session, tipo: str, nueva_tasa: Decimal, fecha: Optional[date_type]) -> TasaCambio:
    if nueva_tasa <= 0:
        raise ValueError("La tasa debe ser mayor a cero")
    fecha = fecha or today()
    registro = (
        db.query(TasaCambio)
        .filter(TasaCambio.fecha == fecha, TasaCambio.tipo == tipo)
        .first()
    )
    if registro:
        registro.usd_a_ves = nueva_tasa
    else:
        registro = TasaCambio(fecha=fecha, tipo=tipo, usd_a_ves=nueva_tasa)
        db.add(registro)
    db.flush()
    return registro


def obtener_tasa_bcv(db: Session, fecha: Optional[date_type] = None) -> Decimal:
    return _obtener(db, "bcv", fecha)


def obtener_tasa_paralelo(db: Session, fecha: Optional[date_type] = None) -> Decimal:
    return _obtener(db, "paralelo", fecha)


def actualizar_tasa_bcv(
    db: Session,
    nueva_tasa: Decimal,
    fecha: Optional[date_type] = None,
) -> TasaCambio:
    return _actualizar(db, "bcv", nueva_tasa, fecha)


def actualizar_tasa_paralelo(
    db: Session,
    nueva_tasa: Decimal,
    fecha: Optional[date_type] = None,
) -> TasaCambio:
    return _actualizar(db, "paralelo", nueva_tasa, fecha)


def obtener_tasa_dia(
    db: Session,
    fecha: Optional[date_type] = None,
    tipo: Optional[str] = "bcv",
) -> Decimal:
    """Devuelve la tasa del día para el tipo solicitado (bcv por defecto)."""
    tipo_norm = _normalizar_tipo(tipo)
    return _obtener(db, tipo_norm, fecha)


def actualizar_tasa(
    db: Session,
    nueva_tasa: Decimal,
    fecha: Optional[date_type] = None,
    tipo: Optional[str] = "bcv",
) -> TasaCambio:
    """Compat: actualizar tasa indicando el tipo (default bcv)."""
    tipo_norm = _normalizar_tipo(tipo)
    return _actualizar(db, tipo_norm, nueva_tasa, fecha)
