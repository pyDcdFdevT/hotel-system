from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    ConsumoHabitacion,
    CuentaBanco,
    DetallePedido,
    Habitacion,
    MovimientoCuenta,
    Pedido,
    Producto,
    Reserva,
    utc_now,
)
from app.schemas import (
    PedidoCargoHabitacion,
    PedidoCreate,
    PedidoOut,
    PedidoPago,
)
from app.services.inventario_service import descontar_inventario_por_receta
from app.services.tasa_service import obtener_tasa_bcv, obtener_tasa_dia


router = APIRouter(prefix="/pedidos", tags=["pedidos"])


TIPOS_VALIDOS = {"restaurante", "bar", "habitacion", "general"}
METODOS_VALIDOS = {
    "bs",
    "usd",
    "mixto",
    "habitacion",
    "transferencia",
    "pagomovil",
}
TIPOS_TASA_VALIDOS = {"bcv", "paralelo"}


def _cargar_pedido(db: Session, pedido_id: int) -> Pedido:
    pedido = (
        db.query(Pedido)
        .options(joinedload(Pedido.detalles))
        .filter(Pedido.id == pedido_id)
        .first()
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return pedido


@router.get("/", response_model=List[PedidoOut])
def listar(
    estado: Optional[str] = Query(default=None),
    tipo: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(Pedido).options(joinedload(Pedido.detalles))
        if estado:
            query = query.filter(Pedido.estado == estado)
        if tipo:
            query = query.filter(Pedido.tipo == tipo)
        return query.order_by(Pedido.id.desc()).limit(200).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando pedidos: {exc}") from exc


@router.get("/activos", response_model=List[PedidoOut])
def listar_activos(db: Session = Depends(get_db)):
    """Pedidos abiertos ordenados por mesa (los sin mesa al final)."""
    try:
        return (
            db.query(Pedido)
            .options(joinedload(Pedido.detalles))
            .filter(Pedido.estado == "abierto")
            .order_by(Pedido.mesa.is_(None).asc(), Pedido.mesa.asc(), Pedido.fecha.desc())
            .all()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando pedidos activos: {exc}") from exc


@router.get("/por-habitacion/{numero}", response_model=List[PedidoOut])
def listar_por_habitacion(
    numero: str,
    incluir_cerrados: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Pedidos asociados a un número de habitación (abiertos por defecto)."""
    try:
        query = (
            db.query(Pedido)
            .options(joinedload(Pedido.detalles))
            .filter(Pedido.habitacion_numero == numero)
        )
        if not incluir_cerrados:
            query = query.filter(Pedido.estado == "abierto")
        return query.order_by(Pedido.fecha.desc()).all()
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Error listando pedidos por habitación: {exc}"
        ) from exc


@router.get("/{pedido_id}", response_model=PedidoOut)
def obtener(pedido_id: int, db: Session = Depends(get_db)):
    return _cargar_pedido(db, pedido_id)


@router.post("/", response_model=PedidoOut, status_code=status.HTTP_201_CREATED)
def crear_pedido(data: PedidoCreate, db: Session = Depends(get_db)):
    if data.tipo not in TIPOS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {sorted(TIPOS_VALIDOS)}")

    habitacion_numero = (data.habitacion_numero or "").strip() or None
    if habitacion_numero:
        habitacion = (
            db.query(Habitacion).filter(Habitacion.numero == habitacion_numero).first()
        )
        if not habitacion:
            raise HTTPException(
                status_code=404,
                detail=f"Habitación '{habitacion_numero}' no existe",
            )
        if habitacion.estado == "inhabilitada":
            raise HTTPException(
                status_code=400,
                detail=f"La habitación {habitacion_numero} está inhabilitada y no acepta consumos",
            )

    try:
        tasa = obtener_tasa_bcv(db)
        pedido = Pedido(
            tipo=data.tipo,
            mesa=data.mesa,
            habitacion_numero=habitacion_numero,
            reserva_id=data.reserva_id,
            estado="abierto",
            tasa_usd_del_dia=tasa,
            notas=data.notas,
        )
        db.add(pedido)
        db.flush()

        total_bs = Decimal("0")
        total_usd = Decimal("0")

        for item in data.items:
            producto = db.query(Producto).filter(Producto.id == item.producto_id).first()
            if not producto:
                raise HTTPException(status_code=404, detail=f"Producto {item.producto_id} no existe")
            if not producto.activo:
                raise HTTPException(status_code=400, detail=f"Producto '{producto.nombre}' inactivo")
            if not producto.es_para_venta:
                raise HTTPException(status_code=400, detail=f"Producto '{producto.nombre}' no es para venta")

            cantidad = Decimal(item.cantidad)
            precio_bs = Decimal(producto.precio_bs or 0)
            precio_usd = Decimal(producto.precio_usd or 0)
            subtotal_bs = (precio_bs * cantidad).quantize(Decimal("0.01"))
            subtotal_usd = (precio_usd * cantidad).quantize(Decimal("0.01"))

            descontar_inventario_por_receta(
                db,
                producto_id=producto.id,
                cantidad=cantidad,
                motivo=f"Pedido #{pedido.id}",
                referencia=f"pedido:{pedido.id}",
            )

            detalle = DetallePedido(
                pedido_id=pedido.id,
                producto_id=producto.id,
                cantidad=cantidad,
                precio_unit_bs=precio_bs,
                precio_unit_usd=precio_usd,
                subtotal_bs=subtotal_bs,
                subtotal_usd=subtotal_usd,
            )
            db.add(detalle)
            total_bs += subtotal_bs
            total_usd += subtotal_usd

        pedido.total_bs = total_bs
        pedido.total_usd = total_usd
        db.commit()
        return _cargar_pedido(db, pedido.id)
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creando pedido: {exc}") from exc


@router.post("/{pedido_id}/agregar", response_model=PedidoOut)
def agregar_items(pedido_id: int, data: PedidoCreate, db: Session = Depends(get_db)):
    """Añade productos a un pedido ya creado y en estado 'abierto'."""
    pedido = _cargar_pedido(db, pedido_id)
    if pedido.estado != "abierto":
        raise HTTPException(
            status_code=400, detail=f"No se pueden agregar ítems a un pedido {pedido.estado}"
        )
    if not data.items:
        raise HTTPException(status_code=400, detail="Indique al menos un ítem para agregar")

    try:
        total_bs = Decimal(pedido.total_bs or 0)
        total_usd = Decimal(pedido.total_usd or 0)

        for item in data.items:
            producto = db.query(Producto).filter(Producto.id == item.producto_id).first()
            if not producto:
                raise HTTPException(status_code=404, detail=f"Producto {item.producto_id} no existe")
            if not producto.activo:
                raise HTTPException(status_code=400, detail=f"Producto '{producto.nombre}' inactivo")
            if not producto.es_para_venta:
                raise HTTPException(status_code=400, detail=f"Producto '{producto.nombre}' no es para venta")

            cantidad = Decimal(item.cantidad)
            precio_bs = Decimal(producto.precio_bs or 0)
            precio_usd = Decimal(producto.precio_usd or 0)
            subtotal_bs = (precio_bs * cantidad).quantize(Decimal("0.01"))
            subtotal_usd = (precio_usd * cantidad).quantize(Decimal("0.01"))

            descontar_inventario_por_receta(
                db,
                producto_id=producto.id,
                cantidad=cantidad,
                motivo=f"Pedido #{pedido.id} (agregado)",
                referencia=f"pedido:{pedido.id}",
            )

            detalle = DetallePedido(
                pedido_id=pedido.id,
                producto_id=producto.id,
                cantidad=cantidad,
                precio_unit_bs=precio_bs,
                precio_unit_usd=precio_usd,
                subtotal_bs=subtotal_bs,
                subtotal_usd=subtotal_usd,
            )
            db.add(detalle)
            total_bs += subtotal_bs
            total_usd += subtotal_usd

        pedido.total_bs = total_bs
        pedido.total_usd = total_usd
        pedido.updated_at = utc_now()
        if data.notas:
            existentes = (pedido.notas or "").strip()
            pedido.notas = f"{existentes} | {data.notas}".strip(" |") if existentes else data.notas

        db.commit()
        db.expire_all()
        return _cargar_pedido(db, pedido.id)
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error agregando ítems: {exc}") from exc


@router.post("/{pedido_id}/pagar", response_model=PedidoOut)
def pagar_pedido(pedido_id: int, data: PedidoPago, db: Session = Depends(get_db)):
    pedido = _cargar_pedido(db, pedido_id)
    if pedido.estado != "abierto":
        raise HTTPException(status_code=400, detail=f"Pedido ya está {pedido.estado}")
    if data.metodo_pago not in METODOS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Método inválido. Use: {sorted(METODOS_VALIDOS)}")
    if data.metodo_pago == "habitacion":
        raise HTTPException(
            status_code=400,
            detail="Use el endpoint /cargo-habitacion para cargar el pedido a una reserva",
        )

    try:
        tasa_tipo = (data.tasa_tipo or "bcv").lower().strip()
        if tasa_tipo not in TIPOS_TASA_VALIDOS:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo de tasa inválido. Use: {sorted(TIPOS_TASA_VALIDOS)}",
            )

        tasa_seleccionada = obtener_tasa_dia(db, tipo=tasa_tipo)
        tasa = tasa_seleccionada or Decimal(pedido.tasa_usd_del_dia or 0)
        if tasa <= 0:
            raise HTTPException(status_code=400, detail="Tasa de cambio inválida")

        # total_bs y total_usd son el MISMO monto en dos monedas. Usamos Bs como base.
        total_bs_total = Decimal(pedido.total_bs or 0)

        pago_bs = Decimal(data.monto_bs or 0)
        pago_usd = Decimal(data.monto_usd or 0)

        # Pago Móvil: se cobra el total en Bs usando la tasa elegida.
        if data.metodo_pago == "pagomovil" and pago_bs == 0 and pago_usd == 0:
            pago_bs = total_bs_total

        pago_equivalente_bs = pago_bs + (pago_usd * tasa)

        if pago_equivalente_bs + Decimal("0.01") < total_bs_total:
            faltante = (total_bs_total - pago_equivalente_bs).quantize(Decimal("0.01"))
            raise HTTPException(
                status_code=400,
                detail=f"Pago insuficiente. Falta {faltante} Bs equivalente (tasa {tasa})",
            )

        vuelto_total_bs = (pago_equivalente_bs - total_bs_total).quantize(Decimal("0.01"))
        if pago_usd > 0 and vuelto_total_bs > 0:
            vuelto_usd = (vuelto_total_bs / tasa).quantize(Decimal("0.01")) if tasa > 0 else Decimal("0")
            vuelto_bs = Decimal("0")
        else:
            vuelto_usd = Decimal("0")
            vuelto_bs = vuelto_total_bs

        pedido.pagado_bs = pago_bs
        pedido.pagado_usd = pago_usd
        pedido.vuelto_bs = vuelto_bs
        pedido.vuelto_usd = vuelto_usd
        pedido.metodo_pago = data.metodo_pago
        pedido.tasa_usd_del_dia = tasa
        pedido.estado = "pagado"
        pedido.updated_at = utc_now()

        if data.cuenta_banco_id:
            cuenta = db.query(CuentaBanco).filter(CuentaBanco.id == data.cuenta_banco_id).first()
            if not cuenta:
                raise HTTPException(status_code=404, detail="Cuenta de banco no encontrada")
            pedido.cuenta_banco_id = cuenta.id
            monto_movimiento = pago_bs if cuenta.moneda == "BS" else pago_usd
            cuenta.saldo = Decimal(cuenta.saldo or 0) + monto_movimiento
            db.add(
                MovimientoCuenta(
                    cuenta_id=cuenta.id,
                    tipo="entrada",
                    monto=monto_movimiento,
                    saldo_resultante=cuenta.saldo,
                    concepto=f"Pago pedido #{pedido.id} ({data.metodo_pago})",
                    referencia=f"pedido:{pedido.id}",
                )
            )

        db.commit()
        return _cargar_pedido(db, pedido.id)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error procesando pago: {exc}") from exc


@router.put("/{pedido_id}/cargo-habitacion", response_model=PedidoOut)
def cargar_a_habitacion(
    pedido_id: int,
    data: PedidoCargoHabitacion,
    db: Session = Depends(get_db),
):
    pedido = _cargar_pedido(db, pedido_id)
    if pedido.estado not in {"abierto", "cargado"}:
        raise HTTPException(status_code=400, detail=f"No se puede cargar pedido en estado '{pedido.estado}'")

    reserva = db.query(Reserva).filter(Reserva.id == data.reserva_id).first()
    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    if reserva.estado != "activa":
        raise HTTPException(status_code=400, detail="La reserva no está activa")

    try:
        pedido.reserva_id = reserva.id
        pedido.metodo_pago = "habitacion"
        pedido.estado = "cargado"
        pedido.updated_at = utc_now()

        total_bs = Decimal(pedido.total_bs or 0)
        total_usd = Decimal(pedido.total_usd or 0)
        tasa = Decimal(pedido.tasa_usd_del_dia or 0)

        reserva.total_consumos_bs = Decimal(reserva.total_consumos_bs or 0) + total_bs
        reserva.total_consumos_usd = Decimal(reserva.total_consumos_usd or 0) + total_usd
        reserva.total_final_bs = (
            Decimal(reserva.tarifa_bs or 0) * reserva.noches + Decimal(reserva.total_consumos_bs)
        )
        reserva.total_final_usd = (
            Decimal(reserva.tarifa_usd or 0) * reserva.noches + Decimal(reserva.total_consumos_usd)
        )

        consumo = ConsumoHabitacion(
            reserva_id=reserva.id,
            pedido_id=pedido.id,
            concepto=f"Pedido #{pedido.id} ({pedido.tipo})",
            monto_bs=total_bs,
            monto_usd=total_usd,
            tasa_usd_del_dia=tasa,
        )
        db.add(consumo)
        db.commit()
        return _cargar_pedido(db, pedido.id)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error cargando a habitación: {exc}") from exc


@router.delete("/{pedido_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancelar(pedido_id: int, db: Session = Depends(get_db)):
    pedido = _cargar_pedido(db, pedido_id)
    if pedido.estado not in {"abierto"}:
        raise HTTPException(status_code=400, detail="Solo se pueden cancelar pedidos abiertos")
    try:
        pedido.estado = "cancelado"
        pedido.updated_at = utc_now()
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error cancelando pedido: {exc}") from exc
    return None
