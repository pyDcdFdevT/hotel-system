from __future__ import annotations

import math
from datetime import timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    ESTADOS_HABITACION,
    Habitacion,
    Pedido,
    Reserva,
    caracas_now,
    today,
)
from app.services.tasa_service import obtener_tasa_bcv, obtener_tasa_dia
from app.schemas import (
    HabitacionCheckinRequest,
    HabitacionCheckoutPreview,
    HabitacionCheckoutRequest,
    HabitacionCreate,
    HabitacionEstado,
    HabitacionOut,
    HabitacionUpdate,
    ReservaOut,
)


router = APIRouter(prefix="/habitaciones", tags=["habitaciones"])


ESTADOS_VALIDOS = set(ESTADOS_HABITACION)


def _cargar_habitacion(db: Session, habitacion_id: int) -> Habitacion:
    habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitaci?n no encontrada")
    return habitacion


def _reserva_activa(db: Session, habitacion_id: int) -> Optional[Reserva]:
    return (
        db.query(Reserva)
        .filter(Reserva.habitacion_id == habitacion_id)
        .filter(Reserva.estado == "activa")
        .order_by(Reserva.id.desc())
        .first()
    )


@router.get("/", response_model=List[HabitacionOut])
def listar(
    estado: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(Habitacion)
        if estado:
            query = query.filter(Habitacion.estado == estado)
        return query.order_by(Habitacion.numero.asc()).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando habitaciones: {exc}") from exc


@router.get("/{habitacion_id}", response_model=HabitacionOut)
def obtener(habitacion_id: int, db: Session = Depends(get_db)):
    return _cargar_habitacion(db, habitacion_id)


@router.post("/", response_model=HabitacionOut, status_code=status.HTTP_201_CREATED)
def crear(data: HabitacionCreate, db: Session = Depends(get_db)):
    try:
        if data.estado not in ESTADOS_VALIDOS:
            raise HTTPException(
                status_code=400,
                detail=f"Estado inv?lido. Use: {sorted(ESTADOS_VALIDOS)}",
            )
        habitacion = Habitacion(**data.model_dump())
        db.add(habitacion)
        db.commit()
        db.refresh(habitacion)
        return habitacion
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe una habitaci?n con ese n?mero") from exc
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creando habitaci?n: {exc}") from exc


@router.put("/{habitacion_id}", response_model=HabitacionOut)
def actualizar(habitacion_id: int, data: HabitacionUpdate, db: Session = Depends(get_db)):
    habitacion = _cargar_habitacion(db, habitacion_id)
    try:
        payload = data.model_dump(exclude_unset=True)
        if "estado" in payload and payload["estado"] not in ESTADOS_VALIDOS:
            raise HTTPException(
                status_code=400,
                detail=f"Estado inv?lido. Use: {sorted(ESTADOS_VALIDOS)}",
            )
        for key, value in payload.items():
            setattr(habitacion, key, value)
        db.commit()
        db.refresh(habitacion)
        return habitacion
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error actualizando habitaci?n: {exc}") from exc


@router.patch("/{habitacion_id}/estado", response_model=HabitacionOut)
@router.put("/{habitacion_id}/estado", response_model=HabitacionOut)
def cambiar_estado(habitacion_id: int, data: HabitacionEstado, db: Session = Depends(get_db)):
    if data.estado not in ESTADOS_VALIDOS:
        raise HTTPException(
            status_code=400, detail=f"Estado inv?lido. Use: {sorted(ESTADOS_VALIDOS)}"
        )
    habitacion = _cargar_habitacion(db, habitacion_id)
    try:
        habitacion.estado = data.estado
        db.commit()
        db.refresh(habitacion)
        return habitacion
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error cambiando estado: {exc}") from exc


# ---------------------------------------------------------------------------
# Check-in directo (sin tener que pasar por el m?dulo de reservas)
# ---------------------------------------------------------------------------
@router.post("/{habitacion_id}/checkin", response_model=ReservaOut)
def checkin(habitacion_id: int, data: HabitacionCheckinRequest, db: Session = Depends(get_db)):
    habitacion = _cargar_habitacion(db, habitacion_id)

    if habitacion.estado == "inhabilitada":
        raise HTTPException(
            status_code=400,
            detail="La habitaci?n est? inhabilitada. Habil?tela antes de hacer check-in.",
        )
    if habitacion.estado == "ocupada":
        raise HTTPException(status_code=400, detail="La habitaci?n ya est? ocupada")

    activa = _reserva_activa(db, habitacion_id)
    if activa:
        raise HTTPException(
            status_code=400,
            detail=f"Ya existe la reserva #{activa.id} activa para esta habitaci?n",
        )

    # Si llega con reserva_id, validamos que sea una reserva previa
    # (estado="reservada") asociada a esta habitaci?n. La convertiremos en
    # vez de crear una nueva.
    reserva_previa: Optional[Reserva] = None
    if data.reserva_id:
        reserva_previa = (
            db.query(Reserva)
            .filter(Reserva.id == data.reserva_id)
            .first()
        )
        if not reserva_previa:
            raise HTTPException(status_code=404, detail=f"Reserva #{data.reserva_id} no existe")
        if reserva_previa.habitacion_id != habitacion.id:
            raise HTTPException(
                status_code=400,
                detail="La reserva no pertenece a esta habitaci?n",
            )
        if reserva_previa.estado != "reservada":
            raise HTTPException(
                status_code=400,
                detail=f"La reserva #{reserva_previa.id} no est? en estado 'reservada' (actual: {reserva_previa.estado})",
            )

    try:
        fecha_in = data.fecha_checkin or today()
        noches = max(1, int(data.noches or 1))
        fecha_out = data.fecha_checkout_estimado or (fecha_in + timedelta(days=noches))

        # Precio unitario por noche: lo recibido o el de la habitaci?n.
        precio_unit_usd = (
            Decimal(data.tarifa_usd)
            if data.tarifa_usd is not None
            else Decimal(habitacion.precio_usd or 0)
        )
        # Almacenamos la tarifa total de la estad?a (precio ? noches).
        tarifa_usd = (precio_unit_usd * noches).quantize(Decimal("0.01"))

        if data.tarifa_bs is not None:
            # Si se especifica un total Bs expl?cito, resp?telo.
            tarifa_bs = Decimal(data.tarifa_bs)
        else:
            tasa = obtener_tasa_bcv(db)
            tarifa_bs = (tarifa_usd * Decimal(tasa)).quantize(Decimal("0.01"))

        # ---- Pago anticipado opcional ----
        pagado_usd = Decimal("0")
        pagado_bs = Decimal("0")
        estado_pago = "pendiente"
        metodo_pago_reserva: Optional[str] = None
        if data.pago_anticipado:
            moneda = (data.moneda_pago or "usd").lower().strip()
            if moneda not in {"usd", "bs"}:
                raise HTTPException(
                    status_code=400,
                    detail="moneda_pago inv?lida para pago anticipado. Use 'usd' o 'bs'.",
                )
            metodo_pago_reserva = (data.metodo_pago or "efectivo").lower().strip()

            tasa_tipo = (data.tasa_tipo or "bcv").lower().strip()
            if tasa_tipo not in {"bcv", "paralelo"}:
                tasa_tipo = "bcv"
            tasa_aplicada = Decimal(obtener_tasa_dia(db, tipo=tasa_tipo))

            recibido_usd = Decimal(data.monto_recibido_usd or 0).quantize(Decimal("0.01"))
            recibido_bs = Decimal(data.monto_recibido_bs or 0).quantize(Decimal("0.01"))
            # Si no especific? montos, asumimos que cubre el total de estad?a.
            total_estadia_usd = tarifa_usd
            if moneda == "usd":
                if recibido_usd == 0 and recibido_bs == 0:
                    recibido_usd = total_estadia_usd
                pagado_usd = recibido_usd
                pagado_bs = Decimal("0")
            else:  # bs
                if recibido_usd == 0 and recibido_bs == 0:
                    recibido_bs = (total_estadia_usd * tasa_aplicada).quantize(Decimal("0.01"))
                pagado_bs = recibido_bs
                pagado_usd = Decimal("0")

            # Para estado: comparamos el equivalente abonado en USD vs total estad?a.
            equivalente_usd_abonado = pagado_usd + (
                (pagado_bs / tasa_aplicada).quantize(Decimal("0.01"))
                if tasa_aplicada > 0
                else Decimal("0")
            )
            if equivalente_usd_abonado + Decimal("0.01") >= total_estadia_usd:
                estado_pago = "pagado"
            elif equivalente_usd_abonado > 0:
                estado_pago = "parcial"
            else:
                estado_pago = "pendiente"

        if reserva_previa is not None:
            # Convertir reserva previa ? check-in efectivo.
            reserva = reserva_previa
            reserva.huesped = data.huesped or reserva.huesped
            reserva.documento = data.documento or reserva.documento
            reserva.telefono = data.telefono or reserva.telefono
            reserva.fecha_checkin = fecha_in
            reserva.fecha_checkout_estimado = fecha_out
            reserva.noches = noches
            reserva.tarifa_bs = tarifa_bs
            reserva.tarifa_usd = tarifa_usd
            reserva.estado = "activa"
            reserva.vehiculo_modelo = data.vehiculo_modelo or reserva.vehiculo_modelo
            reserva.vehiculo_color = data.vehiculo_color or reserva.vehiculo_color
            reserva.vehiculo_placa = data.vehiculo_placa or reserva.vehiculo_placa
            reserva.hora_ingreso = data.hora_ingreso or reserva.hora_ingreso
            reserva.pais_origen = data.pais_origen or reserva.pais_origen
            reserva.tipo_documento = data.tipo_documento or reserva.tipo_documento
            reserva.numero_documento = data.numero_documento or reserva.numero_documento
            # Si se env?a un nuevo pago anticipado, se suma al existente.
            if data.pago_anticipado:
                reserva.pagado_parcial_usd = Decimal(
                    reserva.pagado_parcial_usd or 0
                ) + pagado_usd
                reserva.pagado_parcial_bs = Decimal(
                    reserva.pagado_parcial_bs or 0
                ) + pagado_bs
                if metodo_pago_reserva:
                    reserva.metodo_pago = metodo_pago_reserva
                reserva.estado_pago = estado_pago
            reserva.updated_at = caracas_now()
        else:
            reserva = Reserva(
                habitacion_id=habitacion.id,
                huesped=data.huesped,
                documento=data.documento,
                telefono=data.telefono,
                fecha_checkin=fecha_in,
                fecha_checkout_estimado=fecha_out,
                noches=noches,
                tarifa_bs=tarifa_bs,
                tarifa_usd=tarifa_usd,
                estado="activa",
                vehiculo_modelo=(data.vehiculo_modelo or None),
                vehiculo_color=(data.vehiculo_color or None),
                vehiculo_placa=(data.vehiculo_placa or None),
                hora_ingreso=(data.hora_ingreso or None),
                pais_origen=(data.pais_origen or None),
                tipo_documento=(data.tipo_documento or None),
                numero_documento=(data.numero_documento or None),
                pagado_parcial_usd=pagado_usd,
                pagado_parcial_bs=pagado_bs,
                estado_pago=estado_pago,
                metodo_pago=metodo_pago_reserva,
            )
            db.add(reserva)

        habitacion.estado = "ocupada"
        db.commit()
        db.refresh(reserva)
        return reserva
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error en check-in: {exc}") from exc


# ---------------------------------------------------------------------------
# Check-out: total estad?a + consumos
# ---------------------------------------------------------------------------
TIPOS_TASA_VALIDOS = {"bcv", "paralelo"}
MONEDAS_PAGO_VALIDAS = {"usd", "bs", "mixto"}

# Reglas de late check-out.
HORA_SALIDA_ESTANDAR = "13:00"
RECARGA_HORA_EXTRA_USD = Decimal("5")


def _parsear_hora(valor: Optional[str]) -> Optional[Tuple[int, int]]:
    """Convierte ``HH:MM`` a ``(hh, mm)``; devuelve ``None`` si no es v?lida."""
    if not valor:
        return None
    txt = str(valor).strip()
    if not txt:
        return None
    partes = txt.split(":")
    try:
        hh = int(partes[0])
        mm = int(partes[1]) if len(partes) > 1 else 0
    except (ValueError, IndexError):
        return None
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return None
    return hh, mm


def _calcular_horas_extra(hora_salida: Optional[str]) -> int:
    """Horas (redondeo hacia arriba) por encima de las 13:00.

    Si no se env?a hora o la hora es <= 13:00, devuelve ``0``.
    """
    parsed = _parsear_hora(hora_salida)
    if not parsed:
        return 0
    hh, mm = parsed
    minutos = hh * 60 + mm
    minutos_estandar = 13 * 60
    if minutos <= minutos_estandar:
        return 0
    return int(math.ceil((minutos - minutos_estandar) / 60.0))


# Mapeo opci?n combinada ? (moneda_pago, metodo_pago)
OPCION_PAGO_MAP: dict[str, tuple[str, str]] = {
    "efectivo_usd": ("usd", "efectivo"),
    "efectivo_bs": ("bs", "efectivo"),
    "transferencia_bs": ("bs", "transferencia"),
    "pagomovil_bs": ("bs", "pagomovil"),
    "mixto": ("mixto", "mixto"),
}


def _resolver_opcion_pago(
    opcion_pago: Optional[str],
    moneda_pago: Optional[str],
    metodo_pago: Optional[str],
) -> tuple[str, str]:
    """Devuelve la tupla (moneda_pago, metodo_pago) final.

    Si llega ``opcion_pago``, manda; si no, se infiere a partir de los campos
    sueltos (compatibilidad con clientes antiguos).
    """
    if opcion_pago:
        clave = opcion_pago.lower().strip()
        if clave in OPCION_PAGO_MAP:
            return OPCION_PAGO_MAP[clave]
        raise HTTPException(
            status_code=400,
            detail=f"opcion_pago inv?lida. Use: {sorted(OPCION_PAGO_MAP)}",
        )

    moneda = (moneda_pago or "usd").lower().strip()
    if moneda not in MONEDAS_PAGO_VALIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"moneda_pago inv?lida. Use: {sorted(MONEDAS_PAGO_VALIDAS)}",
        )
    metodo = (metodo_pago or "efectivo").lower().strip()
    return moneda, metodo


