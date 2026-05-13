from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Tasa
# ---------------------------------------------------------------------------
class TasaCambioOut(ORMModel):
    id: int
    fecha: date
    tipo: str = "bcv"
    usd_a_ves: Decimal
    created_at: Optional[datetime] = None


class TasaCambioCreate(BaseModel):
    usd_a_ves: Decimal = Field(..., gt=0)
    fecha: Optional[date] = None
    tipo: Optional[str] = Field(default="bcv", max_length=20)


class TasasActualesOut(BaseModel):
    fecha: date
    bcv: Decimal
    paralelo: Decimal


# ---------------------------------------------------------------------------
# Habitaciones
# ---------------------------------------------------------------------------
class HabitacionBase(BaseModel):
    numero: str = Field(..., min_length=1, max_length=10)
    tipo: str = Field(default="standard", max_length=40)
    precio_bs: Decimal = Field(default=Decimal("0"), ge=0)
    precio_usd: Decimal = Field(default=Decimal("0"), ge=0)
    estado: str = Field(default="disponible", max_length=20)
    notas: Optional[str] = Field(default=None, max_length=255)


class HabitacionCreate(HabitacionBase):
    pass


class HabitacionUpdate(BaseModel):
    tipo: Optional[str] = None
    precio_bs: Optional[Decimal] = Field(default=None, ge=0)
    precio_usd: Optional[Decimal] = Field(default=None, ge=0)
    estado: Optional[str] = None
    notas: Optional[str] = None


class HabitacionEstado(BaseModel):
    estado: str = Field(..., min_length=1, max_length=20)


class HabitacionOut(ORMModel):
    id: int
    numero: str
    tipo: str
    precio_bs: Decimal
    precio_usd: Decimal
    estado: str
    notas: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Reservas
# ---------------------------------------------------------------------------
class ReservaCreate(BaseModel):
    habitacion_id: int = Field(..., gt=0)
    huesped: str = Field(..., min_length=2, max_length=120)
    documento: Optional[str] = Field(default=None, max_length=40)
    telefono: Optional[str] = Field(default=None, max_length=40)
    fecha_checkin: Optional[date] = None
    fecha_checkout_estimado: date
    noches: int = Field(default=1, ge=1)
    tarifa_bs: Decimal = Field(default=Decimal("0"), ge=0)
    tarifa_usd: Decimal = Field(default=Decimal("0"), ge=0)
    vehiculo_modelo: Optional[str] = Field(default=None, max_length=100)
    vehiculo_color: Optional[str] = Field(default=None, max_length=50)
    vehiculo_placa: Optional[str] = Field(default=None, max_length=20)
    hora_ingreso: Optional[str] = Field(default=None, max_length=10)
    hora_salida: Optional[str] = Field(default=None, max_length=10)
    # Datos del huésped
    pais_origen: Optional[str] = Field(default=None, max_length=100)
    tipo_documento: Optional[str] = Field(default=None, max_length=20)
    numero_documento: Optional[str] = Field(default=None, max_length=50)
    notas: Optional[str] = Field(default=None, max_length=255)
    # Pago anticipado (opcional, idéntico al check-in).
    pago_anticipado: bool = False
    moneda_pago: Optional[str] = Field(default=None, max_length=10)
    metodo_pago: Optional[str] = Field(default=None, max_length=30)
    monto_recibido_usd: Decimal = Field(default=Decimal("0"), ge=0)
    monto_recibido_bs: Decimal = Field(default=Decimal("0"), ge=0)
    tasa_tipo: Optional[str] = Field(default=None, max_length=20)


class ReservaCheckout(BaseModel):
    metodo_pago: str = Field(default="bs", min_length=2, max_length=20)
    cuenta_banco_id: Optional[int] = Field(default=None, gt=0)
    monto_recibido_bs: Decimal = Field(default=Decimal("0"), ge=0)
    monto_recibido_usd: Decimal = Field(default=Decimal("0"), ge=0)
    notas: Optional[str] = None


