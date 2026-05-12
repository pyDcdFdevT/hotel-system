"""Seed inicial del sistema de hotel.

Idempotente: solo crea filas que no existen. Si la variable de entorno
``SEED_ONLY_IF_EMPTY=1`` está definida, salta si ya hay habitaciones cargadas.

Uso::

    python -m app.seed
"""

from __future__ import annotations

import os
from decimal import Decimal

from app.database import Base, SessionLocal, engine
from app.models import (
    CategoriaGasto,
    CuentaBanco,
    Habitacion,
    Producto,
    Receta,
    TasaCambio,
    Usuario,
    today,
)
from app.routers.auth import hash_pin


TASA_INICIAL_BCV = Decimal("405.35")
TASA_INICIAL_PARALELO = Decimal("415.00")

# Precio actual de habitación: USD 20.
HABITACION_PRECIO_USD = Decimal("20.00")
HABITACION_PRECIO_BS = Decimal("8000.00")


def _hab(numero: int, estado: str) -> dict:
    return {
        "numero": f"{numero}",
        "tipo": "standard",
        "precio_usd": HABITACION_PRECIO_USD,
        "precio_bs": HABITACION_PRECIO_BS,
        "estado": estado,
    }


# 24 habitaciones: 101-111 disponibles, 201-210 + 301-303 inhabilitadas
# (mismo precio por si se habilitan más adelante).
HABITACIONES_INICIALES = (
    [_hab(n, "disponible") for n in range(101, 112)]
    + [_hab(n, "inhabilitada") for n in range(201, 211)]
    + [_hab(n, "inhabilitada") for n in range(301, 304)]
)


CATEGORIAS_GASTO = [
    {"nombre": "Servicios", "tipo": "operativo", "descripcion": "Luz, agua, gas, internet"},
    {"nombre": "Insumos", "tipo": "operativo", "descripcion": "Compras menores para operación"},
    {"nombre": "Mantenimiento", "tipo": "operativo", "descripcion": "Reparaciones y mantenimiento"},
    {"nombre": "Nómina", "tipo": "personal", "descripcion": "Pago a empleados"},
    {"nombre": "Proveedores", "tipo": "inventario", "descripcion": "Compras a proveedores"},
    {"nombre": "Marketing", "tipo": "ventas", "descripcion": "Publicidad y promoción"},
    {"nombre": "Impuestos", "tipo": "tributario", "descripcion": "Impuestos municipales y nacionales"},
    {"nombre": "Otros", "tipo": "operativo", "descripcion": "Gastos varios"},
]


CUENTAS_INICIALES = [
    {"nombre": "Banco HLC", "tipo": "banco", "moneda": "BS", "saldo": Decimal("0")},
    {"nombre": "Banco Z", "tipo": "banco", "moneda": "BS", "saldo": Decimal("0")},
    {"nombre": "Efectivo Bs", "tipo": "caja", "moneda": "BS", "saldo": Decimal("0")},
    {"nombre": "Efectivo USD", "tipo": "caja", "moneda": "USD", "saldo": Decimal("0")},
]


CUENTAS_RENOMBRADAS = {
    "BcoHLC": "Banco HLC",
    "BcoZ": "Banco Z",
    "EfectivoBs": "Efectivo Bs",
    "EfectivoUsd": "Efectivo USD",
}


USUARIOS_INICIALES = [
    {"nombre": "Administrador", "pin": "1234", "rol": "admin"},
    {"nombre": "Recepcion", "pin": "1111", "rol": "recepcion"},
    {"nombre": "Mesero", "pin": "2222", "rol": "mesero"},
    {"nombre": "Cocina", "pin": "3333", "rol": "cocina"},
]


def _seed_usuarios(db) -> None:
    for u in USUARIOS_INICIALES:
        existente = db.query(Usuario).filter(Usuario.nombre == u["nombre"]).first()
        if existente:
            # Reaplica el rol/activo por si fue editado a un valor inválido,
            # pero no resetea el PIN si ya fue cambiado manualmente.
            existente.rol = existente.rol or u["rol"]
            existente.activo = True
            continue
        db.add(
            Usuario(
                nombre=u["nombre"],
                pin_hash=hash_pin(u["pin"]),
                rol=u["rol"],
                activo=True,
            )
        )


# ---------------------------------------------------------------------------
# Menú del hotel
# ---------------------------------------------------------------------------
# Áreas válidas: "cocina", "bar", "general".
# La tasa BCV inicial es ~405 Bs/USD; usamos un redondeo razonable.

_BCV = TASA_INICIAL_BCV


def _precio_bs(usd: Decimal) -> Decimal:
    return (usd * _BCV).quantize(Decimal("0.01"))


