from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    DetallePedido,
    Gasto,
    Habitacion,
    Pedido,
    Producto,
    Reserva,
    today,
)
from app.schemas import ResumenDia, VentasArea, VentasPorArea
from app.services.tasa_service import obtener_tasa_dia


router = APIRouter(prefix="/reportes", tags=["reportes"])


@router.get("/resumen-dia", response_model=ResumenDia)
def resumen_dia(
    fecha: Optional[date_type] = Query(default=None),
    db: Session = Depends(get_db),
):
    fecha_objetivo = fecha or today()
    try:
        ventas_bs, ventas_usd = (
            db.query(
                func.coalesce(func.sum(Pedido.total_bs), 0),
                func.coalesce(func.sum(Pedido.total_usd), 0),
            )
            .filter(func.date(Pedido.fecha) == fecha_objetivo)
            .filter(Pedido.estado.in_(["pagado", "cargado"]))
            .one()
        )
        pedidos_cantidad = (
            db.query(func.count(Pedido.id))
            .filter(func.date(Pedido.fecha) == fecha_objetivo)
            .scalar()
            or 0
        )
        gastos_bs, gastos_usd = (
            db.query(
                func.coalesce(func.sum(Gasto.monto_bs), 0),
                func.coalesce(func.sum(Gasto.monto_usd), 0),
            )
            .filter(Gasto.fecha == fecha_objetivo)
            .one()
        )

        total_habitaciones = db.query(func.count(Habitacion.id)).scalar() or 0
        ocupadas = (
            db.query(func.count(Habitacion.id))
            .filter(Habitacion.estado == "ocupada")
            .scalar()
            or 0
        )
        ocupacion_pct = round((ocupadas / total_habitaciones) * 100, 2) if total_habitaciones else 0.0

        bajo_stock = (
            db.query(func.count(Producto.id))
            .filter(Producto.activo.is_(True))
            .filter(Producto.stock_actual <= Producto.stock_minimo)
            .scalar()
            or 0
        )

        return ResumenDia(
            fecha=fecha_objetivo,
            ventas_bs=Decimal(ventas_bs or 0),
            ventas_usd=Decimal(ventas_usd or 0),
            gastos_bs=Decimal(gastos_bs or 0),
            gastos_usd=Decimal(gastos_usd or 0),
            pedidos_cantidad=int(pedidos_cantidad),
            habitaciones_totales=int(total_habitaciones),
            habitaciones_ocupadas=int(ocupadas),
            ocupacion_porcentaje=float(ocupacion_pct),
            productos_bajo_stock=int(bajo_stock),
            tasa_dia=obtener_tasa_dia(db, fecha_objetivo),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generando resumen: {exc}") from exc


@router.get("/ventas-por-area", response_model=VentasPorArea)
def ventas_por_area(
    fecha: Optional[date_type] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Devuelve ventas del día agrupadas en tres áreas:

    * **habitaciones**: ingresos por reservas con ``fecha_checkin`` el día
      consultado (tarifa × noches).
    * **bar** y **cocina**: agregados de ``detalles_pedido`` cruzados con
      ``productos.area`` para los pedidos en estado ``pagado`` o ``cargado``
      cuya ``fecha`` corresponde al día consultado.
    """
    fecha_objetivo = fecha or today()
    try:
        # Habitaciones: reservas que checkin = fecha objetivo.
        hab_row = (
            db.query(
                func.coalesce(func.sum(Reserva.tarifa_bs * Reserva.noches), 0),
                func.coalesce(func.sum(Reserva.tarifa_usd * Reserva.noches), 0),
            )
            .filter(Reserva.fecha_checkin == fecha_objetivo)
            .one()
        )
        hab_bs = Decimal(hab_row[0] or 0)
        hab_usd = Decimal(hab_row[1] or 0)

        # Bar y cocina: agregamos detalles de pedidos confirmados.
        productos_por_area = (
            db.query(
                Producto.area,
                func.coalesce(func.sum(DetallePedido.subtotal_bs), 0),
                func.coalesce(func.sum(DetallePedido.subtotal_usd), 0),
            )
            .join(DetallePedido, DetallePedido.producto_id == Producto.id)
            .join(Pedido, DetallePedido.pedido_id == Pedido.id)
            .filter(func.date(Pedido.fecha) == fecha_objetivo)
            .filter(Pedido.estado.in_(["pagado", "cargado"]))
            .group_by(Producto.area)
            .all()
        )
        bar_bs = Decimal("0")
        bar_usd = Decimal("0")
        cocina_bs = Decimal("0")
        cocina_usd = Decimal("0")
        for area_nombre, sub_bs, sub_usd in productos_por_area:
            area_lower = (area_nombre or "general").lower()
            if area_lower == "bar":
                bar_bs += Decimal(sub_bs or 0)
                bar_usd += Decimal(sub_usd or 0)
            elif area_lower == "cocina":
                cocina_bs += Decimal(sub_bs or 0)
                cocina_usd += Decimal(sub_usd or 0)
            else:
                # "general" u otras áreas se contabilizan como cocina por defecto
                # para no perder visibilidad de la venta.
                cocina_bs += Decimal(sub_bs or 0)
                cocina_usd += Decimal(sub_usd or 0)

        total_bs = hab_bs + bar_bs + cocina_bs
        total_usd = hab_usd + bar_usd + cocina_usd

        return VentasPorArea(
            fecha=fecha_objetivo,
            areas=[
                VentasArea(area="habitaciones", ventas_bs=hab_bs, ventas_usd=hab_usd),
                VentasArea(area="bar", ventas_bs=bar_bs, ventas_usd=bar_usd),
                VentasArea(area="cocina", ventas_bs=cocina_bs, ventas_usd=cocina_usd),
            ],
            total_bs=total_bs,
            total_usd=total_usd,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Error calculando ventas por área: {exc}"
        ) from exc