class HabitacionCheckinRequest(BaseModel):
    """Check-in directo desde la grilla de habitaciones."""

    huesped: str = Field(..., min_length=2, max_length=120)
    documento: Optional[str] = Field(default=None, max_length=40)
    telefono: Optional[str] = Field(default=None, max_length=40)
    fecha_checkin: Optional[date] = None
    fecha_checkout_estimado: Optional[date] = None
    noches: int = Field(default=1, ge=1)
    tarifa_usd: Optional[Decimal] = Field(default=None, ge=0)
    tarifa_bs: Optional[Decimal] = Field(default=None, ge=0)
    notas: Optional[str] = None
    vehiculo_modelo: Optional[str] = Field(default=None, max_length=100)
    vehiculo_color: Optional[str] = Field(default=None, max_length=50)
    vehiculo_placa: Optional[str] = Field(default=None, max_length=20)
    hora_ingreso: Optional[str] = Field(default=None, max_length=10)
    """Hora manual de ingreso del huésped (formato ``HH:MM``)."""
    # Datos del huésped (nacionalidad y documento).
    pais_origen: Optional[str] = Field(default=None, max_length=100)
    tipo_documento: Optional[str] = Field(default=None, max_length=20)
    numero_documento: Optional[str] = Field(default=None, max_length=50)
    # Si se llega con una reserva previa (estado="reservada"), pasar su id
    # para convertirla en check-in activo en vez de crear una nueva.
    reserva_id: Optional[int] = Field(default=None, gt=0)

    # ---- Pago anticipado opcional ----
    pago_anticipado: bool = False
    moneda_pago: Optional[str] = Field(default=None, max_length=10)
    """``usd`` o ``bs`` (sólo aplica si ``pago_anticipado``)."""
    metodo_pago: Optional[str] = Field(default=None, max_length=30)
    """``efectivo``, ``transferencia``, ``pagomovil``..."""
    monto_recibido_usd: Decimal = Field(default=Decimal("0"), ge=0)
    monto_recibido_bs: Decimal = Field(default=Decimal("0"), ge=0)
    tasa_tipo: Optional[str] = Field(default=None, max_length=20)
    """Tasa a usar si el pago se hace en Bs."""


class HabitacionCheckoutRequest(BaseModel):
    """Check-out + cobro de la habitación (estadía + consumos).

    El frontend envía ``opcion_pago`` (botones combinados) y el backend lo mapea
    a ``moneda_pago`` + ``metodo_pago``. Para compatibilidad con clientes antiguos
    también se aceptan ``moneda_pago`` / ``metodo_pago`` por separado.

    Si el saldo pendiente es 0 (todo pagado por adelantado), ``opcion_pago`` puede
    omitirse: el cierre no registra cobro adicional.
    """

    opcion_pago: Optional[str] = Field(default=None, max_length=30)
    """Opción combinada: ``efectivo_usd``, ``efectivo_bs``, ``transferencia_bs``,
    ``pagomovil_bs``, ``mixto``."""

    moneda_pago: Optional[str] = Field(default=None, min_length=2, max_length=10)
    """``usd``, ``bs`` o ``mixto`` (se infiere de ``opcion_pago`` si no se envía)."""

    metodo_pago: Optional[str] = Field(default=None, max_length=20)
    """Método específico de pago (efectivo, transferencia, pagomovil, mixto...)."""

    tasa_tipo: Optional[str] = Field(default=None, max_length=20)
    """Si ``moneda_pago='bs'`` o ``'mixto'``, qué tasa aplicar (``bcv`` o ``paralelo``)."""

    cuenta_banco_id: Optional[int] = Field(default=None, gt=0)
    monto_recibido_bs: Decimal = Field(default=Decimal("0"), ge=0)
    monto_recibido_usd: Decimal = Field(default=Decimal("0"), ge=0)
    notas: Optional[str] = None
    hora_salida: Optional[str] = Field(default=None, max_length=10)
    """Hora manual de salida (formato ``HH:MM``). Si excede 13:00 se aplica recargo."""