# Tuplas: (nombre, area, categoria, precio_usd, porcion)
MENU = [
    # ---------------- COCINA ----------------
    # Para Picar
    ("Tequeños", "cocina", "Para Picar", Decimal("6.00"), None),
    ("Papas Francesas", "cocina", "Para Picar", Decimal("5.00"), None),
    ("Tiritas de Pollo", "cocina", "Para Picar", Decimal("8.00"), None),
    ("Tabla de Quesos", "cocina", "Para Picar", Decimal("9.00"), None),
    ("Nachos con Queso", "cocina", "Para Picar", Decimal("7.00"), None),
    # Desayunos
    ("Sandwich", "cocina", "Desayunos", Decimal("3.00"), None),
    ("Desayuno Criollo", "cocina", "Desayunos", Decimal("8.00"), None),
    ("Desayuno Americano", "cocina", "Desayunos", Decimal("8.00"), None),
    ("Omelette", "cocina", "Desayunos", Decimal("6.00"), None),
    ("Desayuno Minero", "cocina", "Desayunos", Decimal("6.00"), None),
    # A la Carta
    ("Hamburguesa Clásica", "cocina", "A la Carta", Decimal("5.00"), None),
    ("Hamburguesa Cumbre", "cocina", "A la Carta", Decimal("10.00"), None),
    ("Club House", "cocina", "A la Carta", Decimal("10.00"), None),
    ("Parrilla de Lomito P1", "cocina", "A la Carta", Decimal("12.00"), "P1"),
    ("Parrilla de Lomito P2", "cocina", "A la Carta", Decimal("20.00"), "P2"),
    ("Churrasco de Solomo", "cocina", "A la Carta", Decimal("12.00"), None),
    ("Churrasco de Lau-Lau", "cocina", "A la Carta", Decimal("10.00"), None),
    ("Cuadritos de Lau-Lau", "cocina", "A la Carta", Decimal("9.00"), None),

    # ---------------- BAR ----------------
    # Ligeras
    ("Agua Mineral", "bar", "Ligeras", Decimal("1.50"), None),
    ("Refresco", "bar", "Ligeras", Decimal("2.00"), None),
    ("Jugo Natural", "bar", "Ligeras", Decimal("3.00"), None),
    # Cervezas
    ("Cerveza Solera", "bar", "Cervezas", Decimal("1.50"), None),
    ("Cerveza Pilsen", "bar", "Cervezas", Decimal("1.30"), None),
    ("Cerveza Light", "bar", "Cervezas", Decimal("1.30"), None),
    # Rones
    ("Ron Estelar 1L", "bar", "Rones", Decimal("15.00"), "1L"),
    ("Ron Cacique 1L", "bar", "Rones", Decimal("18.00"), "1L"),
    ("Ron Santa Teresa 1L", "bar", "Rones", Decimal("20.00"), "1L"),
    # Whisky
    ("Whisky Black and White", "bar", "Whisky", Decimal("30.00"), None),
    ("Whisky Buchanan's 12", "bar", "Whisky", Decimal("55.00"), None),
    ("Whisky Old Parr", "bar", "Whisky", Decimal("60.00"), None),
    # Licores
    ("Vodka Absolut", "bar", "Licores", Decimal("35.00"), None),
    ("Tequila José Cuervo", "bar", "Licores", Decimal("40.00"), None),
    ("Ginebra Gordon's", "bar", "Licores", Decimal("28.00"), None),
    # Vinos
    ("Vino Tinto Casa", "bar", "Vinos", Decimal("18.00"), None),
    ("Vino Blanco Casa", "bar", "Vinos", Decimal("18.00"), None),
    ("Sangría", "bar", "Vinos", Decimal("5.00"), None),
    # Cockeles
    ("Mojito", "bar", "Cockeles", Decimal("6.00"), None),
    ("Piña Colada", "bar", "Cockeles", Decimal("6.00"), None),
    ("Margarita", "bar", "Cockeles", Decimal("6.00"), None),
    ("Daiquiri", "bar", "Cockeles", Decimal("6.00"), None),
    ("Cuba Libre", "bar", "Cockeles", Decimal("5.00"), None),
]


PRODUCTOS_MENU = [
    {
        "nombre": nombre,
        "area": area,
        "categoria": categoria,
        "porcion": porcion,
        "descripcion": None,
        "precio_usd": precio_usd,
        "precio_bs": _precio_bs(precio_usd),
        "costo_bs": Decimal("0"),
        # Stock inicial razonable; ajustable luego desde Inventario.
        "stock_actual": Decimal("100"),
        "stock_minimo": Decimal("5"),
        "unidad": "unidad",
        "es_para_venta": True,
    }
    for (nombre, area, categoria, precio_usd, porcion) in MENU
]


