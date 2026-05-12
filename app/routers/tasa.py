from __future__ import annotations

from datetime import date as date_type
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TasaCambio
from app.schemas import TasaCambioCreate, TasaCambioOut
from app.services.tasa_service import actualizar_tasa, obtener_tasa_dia


router = APIRouter(prefix="/tasa", tags=["tasa"])


@router.get("/actual", response_model=TasaCambioOut | dict)
def tasa_actual(fecha: Optional[date_type] = None, db: Session = Depends(get_db)):
    try:
        valor = obtener_tasa_dia(db, fecha)
        return {
            "id": 0,
            "fecha": fecha or date_type.today(),
            "usd_a_ves": valor,
            "created_at": None,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error obteniendo tasa: {exc}") from exc


@router.get("/", response_model=List[TasaCambioOut])
def listar_tasas(
    desde: Optional[date_type] = Query(default=None),
    hasta: Optional[date_type] = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(TasaCambio)
        if desde:
            query = query.filter(TasaCambio.fecha >= desde)
        if hasta:
            query = query.filter(TasaCambio.fecha <= hasta)
        return query.order_by(TasaCambio.fecha.desc()).limit(200).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando tasas: {exc}") from exc


@router.post("/", response_model=TasaCambioOut, status_code=status.HTTP_201_CREATED)
def crear_o_actualizar_tasa(data: TasaCambioCreate, db: Session = Depends(get_db)):
    try:
        registro = actualizar_tasa(db, data.usd_a_ves, fecha=data.fecha)
        db.commit()
        db.refresh(registro)
        return registro
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error guardando tasa: {exc}") from exc
