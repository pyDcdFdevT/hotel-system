from __future__ import annotations

from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CuentaBanco, Empleado, MovimientoCuenta, PagoNomina, today
from app.schemas import (
    EmpleadoCreate,
    EmpleadoOut,
    PagoNominaCreate,
    PagoNominaOut,
)


router = APIRouter(prefix="/personal", tags=["personal"])


@router.get("/", response_model=List[EmpleadoOut])
def listar(db: Session = Depends(get_db)):
    try:
        return db.query(Empleado).order_by(Empleado.nombre.asc()).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando empleados: {exc}") from exc


@router.post("/", response_model=EmpleadoOut, status_code=status.HTTP_201_CREATED)
def crear(data: EmpleadoCreate, db: Session = Depends(get_db)):
    try:
        empleado = Empleado(**data.model_dump())
        db.add(empleado)
        db.commit()
        db.refresh(empleado)
        return empleado
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creando empleado: {exc}") from exc


@router.get("/pagos", response_model=List[PagoNominaOut])
def listar_pagos(db: Session = Depends(get_db)):
    try:
        return db.query(PagoNomina).order_by(PagoNomina.id.desc()).limit(200).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando pagos: {exc}") from exc


@router.post("/pagos", response_model=PagoNominaOut, status_code=status.HTTP_201_CREATED)
def crear_pago(data: PagoNominaCreate, db: Session = Depends(get_db)):
    empleado = db.query(Empleado).filter(Empleado.id == data.empleado_id).first()
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    try:
        pago = PagoNomina(
            empleado_id=data.empleado_id,
            periodo=data.periodo,
            fecha_pago=data.fecha_pago or today(),
            monto_bs=data.monto_bs,
            monto_usd=data.monto_usd,
            cuenta_banco_id=data.cuenta_banco_id,
            notas=data.notas,
        )
        db.add(pago)
        db.flush()

        if data.cuenta_banco_id:
            cuenta = db.query(CuentaBanco).filter(CuentaBanco.id == data.cuenta_banco_id).first()
            if not cuenta:
                raise HTTPException(status_code=404, detail="Cuenta de banco no encontrada")
            monto = Decimal(data.monto_bs or 0) if cuenta.moneda == "BS" else Decimal(data.monto_usd or 0)
            cuenta.saldo = Decimal(cuenta.saldo or 0) - monto
            db.add(
                MovimientoCuenta(
                    cuenta_id=cuenta.id,
                    tipo="salida",
                    monto=monto,
                    saldo_resultante=cuenta.saldo,
                    concepto=f"Nómina {empleado.nombre} ({data.periodo})",
                    referencia=f"nomina:{pago.id}",
                )
            )

        db.commit()
        db.refresh(pago)
        return pago
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error registrando pago: {exc}") from exc