class HabitacionCheckoutPreview(BaseModel):
    """Resumen de lo que se cobrará al hacer checkout."""

    habitacion_id: int
    numero: str
    reserva_id: Optional[int] = None
    huesped: Optional[str] = None
    noches: int = 0
    tarifa_usd: Decimal = Decimal("0")
    tarifa_bs: Decimal = Decimal("0")
    consumos_usd: Decimal = Decimal("0")
    consumos_bs: Decimal = Decimal("0")
    total_usd: Decimal = Decimal("0")
    total_bs: Decimal = Decimal("0")
    tasa_tipo: str = "bcv"
    tasa_aplicada: Decimal = Decimal("0")
    pedidos: List[int] = []
    hora_salida_estandar: str = "13:00"
    hora_salida: Optional[str] = None
    horas_extra: int = 0
    recarga_extra_usd: Decimal = Decimal("0")
    recarga_extra_bs: Decimal = Decimal("0")
    # Pago anticipado: monto ya abonado al hacer check-in.
    pagado_parcial_usd: Decimal = Decimal("0")
    pagado_parcial_bs: Decimal = Decimal("0")
    estado_pago: str = "pendiente"
    # Saldo pendiente tras restar el pago anticipado del total.
    pendiente_usd: Decimal = Decimal("0")
    pendiente_bs: Decimal = Decimal("0")
    # Alias explícitos para UI / integraciones (mismo valor que pagado_parcial_* y pendiente_*).
    pagado_por_adelantado_usd: Decimal = Decimal("0")
    pagado_por_adelantado_bs: Decimal = Decimal("0")
    # Saldo a cobrar (total estadía + consumos + recargo - adelanto); alias de pendiente_*.
    saldo_pendiente_usd: Decimal = Decimal("0")
    saldo_pendiente_bs: Decimal = Decimal("0")
    # True si no queda nada por cobrar (adelanto cubre el total).
    pago_completo_adelantado: bool = False


class ReservaOut(ORMModel):
    id: int
    habitacion_id: int
    huesped: str
    documento: Optional[str] = None
    telefono: Optional[str] = None
    fecha_checkin: date
    fecha_checkout_estimado: date
    fecha_checkout_real: Optional[date] = None
    noches: int
    tarifa_bs: Decimal
    tarifa_usd: Decimal
    total_consumos_bs: Decimal
    total_consumos_usd: Decimal
    total_final_bs: Decimal
    total_final_usd: Decimal
    estado: str
    vehiculo_modelo: Optional[str] = None
    vehiculo_color: Optional[str] = None
    vehiculo_placa: Optional[str] = None
    hora_ingreso: Optional[str] = None
    hora_salida: Optional[str] = None
    horas_extra: int = 0
    recarga_extra_usd: Decimal = Decimal("0")
    recarga_extra_bs: Decimal = Decimal("0")
    pagado_parcial_usd: Decimal = Decimal("0")
    pagado_parcial_bs: Decimal = Decimal("0")
    estado_pago: str = "pendiente"
    pais_origen: Optional[str] = None
    tipo_documento: Optional[str] = None
    numero_documento: Optional[str] = None
    cancelada: bool = False
    cancelada_motivo: Optional[str] = None
    cancelada_en: Optional[datetime] = None
    reembolso_porcentaje: int = 0
    reembolso_monto_usd: Decimal = Decimal("0")
    reembolso_monto_bs: Decimal = Decimal("0")
    metodo_pago: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Productos / recetas
# ---------------------------------------------------------------------------
class ProductoBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=120)
    categoria: str = Field(default="general", max_length=60)
    area: str = Field(default="general", max_length=20)
    porcion: Optional[str] = Field(default=None, max_length=20)
    descripcion: Optional[str] = Field(default=None, max_length=255)
    precio_bs: Decimal = Field(default=Decimal("0"), ge=0)
    precio_usd: Decimal = Field(default=Decimal("0"), ge=0)
    costo_bs: Decimal = Field(default=Decimal("0"), ge=0)
    stock_actual: Decimal = Field(default=Decimal("0"), ge=0)
    stock_minimo: Decimal = Field(default=Decimal("0"), ge=0)
    unidad: str = Field(default="unidad", max_length=20)
    es_para_venta: bool = True
    activo: bool = True


class ProductoCreate(ProductoBase):
    pass


