from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def today() -> date:
    return datetime.now(UTC).date()


# ---------------------------------------------------------------------------
# Tasa de cambio
# ---------------------------------------------------------------------------
class TasaCambio(Base):
    __tablename__ = "tasas_cambio"
    __table_args__ = (
        UniqueConstraint("fecha", "tipo", name="uq_tasa_fecha_tipo"),
        CheckConstraint("usd_a_ves > 0", name="ck_tasa_positiva"),
    )

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, default=today, nullable=False, index=True)
    tipo = Column(String(20), default="bcv", nullable=False, index=True)
    usd_a_ves = Column(Numeric(12, 4), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


# ---------------------------------------------------------------------------
# Habitaciones
# ---------------------------------------------------------------------------
class Habitacion(Base):
    __tablename__ = "habitaciones"
    __table_args__ = (
        UniqueConstraint("numero", name="uq_habitacion_numero"),
        CheckConstraint("precio_bs >= 0", name="ck_habitacion_precio_bs"),
        CheckConstraint("precio_usd >= 0", name="ck_habitacion_precio_usd"),
    )

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(String(10), nullable=False, unique=True, index=True)
    tipo = Column(String(40), default="standard", nullable=False)
    precio_bs = Column(Numeric(12, 2), default=0, nullable=False)
    precio_usd = Column(Numeric(10, 2), default=0, nullable=False)
    estado = Column(String(20), default="disponible", nullable=False, index=True)
    notas = Column(String(255))
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    reservas = relationship("Reserva", back_populates="habitacion")


# ---------------------------------------------------------------------------
# Reservas y consumos
# ---------------------------------------------------------------------------
class Reserva(Base):
    __tablename__ = "reservas"
    __table_args__ = (
        CheckConstraint("noches >= 1", name="ck_reserva_noches"),
        CheckConstraint("tarifa_bs >= 0", name="ck_reserva_tarifa_bs"),
        CheckConstraint("tarifa_usd >= 0", name="ck_reserva_tarifa_usd"),
    )

    id = Column(Integer, primary_key=True, index=True)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False, index=True)
    huesped = Column(String(120), nullable=False)
    documento = Column(String(40))
    telefono = Column(String(40))
    fecha_checkin = Column(Date, default=today, nullable=False, index=True)
    fecha_checkout_estimado = Column(Date, nullable=False)
    fecha_checkout_real = Column(Date)
    noches = Column(Integer, default=1, nullable=False)
    tarifa_bs = Column(Numeric(12, 2), default=0, nullable=False)
    tarifa_usd = Column(Numeric(10, 2), default=0, nullable=False)
    total_consumos_bs = Column(Numeric(12, 2), default=0, nullable=False)
    total_consumos_usd = Column(Numeric(10, 2), default=0, nullable=False)
    total_final_bs = Column(Numeric(12, 2), default=0, nullable=False)
    total_final_usd = Column(Numeric(10, 2), default=0, nullable=False)
    estado = Column(String(20), default="activa", nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    habitacion = relationship("Habitacion", back_populates="reservas")
    consumos = relationship("ConsumoHabitacion", back_populates="reserva", cascade="all, delete-orphan")
    pedidos = relationship("Pedido", back_populates="reserva")


class ConsumoHabitacion(Base):
    __tablename__ = "consumos_habitacion"
    __table_args__ = (
        CheckConstraint("monto_bs >= 0", name="ck_consumo_monto_bs"),
        CheckConstraint("monto_usd >= 0", name="ck_consumo_monto_usd"),
    )

    id = Column(Integer, primary_key=True, index=True)
    reserva_id = Column(Integer, ForeignKey("reservas.id"), nullable=False, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"))
    fecha = Column(DateTime, default=utc_now, nullable=False)
    concepto = Column(String(120), nullable=False)
    monto_bs = Column(Numeric(12, 2), default=0, nullable=False)
    monto_usd = Column(Numeric(10, 2), default=0, nullable=False)
    tasa_usd_del_dia = Column(Numeric(12, 4), default=0, nullable=False)

    reserva = relationship("Reserva", back_populates="consumos")


# ---------------------------------------------------------------------------
# Productos y recetas
# ---------------------------------------------------------------------------
class Producto(Base):
    __tablename__ = "productos"
    __table_args__ = (
        UniqueConstraint("nombre", name="uq_producto_nombre"),
        CheckConstraint("precio_bs >= 0", name="ck_producto_precio_bs"),
        CheckConstraint("precio_usd >= 0", name="ck_producto_precio_usd"),
        CheckConstraint("stock_actual >= 0", name="ck_producto_stock"),
        CheckConstraint("stock_minimo >= 0", name="ck_producto_stock_min"),
    )

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(120), nullable=False, unique=True, index=True)
    categoria = Column(String(60), default="general", nullable=False, index=True)
    descripcion = Column(String(255))
    precio_bs = Column(Numeric(12, 2), default=0, nullable=False)
    precio_usd = Column(Numeric(10, 2), default=0, nullable=False)
    costo_bs = Column(Numeric(12, 2), default=0, nullable=False)
    stock_actual = Column(Numeric(12, 3), default=0, nullable=False)
    stock_minimo = Column(Numeric(12, 3), default=0, nullable=False)
    unidad = Column(String(20), default="unidad", nullable=False)
    es_para_venta = Column(Boolean, default=True, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    recetas = relationship(
        "Receta",
        back_populates="producto",
        foreign_keys="Receta.producto_id",
        cascade="all, delete-orphan",
    )


class Receta(Base):
    __tablename__ = "recetas"
    __table_args__ = (
        UniqueConstraint("producto_id", "ingrediente_id", name="uq_receta_producto_ingrediente"),
        CheckConstraint("cantidad > 0", name="ck_receta_cantidad"),
    )

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    ingrediente_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    cantidad = Column(Numeric(12, 3), nullable=False)

    producto = relationship("Producto", back_populates="recetas", foreign_keys=[producto_id])
    ingrediente = relationship("Producto", foreign_keys=[ingrediente_id])


# ---------------------------------------------------------------------------
# Pedidos (POS)
# ---------------------------------------------------------------------------
class Pedido(Base):
    __tablename__ = "pedidos"
    __table_args__ = (
        CheckConstraint("total_bs >= 0", name="ck_pedido_total_bs"),
        CheckConstraint("total_usd >= 0", name="ck_pedido_total_usd"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String(30), default="restaurante", nullable=False, index=True)
    mesa = Column(String(20))
    reserva_id = Column(Integer, ForeignKey("reservas.id"), index=True)
    estado = Column(String(20), default="abierto", nullable=False, index=True)
    fecha = Column(DateTime, default=utc_now, nullable=False, index=True)
    tasa_usd_del_dia = Column(Numeric(12, 4), default=0, nullable=False)
    total_bs = Column(Numeric(12, 2), default=0, nullable=False)
    total_usd = Column(Numeric(10, 2), default=0, nullable=False)
    pagado_bs = Column(Numeric(12, 2), default=0, nullable=False)
    pagado_usd = Column(Numeric(10, 2), default=0, nullable=False)
    vuelto_bs = Column(Numeric(12, 2), default=0, nullable=False)
    vuelto_usd = Column(Numeric(10, 2), default=0, nullable=False)
    metodo_pago = Column(String(30))
    cuenta_banco_id = Column(Integer, ForeignKey("cuentas_banco.id"))
    notas = Column(String(255))
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    reserva = relationship("Reserva", back_populates="pedidos")
    detalles = relationship("DetallePedido", back_populates="pedido", cascade="all, delete-orphan")
    cuenta = relationship("CuentaBanco")


class DetallePedido(Base):
    __tablename__ = "detalles_pedido"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_detalle_cantidad"),
        CheckConstraint("precio_unit_bs >= 0", name="ck_detalle_precio_bs"),
        CheckConstraint("precio_unit_usd >= 0", name="ck_detalle_precio_usd"),
    )

    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    cantidad = Column(Numeric(12, 3), nullable=False)
    precio_unit_bs = Column(Numeric(12, 2), default=0, nullable=False)
    precio_unit_usd = Column(Numeric(10, 2), default=0, nullable=False)
    subtotal_bs = Column(Numeric(12, 2), default=0, nullable=False)
    subtotal_usd = Column(Numeric(10, 2), default=0, nullable=False)

    pedido = relationship("Pedido", back_populates="detalles")
    producto = relationship("Producto")


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------
class MovimientoInventario(Base):
    __tablename__ = "movimientos_inventario"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_movimiento_cantidad"),
    )

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    tipo = Column(String(20), nullable=False, index=True)
    cantidad = Column(Numeric(12, 3), nullable=False)
    stock_anterior = Column(Numeric(12, 3), default=0, nullable=False)
    stock_nuevo = Column(Numeric(12, 3), default=0, nullable=False)
    motivo = Column(String(255))
    referencia = Column(String(60), index=True)
    fecha = Column(DateTime, default=utc_now, nullable=False, index=True)

    producto = relationship("Producto")


# ---------------------------------------------------------------------------
# Gastos
# ---------------------------------------------------------------------------
class CategoriaGasto(Base):
    __tablename__ = "categorias_gasto"
    __table_args__ = (UniqueConstraint("nombre", name="uq_categoria_gasto_nombre"),)

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(80), nullable=False, unique=True, index=True)
    tipo = Column(String(30), default="operativo", nullable=False)
    descripcion = Column(String(255))


