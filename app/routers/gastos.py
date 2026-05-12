from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CategoriaGasto, CuentaBanco, Gasto, MovimientoCuenta, today
from app.schemas import (
    CategoriaGastoCreate,
    CategoriaGastoOut,
    GastoCreate,
    GastoOut,
)


router = APIRouter(prefix="/gastos", tags=["gastos"])


@router.get("/categorias", response_model=List[CategoriaGastoOut])
def listar_categorias(db: Session = Depends(get_db)):
    try:
        return db.query(CategoriaGasto).order_by(CategoriaGasto.nombre.asc()).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando categorías: {exc}") from exc


@router.post("/categorias", response_model=CategoriaGastoOut, status_code=status.HTTP_201_CREATED)
def crear_categoria(data: CategoriaGastoCreate, db: Session = Depends(get_db)):
    try:
        categoria = CategoriaGasto(**data.model_dump())
        db.add(categoria)
        db.commit()
        db.refresh(categoria)
        return categoria
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe una categoría con ese nombre") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creando categoría: {exc}") from exc


@router.get("/", response_model=List[GastoOut])
def listar(
    desde: Optional[date_type] = Query(default=None),
    hasta: Optional[date_type] = Query(default=None),
    categoria_id: Optional[int] = Query(default=None),
    cuenta_banco_id: Optional[int] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(Gasto)
        if desde:
            query = query.filter(Gasto.fecha >= desde)
        if hasta:
            query = query.filter(Gasto.fecha <= hasta)
        if categoria_id:
            query = query.filter(Gasto.categoria_id == categoria_id)
        if cuenta_banco_id:
            query = query.filter(Gasto.cuenta_banco_id == cuenta_banco_id)
        return query.order_by(Gasto.id.desc()).limit(limit).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando gastos: {exc}") from exc


@router.post("/", response_model=GastoOut, status_code=status.HTTP_201_CREATED)
def crear_gasto(data: GastoCreate, db: Session = Depends(get_db)):
    categoria = db.query(CategoriaGasto).filter(CategoriaGasto.id == data.categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    monto_bs = Decimal(data.monto_bs or 0)
    monto_usd = Decimal(data.monto_usd or 0)
    if monto_bs == 0 and monto_usd == 0:
        raise HTTPException(status_code=400, detail="El gasto debe tener monto en Bs o USD")

    try:
        gasto = Gasto(
            fecha=data.fecha or today(),
            categoria_id=data.categoria_id,
            descripcion=data.descripcion,
            monto_bs=monto_bs,
            monto_usd=monto_usd,
            cuenta_banco_id=data.cuenta_banco_id,
            beneficiario=data.beneficiario,
            referencia=data.referencia,
            notas=data.notas,
        )
        db.add(gasto)
        db.flush()

        if data.cuenta_banco_id:
            cuenta = db.query(CuentaBanco).filter(CuentaBanco.id == data.cuenta_banco_id).first()
            if not cuenta:
                raise HTTPException(status_code=404, detail="Cuenta de banco no encontrada")
            monto = monto_bs if cuenta.moneda == "BS" else monto_usd
            saldo_anterior = Decimal(cuenta.saldo or 0)
            nuevo_saldo = saldo_anterior - monto
            cuenta.saldo = nuevo_saldo
            db.add(
                MovimientoCuenta(
                    cuenta_id=cuenta.id,
                    tipo="salida",
                    monto=monto,
                    saldo_resultante=nuevo_saldo,
                    concepto=f"Gasto: {data.descripcion}",
                    referencia=f"gasto:{gasto.id}",
                )
            )

        db.commit()
        db.refresh(gasto)
        return gasto
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creando gasto: {exc}") from exc


@router.delete("/{gasto_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(gasto_id: int, db: Session = Depends(get_db)):
    gasto = db.query(Gasto).filter(Gasto.id == gasto_id).first()
    if not gasto:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    try:
        db.delete(gasto)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error eliminando gasto: {exc}") from exc
    return None