class ProductoUpdate(BaseModel):
    nombre: Optional[str] = None
    categoria: Optional[str] = None
    area: Optional[str] = None
    porcion: Optional[str] = None
    descripcion: Optional[str] = None
    precio_bs: Optional[Decimal] = Field(default=None, ge=0)
    precio_usd: Optional[Decimal] = Field(default=None, ge=0)
    costo_bs: Optional[Decimal] = Field(default=None, ge=0)
    stock_actual: Optional[Decimal] = Field(default=None, ge=0)
    stock_minimo: Optional[Decimal] = Field(default=None, ge=0)
    unidad: Optional[str] = None
    es_para_venta: Optional[bool] = None
    activo: Optional[bool] = None


class ProductoOut(ORMModel):
    id: int
    nombre: str
    categoria: str
    area: str = "general"
    porcion: Optional[str] = None
    descripcion: Optional[str] = None
    precio_bs: Decimal
    precio_usd: Decimal
    costo_bs: Decimal
    stock_actual: Decimal
    stock_minimo: Decimal
    unidad: str
    es_para_venta: bool
    activo: bool


class VentasArea(BaseModel):
    area: str
    ventas_bs: Decimal
    ventas_usd: Decimal


class VentasPorArea(BaseModel):
    fecha: date
    areas: List[VentasArea]
    total_bs: Decimal
    total_usd: Decimal


class RecetaIngrediente(BaseModel):
    ingrediente_id: int = Field(..., gt=0)
    cantidad: Decimal = Field(..., gt=0)


class RecetaCreate(BaseModel):
    producto_id: int = Field(..., gt=0)
    ingredientes: List[RecetaIngrediente] = Field(..., min_length=1)


class RecetaOut(ORMModel):
    id: int
    producto_id: int
    ingrediente_id: int
    cantidad: Decimal


# ---------------------------------------------------------------------------
# Pedidos (POS)
# ---------------------------------------------------------------------------
class DetallePedidoIn(BaseModel):
    producto_id: int = Field(..., gt=0)
    cantidad: Decimal = Field(..., gt=0)


class PedidoCreate(BaseModel):
    tipo: str = Field(default="restaurante", max_length=30)
    mesa: Optional[str] = Field(default=None, max_length=20)
    habitacion_numero: Optional[str] = Field(default=None, max_length=10)
    reserva_id: Optional[int] = Field(default=None, gt=0)
    items: List[DetallePedidoIn] = Field(..., min_length=1)
    notas: Optional[str] = None


class PedidoPago(BaseModel):
    metodo_pago: str = Field(default="mixto", max_length=30)
    metodo_pago_usd: Optional[str] = Field(default=None, max_length=30)
    metodo_pago_bs: Optional[str] = Field(default=None, max_length=30)
    monto_bs: Decimal = Field(default=Decimal("0"), ge=0)
    monto_usd: Decimal = Field(default=Decimal("0"), ge=0)
    cuenta_banco_id: Optional[int] = Field(default=None, gt=0)
    tasa_tipo: Optional[str] = Field(default=None, max_length=20)


class PedidoCargoHabitacion(BaseModel):
    reserva_id: int = Field(..., gt=0)


class PedidoItemsUpdate(BaseModel):
    """Reemplaza los detalles de un pedido abierto.

    Si se omite un producto que existía, se devuelve su stock al inventario.
    Si una cantidad cambia, se ajusta la diferencia.
    """

    items: List[DetallePedidoIn] = Field(default_factory=list)
    notas: Optional[str] = None


class PedidoAnular(BaseModel):
    """Anulación de una venta ya pagada (sólo admin)."""

    motivo: str = Field(..., min_length=2, max_length=200)


class DetallePedidoOut(ORMModel):
    id: int
    producto_id: int
    cantidad: Decimal
    precio_unit_bs: Decimal
    precio_unit_usd: Decimal
    subtotal_bs: Decimal
    subtotal_usd: Decimal
    # Flujo cocina/bar por ítem (autoridad por encima de Pedido.estado_cocina).
    estado: Optional[str] = "pendiente"
    iniciado_en: Optional[datetime] = None
    listo_en: Optional[datetime] = None
    entregado_en: Optional[datetime] = None


class DetalleEstadoUpdate(BaseModel):
    """Payload para ``PUT /pedidos/{id}/detalles/{detalle_id}/estado``."""

    estado: str = Field(..., min_length=3, max_length=20)