def _calcular_preview(
    db: Session,
    habitacion: Habitacion,
    tasa_tipo: str = "bcv",
    hora_salida: Optional[str] = None,
) -> HabitacionCheckoutPreview:
    tasa_tipo = (tasa_tipo or "bcv").lower().strip()
    if tasa_tipo not in TIPOS_TASA_VALIDOS:
        tasa_tipo = "bcv"

    reserva = _reserva_activa(db, habitacion.id)

    consumos_bs = Decimal("0")
    consumos_usd = Decimal("0")
    pedidos_ids: list[int] = []

    if reserva:
        for consumo in reserva.consumos:
            consumos_bs += Decimal(consumo.monto_bs or 0)
            consumos_usd += Decimal(consumo.monto_usd or 0)

    pedidos_abiertos = (
        db.query(Pedido)
        .filter(Pedido.habitacion_numero == habitacion.numero)
        .filter(Pedido.estado == "abierto")
        .all()
    )
    for pedido in pedidos_abiertos:
        consumos_bs += Decimal(pedido.total_bs or 0)
        consumos_usd += Decimal(pedido.total_usd or 0)
        pedidos_ids.append(pedido.id)

    tarifa_usd = Decimal(reserva.tarifa_usd or 0) if reserva else Decimal("0")

    # Tasa de referencia del d?a (BCV o paralelo seg?n lo pedido).
    tasa_aplicada = Decimal(obtener_tasa_dia(db, tipo=tasa_tipo))

    # Recargo por late check-out (despu?s de las 13:00).
    horas_extra = _calcular_horas_extra(hora_salida)
    recarga_extra_usd = (
        (Decimal(horas_extra) * RECARGA_HORA_EXTRA_USD).quantize(Decimal("0.01"))
        if horas_extra > 0
        else Decimal("0")
    )
    recarga_extra_bs = (recarga_extra_usd * tasa_aplicada).quantize(Decimal("0.01"))

    # Los importes en bol?vares se recalculan SIEMPRE con la tasa solicitada
    # para que el monto a cobrar refleje la moneda elegida en el check-out,
    # independientemente de la tasa usada al check-in.
    tarifa_bs = (tarifa_usd * tasa_aplicada).quantize(Decimal("0.01"))
    consumos_bs = (consumos_usd * tasa_aplicada).quantize(Decimal("0.01"))

    total_usd = (tarifa_usd + consumos_usd + recarga_extra_usd).quantize(Decimal("0.01"))
    total_bs = (total_usd * tasa_aplicada).quantize(Decimal("0.01"))

    # Pago anticipado abonado en el check-in.
    pagado_parcial_usd = (
        Decimal(reserva.pagado_parcial_usd or 0) if reserva else Decimal("0")
    )
    pagado_parcial_bs = (
        Decimal(reserva.pagado_parcial_bs or 0) if reserva else Decimal("0")
    )
    estado_pago = (reserva.estado_pago if reserva else None) or "pendiente"

    # Convertimos lo abonado en Bs a USD para restarlo del total expresado en USD.
    abonado_usd_eq = pagado_parcial_usd + (
        (pagado_parcial_bs / tasa_aplicada).quantize(Decimal("0.01"))
        if tasa_aplicada > 0
        else Decimal("0")
    )
    pendiente_usd = (total_usd - abonado_usd_eq).quantize(Decimal("0.01"))
    if pendiente_usd < 0:
        pendiente_usd = Decimal("0")
    pendiente_bs = (pendiente_usd * tasa_aplicada).quantize(Decimal("0.01"))

    return HabitacionCheckoutPreview(
        habitacion_id=habitacion.id,
        numero=habitacion.numero,
        reserva_id=reserva.id if reserva else None,
        huesped=reserva.huesped if reserva else None,
        noches=int(reserva.noches) if reserva else 0,
        tarifa_usd=tarifa_usd,
        tarifa_bs=tarifa_bs,
        consumos_usd=consumos_usd,
        consumos_bs=consumos_bs,
        total_usd=total_usd,
        total_bs=total_bs,
        tasa_tipo=tasa_tipo,
        tasa_aplicada=tasa_aplicada,
        pedidos=pedidos_ids,
        hora_salida_estandar=HORA_SALIDA_ESTANDAR,
        hora_salida=hora_salida or None,
        horas_extra=horas_extra,
        recarga_extra_usd=recarga_extra_usd,
        recarga_extra_bs=recarga_extra_bs,
        pagado_parcial_usd=pagado_parcial_usd,
        pagado_parcial_bs=pagado_parcial_bs,
        estado_pago=estado_pago,
        pendiente_usd=pendiente_usd,
        pendiente_bs=pendiente_bs,
    )


