from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Gasto,
    Habitacion,
    Pedido,
    Producto,
    today,
)
from app.schemas import ResumenDia
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