class DetalleCocinaOut(BaseModel):
    """Información reducida de un detalle para la pantalla de cocina."""

    id: int
    producto_id: int
    producto_nombre: str
    cantidad: float
    area: Optional[str] = None
    categoria: Optional[str] = None
    estado: str
    iniciado_en: Optional[datetime] = None
    listo_en: Optional[datetime] = None


class PedidoCocinaOut(BaseModel):
    """Pedido agrupado para la pantalla cocina (sin precios)."""

    id: int
    mesa: Optional[str] = None
    habitacion_numero: Optional[str] = None
    tipo: str
    estado: str
    estado_cocina: str
    fecha: Optional[datetime] = None
    detalles: List[DetalleCocinaOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Favoritos por usuario
# ---------------------------------------------------------------------------
class FavoritoIn(BaseModel):
    producto_id: int


class FavoritoReorden(BaseModel):
    """Reordenamiento batch: lista de ``producto_id`` en el nuevo orden."""

    producto_ids: List[int] = Field(default_factory=list)


class FavoritoOut(ORMModel):
    id: int
    usuario_id: int
    producto_id: int
    orden: int
    created_at: datetime


class PedidoOut(ORMModel):
    id: int
    tipo: str
    mesa: Optional[str] = None
    habitacion_numero: Optional[str] = None
    reserva_id: Optional[int] = None
    estado: str
    estado_cocina: Optional[str] = "pendiente"
    fecha: datetime
    tasa_usd_del_dia: Decimal
    total_bs: Decimal
    total_usd: Decimal
    servicio_10_porciento_bs: Decimal = Decimal("0")
    servicio_10_porciento_usd: Decimal = Decimal("0")
    pagado_bs: Decimal
    pagado_usd: Decimal
    propina_monto_bs: Decimal = Decimal("0")
    propina_monto_usd: Decimal = Decimal("0")
    vuelto_bs: Decimal
    vuelto_usd: Decimal
    metodo_pago: Optional[str] = None
    cuenta_banco_id: Optional[int] = None
    notas: Optional[str] = None
    anulado: bool = False
    anulado_motivo: Optional[str] = None
    anulado_por: Optional[str] = None
    anulado_en: Optional[datetime] = None
    cancelado_por: Optional[str] = None
    cancelado_en: Optional[datetime] = None
    ultima_actividad: Optional[datetime] = None
    detalles: List[DetallePedidoOut] = []


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------
class MovimientoInventarioCreate(BaseModel):
    producto_id: int = Field(..., gt=0)
    tipo: str = Field(..., max_length=20)
    cantidad: Decimal = Field(..., gt=0)
    motivo: Optional[str] = None
    referencia: Optional[str] = None


class MovimientoInventarioOut(ORMModel):
    id: int
    producto_id: int
    tipo: str
    cantidad: Decimal
    stock_anterior: Decimal
    stock_nuevo: Decimal
    motivo: Optional[str] = None
    referencia: Optional[str] = None
    fecha: datetime


# ---------------------------------------------------------------------------
# Gastos
# ---------------------------------------------------------------------------
class CategoriaGastoCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=80)
    tipo: str = Field(default="operativo", max_length=30)
    descripcion: Optional[str] = None


class CategoriaGastoOut(ORMModel):
    id: int
    nombre: str
    tipo: str
    descripcion: Optional[str] = None


class GastoCreate(BaseModel):
    fecha: Optional[date] = None
    categoria_id: int = Field(..., gt=0)
    descripcion: str = Field(..., min_length=2, max_length=255)
    monto_bs: Decimal = Field(default=Decimal("0"), ge=0)
    monto_usd: Decimal = Field(default=Decimal("0"), ge=0)
    cuenta_banco_id: Optional[int] = Field(default=None, gt=0)
    beneficiario: Optional[str] = Field(default=None, max_length=120)
    referencia: Optional[str] = Field(default=None, max_length=60)
    notas: Optional[str] = None