@router.get("/{habitacion_id}/checkout-preview", response_model=HabitacionCheckoutPreview)
def checkout_preview(
    habitacion_id: int,
    tasa_tipo: str = "bcv",
    hora_salida: Optional[str] = None,
    db: Session = Depends(get_db),
):
    habitacion = _cargar_habitacion(db, habitacion_id)
    return _calcular_preview(
        db, habitacion, tasa_tipo=tasa_tipo, hora_salida=hora_salida
    )


@router.get("/{habitacion_id}/checkin-cotizacion")
def checkin_cotizacion(
    habitacion_id: int,
    noches: int = 1,
    tasa_tipo: str = "bcv",
    tarifa_usd: Optional[float] = None,
    db: Session = Depends(get_db),
):
    """Calcula el total a cobrar dada una habitaci?n, noches y tarifa.

    Si ``tarifa_usd`` viene en query, se usa ese precio; en caso contrario,
    se toma el ``precio_usd`` de la habitaci?n. Devuelve tambi?n el equivalente
    en bol?vares seg?n la tasa seleccionada (BCV o paralelo).
    """
    habitacion = _cargar_habitacion(db, habitacion_id)
    tasa_tipo = (tasa_tipo or "bcv").lower().strip()
    if tasa_tipo not in TIPOS_TASA_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"tasa_tipo inv?lido. Use: {sorted(TIPOS_TASA_VALIDOS)}",
        )
    noches = max(1, int(noches or 1))
    precio_unit_usd = (
        Decimal(str(tarifa_usd)) if tarifa_usd is not None
        else Decimal(habitacion.precio_usd or 0)
    )
    tasa = Decimal(obtener_tasa_dia(db, tipo=tasa_tipo))
    total_usd = (precio_unit_usd * noches).quantize(Decimal("0.01"))
    total_bs = (total_usd * tasa).quantize(Decimal("0.01"))
    return {
        "habitacion_id": habitacion.id,
        "numero": habitacion.numero,
        "noches": noches,
        "precio_unit_usd": precio_unit_usd,
        "precio_unit_bs": (precio_unit_usd * tasa).quantize(Decimal("0.01")),
        "total_usd": total_usd,
        "total_bs": total_bs,
        "tasa_tipo": tasa_tipo,
        "tasa_aplicada": tasa,
    }


