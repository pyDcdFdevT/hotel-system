from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import List, Optional

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
from app.services.tasa_service import obtener_tasa_bcv
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

    try:
        fecha_in = data.fecha_checkin or today()
        noches = max(1, int(data.noches or 1))
        fecha_out = data.fecha_checkout_estimado or (fecha_in + timedelta(days=noches))

        tarifa_usd = (
            Decimal(data.tarifa_usd) if data.tarifa_usd is not None else Decimal(habitacion.precio_usd or 0)
        )
        if data.tarifa_bs is not None:
            tarifa_bs = Decimal(data.tarifa_bs)
        else:
            tarifa_bs = Decimal(habitacion.precio_bs or 0)
            if not tarifa_bs:
                tasa = obtener_tasa_bcv(db)
                tarifa_bs = (tarifa_usd * Decimal(tasa)).quantize(Decimal("0.01"))

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
def _calcular_preview(db: Session, habitacion: Habitacion) -> HabitacionCheckoutPreview:
    reserva = _reserva_activa(db, habitacion.id)

    consumos_bs = Decimal("0")
    consumos_usd = Decimal("0")
    pedidos_ids: list[int] = []

    # Consumos ya cargados a una reserva activa.
    if reserva:
        for consumo in reserva.consumos:
            consumos_bs += Decimal(consumo.monto_bs or 0)
            consumos_usd += Decimal(consumo.monto_usd or 0)

    # Pedidos abiertos asociados al n?mero de habitaci?n (cuenta sin check-in previo).
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

    tarifa_bs = Decimal(reserva.tarifa_bs or 0) if reserva else Decimal("0")
    tarifa_usd = Decimal(reserva.tarifa_usd or 0) if reserva else Decimal("0")

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
        total_usd=(tarifa_usd + consumos_usd).quantize(Decimal("0.01")),
        total_bs=(tarifa_bs + consumos_bs).quantize(Decimal("0.01")),
        pedidos=pedidos_ids,
    )


@router.get("/{habitacion_id}/checkout-preview", response_model=HabitacionCheckoutPreview)
def checkout_preview(habitacion_id: int, db: Session = Depends(get_db)):
    habitacion = _cargar_habitacion(db, habitacion_id)
    return _calcular_preview(db, habitacion)


@router.post("/{habitacion_id}/checkout", response_model=HabitacionCheckoutPreview)
def checkout(
    habitacion_id: int,
    data: HabitacionCheckoutRequest,
    db: Session = Depends(get_db),
):
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
        preview = _calcular_preview(db, habitacion)

        # Cerrar todos los pedidos abiertos en habitaci?n con el mismo m?todo.
        ahora = caracas_now()
        for pedido in pedidos_abiertos:
            pedido.estado = "pagado"
            pedido.metodo_pago = data.metodo_pago
            pedido.cuenta_banco_id = data.cuenta_banco_id
            pedido.pagado_bs = Decimal(pedido.total_bs or 0)
            pedido.pagado_usd = Decimal(pedido.total_usd or 0)
            pedido.updated_at = ahora

        # Cerrar reserva si existe.
        if reserva:
            reserva.fecha_checkout_real = today()
            reserva.estado = "cerrada"
            reserva.total_consumos_bs = preview.consumos_bs
            reserva.total_consumos_usd = preview.consumos_usd
            reserva.total_final_bs = preview.total_bs
            reserva.total_final_usd = preview.total_usd
            reserva.updated_at = ahora

        habitacion.estado = "limpieza"
        habitacion.updated_at = ahora

        db.commit()
        return preview
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