class GastoOut(ORMModel):
    id: int
    fecha: date
    categoria_id: int
    descripcion: str
    monto_bs: Decimal
    monto_usd: Decimal
    cuenta_banco_id: Optional[int] = None
    beneficiario: Optional[str] = None
    referencia: Optional[str] = None
    notas: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Empleados / nomina
# ---------------------------------------------------------------------------
class EmpleadoCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=120)
    documento: Optional[str] = None
    cargo: str = Field(default="general", max_length=80)
    salario_bs: Decimal = Field(default=Decimal("0"), ge=0)
    salario_usd: Decimal = Field(default=Decimal("0"), ge=0)
    forma_pago: str = Field(default="quincenal", max_length=40)
    activo: bool = True


class EmpleadoOut(ORMModel):
    id: int
    nombre: str
    documento: Optional[str] = None
    cargo: str
    salario_bs: Decimal
    salario_usd: Decimal
    forma_pago: str
    activo: bool


class PagoNominaCreate(BaseModel):
    empleado_id: int = Field(..., gt=0)
    periodo: str = Field(..., min_length=2, max_length=40)
    fecha_pago: Optional[date] = None
    monto_bs: Decimal = Field(default=Decimal("0"), ge=0)
    monto_usd: Decimal = Field(default=Decimal("0"), ge=0)
    cuenta_banco_id: Optional[int] = Field(default=None, gt=0)
    notas: Optional[str] = None


class PagoNominaOut(ORMModel):
    id: int
    empleado_id: int
    periodo: str
    fecha_pago: date
    monto_bs: Decimal
    monto_usd: Decimal
    cuenta_banco_id: Optional[int] = None
    notas: Optional[str] = None


# ---------------------------------------------------------------------------
# Cuentas banco
# ---------------------------------------------------------------------------
class CuentaBancoCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=60)
    tipo: str = Field(default="banco", max_length=30)
    moneda: str = Field(default="BS", max_length=10)
    saldo: Decimal = Field(default=Decimal("0"))


class CuentaBancoOut(ORMModel):
    id: int
    nombre: str
    tipo: str
    moneda: str
    saldo: Decimal
    activo: bool


class MovimientoCuentaOut(ORMModel):
    id: int
    cuenta_id: int
    fecha: datetime
    tipo: str
    monto: Decimal
    saldo_resultante: Decimal
    concepto: Optional[str] = None
    referencia: Optional[str] = None


# ---------------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------------
class ResumenDia(BaseModel):
    fecha: date
    ventas_bs: Decimal
    ventas_usd: Decimal
    gastos_bs: Decimal
    gastos_usd: Decimal
    pedidos_cantidad: int
    habitaciones_totales: int
    habitaciones_ocupadas: int
    ocupacion_porcentaje: float
    productos_bajo_stock: int
    tasa_dia: Decimal


class TransaccionResumen(BaseModel):
    """Fila unificada para el historial de transacciones del dashboard."""

    id: int
    fecha: datetime
    concepto: str
    monto_usd: Decimal
    monto_bs: Decimal
    tipo: str
    area: Optional[str] = None
    estado: Optional[str] = None
    usuario_nombre: Optional[str] = None


class HistorialResumen(BaseModel):
    """Totales financieros agregados del período."""

    desde: date
    hasta: date
    total_ventas_usd: Decimal = Decimal("0")
    total_ventas_bs: Decimal = Decimal("0")
    total_gastos_usd: Decimal = Decimal("0")
    total_gastos_bs: Decimal = Decimal("0")
    ganancia_neta_usd: Decimal = Decimal("0")
    ganancia_neta_bs: Decimal = Decimal("0")


class MontoMoneda(BaseModel):
    """Tupla USD/Bs para un agrupador."""

    usd: Decimal = Decimal("0")
    bs: Decimal = Decimal("0")


class HistorialVentasPorArea(BaseModel):
    desde: date
    hasta: date
    habitaciones: MontoMoneda = MontoMoneda()
    bar: MontoMoneda = MontoMoneda()
    cocina: MontoMoneda = MontoMoneda()
    piscina: MontoMoneda = MontoMoneda()


