from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    CuentaBanco,
    Habitacion,
    MovimientoCuenta,
    Reserva,
    today,
    utc_now,
)
from app.schemas import ReservaCheckout, ReservaCreate, ReservaOut
from app.services.tasa_service import obtener_tasa_dia


router = APIRouter(prefix="/reservas", tags=["reservas"])


def _calcular_totales_finales(reserva: Reserva) -> None:
    consumos_bs = Decimal(reserva.total_consumos_bs or 0)
    consumos_usd = Decimal(reserva.total_consumos_usd or 0)
    reserva.total_final_bs = Decimal(reserva.tarifa_bs or 0) * reserva.noches + consumos_bs
    reserva.total_final_usd = Decimal(reserva.tarifa_usd or 0) * reserva.noches + consumos_usd


@router.get("/", response_model=List[ReservaOut])
def listar(
    estado: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(Reserva)
        if estado:
            query = query.filter(Reserva.estado == estado)
        return query.order_by(Reserva.id.desc()).limit(200).all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando reservas: {exc}") from exc


@router.get("/activas", response_model=List[ReservaOut])
def listar_activas(db: Session = Depends(get_db)):
    try:
        return (
            db.query(Reserva)
            .filter(Reserva.estado == "activa")
            .order_by(Reserva.fecha_checkin.desc())
            .all()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error listando reservas activas: {exc}") from exc


@router.get("/{reserva_id}", response_model=ReservaOut)
def obtener(reserva_id: int, db: Session = Depends(get_db)):
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    return reserva


@router.post("/", response_model=ReservaOut, status_code=status.HTTP_201_CREATED)
def crear_checkin(data: ReservaCreate, db: Session = Depends(get_db)):
    habitacion = db.query(Habitacion).filter(Habitacion.id == data.habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
    if habitacion.estado == "ocupada":
        raise HTTPException(status_code=400, detail="Habitación ya ocupada")
    if habitacion.estado in {"mantenimiento", "bloqueada"}:
        raise HTTPException(status_code=400, detail=f"Habitación en estado '{habitacion.estado}'")

    try:
        tarifa_bs = data.tarifa_bs or Decimal(habitacion.precio_bs or 0)
        tarifa_usd = data.tarifa_usd or Decimal(habitacion.precio_usd or 0)
        reserva = Reserva(
            habitacion_id=data.habitacion_id,
            huesped=data.huesped,
            documento=data.documento,
            telefono=data.telefono,
            fecha_checkin=data.fecha_checkin or today(),
            fecha_checkout_estimado=data.fecha_checkout_estimado,
            noches=data.noches,
            tarifa_bs=tarifa_bs,
            tarifa_usd=tarifa_usd,
            estado="activa",
        )
        _calcular_totales_finales(reserva)
        habitacion.estado = "ocupada"
        db.add(reserva)
        db.commit()
        db.refresh(reserva)
        return reserva
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creando reserva: {exc}") from exc


@router.put("/{reserva_id}/checkout", response_model=ReservaOut)
def checkout(reserva_id: int, data: ReservaCheckout, db: Session = Depends(get_db)):
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    if reserva.estado != "activa":
        raise HTTPException(status_code=400, detail=f"Reserva ya está {reserva.estado}")

    try:
        _calcular_totales_finales(reserva)
        tasa_dia = obtener_tasa_dia(db)
        if tasa_dia <= 0:
            raise HTTPException(status_code=400, detail="Tasa de cambio inválida")
        # total_final_bs y total_final_usd son el MISMO monto en dos monedas. Base: Bs.
        total_bs_total = Decimal(reserva.total_final_bs or 0)

        pago_bs = Decimal(data.monto_recibido_bs or 0)
        pago_usd = Decimal(data.monto_recibido_usd or 0)
        equivalente_pago_bs = pago_bs + (pago_usd * tasa_dia)

        if equivalente_pago_bs + Decimal("0.01") < total_bs_total:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Pago insuficiente. Falta {(total_bs_total - equivalente_pago_bs):.2f} Bs "
                    f"(tasa {tasa_dia})"
                ),
            )

        if data.cuenta_banco_id:
            cuenta = db.query(CuentaBanco).filter(CuentaBanco.id == data.cuenta_banco_id).first()
            if not cuenta:
                raise HTTPException(status_code=404, detail="Cuenta de banco no encontrada")
            monto_movimiento = pago_bs if cuenta.moneda == "BS" else pago_usd
            cuenta.saldo = Decimal(cuenta.saldo or 0) + monto_movimiento
            db.add(
                MovimientoCuenta(
                    cuenta_id=cuenta.id,
                    tipo="entrada",
                    monto=monto_movimiento,
                    saldo_resultante=cuenta.saldo,
                    concepto=f"Checkout reserva #{reserva.id} - {reserva.huesped}",
                    referencia=f"reserva:{reserva.id}",
                )
            )

        reserva.estado = "cerrada"
        reserva.fecha_checkout_real = today()
        reserva.updated_at = utc_now()

        habitacion = db.query(Habitacion).filter(Habitacion.id == reserva.habitacion_id).first()
        if habitacion:
            habitacion.estado = "limpieza"

        db.commit()
        db.refresh(reserva)
        return reserva
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error realizando checkout: {exc}") from exc
