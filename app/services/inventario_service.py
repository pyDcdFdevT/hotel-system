from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models import MovimientoInventario, Producto, Receta


def _registrar_movimiento(
    db: Session,
    producto: Producto,
    cantidad: Decimal,
    tipo: str,
    motivo: Optional[str],
    referencia: Optional[str],
) -> MovimientoInventario:
    stock_anterior = Decimal(producto.stock_actual or 0)
    if tipo == "entrada":
        stock_nuevo = stock_anterior + cantidad
    else:
        stock_nuevo = stock_anterior - cantidad
    if stock_nuevo < 0:
        raise ValueError(
            f"Stock insuficiente para '{producto.nombre}'. Disponible: {stock_anterior}, requerido: {cantidad}"
        )
    producto.stock_actual = stock_nuevo
    movimiento = MovimientoInventario(
        producto_id=producto.id,
        tipo=tipo,
        cantidad=cantidad,
        stock_anterior=stock_anterior,
        stock_nuevo=stock_nuevo,
        motivo=motivo,
        referencia=referencia,
    )
    db.add(movimiento)
    db.flush()
    return movimiento


def descontar_inventario_por_receta(
    db: Session,
    producto_id: int,
    cantidad: Decimal,
    motivo: Optional[str] = None,
    referencia: Optional[str] = None,
) -> None:
    cantidad = Decimal(cantidad)
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a cero")

    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise ValueError(f"Producto {producto_id} no existe")

    recetas = db.query(Receta).filter(Receta.producto_id == producto_id).all()
    if recetas:
        for receta in recetas:
            ingrediente = db.query(Producto).filter(Producto.id == receta.ingrediente_id).first()
            if not ingrediente:
                raise ValueError(f"Ingrediente {receta.ingrediente_id} no existe")
            total = Decimal(receta.cantidad) * cantidad
            _registrar_movimiento(
                db,
                ingrediente,
                total,
                tipo="salida",
                motivo=motivo or f"Receta de {producto.nombre}",
                referencia=referencia,
            )
        return

    _registrar_movimiento(
        db,
        producto,
        cantidad,
        tipo="salida",
        motivo=motivo or "Venta directa",
        referencia=referencia,
    )


def aumentar_stock(
    db: Session,
    producto_id: int,
    cantidad: Decimal,
    motivo: Optional[str] = None,
    referencia: Optional[str] = None,
) -> None:
    cantidad = Decimal(cantidad)
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a cero")
    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise ValueError(f"Producto {producto_id} no existe")
    _registrar_movimiento(db, producto, cantidad, tipo="entrada", motivo=motivo, referencia=referencia)


def restaurar_inventario_por_receta(
    db: Session,
    producto_id: int,
    cantidad: Decimal,
    motivo: Optional[str] = None,
    referencia: Optional[str] = None,
) -> None:
    """Inverso de ``descontar_inventario_por_receta``.

    Si el producto tiene receta, devuelve los ingredientes consumidos; si no,
    devuelve la unidad del propio producto. Útil al cancelar un pedido.
    """
    cantidad = Decimal(cantidad)
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a cero")

    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise ValueError(f"Producto {producto_id} no existe")

    recetas = db.query(Receta).filter(Receta.producto_id == producto_id).all()
    if recetas:
        for receta in recetas:
            ingrediente = db.query(Producto).filter(Producto.id == receta.ingrediente_id).first()
            if not ingrediente:
                continue
            total = Decimal(receta.cantidad) * cantidad
            _registrar_movimiento(
                db,
                ingrediente,
                total,
                tipo="entrada",
                motivo=motivo or f"Devolución por cancelación de {producto.nombre}",
                referencia=referencia,
            )
        return

    _registrar_movimiento(
        db,
        producto,
        cantidad,
        tipo="entrada",
        motivo=motivo or "Devolución por cancelación",
        referencia=referencia,
    )
