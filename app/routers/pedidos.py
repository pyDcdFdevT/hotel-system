from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
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
    Usuario,
    caracas_now,
    utc_now,
)
from app.routers.auth import get_current_user, require_roles
from app.schemas import (
    CocinaEstadoUpdate,
    DetalleCocinaOut,
    DetalleEstadoUpdate,
    DetallePedidoOut,
    PedidoAnular,
    PedidoCargoHabitacion,
    PedidoCocinaOut,
    PedidoCreate,
    PedidoItemsUpdate,
    PedidoOut,
    PedidoPago,
)
from app.services.inventario_service import (
    descontar_inventario_por_receta,
    restaurar_inventario_por_receta,
)
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


ESTADOS_DETALLE = ("pendiente", "en_preparacion", "listo", "entregado")
TRANSICIONES_DETALLE = {
    "pendiente": {"en_preparacion", "listo"},
    "en_preparacion": {"listo", "pendiente"},
    "listo": {"entregado", "en_preparacion"},
    "entregado": set(),
}


def _agregar_estado_pedido(detalles: list[DetallePedido]) -> str:
    """Calcula el estado agregado del pedido a partir de sus detalles.

    Reglas:
    * todos ``entregado``  → ``entregado``
    * todos ``listo`` (o entregado)  → ``listo``
    * alguno ``en_preparacion``  → ``en_preparacion``
    * en cualquier otro caso → ``pendiente``
    """
    estados = [(d.estado or "pendiente") for d in (detalles or [])]
    if not estados:
        return "pendiente"
    if all(e == "entregado" for e in estados):
        return "entregado"
    if all(e in ("listo", "entregado") for e in estados):
        return "listo"
    if any(e == "en_preparacion" for e in estados):
        return "en_preparacion"
    return "pendiente"


@router.get(
    "/activos-cocina",
    response_model=List[PedidoCocinaOut],
    dependencies=[Depends(require_roles("admin", "cocina"))],
)
def listar_pedidos_cocina(db: Session = Depends(get_db)):
    """Pedidos abiertos con al menos un ítem pendiente/en_preparacion.

    Cada pedido devuelve **todos** sus detalles para que la pantalla de
    cocina pueda gestionarlos individualmente; sólo se filtran del listado
    los pedidos cuyos detalles están todos en estado ``listo`` o
    ``entregado`` (ya nada por hacer).
    """
    pedidos = (
        db.query(Pedido)
        .options(joinedload(Pedido.detalles).joinedload(DetallePedido.producto))
        .filter(Pedido.estado == "abierto")
        .order_by(Pedido.fecha.asc())
        .all()
    )
    salida: list[PedidoCocinaOut] = []
    for p in pedidos:
        # Si todos los detalles ya están listos/entregados, el pedido sale de cocina.
        if all((d.estado or "pendiente") in ("listo", "entregado") for d in p.detalles):
            continue
        salida.append(
            PedidoCocinaOut(
                id=p.id,
                mesa=p.mesa,
                habitacion_numero=p.habitacion_numero,
                tipo=p.tipo,
                estado=p.estado,
                estado_cocina=_agregar_estado_pedido(list(p.detalles)),
                fecha=p.fecha,
                detalles=[
                    DetalleCocinaOut(
                        id=d.id,
                        producto_id=d.producto_id,
                        producto_nombre=(
                            d.producto.nombre if d.producto else f"#{d.producto_id}"
                        ),
                        cantidad=float(d.cantidad),
                        area=(d.producto.area if d.producto else None),
                        categoria=(d.producto.categoria if d.producto else None),
                        estado=d.estado or "pendiente",
                        iniciado_en=d.iniciado_en,
                        listo_en=d.listo_en,
                    )
                    for d in p.detalles
                ],
            )
        )
    return salida


@router.get(
    "/{pedido_id}/detalles",
    response_model=List[DetallePedidoOut],
)
def listar_detalles(pedido_id: int, db: Session = Depends(get_db)):
    """Devuelve los detalles del pedido con sus estados individuales."""
    pedido = _cargar_pedido(db, pedido_id)
    return list(pedido.detalles)