class Gasto(Base):
    __tablename__ = "gastos"
    __table_args__ = (
        CheckConstraint("monto_bs >= 0", name="ck_gasto_monto_bs"),
        CheckConstraint("monto_usd >= 0", name="ck_gasto_monto_usd"),
    )

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, default=today, nullable=False, index=True)
    categoria_id = Column(Integer, ForeignKey("categorias_gasto.id"), nullable=False, index=True)
    descripcion = Column(String(255), nullable=False)
    monto_bs = Column(Numeric(12, 2), default=0, nullable=False)
    monto_usd = Column(Numeric(10, 2), default=0, nullable=False)
    cuenta_banco_id = Column(Integer, ForeignKey("cuentas_banco.id"), index=True)
    beneficiario = Column(String(120))
    referencia = Column(String(60))
    notas = Column(String(255))
    created_at = Column(DateTime, default=utc_now, nullable=False)

    categoria = relationship("CategoriaGasto")
    cuenta = relationship("CuentaBanco")


# ---------------------------------------------------------------------------
# Personal
# ---------------------------------------------------------------------------
class Empleado(Base):
    __tablename__ = "empleados"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(120), nullable=False, index=True)
    documento = Column(String(40))
    cargo = Column(String(80), default="general", nullable=False)
    salario_bs = Column(Numeric(12, 2), default=0, nullable=False)
    salario_usd = Column(Numeric(10, 2), default=0, nullable=False)
    forma_pago = Column(String(40), default="quincenal", nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class PagoNomina(Base):
    __tablename__ = "pagos_nomina"
    __table_args__ = (
        CheckConstraint("monto_bs >= 0", name="ck_pago_nomina_bs"),
        CheckConstraint("monto_usd >= 0", name="ck_pago_nomina_usd"),
    )

    id = Column(Integer, primary_key=True, index=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False, index=True)
    periodo = Column(String(40), nullable=False)
    fecha_pago = Column(Date, default=today, nullable=False, index=True)
    monto_bs = Column(Numeric(12, 2), default=0, nullable=False)
    monto_usd = Column(Numeric(10, 2), default=0, nullable=False)
    cuenta_banco_id = Column(Integer, ForeignKey("cuentas_banco.id"))
    notas = Column(String(255))
    created_at = Column(DateTime, default=utc_now, nullable=False)

    empleado = relationship("Empleado")
    cuenta = relationship("CuentaBanco")


# ---------------------------------------------------------------------------
# Cuentas banco
# ---------------------------------------------------------------------------
class CuentaBanco(Base):
    __tablename__ = "cuentas_banco"
    __table_args__ = (UniqueConstraint("nombre", name="uq_cuenta_nombre"),)

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(60), nullable=False, unique=True, index=True)
    tipo = Column(String(30), default="banco", nullable=False)
    moneda = Column(String(10), default="BS", nullable=False)
    saldo = Column(Numeric(14, 2), default=0, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class MovimientoCuenta(Base):
    __tablename__ = "movimientos_cuenta"

    id = Column(Integer, primary_key=True, index=True)
    cuenta_id = Column(Integer, ForeignKey("cuentas_banco.id"), nullable=False, index=True)
    fecha = Column(DateTime, default=utc_now, nullable=False, index=True)
    tipo = Column(String(20), nullable=False, index=True)
    monto = Column(Numeric(14, 2), nullable=False)
    saldo_resultante = Column(Numeric(14, 2), default=0, nullable=False)
    concepto = Column(String(255))
    referencia = Column(String(60), index=True)

    cuenta = relationship("CuentaBanco")


# ---------------------------------------------------------------------------
# Cierre diario
# ---------------------------------------------------------------------------
class CierreDiario(Base):
    __tablename__ = "cierres_diarios"
    __table_args__ = (UniqueConstraint("fecha", name="uq_cierre_fecha"),)

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, default=today, nullable=False, unique=True, index=True)
    ventas_bs = Column(Numeric(14, 2), default=0, nullable=False)
    ventas_usd = Column(Numeric(12, 2), default=0, nullable=False)
    gastos_bs = Column(Numeric(14, 2), default=0, nullable=False)
    gastos_usd = Column(Numeric(12, 2), default=0, nullable=False)
    saldo_cierre_bs = Column(Numeric(14, 2), default=0, nullable=False)
    saldo_cierre_usd = Column(Numeric(12, 2), default=0, nullable=False)
    notas = Column(Text)
    created_at = Column(DateTime, default=utc_now, nullable=False)
