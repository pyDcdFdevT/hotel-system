from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Producto, Receta
from app.schemas import (
    ProductoCreate,
    ProductoOut,
    ProductoUpdate,
    RecetaCreate,
    RecetaOut,
)


router = APIRouter(prefix="/productos", tags=["productos"])


@router.get("/", response_model=List[ProductoOut])
def listar(
    categoria: Optional[str] = Query(default=None),
    activo: Optional[bool] = Query(default=None),
    para_venta: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(Producto)
        if categoria:
            query = query.filter(Producto.categoria == categoria)
        if activo is not None:
            query = query.filter(Producto.activo == activo)
        if para_venta is not None:
            query = query.filter(Producto.es_para_venta == para_venta)
        return query.order_by(Producto.nombre.asc()).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando productos: {exc}") from exc


@router.get("/{producto_id}", response_model=ProductoOut)
def obtener(producto_id: int, db: Session = Depends(get_db)):
    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return producto


@router.post("/", response_model=ProductoOut, status_code=status.HTTP_201_CREATED)
def crear(data: ProductoCreate, db: Session = Depends(get_db)):
    try:
        producto = Producto(**data.model_dump())
        db.add(producto)
        db.commit()
        db.refresh(producto)
        return producto
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe un producto con ese nombre") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creando producto: {exc}") from exc


@router.put("/{producto_id}", response_model=ProductoOut)
def actualizar(producto_id: int, data: ProductoUpdate, db: Session = Depends(get_db)):
    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    try:
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(producto, key, value)
        db.commit()
        db.refresh(producto)
        return producto
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Conflicto al actualizar producto") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error actualizando producto: {exc}") from exc


@router.delete("/{producto_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(producto_id: int, db: Session = Depends(get_db)):
    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    try:
        producto.activo = False
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error eliminando producto: {exc}") from exc
    return None


# ---------------------------------------------------------------------------
# Recetas
# ---------------------------------------------------------------------------
@router.get("/{producto_id}/receta", response_model=List[RecetaOut])
def obtener_receta(producto_id: int, db: Session = Depends(get_db)):
    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return db.query(Receta).filter(Receta.producto_id == producto_id).all()


@router.post("/recetas", response_model=List[RecetaOut], status_code=status.HTTP_201_CREATED)
def definir_receta(data: RecetaCreate, db: Session = Depends(get_db)):
    producto = db.query(Producto).filter(Producto.id == data.producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    try:
        db.query(Receta).filter(Receta.producto_id == data.producto_id).delete()
        creadas = []
        for item in data.ingredientes:
            if item.ingrediente_id == data.producto_id:
                raise HTTPException(status_code=400, detail="Un producto no puede ser su propio ingrediente")
            ingrediente = db.query(Producto).filter(Producto.id == item.ingrediente_id).first()
            if not ingrediente:
                raise HTTPException(status_code=404, detail=f"Ingrediente {item.ingrediente_id} no existe")
            receta = Receta(
                producto_id=data.producto_id,
                ingrediente_id=item.ingrediente_id,
                cantidad=item.cantidad,
            )
            db.add(receta)
            creadas.append(receta)
        db.commit()
        for r in creadas:
            db.refresh(r)
        return creadas
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error guardando receta: {exc}") from exc
