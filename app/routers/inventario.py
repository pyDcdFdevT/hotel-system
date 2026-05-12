from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MovimientoInventario, Producto
from app.schemas import (
    MovimientoInventarioCreate,
    MovimientoInventarioOut,
    ProductoOut,
)
from app.services.inventario_service import aumentar_stock, descontar_inventario_por_receta


router = APIRouter(prefix="/inventario", tags=["inventario"])


@router.get("/movimientos", response_model=List[MovimientoInventarioOut])
def listar_movimientos(
    producto_id: Optional[int] = Query(default=None),
    tipo: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(MovimientoInventario)
        if producto_id:
            query = query.filter(MovimientoInventario.producto_id == producto_id)
        if tipo:
            query = query.filter(MovimientoInventario.tipo == tipo)
        return query.order_by(MovimientoInventario.id.desc()).limit(limit).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando movimientos: {exc}") from exc


@router.get("/bajo-stock", response_model=List[ProductoOut])
def productos_bajo_stock(db: Session = Depends(get_db)):
    try:
        return (
            db.query(Producto)
            .filter(Producto.activo.is_(True))
            .filter(Producto.stock_actual <= Producto.stock_minimo)
            .order_by(Producto.nombre.asc())
            .all()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando bajo stock: {exc}") from exc


@router.post("/movimientos", response_model=MovimientoInventarioOut, status_code=status.HTTP_201_CREATED)
def registrar_movimiento(data: MovimientoInventarioCreate, db: Session = Depends(get_db)):
    if data.tipo not in {"entrada", "salida", "ajuste"}:
        raise HTTPException(status_code=400, detail="Tipo debe ser 'entrada', 'salida' o 'ajuste'")
    try:
        if data.tipo == "entrada":
            aumentar_stock(
                db,
                producto_id=data.producto_id,
                cantidad=data.cantidad,
                motivo=data.motivo,
                referencia=data.referencia,
            )
        else:
            descontar_inventario_por_receta(
                db,
                producto_id=data.producto_id,
                cantidad=data.cantidad,
                motivo=data.motivo,
                referencia=data.referencia,
            )
        movimiento = (
            db.query(MovimientoInventario)
            .order_by(MovimientoInventario.id.desc())
            .first()
        )
        db.commit()
        db.refresh(movimiento)
        return movimiento
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error registrando movimiento: {exc}") from exc