@router.post("/{habitacion_id}/checkout", response_model=HabitacionCheckoutPreview)
def checkout(
    habitacion_id: int,
    data: HabitacionCheckoutRequest,
    db: Session = Depends(get_db),
):
    moneda_pago, metodo_pago = _resolver_opcion_pago(
        data.opcion_pago, data.moneda_pago, data.metodo_pago
    )
    tasa_tipo = (data.tasa_tipo or "bcv").lower().strip()
    if tasa_tipo not in TIPOS_TASA_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"tasa_tipo inv?lido. Use: {sorted(TIPOS_TASA_VALIDOS)}",
        )

    habitacion = _cargar_habitacion(db, habitacion_id)
    reserva = _reserva_activa(db, habitacion_id)
    pedidos_abiertos = (
        db.query(Pedido)
        .options(joinedload(Pedido.detalles))
        .filter(Pedido.habitacion_numero == habitacion.numero)
        .filter(Pedido.estado == "abierto")
        .all()
    )

    if not reserva and not pedidos_abiertos:
        raise HTTPException(
            status_code=400,
            detail="No hay reserva activa ni consumos abiertos para esta habitaci?n",
        )

    try:
        preview = _calcular_preview(
            db, habitacion, tasa_tipo=tasa_tipo, hora_salida=data.hora_salida
        )

        # S?lo cobramos el saldo pendiente (total - pago anticipado).
        cobro_usd = preview.pendiente_usd
        cobro_bs = preview.pendiente_bs

        # Reparto del cobro entre USD y Bs seg?n la moneda elegida:
        #   - usd  ? todo en d?lares (sin tasa).
        #   - bs   ? todo en bol?vares (con tasa BCV o paralelo).
        #   - mixto ? respeta lo que el usuario haya ingresado en
        #             monto_recibido_usd / monto_recibido_bs; lo no cubierto en
        #             USD se completa con Bs a la tasa aplicada.
        if moneda_pago == "usd":
            pagado_usd_total = cobro_usd
            pagado_bs_total = Decimal("0")
        elif moneda_pago == "bs":
            pagado_usd_total = Decimal("0")
            pagado_bs_total = cobro_bs
        else:  # mixto
            pagado_usd_total = Decimal(data.monto_recibido_usd or 0).quantize(Decimal("0.01"))
            # Lo que falta en USD se cobra en Bs a la tasa aplicada.
            faltante_usd = (cobro_usd - pagado_usd_total).quantize(Decimal("0.01"))
            if faltante_usd < 0:
                faltante_usd = Decimal("0")
            pagado_bs_total = (faltante_usd * preview.tasa_aplicada).quantize(Decimal("0.01"))
            # Si el cliente indic? expl?citamente bol?vares recibidos,
            # respetamos ese valor (debe coincidir con el faltante).
            if data.monto_recibido_bs and Decimal(data.monto_recibido_bs) > 0:
                pagado_bs_total = Decimal(data.monto_recibido_bs).quantize(Decimal("0.01"))

        ahora = caracas_now()
        for pedido in pedidos_abiertos:
            pedido.estado = "pagado"
            pedido.metodo_pago = metodo_pago
            pedido.cuenta_banco_id = data.cuenta_banco_id
            if moneda_pago == "usd":
                pedido.pagado_usd = Decimal(pedido.total_usd or 0)
                pedido.pagado_bs = Decimal("0")
            elif moneda_pago == "bs":
                pedido.pagado_bs = Decimal(pedido.total_bs or 0)
                pedido.pagado_usd = Decimal("0")
            else:  # mixto: prorrateamos en proporci?n al total recibido
                total_pedido_usd = Decimal(pedido.total_usd or 0)
                if preview.total_usd > 0:
                    proporcion = total_pedido_usd / preview.total_usd
                    pedido.pagado_usd = (pagado_usd_total * proporcion).quantize(Decimal("0.01"))
                    pedido.pagado_bs = (pagado_bs_total * proporcion).quantize(Decimal("0.01"))
                else:
                    pedido.pagado_usd = Decimal("0")
                    pedido.pagado_bs = Decimal("0")
            pedido.updated_at = ahora

        if reserva:
            reserva.fecha_checkout_real = today()
            reserva.estado = "cerrada"
            reserva.total_consumos_bs = preview.consumos_bs
            reserva.total_consumos_usd = preview.consumos_usd
            # total_final_* = anticipo + cobro del check-out (lo realmente percibido).
            reserva.total_final_usd = (
                Decimal(preview.pagado_parcial_usd or 0) + pagado_usd_total
            ).quantize(Decimal("0.01"))
            reserva.total_final_bs = (
                Decimal(preview.pagado_parcial_bs or 0) + pagado_bs_total
            ).quantize(Decimal("0.01"))
            reserva.hora_salida = (data.hora_salida or HORA_SALIDA_ESTANDAR)
            reserva.horas_extra = int(preview.horas_extra or 0)
            reserva.recarga_extra_usd = preview.recarga_extra_usd
            reserva.recarga_extra_bs = preview.recarga_extra_bs
            reserva.metodo_pago = metodo_pago
            reserva.estado_pago = "pagado"
            reserva.updated_at = ahora

        habitacion.estado = "limpieza"
        habitacion.updated_at = ahora

        db.commit()
        preview_resp = preview.model_copy(
            update={
                "tasa_tipo": tasa_tipo,
                # Devolvemos al frontend el monto efectivamente cobrado ahora
                # (excluyendo el anticipo) para que pinte el ticket correctamente.
                "total_usd": pagado_usd_total if moneda_pago != "bs" else cobro_usd,
                "total_bs": pagado_bs_total if moneda_pago != "usd" else cobro_bs,
                "estado_pago": "pagado",
            }
        )
        return preview_resp
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error en check-out: {exc}") from exc


@router.delete("/{habitacion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(habitacion_id: int, db: Session = Depends(get_db)):
    habitacion = _cargar_habitacion(db, habitacion_id)
    try:
        db.delete(habitacion)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="La habitaci?n tiene reservas vinculadas",
        ) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error eliminando habitaci?n: {exc}") from exc
    return None