class HistorialPorMetodo(BaseModel):
    desde: date
    hasta: date
    efectivo_usd: MontoMoneda = MontoMoneda()
    efectivo_bs: MontoMoneda = MontoMoneda()
    transferencia_bs: MontoMoneda = MontoMoneda()
    pagomovil_bs: MontoMoneda = MontoMoneda()
    mixto: MontoMoneda = MontoMoneda()
    otros: MontoMoneda = MontoMoneda()


class HistorialTransacciones(BaseModel):
    desde: date
    hasta: date
    total: int
    limite: int
    offset: int
    items: List[TransaccionResumen]


class VentasMetodo(BaseModel):
    """Aporte de un método de pago dentro de un área."""

    label: str
    usd: Decimal = Decimal("0")
    bs: Decimal = Decimal("0")


class VentasAreaConMetodos(BaseModel):
    total_usd: Decimal = Decimal("0")
    total_bs: Decimal = Decimal("0")
    metodos: dict[str, VentasMetodo] = {}


class VentasPorAreaConMetodos(BaseModel):
    fecha: date
    habitaciones: VentasAreaConMetodos
    bar: VentasAreaConMetodos
    cocina: VentasAreaConMetodos
    piscina: VentasAreaConMetodos


# ---------------------------------------------------------------------------
# Auth / Usuarios
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    pin: str = Field(..., min_length=3, max_length=12)


class UsuarioPublico(BaseModel):
    id: int
    nombre: str
    rol: str


class LoginResponse(BaseModel):
    success: bool
    usuario: UsuarioPublico
    token: str
    mensaje: Optional[str] = None


class UsuarioOut(ORMModel):
    id: int
    nombre: str
    rol: str
    activo: bool
    ultimo_acceso: Optional[datetime] = None
    created_at: datetime


class UsuarioCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    pin: str = Field(..., min_length=3, max_length=12)
    rol: str = Field(..., min_length=3, max_length=20)
    activo: bool = True


class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = None
    pin: Optional[str] = None
    rol: Optional[str] = None
    activo: Optional[bool] = None


class CocinaEstadoUpdate(BaseModel):
    estado_cocina: str = Field(..., min_length=3, max_length=20)


class LogAccesoOut(ORMModel):
    id: int
    usuario_id: Optional[int] = None
    usuario_nombre: Optional[str] = None
    accion: Optional[str] = None
    detalle: Optional[str] = None
    ip: Optional[str] = None
    exitoso: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Cancelación de check-in / reserva, edición de huésped
# ---------------------------------------------------------------------------
class CancelarCheckinRequest(BaseModel):
    """Cancela un check-in en curso. Sólo admin.

    Si ``eliminar_consumos`` está activo, los pedidos abiertos asociados a la
    habitación se cancelan también (devolviendo stock). En caso contrario, los
    pedidos quedan abiertos para cobrarse después (cuenta independiente).
    """

    eliminar_consumos: bool = False
    motivo: str = Field(..., min_length=2, max_length=200)


class CancelarReservaRequest(BaseModel):
    """Cancela una reserva (estado ``reservada`` o ``activa``) con reembolso opcional."""

    porcentaje_reembolso: int = Field(default=0, ge=0, le=100)
    nota: Optional[str] = Field(default=None, max_length=255)
    metodo_pago_reembolso: Optional[str] = Field(default=None, max_length=30)


class EditarHuespedRequest(BaseModel):
    """Edita los datos del huésped después del check-in. Sólo admin/recepción."""

    huesped: Optional[str] = Field(default=None, max_length=120)
    documento: Optional[str] = Field(default=None, max_length=40)
    telefono: Optional[str] = Field(default=None, max_length=40)
    pais_origen: Optional[str] = Field(default=None, max_length=100)
    tipo_documento: Optional[str] = Field(default=None, max_length=20)
    numero_documento: Optional[str] = Field(default=None, max_length=50)
    vehiculo_modelo: Optional[str] = Field(default=None, max_length=100)
    vehiculo_color: Optional[str] = Field(default=None, max_length=50)
    vehiculo_placa: Optional[str] = Field(default=None, max_length=20)
    fecha_checkin: Optional[date] = None
    hora_ingreso: Optional[str] = Field(default=None, max_length=10)
    fecha_checkout_estimado: Optional[date] = None
    hora_salida: Optional[str] = Field(default=None, max_length=10)
