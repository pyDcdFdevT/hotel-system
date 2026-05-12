from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models import TasaCambio, today


TASA_FALLBACK = Decimal("405.35")


def obtener_tasa_dia(db: Session, fecha: Optional[date_type] = None) -> Decimal:
    fecha = fecha or today()
    registro = (
        db.query(TasaCambio)
        .filter(TasaCambio.fecha == fecha)
        .order_by(TasaCambio.id.desc())
        .first()
    )
    if registro and registro.usd_a_ves and registro.usd_a_ves > 0:
        return Decimal(registro.usd_a_ves)
    ultima = (
        db.query(TasaCambio)
        .filter(TasaCambio.fecha <= fecha)
        .order_by(TasaCambio.fecha.desc(), TasaCambio.id.desc())
        .first()
    )
    if ultima and ultima.usd_a_ves and ultima.usd_a_ves > 0:
        return Decimal(ultima.usd_a_ves)
    return TASA_FALLBACK


def actualizar_tasa(db: Session, nueva_tasa: Decimal, fecha: Optional[date_type] = None) -> TasaCambio:
    if nueva_tasa <= 0:
        raise ValueError("La tasa debe ser mayor a cero")
    fecha = fecha or today()
    registro = db.query(TasaCambio).filter(TasaCambio.fecha == fecha).first()
    if registro:
        registro.usd_a_ves = nueva_tasa
    else:
        registro = TasaCambio(fecha=fecha, usd_a_ves=nueva_tasa)
        db.add(registro)
    db.flush()
    return registro
