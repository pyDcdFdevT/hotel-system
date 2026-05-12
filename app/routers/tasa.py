from __future__ import annotations

from datetime import date as date_type
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TasaCambio, today
from app.schemas import TasaCambioCreate, TasaCambioOut, TasasActualesOut
from app.services.tasa_service import (
    actualizar_tasa,
    actualizar_tasa_bcv,
    actualizar_tasa_paralelo,
    obtener_tasa_bcv,
    obtener_tasa_paralelo,
)


router = APIRouter(prefix="/tasa", tags=["tasa"])


@router.get("/actual", response_model=TasasActualesOut)
def tasa_actual(fecha: Optional[date_type] = None, db: Session = Depends(get_db)):
    fecha_objetivo = fecha or today()
    try:
        return TasasActualesOut(
            fecha=fecha_objetivo,
            bcv=obtener_tasa_bcv(db, fecha_objetivo),
            paralelo=obtener_tasa_paralelo(db, fecha_objetivo),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error obteniendo tasa: {exc}") from exc


@router.get("/", response_model=List[TasaCambioOut])
def listar_tasas(
    desde: Optional[date_type] = Query(default=None),
    hasta: Optional[date_type] = Query(default=None),
    tipo: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(TasaCambio)
        if desde:
            query = query.filter(TasaCambio.fecha >= desde)
        if hasta:
            query = query.filter(TasaCambio.fecha <= hasta)
        if tipo:
            query = query.filter(TasaCambio.tipo == tipo)
        return (
            query.order_by(TasaCambio.fecha.desc(), TasaCambio.tipo.asc())
            .limit(200)
            .all()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando tasas: {exc}") from exc


@router.post("/", response_model=TasaCambioOut, status_code=status.HTTP_201_CREATED)
def crear_o_actualizar_tasa(data: TasaCambioCreate, db: Session = Depends(get_db)):
    try:
        registro = actualizar_tasa(db, data.usd_a_ves, fecha=data.fecha, tipo=data.tipo)
        db.commit()
        db.refresh(registro)
        return registro
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error guardando tasa: {exc}") from exc


@router.post("/bcv", response_model=TasaCambioOut, status_code=status.HTTP_201_CREATED)
def actualizar_bcv(data: TasaCambioCreate, db: Session = Depends(get_db)):
    try:
        registro = actualizar_tasa_bcv(db, data.usd_a_ves, fecha=data.fecha)
        db.commit()
        db.refresh(registro)
        return registro
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error guardando tasa BCV: {exc}") from exc


@router.post("/paralelo", response_model=TasaCambioOut, status_code=status.HTTP_201_CREATED)
def actualizar_paralelo(data: TasaCambioCreate, db: Session = Depends(get_db)):
    try:
        registro = actualizar_tasa_paralelo(db, data.usd_a_ves, fecha=data.fecha)
        db.commit()
        db.refresh(registro)
        return registro
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error guardando tasa paralelo: {exc}") from exc
