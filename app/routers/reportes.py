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
from app.schemas import (
    HistorialPorMetodo,
    HistorialResumen,
    HistorialTransacciones,
    HistorialVentasPorArea,
    MontoMoneda,
    ResumenDia,
    TransaccionResumen,
    VentasArea,
    VentasAreaConMetodos,
    VentasMetodo,
    VentasPorArea,
    VentasPorAreaConMetodos,
)
from app.services.tasa_service import obtener_tasa_dia


router = APIRouter(prefix="/reportes", tags=["reportes"])


# Dependencias por endpoint (el router está montado con _AUTH para que el
# mesero también pueda llegar al endpoint de transacciones recientes).
_REPORTES_GERENCIA = Depends(require_roles("admin", "recepcion"))
_REPORTES_OPERATIVO = Depends(require_roles("admin", "recepcion", "mesero"))
_REPORTES_ADMIN = Depends(require_roles("admin"))


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


# ---------------------------------------------------------------------------
# Ventas del día por área con desglose por método de pago
# ---------------------------------------------------------------------------
METODOS_NOMBRES: dict[str, str] = {
    "efectivo_usd": "💵 Efectivo USD",
    "efectivo_bs": "💴 Efectivo Bs",
    "transferencia_bs": "💳 Transferencia Bs",
    "pagomovil_bs": "📱 Pago Móvil Bs",
    "mixto": "💵+💴 Mixto",
    "otros": "Otros",
}

# Orden estable para serializar (el frontend espera este orden).
METODOS_ORDEN: tuple[str, ...] = (
    "efectivo_usd",
    "efectivo_bs",
    "transferencia_bs",
    "pagomovil_bs",
    "mixto",
)


def _nuevo_area_acumulador() -> dict:
    """Estructura interna para acumular USD/Bs por método dentro de un área."""
    return {
        "total_usd": Decimal("0"),
        "total_bs": Decimal("0"),
        "metodos": {clave: {"usd": Decimal("0"), "bs": Decimal("0")} for clave in METODOS_ORDEN},
    }


def _sumar_a_area(area_acc: dict, etiqueta: str, usd: Decimal, bs: Decimal) -> None:
    if etiqueta not in area_acc["metodos"]:
        area_acc["metodos"][etiqueta] = {"usd": Decimal("0"), "bs": Decimal("0")}
    area_acc["metodos"][etiqueta]["usd"] += usd
    area_acc["metodos"][etiqueta]["bs"] += bs
    area_acc["total_usd"] += usd
    area_acc["total_bs"] += bs


def _materializar_area(area_acc: dict) -> VentasAreaConMetodos:
    metodos_out: dict[str, VentasMetodo] = {}
    for clave, monto in area_acc["metodos"].items():
        usd = monto["usd"].quantize(Decimal("0.01"))
        bs = monto["bs"].quantize(Decimal("0.01"))
        # Sólo exponemos los métodos que realmente tienen movimiento, para
        # que el frontend pinte únicamente las líneas relevantes.
        if usd == 0 and bs == 0:
            continue
        metodos_out[clave] = VentasMetodo(
            label=METODOS_NOMBRES.get(clave, clave),
            usd=usd,
            bs=bs,
        )
    return VentasAreaConMetodos(
        total_usd=area_acc["total_usd"].quantize(Decimal("0.01")),
        total_bs=area_acc["total_bs"].quantize(Decimal("0.01")),
        metodos=metodos_out,
    )


