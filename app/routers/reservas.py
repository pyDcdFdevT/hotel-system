from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    CuentaBanco,
    Habitacion,
    LogAcceso,
    MovimientoCuenta,
    Reserva,
    Usuario,
    caracas_now,
    today,
    utc_now,
)
from app.routers.auth import require_roles
from app.schemas import (
    CancelarReservaRequest,
    ReservaCheckout,
    ReservaCreate,
    ReservaOut,
)
from app.services.tasa_service import obtener_tasa_dia


router = APIRouter(prefix="/reservas", tags=["reservas"])


MONEDAS_PAGO_VALIDAS = {"usd", "bs"}


def _inicio_fin_bloqueo_reserva(r: Reserva) -> tuple[date, date]:
    """Rango inclusive en el que la reserva impide otras reservas solapadas."""
    fin = r.fecha_checkout_estimado
    if r.estado == "activa":
        ini = r.fecha_checkin
    else:
        ini = r.fecha_checkin - timedelta(days=1)
    return ini, fin


def _rangos_bloqueo_se_solapan(
    a_ini: date, a_fin: date, b_ini: date, b_fin: date
) -> bool:
    return a_ini <= b_fin and b_ini <= a_fin


def _calcular_totales_finales(reserva: Reserva) -> None:
    consumos_bs = Decimal(reserva.total_consumos_bs or 0)
    consumos_usd = Decimal(reserva.total_consumos_usd or 0)
    reserva.total_final_bs = Decimal(reserva.tarifa_bs or 0) * reserva.noches + consumos_bs
    reserva.total_final_usd = Decimal(reserva.tarifa_usd or 0) * reserva.noches + consumos_usd


def _aplicar_pago_anticipado(data: ReservaCreate, tarifa_usd: Decimal, db: Session) -> tuple:
    """Resuelve montos abonados al hacer la reserva.

    Devuelve ``(pagado_usd, pagado_bs, estado_pago, metodo_pago)``.
    """
    if not data.pago_anticipado:
        return Decimal("0"), Decimal("0"), "pendiente", None

    moneda = (data.moneda_pago or "usd").lower().strip()
    if moneda not in MONEDAS_PAGO_VALIDAS:
        raise HTTPException(
            status_code=400,
            detail="moneda_pago inválida para pago anticipado. Use 'usd' o 'bs'.",
        )
    metodo = (data.metodo_pago or "efectivo").lower().strip()
    tasa_tipo = (data.tasa_tipo or "bcv").lower().strip()
    if tasa_tipo not in {"bcv", "paralelo"}:
        tasa_tipo = "bcv"
    tasa = Decimal(obtener_tasa_dia(db, tipo=tasa_tipo))

    recibido_usd = Decimal(data.monto_recibido_usd or 0).quantize(Decimal("0.01"))
    recibido_bs = Decimal(data.monto_recibido_bs or 0).quantize(Decimal("0.01"))
    if moneda == "usd":
        if recibido_usd == 0 and recibido_bs == 0:
            recibido_usd = tarifa_usd
        pagado_usd = recibido_usd
        pagado_bs = Decimal("0")
    else:
        if recibido_usd == 0 and recibido_bs == 0:
            recibido_bs = (tarifa_usd * tasa).quantize(Decimal("0.01"))
        pagado_bs = recibido_bs
        pagado_usd = Decimal("0")

    equivalente_usd = pagado_usd + (
        (pagado_bs / tasa).quantize(Decimal("0.01"))
        if tasa > 0
        else Decimal("0")
    )
    if equivalente_usd + Decimal("0.01") >= tarifa_usd:
        estado = "pagado"
    elif equivalente_usd > 0:
        estado = "parcial"
    else:
        estado = "pendiente"
    return pagado_usd, pagado_bs, estado, metodo


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
def crear_reserva(data: ReservaCreate, db: Session = Depends(get_db)):
    """Crea una reserva PRE-Check-in en estado ``reservada``.

    La habitación queda bloqueada (estado ``reservada``) pero no se ocupa
    hasta que se haga el check-in efectivo. Acepta pago anticipado opcional.
    """
    habitacion = db.query(Habitacion).filter(Habitacion.id == data.habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
    if habitacion.estado == "ocupada":
        raise HTTPException(status_code=400, detail="Habitación ya ocupada")
    if habitacion.estado == "inhabilitada":
        raise HTTPException(
            status_code=400,
            detail="La habitación está inhabilitada y no acepta reservas",
        )

    hoy = today()
    fecha_in = data.fecha_checkin or hoy
    fecha_out = data.fecha_checkout_estimado

    otras = (
        db.query(Reserva)
        .filter(
            Reserva.habitacion_id == habitacion.id,
            Reserva.estado.in_(["reservada", "activa"]),
        )
        .all()
    )
    n_ini = fecha_in - timedelta(days=1)
    n_fin = fecha_out
    for r in otras:
        o_ini, o_fin = _inicio_fin_bloqueo_reserva(r)
        if _rangos_bloqueo_se_solapan(o_ini, o_fin, n_ini, n_fin):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"La habitación tiene conflicto con la reserva #{r.id} "
                    "(fechas solapadas en periodo de bloqueo)."
                ),
            )

    try:
        noches = max(1, int(data.noches or 1))
        # Tarifa por noche y total de la estadía (precio × noches).
        precio_unit_usd = (
            Decimal(data.tarifa_usd)
            if data.tarifa_usd
            else Decimal(habitacion.precio_usd or 0)
        )
        tarifa_usd_total = (precio_unit_usd * noches).quantize(Decimal("0.01"))
        if data.tarifa_bs:
            tarifa_bs_total = Decimal(data.tarifa_bs)
        else:
            tasa = Decimal(obtener_tasa_dia(db, tipo="bcv"))
            tarifa_bs_total = (tarifa_usd_total * tasa).quantize(Decimal("0.01"))

        pagado_usd, pagado_bs, estado_pago, metodo_pago_resv = _aplicar_pago_anticipado(
            data, tarifa_usd_total, db
        )

        reserva = Reserva(
            habitacion_id=data.habitacion_id,
            huesped=data.huesped,
            documento=data.documento,
            telefono=data.telefono,
            fecha_checkin=data.fecha_checkin or today(),
            fecha_checkout_estimado=data.fecha_checkout_estimado,
            noches=noches,
            tarifa_bs=tarifa_bs_total,
            tarifa_usd=tarifa_usd_total,
            estado="reservada",
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
            metodo_pago=metodo_pago_resv,
        )
        # La habitación pasa a "reservada" en BD solo al entrar en ventana de bloqueo.
        if habitacion.estado == "disponible" and fecha_in <= hoy + timedelta(days=1):
            habitacion.estado = "reservada"
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