# Insumos para recetas
PRODUCTOS_INSUMO = [
    {
        "nombre": "Pan hamburguesa",
        "area": "cocina",
        "categoria": "Insumo",
        "descripcion": "Pan tipo brioche",
        "precio_bs": Decimal("0"),
        "precio_usd": Decimal("0"),
        "costo_bs": Decimal("250.00"),
        "stock_actual": Decimal("40"),
        "stock_minimo": Decimal("10"),
        "unidad": "unidad",
        "es_para_venta": False,
    },
    {
        "nombre": "Carne para hamburguesa",
        "area": "cocina",
        "categoria": "Insumo",
        "descripcion": "Carne molida 150 g",
        "precio_bs": Decimal("0"),
        "precio_usd": Decimal("0"),
        "costo_bs": Decimal("900.00"),
        "stock_actual": Decimal("30"),
        "stock_minimo": Decimal("8"),
        "unidad": "unidad",
        "es_para_venta": False,
    },
    {
        "nombre": "Lechuga",
        "area": "cocina",
        "categoria": "Insumo",
        "descripcion": "Hoja de lechuga",
        "precio_bs": Decimal("0"),
        "precio_usd": Decimal("0"),
        "costo_bs": Decimal("50.00"),
        "stock_actual": Decimal("80"),
        "stock_minimo": Decimal("20"),
        "unidad": "hoja",
        "es_para_venta": False,
    },
]


# Receta básica para "Hamburguesa Clásica"
RECETA_HAMBURGUESA_CLASICA = [
    ("Pan hamburguesa", Decimal("1")),
    ("Carne para hamburguesa", Decimal("1")),
    ("Lechuga", Decimal("2")),
]


def _upsert(db, modelo, filtro: dict, defaults: dict):
    existente = db.query(modelo).filter_by(**filtro).first()
    if existente:
        return existente, False
    instancia = modelo(**{**filtro, **defaults})
    db.add(instancia)
    db.flush()
    return instancia, True


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if os.getenv("SEED_ONLY_IF_EMPTY") == "1" and db.query(Habitacion).first():
            print("Seed omitido: la base ya tiene datos.")
            return

        if (
            not db.query(TasaCambio)
            .filter(TasaCambio.fecha == today(), TasaCambio.tipo == "bcv")
            .first()
        ):
            db.add(TasaCambio(fecha=today(), tipo="bcv", usd_a_ves=TASA_INICIAL_BCV))
        if (
            not db.query(TasaCambio)
            .filter(TasaCambio.fecha == today(), TasaCambio.tipo == "paralelo")
            .first()
        ):
            db.add(
                TasaCambio(fecha=today(), tipo="paralelo", usd_a_ves=TASA_INICIAL_PARALELO)
            )

        for cat in CATEGORIAS_GASTO:
            _upsert(db, CategoriaGasto, {"nombre": cat["nombre"]}, cat)

        # Renombrar cuentas antiguas si existen (mantiene saldos y movimientos).
        for nombre_viejo, nombre_nuevo in CUENTAS_RENOMBRADAS.items():
            cuenta_vieja = (
                db.query(CuentaBanco).filter(CuentaBanco.nombre == nombre_viejo).first()
            )
            if cuenta_vieja and not (
                db.query(CuentaBanco).filter(CuentaBanco.nombre == nombre_nuevo).first()
            ):
                cuenta_vieja.nombre = nombre_nuevo

        for cuenta in CUENTAS_INICIALES:
            _upsert(db, CuentaBanco, {"nombre": cuenta["nombre"]}, cuenta)

        for hab in HABITACIONES_INICIALES:
            _upsert(db, Habitacion, {"numero": hab["numero"]}, hab)

        _seed_usuarios(db)

        # Productos del menú
        productos_por_nombre: dict[str, Producto] = {}
        for prod in PRODUCTOS_MENU + PRODUCTOS_INSUMO:
            producto, _ = _upsert(db, Producto, {"nombre": prod["nombre"]}, prod)
            productos_por_nombre[prod["nombre"]] = producto

        # Si existe una "Hamburguesa" antigua, dejarla migrada al nombre nuevo.
        legacy = db.query(Producto).filter(Producto.nombre == "Hamburguesa").first()
        if legacy and not db.query(Producto).filter(
            Producto.nombre == "Hamburguesa Clásica"
        ).first():
            legacy.nombre = "Hamburguesa Clásica"
            legacy.area = "cocina"
            legacy.categoria = "A la Carta"
            legacy.precio_usd = Decimal("5.00")
            legacy.precio_bs = _precio_bs(Decimal("5.00"))
            productos_por_nombre["Hamburguesa Clásica"] = legacy

        # Receta de Hamburguesa Clásica
        hamburguesa = productos_por_nombre.get("Hamburguesa Clásica")
        if hamburguesa and not db.query(Receta).filter(
            Receta.producto_id == hamburguesa.id
        ).first():
            for nombre_ingrediente, cantidad in RECETA_HAMBURGUESA_CLASICA:
                ingrediente = productos_por_nombre.get(nombre_ingrediente)
                if not ingrediente:
                    continue
                db.add(
                    Receta(
                        producto_id=hamburguesa.id,
                        ingrediente_id=ingrediente.id,
                        cantidad=cantidad,
                    )
                )

        db.commit()
        print("Seed completado.")
    except Exception as exc:
        db.rollback()
        print(f"Error en seed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
