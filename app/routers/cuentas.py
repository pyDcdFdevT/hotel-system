from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CuentaBanco, MovimientoCuenta
from app.schemas import CuentaBancoCreate, CuentaBancoOut, MovimientoCuentaOut


router = APIRouter(prefix="/cuentas", tags=["cuentas"])


@router.get("/", response_model=List[CuentaBancoOut])
def listar(db: Session = Depends(get_db)):
    try:
        return db.query(CuentaBanco).order_by(CuentaBanco.nombre.asc()).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando cuentas: {exc}") from exc


@router.post("/", response_model=CuentaBancoOut, status_code=status.HTTP_201_CREATED)
def crear(data: CuentaBancoCreate, db: Session = Depends(get_db)):
    try:
        cuenta = CuentaBanco(**data.model_dump())
        db.add(cuenta)
        db.commit()
        db.refresh(cuenta)
        return cuenta
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe una cuenta con ese nombre") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creando cuenta: {exc}") from exc


@router.get("/{cuenta_id}/movimientos", response_model=List[MovimientoCuentaOut])
def movimientos(
    cuenta_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    cuenta = db.query(CuentaBanco).filter(CuentaBanco.id == cuenta_id).first()
    if not cuenta:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    try:
        return (
            db.query(MovimientoCuenta)
            .filter(MovimientoCuenta.cuenta_id == cuenta_id)
            .order_by(MovimientoCuenta.id.desc())
            .limit(limit)
            .all()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando movimientos: {exc}") from exc