@router.get(
    "/ventas-por-area-con-metodos",
    response_model=VentasPorAreaConMetodos,
    dependencies=[_REPORTES_OPERATIVO],
)
def ventas_por_area_con_metodos(
    fecha: Optional[date_type] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Ventas del día agrupadas por área y método de pago.

    * **Habitaciones** = reservas cerradas hoy (``total_final_*`` íntegro).
    * **Bar / Cocina / Piscina** = pedidos pagados hoy, prorrateando ``pagado_*``
      por el peso de cada detalle. Los detalles con producto de categoría
      "Piscina" se reasignan al bucket ``piscina`` independientemente del área
      del pedido o del producto.
    """
    fecha_objetivo = fecha or today()
    try:
        habitaciones = _nuevo_area_acumulador()
        bar = _nuevo_area_acumulador()
        cocina = _nuevo_area_acumulador()
        piscina = _nuevo_area_acumulador()

        # ---- Habitaciones (reservas cerradas hoy) ----
        reservas = (
            db.query(Reserva)
            .filter(Reserva.estado == "cerrada")
            .filter(Reserva.fecha_checkout_real == fecha_objetivo)
            .all()
        )
        for r in reservas:
            usd = Decimal(r.total_final_usd or 0)
            bs = Decimal(r.total_final_bs or 0)
            if usd == 0 and bs == 0:
                continue
            etiqueta = _clasificar_metodo(r.metodo_pago, usd, bs)
            _sumar_a_area(habitaciones, etiqueta, usd, bs)

        # ---- Pedidos pagados hoy → bar / cocina / piscina ----
        pedidos = (
            db.query(Pedido)
            .options(joinedload(Pedido.detalles).joinedload(DetallePedido.producto))
            .filter(Pedido.estado.in_(["pagado", "cargado"]))
            .filter(func.date(Pedido.updated_at) == fecha_objetivo)
            .all()
        )
        for p in pedidos:
            pagado_usd = Decimal(p.pagado_usd or 0)
            pagado_bs = Decimal(p.pagado_bs or 0)
            if pagado_usd == 0 and pagado_bs == 0:
                continue
            etiqueta = _clasificar_metodo(p.metodo_pago, pagado_usd, pagado_bs)
            base = sum(
                (Decimal(d.subtotal_usd or 0) for d in (p.detalles or [])),
                Decimal("0"),
            )
            if not (p.detalles):
                # Sin detalles: no podemos atribuir a área. Lo dejamos como cocina
                # por defecto para no perder visibilidad.
                _sumar_a_area(cocina, etiqueta, pagado_usd, pagado_bs)
                continue
            for det in p.detalles:
                sub_usd = Decimal(det.subtotal_usd or 0)
                if base > 0:
                    peso = sub_usd / base
                    aporte_usd = (pagado_usd * peso).quantize(Decimal("0.01"))
                    aporte_bs = (pagado_bs * peso).quantize(Decimal("0.01"))
                else:
                    aporte_usd = Decimal("0")
                    aporte_bs = Decimal("0")
                producto = getattr(det, "producto", None)
                categoria = (producto.categoria if producto else "") or ""
                area = (producto.area if producto else "general") or "general"
                if categoria.strip().lower() == "piscina":
                    _sumar_a_area(piscina, etiqueta, aporte_usd, aporte_bs)
                elif area.lower() == "bar":
                    _sumar_a_area(bar, etiqueta, aporte_usd, aporte_bs)
                else:
                    _sumar_a_area(cocina, etiqueta, aporte_usd, aporte_bs)

        return VentasPorAreaConMetodos(
            fecha=fecha_objetivo,
            habitaciones=_materializar_area(habitaciones),
            bar=_materializar_area(bar),
            cocina=_materializar_area(cocina),
            piscina=_materializar_area(piscina),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error calculando ventas por área con métodos: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Historial (admin) — agregados por período arbitrario
# ---------------------------------------------------------------------------
def _rango_validado(
    desde: Optional[date_type], hasta: Optional[date_type]
) -> tuple[date_type, date_type]:
    hoy = today()
    inicio = desde or hoy
    fin = hasta or hoy
    if fin < inicio:
        raise HTTPException(
            status_code=400,
            detail="El parámetro 'hasta' debe ser ≥ 'desde'.",
        )
    return inicio, fin


def _clasificar_metodo(
    metodo: Optional[str],
    pagado_usd: Decimal,
    pagado_bs: Decimal,
) -> str:
    """Asigna una etiqueta combinada según el método y la moneda efectivamente cobrada.

    Mantiene las claves usadas por el frontend (``efectivo_usd``, ``efectivo_bs``,
    ``transferencia_bs``, ``pagomovil_bs``, ``mixto``, ``otros``).
    """
    m = (metodo or "").lower().strip()
    if m == "transferencia":
        return "transferencia_bs"
    if m == "pagomovil":
        return "pagomovil_bs"
    if m == "mixto":
        return "mixto"
    if pagado_usd > 0 and pagado_bs > 0:
        return "mixto"
    if pagado_usd > 0:
        return "efectivo_usd"
    if pagado_bs > 0:
        return "efectivo_bs"
    return "otros"


def _pedidos_pagados_en_rango(
    db: Session, desde: date_type, hasta: date_type
) -> list[Pedido]:
    return (
        db.query(Pedido)
        .options(joinedload(Pedido.detalles).joinedload(DetallePedido.producto))
        .filter(Pedido.estado.in_(["pagado", "cargado"]))
        .filter(func.date(Pedido.updated_at) >= desde)
        .filter(func.date(Pedido.updated_at) <= hasta)
        .order_by(Pedido.updated_at.desc(), Pedido.id.desc())
        .all()
    )


def _reservas_cerradas_en_rango(
    db: Session, desde: date_type, hasta: date_type
) -> list[Reserva]:
    return (
        db.query(Reserva)
        .filter(Reserva.estado == "cerrada")
        .filter(Reserva.fecha_checkout_real >= desde)
        .filter(Reserva.fecha_checkout_real <= hasta)
        .order_by(Reserva.updated_at.desc(), Reserva.id.desc())
        .all()
    )


def _room_income_bs(reserva: Reserva) -> Decimal:
    """Ingreso de la habitación en bolívares = total_final_bs − consumos_bs.

    Sólo aporta cuando la reserva se cobró en Bs (o mixto). Para cobros 100% USD
    el ``total_final_bs`` queda en 0 y este monto es 0.
    """
    total_bs = Decimal(reserva.total_final_bs or 0)
    consumos_bs = Decimal(reserva.total_consumos_bs or 0)
    return max(Decimal("0"), (total_bs - consumos_bs).quantize(Decimal("0.01")))


@router.get(
    "/historial/resumen",
    response_model=HistorialResumen,
    dependencies=[_REPORTES_ADMIN],
)
def historial_resumen(
    desde: Optional[date_type] = Query(default=None),
    hasta: Optional[date_type] = Query(default=None),
    db: Session = Depends(get_db),
):
    inicio, fin = _rango_validado(desde, hasta)
    try:
        pedidos = _pedidos_pagados_en_rango(db, inicio, fin)
        ventas_usd = sum(
            (Decimal(p.pagado_usd or 0) for p in pedidos), Decimal("0")
        )
        ventas_bs = sum(
            (Decimal(p.pagado_bs or 0) for p in pedidos), Decimal("0")
        )

        reservas = _reservas_cerradas_en_rango(db, inicio, fin)
        for r in reservas:
            room_usd = Decimal(r.tarifa_usd or 0) + Decimal(r.recarga_extra_usd or 0)
            # Sólo contamos USD si efectivamente se cobró algo en USD.
            if Decimal(r.total_final_usd or 0) > 0:
                ventas_usd += room_usd
            ventas_bs += _room_income_bs(r)

        gastos = (
            db.query(
                func.coalesce(func.sum(Gasto.monto_usd), 0),
                func.coalesce(func.sum(Gasto.monto_bs), 0),
            )
            .filter(Gasto.fecha >= inicio)
            .filter(Gasto.fecha <= fin)
            .one()
        )
        gastos_usd = Decimal(gastos[0] or 0)
        gastos_bs = Decimal(gastos[1] or 0)

        return HistorialResumen(
            desde=inicio,
            hasta=fin,
            total_ventas_usd=ventas_usd.quantize(Decimal("0.01")),
            total_ventas_bs=ventas_bs.quantize(Decimal("0.01")),
            total_gastos_usd=gastos_usd.quantize(Decimal("0.01")),
            total_gastos_bs=gastos_bs.quantize(Decimal("0.01")),
            ganancia_neta_usd=(ventas_usd - gastos_usd).quantize(Decimal("0.01")),
            ganancia_neta_bs=(ventas_bs - gastos_bs).quantize(Decimal("0.01")),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Error generando resumen histórico: {exc}"
        ) from exc


@router.get(
    "/historial/ventas-por-area",
    response_model=HistorialVentasPorArea,
    dependencies=[_REPORTES_ADMIN],
)
def historial_ventas_por_area(
    desde: Optional[date_type] = Query(default=None),
    hasta: Optional[date_type] = Query(default=None),
    db: Session = Depends(get_db),
):
    inicio, fin = _rango_validado(desde, hasta)
    try:
        pedidos = _pedidos_pagados_en_rango(db, inicio, fin)
        bar = MontoMoneda()
        cocina = MontoMoneda()
        piscina = MontoMoneda()

        for p in pedidos:
            total_usd = Decimal(p.total_usd or 0)
            total_bs = Decimal(p.total_bs or 0)
            if total_usd <= 0 and total_bs <= 0:
                continue
            # Repartimos el total del pedido entre las áreas según el peso
            # USD de cada detalle.
            base = sum(
                (Decimal(d.subtotal_usd or 0) for d in (p.detalles or [])),
                Decimal("0"),
            )
            for det in p.detalles or []:
                sub_usd = Decimal(det.subtotal_usd or 0)
                sub_bs = Decimal(det.subtotal_bs or 0)
                if base > 0:
                    peso = sub_usd / base
                    # Para reflejar el cobro real, prorrateamos pagado_usd/bs.
                    aporte_usd = (Decimal(p.pagado_usd or 0) * peso).quantize(
                        Decimal("0.01")
                    )
                    aporte_bs = (Decimal(p.pagado_bs or 0) * peso).quantize(
                        Decimal("0.01")
                    )
                else:
                    aporte_usd = sub_usd
                    aporte_bs = sub_bs
                producto = getattr(det, "producto", None)
                categoria = (producto.categoria if producto else "") or ""
                area = (producto.area if producto else "general") or "general"
                if categoria.strip().lower() == "piscina":
                    piscina.usd += aporte_usd
                    piscina.bs += aporte_bs
                elif area.lower() == "bar":
                    bar.usd += aporte_usd
                    bar.bs += aporte_bs
                else:
                    # cocina / general → contabilizado como cocina.
                    cocina.usd += aporte_usd
                    cocina.bs += aporte_bs

        habitaciones = MontoMoneda()
        for r in _reservas_cerradas_en_rango(db, inicio, fin):
            if Decimal(r.total_final_usd or 0) > 0:
                habitaciones.usd += Decimal(r.tarifa_usd or 0) + Decimal(
                    r.recarga_extra_usd or 0
                )
            habitaciones.bs += _room_income_bs(r)

        for m in (habitaciones, bar, cocina, piscina):
            m.usd = m.usd.quantize(Decimal("0.01"))
            m.bs = m.bs.quantize(Decimal("0.01"))

        return HistorialVentasPorArea(
            desde=inicio,
            hasta=fin,
            habitaciones=habitaciones,
            bar=bar,
            cocina=cocina,
            piscina=piscina,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error generando ventas por área (histórico): {exc}",
        ) from exc


@router.get(
    "/historial/por-metodo-pago",
    response_model=HistorialPorMetodo,
    dependencies=[_REPORTES_ADMIN],
)
def historial_por_metodo_pago(
    desde: Optional[date_type] = Query(default=None),
    hasta: Optional[date_type] = Query(default=None),
    db: Session = Depends(get_db),
):
    inicio, fin = _rango_validado(desde, hasta)
    try:
        buckets: dict[str, MontoMoneda] = {
            "efectivo_usd": MontoMoneda(),
            "efectivo_bs": MontoMoneda(),
            "transferencia_bs": MontoMoneda(),
            "pagomovil_bs": MontoMoneda(),
            "mixto": MontoMoneda(),
            "otros": MontoMoneda(),
        }

        for p in _pedidos_pagados_en_rango(db, inicio, fin):
            etiqueta = _clasificar_metodo(
                p.metodo_pago,
                Decimal(p.pagado_usd or 0),
                Decimal(p.pagado_bs or 0),
            )
            buckets[etiqueta].usd += Decimal(p.pagado_usd or 0)
            buckets[etiqueta].bs += Decimal(p.pagado_bs or 0)

        for r in _reservas_cerradas_en_rango(db, inicio, fin):
            room_usd = (
                Decimal(r.tarifa_usd or 0) + Decimal(r.recarga_extra_usd or 0)
                if Decimal(r.total_final_usd or 0) > 0
                else Decimal("0")
            )
            room_bs = _room_income_bs(r)
            etiqueta = _clasificar_metodo(
                r.metodo_pago,
                Decimal(r.total_final_usd or 0),
                Decimal(r.total_final_bs or 0),
            )
            buckets[etiqueta].usd += room_usd
            buckets[etiqueta].bs += room_bs

        for m in buckets.values():
            m.usd = m.usd.quantize(Decimal("0.01"))
            m.bs = m.bs.quantize(Decimal("0.01"))

        return HistorialPorMetodo(
            desde=inicio,
            hasta=fin,
            **buckets,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error generando desglose por método de pago: {exc}",
        ) from exc


@router.get(
    "/historial/transacciones",
    response_model=HistorialTransacciones,
    dependencies=[_REPORTES_ADMIN],
)
def historial_transacciones(
    desde: Optional[date_type] = Query(default=None),
    hasta: Optional[date_type] = Query(default=None),
    limite: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    inicio, fin = _rango_validado(desde, hasta)
    try:
        pedidos = _pedidos_pagados_en_rango(db, inicio, fin)
        reservas = _reservas_cerradas_en_rango(db, inicio, fin)

        filas: list[TransaccionResumen] = []
        for p in pedidos:
            fecha = p.updated_at or p.fecha or datetime_type.utcnow()
            filas.append(
                TransaccionResumen(
                    id=int(p.id),
                    fecha=fecha,
                    concepto=_concepto_pedido(p),
                    monto_usd=Decimal(p.pagado_usd or 0),
                    monto_bs=Decimal(p.pagado_bs or 0),
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
        total = len(filas)
        return HistorialTransacciones(
            desde=inicio,
            hasta=fin,
            total=total,
            limite=limite,
            offset=offset,
            items=filas[offset : offset + limite],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error generando historial de transacciones: {exc}",
        ) from exc