@router.put(
    "/{pedido_id}/detalles/{detalle_id}/estado",
    response_model=DetallePedidoOut,
)
def actualizar_estado_detalle(
    pedido_id: int,
    detalle_id: int,
    data: DetalleEstadoUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Avanza/retrocede el estado de un detalle.

    Permisos:
    * ``en_preparacion`` y ``listo`` → admin, cocina (la cocina prepara).
    * ``entregado`` → admin, mesero, recepcion (quien entrega al cliente).
    * ``pendiente`` → admin sólo (retroceder es excepcional).
    """
    estado = (data.estado or "").strip().lower()
    if estado not in ESTADOS_DETALLE:
        raise HTTPException(
            status_code=400,
            detail=f"Estado inválido. Use: {list(ESTADOS_DETALLE)}",
        )

    rol = (usuario.rol or "").lower()
    permitidos_por_estado = {
        "pendiente": {"admin"},
        "en_preparacion": {"admin", "cocina"},
        "listo": {"admin", "cocina"},
        "entregado": {"admin", "mesero", "recepcion"},
    }
    if rol not in permitidos_por_estado.get(estado, set()):
        raise HTTPException(
            status_code=403,
            detail=(
                f"El rol '{rol}' no puede marcar un ítem como '{estado}'."
            ),
        )

    pedido = _cargar_pedido(db, pedido_id)
    detalle = next((d for d in pedido.detalles if d.id == detalle_id), None)
    if not detalle:
        raise HTTPException(status_code=404, detail="Detalle no encontrado")

    estado_actual = (detalle.estado or "pendiente").lower()
    permitidas = TRANSICIONES_DETALLE.get(estado_actual, set())
    if estado != estado_actual and estado not in permitidas and rol != "admin":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Transición no permitida: {estado_actual} → {estado}"
            ),
        )

    ahora = caracas_now()
    detalle.estado = estado
    if estado == "en_preparacion" and not detalle.iniciado_en:
        detalle.iniciado_en = ahora
    elif estado == "listo":
        if not detalle.iniciado_en:
            detalle.iniciado_en = ahora
        detalle.listo_en = ahora
    elif estado == "entregado":
        if not detalle.iniciado_en:
            detalle.iniciado_en = ahora
        if not detalle.listo_en:
            detalle.listo_en = ahora
        detalle.entregado_en = ahora

    # Sincronizamos el agregado en Pedido para retro-compatibilidad.
    pedido.estado_cocina = _agregar_estado_pedido(list(pedido.detalles))
    pedido.ultima_actividad = ahora
    pedido.updated_at = utc_now()
    db.commit()
    db.refresh(detalle)
    return detalle


@router.put(
    "/{pedido_id}/cocina-estado",
    response_model=PedidoOut,
    dependencies=[Depends(require_roles("admin", "cocina"))],
)
def actualizar_estado_cocina(
    pedido_id: int,
    data: CocinaEstadoUpdate,
    db: Session = Depends(get_db),
):
    """Endpoint legado: cambia el estado AGREGADO del pedido.

    Se mantiene por compatibilidad con clientes antiguos, pero el flujo
    nuevo usa ``PUT /pedidos/{id}/detalles/{detalle_id}/estado`` y
    actualiza el agregado automáticamente.
    """
    if data.estado_cocina not in ESTADOS_DETALLE:
        raise HTTPException(
            status_code=400,
            detail=f"Estado cocina inválido. Use: {list(ESTADOS_DETALLE)}",
        )
    pedido = _cargar_pedido(db, pedido_id)
    pedido.estado_cocina = data.estado_cocina
    # Propagamos a los detalles para mantener consistencia con la
    # granularidad por ítem (el agregado refleja el peor caso).
    ahora = caracas_now()
    for d in pedido.detalles:
        d.estado = data.estado_cocina
        if data.estado_cocina == "en_preparacion" and not d.iniciado_en:
            d.iniciado_en = ahora
        elif data.estado_cocina == "listo":
            if not d.iniciado_en:
                d.iniciado_en = ahora
            d.listo_en = d.listo_en or ahora
        elif data.estado_cocina == "entregado":
            if not d.iniciado_en:
                d.iniciado_en = ahora
            if not d.listo_en:
                d.listo_en = ahora
            d.entregado_en = d.entregado_en or ahora
    pedido.updated_at = utc_now()
    db.commit()
    db.expire_all()
    return _cargar_pedido(db, pedido_id)


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
    mesa_nombre = (data.mesa or "").strip() or None

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
        # Bloquea crear una segunda cuenta abierta contra la misma habitación.
        duplicado_hab = (
            db.query(Pedido)
            .filter(Pedido.estado == "abierto")
            .filter(Pedido.habitacion_numero == habitacion_numero)
            .first()
        )
        if duplicado_hab:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Ya existe una cuenta activa para la habitación "
                    f"{habitacion_numero} (#{duplicado_hab.id})"
                ),
            )
    elif mesa_nombre:
        # Comparación case-insensitive y sin espacios al borde para evitar
        # falsos negativos del tipo "Mesa 5" vs "mesa 5".
        duplicado_mesa = (
            db.query(Pedido)
            .filter(Pedido.estado == "abierto")
            .filter(func.lower(func.trim(Pedido.mesa)) == mesa_nombre.lower())
            .first()
        )
        if duplicado_mesa:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Ya existe una cuenta activa con el nombre "
                    f"'{mesa_nombre}' (#{duplicado_mesa.id})"
                ),
            )

    try:
        tasa = obtener_tasa_bcv(db)
        pedido = Pedido(
            tipo=data.tipo,
            mesa=mesa_nombre,
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
        pedido.ultima_actividad = caracas_now()
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
        pedido.ultima_actividad = caracas_now()
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


def _cancelar_pedido_interno(db: Session, pedido_id: int) -> Pedido:
    """Marca el pedido como cancelado y devuelve el stock consumido.

    Sólo cancela pedidos en estado ``abierto``. Para cada detalle, devuelve
    el inventario que se descontó al crearlo (sea ingrediente vía receta o
    el propio producto).
    """
    pedido = _cargar_pedido(db, pedido_id)
    if pedido.estado != "abierto":
        raise HTTPException(
            status_code=400,
            detail=f"Sólo se pueden cancelar pedidos abiertos (estado actual: {pedido.estado})",
        )
    for detalle in (pedido.detalles or []):
        try:
            restaurar_inventario_por_receta(
                db,
                producto_id=detalle.producto_id,
                cantidad=Decimal(detalle.cantidad or 0),
                motivo=f"Cancelación pedido #{pedido.id}",
                referencia=f"pedido:{pedido.id}",
            )
        except ValueError:
            # Si la cantidad era 0 o el producto fue eliminado, seguimos.
            continue
    pedido.estado = "cancelado"
    pedido.updated_at = utc_now()
    return pedido


@router.delete(
    "/{pedido_id}/cancelar",
    dependencies=[Depends(require_roles("admin", "mesero"))],
)
def cancelar_pedido(pedido_id: int, db: Session = Depends(get_db)):
    """Cancela un pedido abierto y devuelve el stock descontado."""
    try:
        pedido = _cancelar_pedido_interno(db, pedido_id)
        db.commit()
        return {"success": True, "pedido_id": pedido.id, "estado": pedido.estado}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error cancelando pedido: {exc}") from exc


@router.delete("/{pedido_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancelar(pedido_id: int, db: Session = Depends(get_db)):
    """Alias legacy: equivalente a /cancelar pero accesible para cualquier usuario autenticado."""
    try:
        _cancelar_pedido_interno(db, pedido_id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error cancelando pedido: {exc}") from exc
    return None


# ---------------------------------------------------------------------------
# Edición de items (cuenta aparcada) y aparcar
# ---------------------------------------------------------------------------
@router.put(
    "/{pedido_id}/items",
    response_model=PedidoOut,
    dependencies=[Depends(require_roles("admin", "mesero"))],
)
def actualizar_items(
    pedido_id: int,
    data: PedidoItemsUpdate,
    db: Session = Depends(get_db),
):
    """Reemplaza la lista de ítems del pedido (sólo si está abierto).

    Devuelve stock por los ítems eliminados y descuenta por los nuevos. Las
    cantidades que se mantienen se ajustan por diferencia.
    """
    pedido = _cargar_pedido(db, pedido_id)
    if pedido.estado != "abierto":
        raise HTTPException(
            status_code=400,
            detail=f"Sólo se pueden editar pedidos abiertos (actual: {pedido.estado})",
        )

    try:
        # Mapeo del estado actual: producto_id → cantidad actual.
        actuales: dict[int, Decimal] = {}
        for det in pedido.detalles or []:
            actuales[det.producto_id] = Decimal(det.cantidad or 0)

        nuevos: dict[int, Decimal] = {}
        for item in data.items or []:
            cant = Decimal(item.cantidad)
            if cant <= 0:
                continue
            nuevos[item.producto_id] = nuevos.get(item.producto_id, Decimal("0")) + cant

        # 1) Productos eliminados: devolver TODO su stock.
        for prod_id, cant in actuales.items():
            if prod_id not in nuevos and cant > 0:
                try:
                    restaurar_inventario_por_receta(
                        db,
                        producto_id=prod_id,
                        cantidad=cant,
                        motivo=f"Edición pedido #{pedido.id} (quitado)",
                        referencia=f"pedido:{pedido.id}",
                    )
                except ValueError:
                    continue

        # 2) Ajuste de cantidades (suma o resta diferencia).
        for prod_id, cant_nueva in nuevos.items():
            cant_actual = actuales.get(prod_id, Decimal("0"))
            delta = cant_nueva - cant_actual
            if delta > 0:
                descontar_inventario_por_receta(
                    db,
                    producto_id=prod_id,
                    cantidad=delta,
                    motivo=f"Edición pedido #{pedido.id} (incrementado)",
                    referencia=f"pedido:{pedido.id}",
                )
            elif delta < 0:
                restaurar_inventario_por_receta(
                    db,
                    producto_id=prod_id,
                    cantidad=-delta,
                    motivo=f"Edición pedido #{pedido.id} (decrementado)",
                    referencia=f"pedido:{pedido.id}",
                )

        # 3) Borrar detalles antiguos y reconstruir.
        for det in list(pedido.detalles or []):
            db.delete(det)
        db.flush()

        total_bs = Decimal("0")
        total_usd = Decimal("0")
        for prod_id, cant in nuevos.items():
            producto = db.query(Producto).filter(Producto.id == prod_id).first()
            if not producto:
                raise HTTPException(
                    status_code=404,
                    detail=f"Producto {prod_id} no existe",
                )
            precio_bs = Decimal(producto.precio_bs or 0)
            precio_usd = Decimal(producto.precio_usd or 0)
            subtotal_bs = (precio_bs * cant).quantize(Decimal("0.01"))
            subtotal_usd = (precio_usd * cant).quantize(Decimal("0.01"))
            db.add(
                DetallePedido(
                    pedido_id=pedido.id,
                    producto_id=prod_id,
                    cantidad=cant,
                    precio_unit_bs=precio_bs,
                    precio_unit_usd=precio_usd,
                    subtotal_bs=subtotal_bs,
                    subtotal_usd=subtotal_usd,
                )
            )
            total_bs += subtotal_bs
            total_usd += subtotal_usd

        pedido.total_bs = total_bs
        pedido.total_usd = total_usd
        pedido.updated_at = utc_now()
        pedido.ultima_actividad = caracas_now()
        if data.notas is not None:
            pedido.notas = data.notas or None

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
        raise HTTPException(status_code=500, detail=f"Error editando ítems: {exc}") from exc


@router.post(
    "/{pedido_id}/aparcar",
    response_model=PedidoOut,
    dependencies=[Depends(require_roles("admin", "mesero"))],
)
def aparcar_pedido(pedido_id: int, db: Session = Depends(get_db)):
    """Aparca (guarda sin cobrar) una cuenta abierta.

    No cambia el estado del pedido (sigue ``abierto``); sólo registra la última
    actividad para que aparezca en la lista de "Cuentas pendientes".
    """
    pedido = _cargar_pedido(db, pedido_id)
    if pedido.estado != "abierto":
        raise HTTPException(
            status_code=400,
            detail=f"Sólo se pueden aparcar pedidos abiertos (actual: {pedido.estado})",
        )
    try:
        pedido.ultima_actividad = caracas_now()
        pedido.updated_at = utc_now()
        db.commit()
        return _cargar_pedido(db, pedido.id)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error aparcando pedido: {exc}") from exc


# ---------------------------------------------------------------------------
# Anular venta pagada (sólo admin)
# ---------------------------------------------------------------------------
@router.post("/{pedido_id}/anular")
def anular_venta(
    pedido_id: int,
    body: PedidoAnular,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("admin")),
):
    """Anula una venta ya pagada. Restaura stock y registra el motivo.

    El pedido pasa a estado ``anulado`` y ``anulado=True``. Los reportes que
    filtran por ``estado in ("pagado", "cargado")`` lo excluyen automáticamente.
    Si el pedido estaba cargado a una habitación con consumos, no se elimina
    el consumo (sólo se anula la venta para reportes).
    """
    pedido = _cargar_pedido(db, pedido_id)
    if pedido.estado not in {"pagado", "cargado"}:
        raise HTTPException(
            status_code=400,
            detail=f"Sólo se pueden anular ventas pagadas (estado actual: {pedido.estado})",
        )
    if pedido.anulado:
        raise HTTPException(status_code=400, detail="La venta ya fue anulada anteriormente")
    try:
        for detalle in pedido.detalles or []:
            try:
                restaurar_inventario_por_receta(
                    db,
                    producto_id=detalle.producto_id,
                    cantidad=Decimal(detalle.cantidad or 0),
                    motivo=f"Anulación venta #{pedido.id}: {body.motivo}",
                    referencia=f"pedido:{pedido.id}",
                )
            except ValueError:
                continue
        ahora = caracas_now()
        pedido.estado = "anulado"
        pedido.anulado = True
        pedido.anulado_motivo = body.motivo
        pedido.anulado_por = usuario.nombre
        pedido.anulado_en = ahora
        pedido.updated_at = utc_now()
        pedido.ultima_actividad = ahora
        db.commit()
        return {
            "success": True,
            "pedido_id": pedido.id,
            "estado": pedido.estado,
            "anulado_por": pedido.anulado_por,
            "anulado_en": pedido.anulado_en.isoformat() if pedido.anulado_en else None,
            "motivo": pedido.anulado_motivo,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error anulando venta: {exc}") from exc
