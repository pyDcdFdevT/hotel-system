from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Habitacion
from app.schemas import (
    HabitacionCreate,
    HabitacionEstado,
    HabitacionOut,
    HabitacionUpdate,
)


router = APIRouter(prefix="/habitaciones", tags=["habitaciones"])


ESTADOS_VALIDOS = {"disponible", "ocupada", "limpieza", "mantenimiento", "bloqueada"}


@router.get("/", response_model=List[HabitacionOut])
def listar(
    estado: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(Habitacion)
        if estado:
            query = query.filter(Habitacion.estado == estado)
        return query.order_by(Habitacion.numero.asc()).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando habitaciones: {exc}") from exc


@router.get("/{habitacion_id}", response_model=HabitacionOut)
def obtener(habitacion_id: int, db: Session = Depends(get_db)):
    habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
    return habitacion


@router.post("/", response_model=HabitacionOut, status_code=status.HTTP_201_CREATED)
def crear(data: HabitacionCreate, db: Session = Depends(get_db)):
    try:
        if data.estado not in ESTADOS_VALIDOS:
            raise HTTPException(status_code=400, detail="Estado inválido")
        habitacion = Habitacion(**data.model_dump())
        db.add(habitacion)
        db.commit()
        db.refresh(habitacion)
        return habitacion
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe una habitación con ese número") from exc
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creando habitación: {exc}") from exc


@router.put("/{habitacion_id}", response_model=HabitacionOut)
def actualizar(habitacion_id: int, data: HabitacionUpdate, db: Session = Depends(get_db)):
    habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
    try:
        payload = data.model_dump(exclude_unset=True)
        if "estado" in payload and payload["estado"] not in ESTADOS_VALIDOS:
            raise HTTPException(status_code=400, detail="Estado inválido")
        for key, value in payload.items():
            setattr(habitacion, key, value)
        db.commit()
        db.refresh(habitacion)
        return habitacion
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error actualizando habitación: {exc}") from exc


@router.patch("/{habitacion_id}/estado", response_model=HabitacionOut)
def cambiar_estado(habitacion_id: int, data: HabitacionEstado, db: Session = Depends(get_db)):
    if data.estado not in ESTADOS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Use: {sorted(ESTADOS_VALIDOS)}")
    habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
    try:
        habitacion.estado = data.estado
        db.commit()
        db.refresh(habitacion)
        return habitacion
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error cambiando estado: {exc}") from exc


@router.delete("/{habitacion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(habitacion_id: int, db: Session = Depends(get_db)):
    habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
    try:
        db.delete(habitacion)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="La habitación tiene reservas vinculadas",
        ) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error eliminando habitación: {exc}") from exc
    return None
