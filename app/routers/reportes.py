from __future__ import annotations

from datetime import date as date_type
from datetime import datetime as datetime_type
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    DetallePedido,
    Gasto,
    Habitacion,
    Pedido,
    Producto,
    Reserva,
    Usuario,
    today,
)
from app.routers.auth import require_roles
from app.schemas import ResumenDia, TransaccionResumen, VentasArea, VentasPorArea
from app.services.tasa_service import obtener_tasa_dia


router = APIRouter(prefix="/reportes", tags=["reportes"])


# Dependencias por endpoint (el router está montado con _AUTH para que el
# mesero también pueda llegar al endpoint de transacciones recientes).
_REPORTES_GERENCIA = Depends(require_roles("admin", "recepcion"))
_REPORTES_OPERATIVO = Depends(require_roles("admin", "recepcion", "mesero"))


@router.get(
    "/resumen-dia",
    response_model=ResumenDia,
    dependencies=[_REPORTES_GERENCIA],
)
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


@router.get(
    "/ventas-por-area",
    response_model=VentasPorArea,
    dependencies=[_REPORTES_GERENCIA],
)
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


# ---------------------------------------------------------------------------
# Historial de transacciones (dashboard)
# ---------------------------------------------------------------------------
def _tipo_transaccion_pedido(pedido: Pedido) -> str:
    """Determina el ``tipo`` reportable de un pedido a partir de su contenido.

    Reglas (de mayor a menor prioridad):
    * Si algún detalle pertenece a la categoría "Piscina" → ``piscina``.
    * Si el pedido se asoció a una habitación → ``habitacion``.
    * Caso contrario, se usa el ``tipo`` propio del pedido (bar/restaurante/...).
    """
    for det in pedido.detalles or []:
        producto = getattr(det, "producto", None)
        categoria = (producto.categoria if producto else "") or ""
        if categoria.strip().lower() == "piscina":
            return "piscina"
    if pedido.habitacion_numero:
        return "habitacion"
    return (pedido.tipo or "venta").lower()


def _concepto_pedido(pedido: Pedido) -> str:
    if pedido.habitacion_numero:
        return f"Consumo Hab. #{pedido.habitacion_numero}"
    if pedido.mesa:
        return f"Pedido {pedido.mesa}"
    return f"Pedido #{pedido.id}"


@router.get(
    "/ultimas-transacciones",
    response_model=List[TransaccionResumen],
    dependencies=[_REPORTES_OPERATIVO],
)
def ultimas_transacciones(
    limite: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Combina check-outs (reservas cerradas) y pedidos pagados/cargados.

    El historial se ordena por fecha descendente para alimentar el dashboard.
    No identifica todavía al cajero por usuario (no se almacena en ``Pedido``)
    y se reporta ``Sistema`` por defecto.
    """
    try:
        # 1) Pedidos pagados/cargados: leemos el doble del límite por si hay
        #    reservas que se intercalen al hacer el merge.
        pedidos: list[Pedido] = (
            db.query(Pedido)
            .options(joinedload(Pedido.detalles).joinedload(DetallePedido.producto))
            .filter(Pedido.estado.in_(["pagado", "cargado"]))
            .order_by(Pedido.updated_at.desc(), Pedido.id.desc())
            .limit(limite * 2)
            .all()
        )
        # 2) Reservas cerradas (check-outs).
        reservas: list[Reserva] = (
            db.query(Reserva)
            .filter(Reserva.estado == "cerrada")
            .order_by(Reserva.updated_at.desc(), Reserva.id.desc())
            .limit(limite * 2)
            .all()
        )

        filas: list[TransaccionResumen] = []
        for p in pedidos:
            fecha = p.updated_at or p.fecha or datetime_type.utcnow()
            filas.append(
                TransaccionResumen(
                    id=int(p.id),
                    fecha=fecha,
                    concepto=_concepto_pedido(p),
                    monto_usd=Decimal(p.pagado_usd or p.total_usd or 0),
                    monto_bs=Decimal(p.pagado_bs or p.total_bs or 0),
                    tipo=_tipo_transaccion_pedido(p),
                    usuario_nombre="Sistema",
                )
            )
        for r in reservas:
            fecha = r.updated_at or datetime_type.utcnow()
            filas.append(
                TransaccionResumen(
                    id=int(r.id),
                    fecha=fecha,
                    concepto=f"Check-out Hab. (reserva #{r.id}) · {r.huesped}",
                    monto_usd=Decimal(r.total_final_usd or 0),
                    monto_bs=Decimal(r.total_final_bs or 0),
                    tipo="checkout",
                    usuario_nombre="Sistema",
                )
            )

        filas.sort(key=lambda f: f.fecha, reverse=True)
        return filas[:limite]
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error generando transacciones recientes: {exc}",
        ) from exc