# ---------------------------------------------------------------------------
# Cancelación de reserva (admin / recepción) con reembolso porcentual
# ---------------------------------------------------------------------------
@router.post("/{reserva_id}/cancelar")
def cancelar_reserva(
    reserva_id: int,
    body: CancelarReservaRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("admin", "recepcion")),
):
    """Cancela una reserva (en estado ``reservada`` o ``activa``).

    Si hay pago anticipado, se aplica un reembolso porcentual sobre lo abonado
    y se registran los montos. La habitación queda ``disponible``.
    """
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    if reserva.estado not in {"reservada", "activa"}:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede cancelar una reserva en estado '{reserva.estado}'",
        )

    try:
        porcentaje = max(0, min(100, int(body.porcentaje_reembolso)))
        factor = Decimal(porcentaje) / Decimal(100)
        abonado_usd = Decimal(reserva.pagado_parcial_usd or 0)
        abonado_bs = Decimal(reserva.pagado_parcial_bs or 0)
        reembolso_usd = (abonado_usd * factor).quantize(Decimal("0.01"))
        reembolso_bs = (abonado_bs * factor).quantize(Decimal("0.01"))

        ahora = caracas_now()
        reserva.estado = "cancelada"
        reserva.cancelada = True
        reserva.cancelada_motivo = body.nota or None
        reserva.cancelada_en = ahora
        reserva.reembolso_porcentaje = porcentaje
        reserva.reembolso_monto_usd = reembolso_usd
        reserva.reembolso_monto_bs = reembolso_bs
        if body.metodo_pago_reembolso:
            reserva.metodo_pago = body.metodo_pago_reembolso
        reserva.updated_at = ahora

        habitacion = (
            db.query(Habitacion).filter(Habitacion.id == reserva.habitacion_id).first()
        )
        if habitacion and habitacion.estado in {"reservada", "ocupada"}:
            habitacion.estado = "disponible"
            habitacion.updated_at = ahora

        db.add(
            LogAcceso(
                usuario_id=usuario.id,
                usuario_nombre=usuario.nombre,
                accion="cancelar_reserva",
                detalle=(
                    f"Reserva #{reserva.id} cancelada. Reembolso {porcentaje}% "
                    f"= {reembolso_usd} USD / {reembolso_bs} Bs. "
                    f"Nota: {body.nota or '-'}"
                ),
                exitoso=True,
            )
        )

        db.commit()
        return {
            "success": True,
            "reserva_id": reserva.id,
            "habitacion_id": reserva.habitacion_id,
            "estado": reserva.estado,
            "porcentaje_reembolso": porcentaje,
            "reembolso_usd": float(reembolso_usd),
            "reembolso_bs": float(reembolso_bs),
            "cancelada_por": usuario.nombre,
            "cancelada_en": ahora.isoformat(),
            "nota": body.nota,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error cancelando reserva: {exc}"
        ) from exc
