from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    DetallePedido,
    FavoritoUsuario,
    MovimientoInventario,
    Pedido,
    Producto,
    Receta,
    Usuario,
    caracas_now,
)
from app.routers.auth import get_current_user, require_roles
from app.schemas import (
    FavoritoIn,
    FavoritoReorden,
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


@router.get("/favoritos", response_model=List[ProductoOut])
def productos_favoritos(
    dias: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Top productos más vendidos en los últimos ``dias`` días."""
    try:
        desde = caracas_now() - timedelta(days=dias)
        ranking = (
            db.query(
                DetallePedido.producto_id,
                func.coalesce(func.sum(DetallePedido.cantidad), 0).label("vendidos"),
            )
            .join(Pedido, DetallePedido.pedido_id == Pedido.id)
            .filter(Pedido.estado.in_(["pagado", "cargado"]))
            .filter(Pedido.fecha >= desde)
            .group_by(DetallePedido.producto_id)
            .order_by(func.sum(DetallePedido.cantidad).desc())
            .limit(limit)
            .all()
        )

        ids_ordenados = [row.producto_id for row in ranking]
        if not ids_ordenados:
            # Fallback: si aún no hay historial, devolvemos los primeros productos
            # marcados como para venta y activos para que la sección no quede vacía.
            return (
                db.query(Producto)
                .filter(Producto.activo.is_(True))
                .filter(Producto.es_para_venta.is_(True))
                .order_by(Producto.nombre.asc())
                .limit(limit)
                .all()
            )

        productos = (
            db.query(Producto)
            .filter(Producto.id.in_(ids_ordenados))
            .filter(Producto.activo.is_(True))
            .filter(Producto.es_para_venta.is_(True))
            .all()
        )
        orden = {pid: idx for idx, pid in enumerate(ids_ordenados)}
        productos.sort(key=lambda p: orden.get(p.id, 999))
        return productos
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Error listando favoritos: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Favoritos editables por usuario (POS)
# ---------------------------------------------------------------------------
@router.get("/favoritos/mis-favoritos", response_model=List[ProductoOut])
def mis_favoritos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Productos favoritos del usuario autenticado, en su orden personalizado."""
    rows = (
        db.query(FavoritoUsuario, Producto)
        .join(Producto, FavoritoUsuario.producto_id == Producto.id)
        .filter(FavoritoUsuario.usuario_id == usuario.id)
        .filter(Producto.activo.is_(True))
        .filter(Producto.es_para_venta.is_(True))
        .order_by(FavoritoUsuario.orden.asc(), FavoritoUsuario.created_at.asc())
        .all()
    )
    return [producto for _fav, producto in rows]


@router.post(
    "/favoritos",
    response_model=ProductoOut,
    status_code=status.HTTP_201_CREATED,
)
def agregar_favorito(
    data: FavoritoIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Agrega un producto a los favoritos del usuario actual.

    Si ya estaba en favoritos, devuelve el producto sin error (idempotente).
    """
    producto = (
        db.query(Producto).filter(Producto.id == data.producto_id).first()
    )
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    if not producto.activo or not producto.es_para_venta:
        raise HTTPException(
            status_code=400,
            detail="Sólo se pueden marcar como favoritos productos activos y para venta",
        )
    existente = (
        db.query(FavoritoUsuario)
        .filter(FavoritoUsuario.usuario_id == usuario.id)
        .filter(FavoritoUsuario.producto_id == producto.id)
        .first()
    )
    if existente:
        return producto

    # Nuevo favorito al final del orden actual.
    max_orden = (
        db.query(func.coalesce(func.max(FavoritoUsuario.orden), -1))
        .filter(FavoritoUsuario.usuario_id == usuario.id)
        .scalar()
    )
    fav = FavoritoUsuario(
        usuario_id=usuario.id,
        producto_id=producto.id,
        orden=int(max_orden) + 1,
    )
    try:
        db.add(fav)
        db.commit()
    except IntegrityError:
        db.rollback()  # Carrera: ya existía. Idempotente.
    return producto


@router.delete(
    "/favoritos/{producto_id}",
    status_code=status.HTTP_200_OK,
)
def quitar_favorito(
    producto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Quita un producto de los favoritos del usuario actual."""
    fav = (
        db.query(FavoritoUsuario)
        .filter(FavoritoUsuario.usuario_id == usuario.id)
        .filter(FavoritoUsuario.producto_id == producto_id)
        .first()
    )
    if not fav:
        # Idempotente: si no existe, devolvemos OK con flag.
        return {"removed": False, "producto_id": producto_id}
    db.delete(fav)
    db.commit()
    return {"removed": True, "producto_id": producto_id}


@router.put("/favoritos/reordenar")
def reordenar_favoritos(
    data: FavoritoReorden,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Actualiza el campo ``orden`` de los favoritos del usuario actual.

    El payload contiene ``producto_ids`` en el orden deseado. Cualquier
    favorito existente no incluido en la lista mantiene su orden actual
    desplazado al final.
    """
    propios = (
        db.query(FavoritoUsuario)
        .filter(FavoritoUsuario.usuario_id == usuario.id)
        .all()
    )
    if not propios:
        return {"updated": 0}

    pid_a_fav = {f.producto_id: f for f in propios}
    nuevo_orden = 0
    actualizados = 0
    for pid in data.producto_ids:
        fav = pid_a_fav.get(pid)
        if fav is None:
            continue
        if fav.orden != nuevo_orden:
            fav.orden = nuevo_orden
            actualizados += 1
        nuevo_orden += 1
    # Lo no listado conserva su orden relativo, desplazado al final.
    restantes = [
        f for f in propios if f.producto_id not in set(data.producto_ids)
    ]
    restantes.sort(key=lambda f: (f.orden, f.created_at))
    for fav in restantes:
        if fav.orden != nuevo_orden:
            fav.orden = nuevo_orden
            actualizados += 1
        nuevo_orden += 1
    db.commit()
    return {"updated": actualizados}


@router.get("/{producto_id}", response_model=ProductoOut)
def obtener(producto_id: int, db: Session = Depends(get_db)):
    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return producto


@router.post(
    "/",
    response_model=ProductoOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
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


@router.put(
    "/{producto_id}",
    response_model=ProductoOut,
    dependencies=[Depends(require_roles("admin"))],
)
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


@router.delete(
    "/{producto_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("admin"))],
)
def eliminar(producto_id: int, db: Session = Depends(get_db)):
    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    try:
        tiene_pedidos = (
            db.query(DetallePedido)
            .filter(DetallePedido.producto_id == producto_id)
            .first()
            is not None
        )
        tiene_movimientos = (
            db.query(MovimientoInventario)
            .filter(MovimientoInventario.producto_id == producto_id)
            .first()
            is not None
        )
        usado_en_receta = (
            db.query(Receta)
            .filter(Receta.ingrediente_id == producto_id)
            .first()
            is not None
        )

        if tiene_pedidos or tiene_movimientos or usado_en_receta:
            producto.activo = False
            db.commit()
            return {
                "id": producto.id,
                "borrado": False,
                "inactivado": True,
                "mensaje": "El producto tiene historial; se marcó como inactivo.",
            }

        db.query(Receta).filter(Receta.producto_id == producto_id).delete()
        db.delete(producto)
        db.commit()
        return {
            "id": producto_id,
            "borrado": True,
            "inactivado": False,
            "mensaje": "Producto eliminado.",
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error eliminando producto: {exc}") from exc


# ---------------------------------------------------------------------------
# Recetas
# ---------------------------------------------------------------------------
@router.get("/{producto_id}/receta", response_model=List[RecetaOut])
def obtener_receta(producto_id: int, db: Session = Depends(get_db)):
    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return db.query(Receta).filter(Receta.producto_id == producto_id).all()


@router.post(
    "/recetas",
    response_model=List[RecetaOut],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
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
